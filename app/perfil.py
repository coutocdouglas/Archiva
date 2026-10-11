"""Perfil da pessoa neste computador (nome escolhido por ela, cor, foto opcional).

Fica em %APPDATA%\\GerenciadorAssets3D\\perfil.json (+ avatar.png). É criado na primeira abertura e
vale para todas as bibliotecas abertas neste computador. O nome do computador só aparece como detalhe
no histórico.
"""
from __future__ import annotations

import json
import os
import socket
import uuid

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QVBoxLayout)

from . import theme, ui
from .config import data_dir

# cores dos ícones com inicial (harmonizam com o tema Nogueira)
CORES = ["#7a2f3a", "#8a5a3c", "#5f6b43", "#3f5f6e", "#4d4a72", "#6e4a63", "#9a7a3e", "#4a4440"]


def computer_name() -> str:
    return os.environ.get("COMPUTERNAME") or socket.gethostname() or "computador"


def _path():
    return data_dir() / "perfil.json"


def avatar_file():
    return data_dir() / "avatar.png"


def load() -> dict | None:
    try:
        d = json.loads(_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or not d.get("id") or not d.get("nome"):
        return None
    d["pc"] = computer_name()
    d["foto"] = bool(d.get("foto")) and avatar_file().exists()
    return d


def save(p: dict) -> None:
    _path().write_text(json.dumps(p, ensure_ascii=False, indent=2), encoding="utf-8")


def avatar_png_bytes(p: dict) -> bytes | None:
    if p.get("foto") and avatar_file().exists():
        try:
            return avatar_file().read_bytes()
        except OSError:
            return None
    return None


def initials(nome: str) -> str:
    parts = [w for w in (nome or "?").split() if w]
    return (parts[0][0] if parts else "?").upper()


def avatar_pixmap(user: dict | None, size: int, dpr: float = 2.0) -> QPixmap:
    """Círculo com a foto da pessoa ou a inicial do nome na fonte do programa."""
    user = user or {}
    pm = QPixmap(int(size * dpr), int(size * dpr))
    pm.setDevicePixelRatio(dpr)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    r = QRectF(0, 0, size, size)
    clip = QPainterPath()
    clip.addEllipse(r)
    photo = user.get("foto_arquivo") or (str(avatar_file()) if user.get("foto") and user.get("_local") else None)
    img = QImage(photo) if photo and os.path.exists(photo) else QImage()
    if not img.isNull():
        p.setClipPath(clip)
        side = min(img.width(), img.height())
        src = QRectF((img.width() - side) / 2, (img.height() - side) / 2, side, side)
        p.drawImage(r, img, src)
        p.setClipping(False)
    else:
        p.fillPath(clip, QColor(user.get("cor") or CORES[0]))
        f = theme.ui_font(size * 0.42 * 0.75, 600)
        p.setFont(f)
        p.setPen(QColor("#f6eadb"))
        p.drawText(r, Qt.AlignCenter, initials(user.get("nome", "?")))
    p.setPen(QColor(255, 236, 210, 60))
    p.setBrush(Qt.NoBrush)
    p.drawEllipse(r.adjusted(0.5, 0.5, -0.5, -0.5))
    p.end()
    return pm


class _Swatch(QPushButton):
    def __init__(self, color: str):
        super().__init__()
        self.color = color
        self.setCheckable(True)
        self.setFixedSize(26, 26)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton{background:transparent;border:none;}")

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(3, 3, -3, -3)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(self.color))
        p.drawEllipse(r)
        if self.isChecked():
            p.setPen(QColor(theme.HILITE))
            p.setBrush(Qt.NoBrush)
            p.drawEllipse(QRectF(self.rect()).adjusted(0.8, 0.8, -0.8, -0.8))


class ProfileDialog(QDialog):
    """Criar ou editar o perfil: nome livre, cor, foto opcional."""

    def __init__(self, parent=None, profile: dict | None = None, first: bool = False):
        super().__init__(parent)
        self.setWindowTitle("Seu perfil")
        self.setMinimumWidth(520)
        self.p = dict(profile or {"id": uuid.uuid4().hex, "nome": "", "cor": CORES[0], "foto": False})
        self.p["_local"] = True
        self._photo: QImage | None = None
        self._remove_photo = False

        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(16)
        t = QLabel("Bem-vindo ao Archiva" if first else "Seu perfil")
        t.setStyleSheet("font-size:18pt;")
        outer.addWidget(t)
        if first:
            s = QLabel("Crie o seu perfil. É assim que você aparece para as outras pessoas que usam a mesma "
                       "biblioteca (por exemplo, quando estiver organizando um item). Fica ligado a este computador.")
            s.setWordWrap(True)
            s.setStyleSheet(f"color:{theme.MUTED.name()};")
            outer.addWidget(s)

        g = ui.Glass(14)
        row = QHBoxLayout(g)
        row.setContentsMargins(20, 18, 20, 18)
        row.setSpacing(20)
        self.preview = QLabel()
        self.preview.setFixedSize(96, 96)
        row.addWidget(self.preview, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(10)
        col.addWidget(ui.heading("Nome", 10))
        self.name = QLineEdit(self.p.get("nome", ""))
        self.name.setPlaceholderText("Como você quer aparecer (ex.: Douglas)")
        self.name.setMaxLength(40)
        self.name.textChanged.connect(self._update)
        col.addWidget(self.name)
        col.addSpacing(4)
        col.addWidget(ui.heading("Cor do ícone", 10))
        sw = QHBoxLayout()
        sw.setSpacing(4)
        self.swatches = []
        for c in CORES:
            b = _Swatch(c)
            b.setChecked(c == self.p.get("cor"))
            b.clicked.connect(lambda _=False, c=c: self._pick_color(c))
            self.swatches.append(b)
            sw.addWidget(b)
        sw.addStretch(1)
        col.addLayout(sw)
        col.addSpacing(4)
        ph = QHBoxLayout()
        ph.setSpacing(10)
        self.btn_photo = QPushButton("Carregar foto…")
        self.btn_photo.clicked.connect(self._load_photo)
        self.btn_initial = QPushButton("Usar a inicial")
        self.btn_initial.clicked.connect(self._use_initial)
        ph.addWidget(self.btn_photo)
        ph.addWidget(self.btn_initial)
        ph.addStretch(1)
        col.addLayout(ph)
        pc = QLabel(f"Computador: {computer_name()}")
        pc.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:9pt;")
        col.addWidget(pc)
        row.addLayout(col, 1)
        outer.addWidget(g)

        bb = QDialogButtonBox()
        self.ok = ui.primary(bb.addButton("Começar" if first else "Salvar", QDialogButtonBox.AcceptRole))
        if not first:
            bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)
        self._update()

    def _pick_color(self, c):
        self.p["cor"] = c
        for b in self.swatches:
            b.setChecked(b.color == c)
        self._update()

    def _load_photo(self):
        f, _ = QFileDialog.getOpenFileName(self, "Escolher foto", "", "Imagens (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not f:
            return
        img = QImage(f)
        if img.isNull():
            return
        side = min(img.width(), img.height())
        img = img.copy((img.width() - side) // 2, (img.height() - side) // 2, side, side)
        self._photo = img.scaled(256, 256, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        self._remove_photo = False
        self._update()

    def _use_initial(self):
        self._photo = None
        self._remove_photo = True
        self._update()

    def _preview_user(self) -> dict:
        u = dict(self.p, nome=self.name.text().strip() or "?")
        if self._photo is not None:
            tmp = data_dir() / "avatar_previa.png"
            self._photo.save(str(tmp), "PNG")
            u["foto_arquivo"] = str(tmp)
        elif self._remove_photo:
            u["foto"] = False
        return u

    def _update(self):
        self.preview.setPixmap(avatar_pixmap(self._preview_user(), 96))
        self.ok.setEnabled(bool(self.name.text().strip()))

    def accept(self):
        if not self.name.text().strip():
            return
        self.p["nome"] = " ".join(self.name.text().split())
        if self._photo is not None:
            self._photo.save(str(avatar_file()), "PNG")
            self.p["foto"] = True
        elif self._remove_photo:
            self.p["foto"] = False
            try:
                avatar_file().unlink()
            except OSError:
                pass
        try:
            (data_dir() / "avatar_previa.png").unlink()
        except OSError:
            pass
        self.p.pop("_local", None)
        self.p["pc"] = computer_name()
        save(self.p)
        super().accept()

    def result_profile(self) -> dict:
        return dict(self.p)


class UserChip(QPushButton):
    """Foto/inicial + nome no menu lateral; clique abre o menu do perfil."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.user: dict = {}
        self.subtitle = ""
        self.setFixedHeight(52)
        self.setCursor(Qt.PointingHandCursor)
        self.setStyleSheet("QPushButton{background:transparent;border:none;}")

    def set_user(self, user: dict, subtitle: str = ""):
        self.user, self.subtitle = dict(user or {}, _local=True), subtitle
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(4, 4, -4, -4)
        if self.underMouse():
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(255, 236, 210, 18))
            p.drawRoundedRect(r, 10, 10)
        av = 30
        p.drawPixmap(int(r.left() + 8), int(r.center().y() - av / 2), avatar_pixmap(self.user, av))
        x = r.left() + 8 + av + 10
        p.setFont(theme.ui_font(10))
        p.setPen(theme.TEXT)
        fm = p.fontMetrics()
        name = fm.elidedText(self.user.get("nome", ""), Qt.ElideRight, int(r.right() - x - 6))
        if self.subtitle:
            p.drawText(QRectF(x, r.top(), r.right() - x, r.height() / 2), Qt.AlignLeft | Qt.AlignBottom, name)
            p.setFont(theme.ui_font(8.5))
            p.setPen(theme.FAINT)
            p.drawText(QRectF(x, r.center().y() + 2, r.right() - x, r.height() / 2), Qt.AlignLeft | Qt.AlignTop,
                       self.subtitle)
        else:
            p.drawText(QRectF(x, r.top(), r.right() - x, r.height()), Qt.AlignLeft | Qt.AlignVCenter, name)

    def enterEvent(self, e):
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.update()
        super().leaveEvent(e)
