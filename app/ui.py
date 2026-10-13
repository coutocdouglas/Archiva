"""Componentes visuais compartilhados: ícones, menu lateral, seletor segmentado, painéis de vidro."""
from __future__ import annotations

from PySide6.QtCore import QByteArray, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (QAbstractButton, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QSizePolicy,
                               QVBoxLayout, QWidget)

from . import theme

_ICONS = {
    "inicio": '<path d="M4 11l8-6 8 6v8a1 1 0 0 1-1 1h-4v-6H9v6H5a1 1 0 0 1-1-1z"/>',
    "biblioteca": '<rect x="4" y="4" width="7" height="7" rx="1.5"/><rect x="13" y="4" width="7" height="7" rx="1.5"/>'
                  '<rect x="4" y="13" width="7" height="7" rx="1.5"/><rect x="13" y="13" width="7" height="7" rx="1.5"/>',
    "tags": '<path d="M4 12V5a1 1 0 0 1 1-1h7l8 8-8 8z"/><circle cx="8.5" cy="8.5" r="1.3"/>',
    "entrada": '<path d="M12 4v10m0 0l-4-4m4 4l4-4"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
    "config": '<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1'
              'M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
    "busca": '<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    "atualizar": '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>',
    "pasta": '<path d="M4 7a1 1 0 0 1 1-1h4l2 2h8a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1z"/>',
    "aprender": '<path d="M12 6.5C10.3 5.2 7.9 4.7 4.5 5v13c3.4-.3 5.8.2 7.5 1.5"/>'
                '<path d="M12 6.5c1.7-1.3 4.1-1.8 7.5-1.5v13c-3.4-.3-5.8.2-7.5 1.5z"/>',
    "fechar": '<path d="M6 6l12 12M18 6L6 18"/>',
    "organizar": '<path d="M5 7h9M18 7h1M5 17h3M12 17h7"/><circle cx="16" cy="7" r="2"/><circle cx="10" cy="17" r="2"/>',
    "colecoes": '<path d="M12 4l8 4-8 4-8-4z"/><path d="M4 12l8 4 8-4"/><path d="M4 16l8 4 8-4"/>',
}


def icon_pixmap(name: str, color: QColor | str, size: int = 20, stroke: float = 1.7) -> QPixmap:
    col = QColor(color).name()
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" '
           f'stroke="{col}" stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{_ICONS[name]}</svg>')
    r = QSvgRenderer(QByteArray(svg.encode()))
    ratio = 2
    pm = QPixmap(size * ratio, size * ratio)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    r.render(p)
    p.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, color: QColor | str = theme.MUTED, size: int = 20) -> QIcon:
    return QIcon(icon_pixmap(name, color, size))


def primary(btn: QPushButton) -> QPushButton:
    btn.setProperty("primary", True)
    btn.setCursor(Qt.PointingHandCursor)
    btn.style().unpolish(btn)
    btn.style().polish(btn)
    return btn


def link_button(text: str) -> QPushButton:
    b = QPushButton(text)
    b.setProperty("flat", True)
    b.setCursor(Qt.PointingHandCursor)
    return b


def heading(text: str, size: float = 10.5) -> QLabel:
    l = QLabel(text)
    l.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:{size}pt;")
    return l


# --------------------------------------------------------------------------- vidro

class Glass(QFrame):
    """Painel de vidro quente (fundo translúcido + borda fina + brilho no topo)."""

    def __init__(self, radius: float = 12, strength: float = 1.0, parent=None):
        super().__init__(parent)
        self.radius, self.strength = radius, strength
        self.hover = False
        self.setAttribute(Qt.WA_StyledBackground, False)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        theme.paint_glass(p, QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), self.radius, self.strength, self.hover)


class SearchField(Glass):
    """Campo de busca em vidro, com lupa e (opcional) botão."""
    submitted = Signal(str)

    def __init__(self, placeholder: str, button: str | None = None, height: int = 46, parent=None):
        super().__init__(12, 1.0, parent)
        self.setFixedHeight(height)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 6, 6 if button else 12, 6)
        lay.setSpacing(10)
        ic = QLabel()
        ic.setPixmap(icon_pixmap("busca", theme.FAINT, 18, 2))
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.setClearButtonEnabled(True)
        self.edit.setStyleSheet("QLineEdit{background:transparent; border:none; padding:0; font-size:11pt;}")
        self.edit.returnPressed.connect(lambda: self.submitted.emit(self.edit.text()))
        lay.addWidget(ic)
        lay.addWidget(self.edit, 1)
        self.button = None
        if button:
            self.button = primary(QPushButton(button))
            self.button.setFixedHeight(height - 12)
            self.button.clicked.connect(lambda: self.submitted.emit(self.edit.text()))
            lay.addWidget(self.button)


# --------------------------------------------------------------------------- seletor segmentado

class Segmented(Glass):
    """Botões lado a lado (Todos / Prontos / ...). API parecida com QComboBox."""
    currentIndexChanged = Signal(int)

    def __init__(self, options: list[tuple[str, str]], parent=None):
        super().__init__(11, 1.0, parent)
        self.options = options
        self._index = 0
        self._hover = -1
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(46)
        self.no_drag = True
        f = theme.ui_font(10)
        fm = QFontMetrics(f)
        self._w = [fm.horizontalAdvance(t) + 30 for t, _ in options]
        self.setFixedWidth(sum(self._w) + 8)

    def _rects(self):
        x = 4.0
        out = []
        for w in self._w:
            out.append(QRectF(x, 4, w, self.height() - 8))
            x += w
        return out

    def count(self):
        return len(self.options)

    def findData(self, key):
        return next((i for i, (_, k) in enumerate(self.options) if k == key), -1)

    def currentData(self):
        return self.options[self._index][1]

    def currentIndex(self):
        return self._index

    def setCurrentIndex(self, i):
        i = max(0, min(len(self.options) - 1, i))
        if i != self._index:
            self._index = i
            self.update()
            if not self.signalsBlocked():
                self.currentIndexChanged.emit(i)

    def mouseMoveEvent(self, e):
        h = next((i for i, r in enumerate(self._rects()) if r.contains(e.position())), -1)
        if h != self._hover:
            self._hover = h
            self.update()

    def leaveEvent(self, e):
        self._hover = -1
        self.update()

    def mousePressEvent(self, e):
        for i, r in enumerate(self._rects()):
            if r.contains(e.position()):
                self.setCurrentIndex(i)

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setFont(theme.ui_font(10))
        for i, (r, (label, _)) in enumerate(zip(self._rects(), self.options)):
            if i == self._index:
                path = QPainterPath()
                path.addRoundedRect(r, 8, 8)
                p.fillPath(path, QColor(255, 230, 200, 31))
                p.setPen(QPen(QColor(255, 240, 220, 36), 1))
                p.drawLine(QPointF(r.left() + 8, r.top() + 0.5), QPointF(r.right() - 8, r.top() + 0.5))
                p.setPen(theme.TEXT)
            else:
                p.setPen(theme.TEXT if i == self._hover else theme.MUTED)
            p.drawText(r, Qt.AlignCenter, label)


# --------------------------------------------------------------------------- menu lateral

class NavButton(QAbstractButton):
    def __init__(self, key: str, text: str, icon_name: str, parent=None):
        super().__init__(parent)
        self.key, self.text_, self.icon_name = key, text, icon_name
        self.badge = 0
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(42)
        self._hover = False

    def set_badge(self, n: int):
        self.badge = n
        self.update()

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        on = self.isChecked()
        if on:
            path = QPainterPath()
            path.addRoundedRect(r, 9, 9)
            from PySide6.QtGui import QLinearGradient
            g = QLinearGradient(r.topLeft(), r.bottomLeft())
            g.setColorAt(0, QColor(255, 230, 200, 33))
            g.setColorAt(1, QColor(255, 230, 200, 15))
            p.fillPath(path, g)
            p.setPen(QPen(QColor(255, 230, 200, 36), 1))
            p.drawPath(path)
            p.setPen(QPen(QColor(255, 240, 220, 40), 1))
            p.drawLine(QPointF(r.left() + 9, r.top() + 1), QPointF(r.right() - 9, r.top() + 1))
        elif self._hover:
            path = QPainterPath()
            path.addRoundedRect(r, 9, 9)
            p.fillPath(path, QColor(255, 230, 200, 14))
        col = QColor("#fff6e8") if on else (QColor("#ead8bf") if self._hover else QColor("#cdb9a0"))
        p.drawPixmap(14, (self.height() - 20) // 2, icon_pixmap(self.icon_name, "#f1dcb8" if on else col, 20))
        p.setFont(theme.ui_font(10.5))
        p.setPen(col)
        p.drawText(QRectF(46, 0, r.width() - 46, r.height()), Qt.AlignVCenter | Qt.AlignLeft, self.text_)
        if self.badge:
            t = str(self.badge)
            f = theme.ui_font(8.5, 700)
            p.setFont(f)
            w = max(22, QFontMetrics(f).horizontalAdvance(t) + 12)
            br = QRectF(r.right() - w - 12, r.center().y() - 9, w, 18)
            path = QPainterPath()
            path.addRoundedRect(br, 9, 9)
            p.fillPath(path, QColor("#e9dcc4"))
            p.setPen(QColor("#2a170d"))
            p.drawText(br, Qt.AlignCenter, t)


class LogoMark(QWidget):
    """Logotipo 'Archiva' centralizado pelo desenho real das letras (ignora os espaços laterais da fonte)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(78)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        path = theme.logo_path()
        br = path.boundingRect()
        top = 6
        path.translate((self.width() - br.width()) / 2 - br.left(), top - br.top())
        p.fillPath(path, theme.LOGO)


class Sidebar(QWidget):
    navigate = Signal(str)

    def __init__(self, items: list[tuple[str, str, str]], parent=None):
        super().__init__(parent)
        self.setFixedWidth(232)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 30, 16, 20)
        lay.setSpacing(4)
        self.logo = LogoMark()
        lay.addWidget(self.logo)
        self.buttons: dict[str, NavButton] = {}
        for key, text, ic in items:
            b = NavButton(key, text, ic)
            b.clicked.connect(lambda _c=False, k=key: self.navigate.emit(k))
            self.buttons[key] = b
            lay.addWidget(b)
        lay.addStretch(1)
        self.settings = NavButton("config", "Configurações", "config")
        self.settings.setCheckable(False)
        lay.addWidget(self.settings)
        self.footer = QLabel()
        self.footer.setStyleSheet("color:rgba(239,226,201,0.45); font-size:8.5pt; padding:12px 12px 0 12px;")
        self.footer.setWordWrap(True)
        lay.addWidget(self.footer)

    def set_current(self, key: str):
        for k, b in self.buttons.items():
            b.setChecked(k == key)

    def paintEvent(self, e):
        p = QPainter(self)
        theme.paint_sidebar(p, QRectF(self.rect()))


class Root(QWidget):
    """Fundo da janela inteira (grafite quente)."""

    def paintEvent(self, e):
        p = QPainter(self)
        theme.paint_background(p, QRectF(self.rect()))
