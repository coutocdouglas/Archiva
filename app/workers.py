"""Tarefas em segundo plano: leitura da biblioteca, miniaturas e extração."""
from __future__ import annotations

import hashlib
import os
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

    def run(self):
        try:
            cats = scan_library(self.root, lambda i, n, c: self.progress.emit(i, n, c.name))
            self.done.emit(cats)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


# --------------------------------------------------------------------------- miniaturas

class _ThumbSignals(QObject):
    loaded = Signal(str, QImage)


class _ThumbJob(QRunnable):
    def __init__(self, path: str, cache_dir: Path, signals: _ThumbSignals):
        super().__init__()
        self.path, self.cache_dir, self.signals = path, cache_dir, signals

    def run(self):
        img = QImage()
        try:
            st = os.stat(self.path)
            h = hashlib.md5(f"{self.path}|{st.st_mtime_ns}|{st.st_size}".encode("utf-8")).hexdigest()
            cached = self.cache_dir / f"{h}.jpg"
            if cached.exists():
                img = QImage(str(cached))
            if img.isNull():
                r = QImageReader(self.path)
                r.setAutoTransform(True)
                sz = r.size()
                if sz.isValid() and max(sz.width(), sz.height()) > THUMB_MAX:
                    r.setScaledSize(sz.scaled(THUMB_MAX, THUMB_MAX, Qt.KeepAspectRatio))
                img = r.read()
                if not img.isNull():
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    img.convertToFormat(QImage.Format_RGB32).save(str(cached), "JPG", 88)
        except OSError:
            pass
        self.signals.loaded.emit(self.path, img)


class ThumbnailCache(QObject):
    changed = Signal()

    def __init__(self, cache_dir: Path):
        super().__init__()
        self.cache_dir = cache_dir / "miniaturas"
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(max(2, min(6, (os.cpu_count() or 4) // 2)))
        self.signals = _ThumbSignals()
        self.signals.loaded.connect(self._on_loaded)
        self.mem: dict[str, QPixmap | None] = {}
        self.pending: set[str] = set()

    def get(self, path: str | None) -> QPixmap | None:
        if not path:
            return None
        if path in self.mem:
            return self.mem[path]
        if path not in self.pending:
            self.pending.add(path)
            self.pool.start(_ThumbJob(path, self.cache_dir, self.signals))
        return None

    def reload(self, paths) -> None:
        """Lê de novo estas imagens; enquanto isso, continua mostrando a que já estava na memória."""
        for path in paths:
            if path in self.mem and path not in self.pending:
                self.pending.add(path)
                self.pool.start(_ThumbJob(path, self.cache_dir, self.signals))

    def cancel_pending(self):
        self.pool.clear()
        self.pending.clear()

    def _on_loaded(self, path: str, img: QImage):
        self.pending.discard(path)
        self.mem[path] = QPixmap.fromImage(img) if not img.isNull() else None
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
