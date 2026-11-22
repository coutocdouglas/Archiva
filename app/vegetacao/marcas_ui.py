"""Interface dos favoritos e das tags da Vegetação (etapa 5): caixa de tags do painel, botão de favorito,
janela de tags (botão direito) e a estrela desenhada nos cartões."""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, QStringListModel, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import (QCompleter, QDialog, QDialogButtonBox, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout, QWidget)

from .. import theme
from . import marcas

STAR = QColor("#f5d36b")

CHIPS_CSS = (
    "QListWidget{background:transparent; border:none;}"
    "QListWidget::item{background:rgba(255,230,200,0.07); border:1px solid rgba(255,230,200,0.10);"
    " border-radius:12px; padding:4px 10px; color:#f1e9dc;}"
    "QListWidget::item:hover{background:rgba(255,230,200,0.13);}"
    "QListWidget::item:selected{background:rgba(255,230,200,0.13); color:#fff6e8;}")


def paint_star(p: QPainter, center: QPointF, r: float, on: bool = True) -> None:
    import math
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append(QPointF(center.x() + rr * math.cos(a), center.y() + rr * math.sin(a)))
    path = QPainterPath()
    path.addPolygon(QPolygonF(pts))
    path.closeSubpath()
    p.save()
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(QPen(QColor(20, 16, 12, 170), 1.2) if on else QPen(STAR, 1.6))
    p.setBrush(STAR if on else Qt.NoBrush)
    p.drawPath(path)
    p.restore()


def star_icon(on: bool) -> QIcon:
    """A fonte do programa não tem o caractere ★: a estrela é desenhada."""
    pm = QPixmap(32, 32)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    paint_star(p, QPointF(16, 16.5), 13, on)
    p.end()
    pm.setDevicePixelRatio(2)
    return QIcon(pm)


def paint_card_star(p: QPainter, img: QRectF) -> None:
    """Estrela no canto de cima à esquerda da imagem do cartão (favorito)."""
    bg = QRectF(img.left() + 8, img.top() + 8, 22, 22)
    path = QPainterPath()
    path.addRoundedRect(bg, 11, 11)
    p.fillPath(path, QColor(20, 22, 25, 160))
    paint_star(p, bg.center(), 7.5)


class FavButton(QPushButton):
    """Favoritar / Favorita (com a estrela) — para a espécie mostrada no painel."""
    toggled_key = Signal(str, bool)

    def __init__(self, page):
        super().__init__()
        self.page = page
        self.key = None
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(16, 16))
        self.clicked.connect(self._click)

    def show_key(self, key: str | None):
        self.key = key
        self._paint()

    def _paint(self):
        on = bool(self.key) and self.key in self.page.favs
        self.setText("  Favorita" if on else "  Favoritar")
        self.setIcon(star_icon(on))
        self.setToolTip("Tirar dos favoritos" if on else "Pôr esta planta nos favoritos (só para você)")
        self.setStyleSheet(f"QPushButton{{color:{STAR.name()};}}" if on else "")

    def _click(self):
        if self.key:
            self.page.toggle_fav(self.key)
            self._paint()


class TagBox(QWidget):
    """Tags de um item (chips; clique tira) + campo para adicionar. Igual ao painel da Biblioteca."""
    changed = Signal()

    def __init__(self, page, placeholder="Adicionar tag e Enter (várias: vírgula)"):
        super().__init__()
        self.page = page
        self.key: str | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        self.list = QListWidget()
        self.list.setFlow(QListView.LeftToRight)
        self.list.setWrapping(True)
        self.list.setResizeMode(QListView.Adjust)
        self.list.setSpacing(4)
        self.max_h = 96
        self.list.setToolTip("Clique numa tag para tirá-la")
        self.list.setStyleSheet(CHIPS_CSS)
        self.list.setCursor(Qt.PointingHandCursor)
        self.list.itemClicked.connect(self._remove)
        lay.addWidget(self.list)
        self.input = QLineEdit()
        self.input.setPlaceholderText(placeholder)
        self.model = QStringListModel()
        comp = QCompleter(self.model, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.input.setCompleter(comp)
        self.input.returnPressed.connect(self._add)
        lay.addWidget(self.input)

    @property
    def db(self):
        return self.page.w.db

    def show_key(self, key: str | None):
        if key != self.key:
            self.input.clear()
        self.key = key
        self.refresh()

    def refresh(self):
        self.list.clear()
        tags = marcas.tags_de(self.db, self.key) if self.key else []
        for t in tags:
            it = QListWidgetItem(t + "   ×")
            it.setData(Qt.UserRole, t)
            self.list.addItem(it)
        self.list.setVisible(bool(tags))
        QTimer.singleShot(0, self._fit)
        self.model.setStringList(marcas.sugestoes(self.db))
        self.input.setEnabled(bool(self.key))

    def _fit(self):
        """Altura só do que as tags ocupam (sem faixa vazia), até 3 linhas."""
        n = self.list.count()
        if not n:
            return
        self.list.doItemsLayout()
        bottom = max(self.list.visualItemRect(self.list.item(i)).bottom() for i in range(n))
        self.list.setFixedHeight(min(bottom + 8, self.max_h))

    def _add(self):
        tags = marcas.split_tags(self.input.text())
        if not tags or not self.key:
            return
        marcas.adicionar(self.db, [self.key], tags)
        self.input.clear()
        self.refresh()
        self.changed.emit()

    def _remove(self, it):
        marcas.remover(self.db, [self.key], it.data(Qt.UserRole))
        self.refresh()
        self.changed.emit()


class TagsDialog(QDialog):
    """Botão direito › Tags… (espécie ou volume)."""

    def __init__(self, page, key: str, nome: str):
        super().__init__(page)
        self.setWindowTitle(f"Tags — {nome}")
        self.setMinimumWidth(420)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(10)
        t = QLabel(nome)
        t.setFont(theme.ui_font(13))
        t.setWordWrap(True)
        lay.addWidget(t)
        hint = QLabel("As tags valem para toda a equipe, como as da Biblioteca.")
        hint.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:9pt;")
        lay.addWidget(hint)
        self.box = TagBox(page)
        self.box.max_h = 150
        self.box.show_key(key)
        lay.addWidget(self.box)
        bb = QDialogButtonBox(QDialogButtonBox.Close)
        bb.rejected.connect(self.reject)
        bb.accepted.connect(self.accept)
        lay.addWidget(bb)
        self.box.input.setFocus()
