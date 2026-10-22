"""Buscar a prévia na web automaticamente (Google Cloud Vision, recurso Web Detection).

  1. A prévia atual (reduzida a ~1024 px) vai para a API, que devolve endereços de imagens iguais e parecidas.
  2. Os candidatos são baixados em segundo plano (vários ao mesmo tempo, com limite de tempo e de tamanho),
     a resolução de cada um é medida e os repetidos/quebrados saem.
  3. A janela mostra os 3 de maior resolução; o escolhido segue para a conferência de sempre (previa.update_with).
A chave da API fica na biblioteca (o administrador grava uma vez para a equipe) ou, sem rede, na configuração local.
Sem chave, ou se nada servir, o botão "Abrir no Google Lens" usa o jeito assistido da 1.1.6.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import tempfile
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize, Qt, QThread, Signal
from PySide6.QtGui import QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSizePolicy,
                               QVBoxLayout)

from . import theme, ui
from .scanner import Asset

API = "https://vision.googleapis.com/v1/images:annotate?key="
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
MAX_BYTES = 25 * 1024 * 1024
MIN_SIDE = 300                 # menor que isso não serve de prévia
TOP = 3


def get_key(w) -> str:
    lib = getattr(w.shared, "lib", None)
    if lib is not None:
        try:
            k = (lib.option("vision_key") or "").strip()
            if k:
                return k
        except Exception:  # noqa: BLE001
            pass
    return (w.cfg.values.get("vision_key") or "").strip()


def _encode_preview(path: str) -> bytes:
    r = QImageReader(path)
    r.setAutoTransform(True)
    sz = r.size()
    if sz.isValid() and max(sz.width(), sz.height()) > 1024:
        r.setScaledSize(sz.scaled(1024, 1024, Qt.KeepAspectRatio))
    img = r.read()
    if img.isNull():
        raise OSError("não consegui ler a prévia atual")
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.convertToFormat(QImage.Format_RGB32).save(buf, "JPG", 90)
    return bytes(ba)


def web_detection(key: str, image: bytes) -> list[str]:
    """Endereços de imagens na ordem de preferência: iguais, parciais, parecidas."""
    body = json.dumps({"requests": [{
        "image": {"content": base64.b64encode(image).decode("ascii")},
        "features": [{"type": "WEB_DETECTION", "maxResults": 40}]}]}).encode("utf-8")
    req = urllib.request.Request(API + key, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
        except Exception:  # noqa: BLE001
            msg = ""
        raise OSError(f"o Google recusou a busca ({e.code}). {msg}".strip()) from None
    except urllib.error.URLError as e:
        raise OSError(f"sem conexão com o Google ({e.reason})") from None
    res = (data.get("responses") or [{}])[0]
    if res.get("error"):
        raise OSError(res["error"].get("message", "erro na busca"))
    wd = res.get("webDetection") or {}
    urls: list[str] = []

    def add(lst):
        for it in lst or []:
            u = it.get("url")
            if u and u.startswith("http") and u not in urls:
                urls.append(u)
    add(wd.get("fullMatchingImages"))
    for page in wd.get("pagesWithMatchingImages") or []:
        add(page.get("fullMatchingImages"))
    add(wd.get("partialMatchingImages"))
    add(wd.get("visuallySimilarImages"))
    return urls


def _download(url: str, folder: str) -> tuple[str, int, int, str] | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "image/*,*/*;q=0.8"})
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = resp.read(MAX_BYTES + 1)
    except Exception:  # noqa: BLE001
        return None
    if not data or len(data) > MAX_BYTES:
        return None
    ba = QByteArray(data)
    buf = QBuffer(ba)
    buf.open(QIODevice.ReadOnly)
    r = QImageReader(buf)
    r.setAutoTransform(True)
    fmt = bytes(r.format()).decode("ascii", "ignore").lower()
    sz = r.size()
    if not sz.isValid() or min(sz.width(), sz.height()) < MIN_SIDE or fmt not in ("jpeg", "jpg", "png", "webp", "bmp", "tiff", "gif"):
        return None
    if fmt == "gif":
        return None
    ext = {"jpeg": ".jpg", "jpg": ".jpg", "tiff": ".tif"}.get(fmt, "." + fmt)
    h = hashlib.sha1(data).hexdigest()
    path = os.path.join(folder, h[:16] + ext)
    with open(path, "wb") as fh:
        fh.write(data)
    return path, sz.width(), sz.height(), h


class SearchThread(QThread):
    progress = Signal(str)
    done = Signal(list)          # [(caminho, largura, altura, url)]
    failed = Signal(str)

    def __init__(self, key: str, preview: str, folder: str):
        super().__init__()
        self.key, self.preview, self.folder = key, preview, folder
        self.cancel = False

    def run(self):
        try:
            self.progress.emit("Procurando imagens parecidas no Google…")
            urls = web_detection(self.key, _encode_preview(self.preview))
            if not urls:
                self.done.emit([])
                return
            self.progress.emit(f"Baixando {len(urls)} candidatas para medir a resolução…")
            out, seen = [], set()
            with ThreadPoolExecutor(max_workers=8) as ex:
                futs = {ex.submit(_download, u, self.folder): u for u in urls}
                for n, f in enumerate(as_completed(futs), 1):
                    if self.cancel:
                        break
                    r = f.result()
                    if r and r[3] not in seen:
                        seen.add(r[3])
                        out.append((r[0], r[1], r[2], futs[f]))
                    self.progress.emit(f"Conferindo as imagens… {n}/{len(urls)}")
            out.sort(key=lambda t: t[1] * t[2], reverse=True)
            self.done.emit(out)
        except OSError as e:
            self.failed.emit(str(e))
        except Exception as e:  # noqa: BLE001
            self.failed.emit(f"erro inesperado: {e}")


class ResultCard(QFrame):
    def __init__(self, path: str, w: int, h: int, url: str, on_pick):
        super().__init__()
        self.setObjectName("res")
        self.setStyleSheet("#res{border:1px solid rgba(240,226,201,0.10); border-radius:12px;}"
                           "#res:hover{border-color:rgba(240,226,201,0.45);}")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 12)
        pic = QLabel()
        pic.setAlignment(Qt.AlignCenter)
        pic.setFixedSize(250, 220)
        r = QImageReader(path)
        r.setAutoTransform(True)
        sz = r.size()
        if sz.isValid():
            r.setScaledSize(sz.scaled(250, 220, Qt.KeepAspectRatio))
        pic.setPixmap(QPixmap.fromImage(r.read()))
        lay.addWidget(pic)
        res = QLabel(f"{w} × {h} px")
        res.setAlignment(Qt.AlignCenter)
        res.setStyleSheet(f"color:{theme.HILITE.name()}; font-size:11pt;")
        lay.addWidget(res)
        host = url.split("/")[2] if "//" in url else url
        src = QLabel(host[:38])
        src.setAlignment(Qt.AlignCenter)
        src.setToolTip(url)
        src.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:8.5pt;")
        lay.addWidget(src)
        b = QPushButton("Usar esta")
        ui.primary(b)
        b.clicked.connect(lambda: on_pick(path))
        lay.addWidget(b)


class ResultsDialog(QDialog):
    def __init__(self, w, a: Asset, key: str):
        super().__init__(w)
        self.w, self.a = w, a
        self.chosen: str | None = None
        self.use_lens = False
        self.folder = tempfile.mkdtemp(prefix="archiva_busca_")
        self.setWindowTitle(f"Buscar prévia na web · {a.name}")
        self.resize(900, 520)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(ui.heading(f"{a.name}: prévias na web", 14))
        self.status = QLabel("Começando…")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{theme.MUTED.name()};")
        lay.addWidget(self.status)
        self.row = QHBoxLayout()
        self.row.setSpacing(14)
        lay.addLayout(self.row, 1)
        b = QHBoxLayout()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        b.addWidget(cancel)
        b.addStretch(1)
        lens = QPushButton("Abrir no Google Lens")
        lens.setToolTip("Procurar você mesmo no navegador (a imagem salva em Downloads vai para a conferência)")
        lens.clicked.connect(self._lens)
        b.addWidget(lens)
        lay.addLayout(b)
        self.th = SearchThread(key, a.preview, self.folder)
        self.th.progress.connect(self.status.setText)
        self.th.done.connect(self._show)
        self.th.failed.connect(lambda m: self.status.setText(f"Não deu para buscar: {m}"))
        self.finished.connect(self._cleanup)
        self.th.start()

    def _show(self, res: list):
        if not res:
            self.status.setText("Nenhuma imagem boa encontrada (maior que 300 px e que abra). "
                                "Tente pelo Google Lens.")
            return
        best = res[:TOP]
        cur = QImageReader(self.a.preview).size() if self.a.preview else QSize()
        cur_txt = f" A prévia atual tem {cur.width()} × {cur.height()} px." if cur.isValid() else ""
        self.status.setText(f"As {len(best)} de maior resolução entre {len(res)} encontradas.{cur_txt} "
                            "Escolha uma para ir à conferência.")
        self.row.addStretch(1)
        for path, wd, ht, url in best:
            self.row.addWidget(ResultCard(path, wd, ht, url, self._pick))
        self.row.addStretch(1)

    def _pick(self, path: str):
        keep = os.path.join(tempfile.gettempdir(), "archiva_escolhida" + os.path.splitext(path)[1])
        shutil.copyfile(path, keep)
        self.chosen = keep
        self.accept()

    def _lens(self):
        self.use_lens = True
        self.reject()

    def _cleanup(self, *_):
        self.th.cancel = True
        self.th.wait(15000)
        shutil.rmtree(self.folder, ignore_errors=True)


def search(w, a: Asset) -> None:
    from . import previa
    if not a.preview:
        QMessageBox.information(w, "Buscar na web", "Este item ainda não tem prévia para procurar.")
        return
    key = get_key(w)
    if not key:
        if QMessageBox.question(
                w, "Buscar na web",
                "A busca automática precisa da chave da Google Cloud Vision (Configurações › Biblioteca).\n\n"
                "Abrir o Google Lens no navegador agora?") == QMessageBox.Yes:
            previa.update_from_web(w, a)
        return
    dlg = ResultsDialog(w, a, key)
    dlg.exec()
    if dlg.chosen:
        previa.update_with(w, a, dlg.chosen)
        try:
            os.remove(dlg.chosen)
        except OSError:
            pass
    elif dlg.use_lens:
        previa.update_from_web(w, a)
