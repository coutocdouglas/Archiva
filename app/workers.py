"""Tarefas em segundo plano: leitura da biblioteca, miniaturas e extração."""
from __future__ import annotations

import hashlib
import os
import threading
import time
from collections import OrderedDict
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QSize, Qt, Signal, QThread
from PySide6.QtGui import QImage, QImageReader, QPixmap

from . import extractor
from .scanner import Asset, scan_library

THUMB_MAX = 320


# --------------------------------------------------------------------------- leitura da biblioteca

class ScanThread(QThread):
    progress = Signal(int, int, str)
    done = Signal(list)
    failed = Signal(str)

    def __init__(self, root: str):
        super().__init__()
        self.root = root
        self.sigs: dict | None = None

    def run(self):
        try:
            cats = scan_library(self.root, lambda i, n, c: self.progress.emit(i, n, c.name))
            from .indice import all_signatures
            sigs = {}
            try:
                from .segundo_plano import map_parallel
                for c, s in zip(cats, map_parallel(lambda c: all_signatures(self.root, [c])[c.key], cats)):
                    sigs[c.key] = s
                self.sigs = sigs
            except Exception:  # noqa: BLE001 — sem assinaturas: a janela calcula
                self.sigs = None
            self.done.emit(cats)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


# --------------------------------------------------------------------------- miniaturas

MEM_MAX = 600              # miniaturas guardadas na memória (~180 MB); as mais antigas saem primeiro
QUEUE_MAX = 400            # pedidos esperando; os mais antigos (que já saíram da tela) são esquecidos
DISK_DAYS = 120            # miniaturas em disco sem uso há mais tempo que isso são apagadas


def load_thumb(path: str, cache_dir: Path) -> QImage:
    img = QImage()
    try:
        st = os.stat(path)
        h = hashlib.md5(f"{path}|{st.st_mtime_ns}|{st.st_size}".encode("utf-8")).hexdigest()
        cached = cache_dir / f"{h}.jpg"
        try:
            cst = cached.stat()
            img = QImage(str(cached))
            if not img.isNull() and time.time() - cst.st_mtime > 7 * 86400:
                os.utime(cached)                 # marca como usada (a limpeza apaga as sem uso)
        except OSError:
            pass
        if img.isNull():
            r = QImageReader(path)
            r.setAutoTransform(True)
            sz = r.size()
            if sz.isValid() and max(sz.width(), sz.height()) > THUMB_MAX:
                r.setScaledSize(sz.scaled(THUMB_MAX, THUMB_MAX, Qt.KeepAspectRatio))
            img = r.read()
            if not img.isNull():
                cache_dir.mkdir(parents=True, exist_ok=True)
                img.convertToFormat(QImage.Format_RGB32).save(str(cached), "JPG", 88)
    except OSError:
        pass
    return img


def clean_thumb_dir(cache_dir: Path, days: int = DISK_DAYS) -> int:
    """Apaga miniaturas guardadas em disco que não são usadas há muito tempo (só a cópia local)."""
    limit, n = time.time() - days * 86400, 0
    try:
        with os.scandir(cache_dir) as it:
            for e in it:
                try:
                    if e.is_file() and e.name.endswith(".jpg") and e.stat().st_mtime < limit:
                        os.remove(e.path)
                        n += 1
                except OSError:
                    continue
    except OSError:
        pass
    return n


class _ThumbSignals(QObject):
    loaded = Signal(str, QImage)


class _ThumbPump(QRunnable):
    """Trabalhador: pega sempre o pedido MAIS NOVO da fila (o que está na tela agora) até a fila esvaziar."""

    def __init__(self, cache: "ThumbnailCache"):
        super().__init__()
        self.cache = cache

    def run(self):
        c = self.cache
        while True:
            with c._lock:
                if not c._queue:
                    c._pumps -= 1
                    return
                path, _ = c._queue.popitem(last=True)
            c.signals.loaded.emit(path, load_thumb(path, c.cache_dir))


class ThumbnailCache(QObject):
    changed = Signal()

    def __init__(self, cache_dir: Path):
        super().__init__()
        self.cache_dir = cache_dir / "miniaturas"
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(max(2, min(6, (os.cpu_count() or 4) // 2)))
        self.signals = _ThumbSignals()
        self.signals.loaded.connect(self._on_loaded)
        self.mem: OrderedDict[str, QPixmap | None] = OrderedDict()
        self.pending: set[str] = set()
        self._queue: OrderedDict[str, None] = OrderedDict()      # fim = pedido mais novo
        self._lock = threading.Lock()
        self._pumps = 0
        threading.Thread(target=clean_thumb_dir, args=(self.cache_dir,), daemon=True).start()

    def get(self, path: str | None) -> QPixmap | None:
        if not path:
            return None
        if path in self.mem:
            self.mem.move_to_end(path)
            return self.mem[path]
        self._request(path)
        return None

    def _request(self, path: str) -> None:
        with self._lock:
            if path in self._queue:
                self._queue.move_to_end(path)          # pedido de novo (ainda na tela): vai para a frente
            elif path in self.pending:
                return                                 # já está sendo lido
            else:
                self._queue[path] = None
                self.pending.add(path)
                while len(self._queue) > QUEUE_MAX:    # saiu da tela há tempo: se voltar, é pedido de novo
                    old, _ = self._queue.popitem(last=False)
                    self.pending.discard(old)
            if self._pumps >= self.pool.maxThreadCount():
                return
            self._pumps += 1
        self.pool.start(_ThumbPump(self))

    def reload(self, paths) -> None:
        """Lê de novo estas imagens; enquanto isso, continua mostrando a que já estava na memória."""
        for path in paths:
            if path in self.mem and path not in self.pending:
                self._request(path)

    def cancel_pending(self):
        with self._lock:
            for p in self._queue:
                self.pending.discard(p)
            self._queue.clear()

    def _on_loaded(self, path: str, img: QImage):
        self.pending.discard(path)
        self.mem[path] = QPixmap.fromImage(img) if not img.isNull() else None
        self.mem.move_to_end(path)
        while len(self.mem) > MEM_MAX:
            self.mem.popitem(last=False)
        self.changed.emit()


# --------------------------------------------------------------------------- extração para a biblioteca

class _ExtractSignals(QObject):
    started = Signal(str)
    finished = Signal(object)


class _ExtractJob(QRunnable):
    def __init__(self, asset: Asset, mgr: "ExtractionManager", extra_password: str | None = None,
                 op: str = "extract"):
        super().__init__()
        self.asset, self.mgr, self.extra_password, self.op = asset, mgr, extra_password, op

    def run(self):
        self.mgr.signals.started.emit(self.asset.key)
        try:
            if self.op == "organize":
                res = extractor.organize_folder(self.asset, self.mgr.library_root, self.mgr.unwanted_ext)
            else:
                pwds = ([self.extra_password] if self.extra_password else []) + list(self.mgr.passwords)
                res = extractor.extract_to_library(self.asset, self.mgr.library_root, self.mgr.tools,
                                                   self.mgr.unwanted_ext, pwds)
        except Exception as e:  # noqa: BLE001
            res = extractor.ExtractResult(key=self.asset.key, name=self.asset.name,
                                          category=self.asset.category, message=str(e))
        self.mgr.signals.finished.emit(res)


class ExtractionManager(QObject):
    """Fila de extrações (uma por vez, para não sobrecarregar o disco)."""
    started = Signal(str)
    finished = Signal(object)        # ExtractResult
    batch_done = Signal(list)        # [ExtractResult]

    def __init__(self, library_root: str, tools: dict, unwanted_ext: list[str], passwords: list[str]):
        super().__init__()
        self.library_root, self.tools, self.unwanted_ext = library_root, tools, unwanted_ext
        self.passwords = passwords
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(1)
        self.queued: set[str] = set()
        self.running: set[str] = set()
        self.results: list = []
        self.total = 0
        self.signals = _ExtractSignals()
        self.signals.started.connect(self._on_started)
        self.signals.finished.connect(self._on_finished)

    def is_ready(self, a: Asset) -> bool:
        return a.kind in ("folder", "max")

    def is_running(self, a: Asset) -> bool:
        return a.key in self.running

    def is_queued(self, a: Asset) -> bool:
        return a.key in self.queued

    def busy(self) -> bool:
        return bool(self.queued or self.running)

    def enqueue(self, assets: list[Asset], extra_password: str | None = None, retry: bool = False,
                op: str = "extract") -> int:
        n = 0
        for a in assets:
            wanted = "folder" if op == "organize" else "archive"
            if a.kind != wanted or a.key in self.queued or a.key in self.running:
                continue
            if not retry:
                if not self.busy():
                    self.results, self.total = [], 0
                self.total += 1
            self.queued.add(a.key)
            self.pool.start(_ExtractJob(a, self, extra_password, op))
            n += 1
        return n

    def done_count(self) -> int:
        return len(self.results)

    def _on_started(self, key: str):
        self.queued.discard(key)
        self.running.add(key)
        self.started.emit(key)

    def _on_finished(self, res):
        self.running.discard(res.key)
        self.results.append(res)
        self.finished.emit(res)
        if not self.busy():
            self.batch_done.emit(list(self.results))
