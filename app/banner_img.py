"""Prévia do banner com as bordas fundidas ao fundo SEM passar por cima do objeto.

- Cor do fundo do banner = cor mais frequente da prévia (funciona mesmo quando o objeto encosta na borda).
- Perto das bordas da imagem, só os pixels parecidos com o fundo ficam transparentes; o objeto fica opaco.
- Uma faixa finíssima na borda sempre esfuma, para objetos cortados não terem corte seco.

Calculado uma vez em segundo plano e guardado em cache\\banner (nada muda na biblioteca).
"""
from __future__ import annotations

import hashlib
import os
from collections import Counter
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Qt, Signal
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter

MAX_SIDE = 820         # tamanho da imagem do banner
MASK_SIDE = 260        # resolução da máscara (ampliada suavemente depois)
BAND = 0.16            # faixa perto das bordas onde o fundo some
EDGE = 0.035           # faixa finíssima que sempre esfuma
VERSION = "2"


def _smooth(t: float) -> float:
    if t <= 0:
        return 0.0
    if t >= 1:
        return 1.0
    return t * t * (3 - 2 * t)


def dominant_color(img: QImage) -> QColor:
    small = img.scaled(96, 96, Qt.IgnoreAspectRatio, Qt.SmoothTransformation).convertToFormat(QImage.Format_RGB32)
    w, h, bpl = small.width(), small.height(), small.bytesPerLine()
    raw = bytes(small.constBits())[: bpl * h]
    cnt: Counter = Counter()
    sums: dict = {}
    for y in range(h):
        row = y * bpl
        for x in range(w):
            o = row + x * 4
            b, g, r = raw[o], raw[o + 1], raw[o + 2]
            k = (r >> 3, g >> 3, b >> 3)
            cnt[k] += 1
            s = sums.get(k)
            if s is None:
                sums[k] = [r, g, b]
            else:
                s[0] += r; s[1] += g; s[2] += b
    k, n = cnt.most_common(1)[0]
    s = sums[k]
    return QColor(s[0] // n, s[1] // n, s[2] // n)


def blend(path: str) -> tuple[QImage, QColor]:
    r = QImageReader(path)
    r.setAutoTransform(True)
    sz = r.size()
    if sz.isValid() and max(sz.width(), sz.height()) > MAX_SIDE:
        r.setScaledSize(sz.scaled(MAX_SIDE, MAX_SIDE, Qt.KeepAspectRatio))
    img = r.read()
    if img.isNull():
        return QImage(), QColor("#1b1612")
    bg = dominant_color(img)
    br, bgc, bb = bg.red(), bg.green(), bg.blue()

    small = img.scaled(MASK_SIDE, MASK_SIDE, Qt.KeepAspectRatio, Qt.SmoothTransformation) \
        .convertToFormat(QImage.Format_RGB32)
    w, h, bpl = small.width(), small.height(), small.bytesPerLine()
    raw = bytes(small.constBits())[: bpl * h]
    m = min(w, h)
    band, edge = BAND * m, EDGE * m
    alpha = bytearray(w * h)
    lut = [int(255 * _smooth((d - 6) / 28.0)) for d in range(256)]
    for y in range(h):
        row = y * bpl
        dy = min(y, h - 1 - y)
        for x in range(w):
            d_edge = min(x, w - 1 - x, dy)
            if d_edge >= band:
                alpha[y * w + x] = 255
                continue
            o = row + x * 4
            dist = max(abs(raw[o + 2] - br), abs(raw[o + 1] - bgc), abs(raw[o] - bb))
            e = _smooth(d_edge / band)
            a = max(e * 255, lut[dist])
            a *= _smooth(d_edge / edge) if d_edge < edge else 1.0
            alpha[y * w + x] = int(a)
    mask = QImage(bytes(alpha), w, h, w, QImage.Format_Alpha8).copy()
    out = img.convertToFormat(QImage.Format_ARGB32_Premultiplied)
    mask = mask.scaled(out.width(), out.height(), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    p = QPainter(out)
    p.setCompositionMode(QPainter.CompositionMode_DestinationIn)
    p.drawImage(0, 0, mask)
    p.end()
    return out, bg


class _Signals(QObject):
    done = Signal(str, QImage, QColor)


class _Job(QRunnable):
    def __init__(self, path: str, cache_dir: Path, signals: _Signals):
        super().__init__()
        self.path, self.cache_dir, self.signals = path, cache_dir, signals

    def run(self):
        img, bg = QImage(), QColor("#1b1612")
        try:
            st = os.stat(self.path)
            h = hashlib.md5(f"{VERSION}|{self.path}|{st.st_mtime_ns}|{st.st_size}".encode("utf-8")).hexdigest()
            png = self.cache_dir / f"{h}.png"
            col = self.cache_dir / f"{h}.cor"
            if png.exists() and col.exists():
                img = QImage(str(png))
                bg = QColor(col.read_text(encoding="ascii").strip())
            if img.isNull():
                img, bg = blend(self.path)
                if not img.isNull():
                    self.cache_dir.mkdir(parents=True, exist_ok=True)
                    img.save(str(png), "PNG")
                    col.write_text(bg.name(), encoding="ascii")
        except Exception:  # noqa: BLE001
            pass
        self.signals.done.emit(self.path, img, bg)


class BannerImages(QObject):
    """get(caminho) → (QImage, QColor) pronto, ou None enquanto calcula (avisa por `changed`)."""
    changed = Signal()

    def __init__(self, cache_dir: Path):
        super().__init__()
        self.cache_dir = cache_dir / "banner"
        self.pool = QThreadPool()
        self.pool.setMaxThreadCount(1)
        self.signals = _Signals()
        self.signals.done.connect(self._done)
        self.mem: dict[str, tuple[QImage, QColor]] = {}
        self.pending: set[str] = set()

    def get(self, path: str | None):
        if not path:
            return None
        if path in self.mem:
            return self.mem[path]
        if path not in self.pending:
            self.pending.add(path)
            self.pool.start(_Job(path, self.cache_dir, self.signals))
        return None

    def _done(self, path, img, bg):
        self.pending.discard(path)
        self.mem[path] = (img, bg)
        if len(self.mem) > 24:
            self.mem.pop(next(iter(self.mem)))
        self.changed.emit()
