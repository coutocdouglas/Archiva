"""Barra de categorias da Biblioteca (1.2.6): linha com miniatura, subpastas que abrem e fecham, e tags em chips.

- `CategoryDelegate`: desenha cada categoria (miniatura da prévia mais recente, nome, contagem, setinha de subpastas).
- `CategoryTree`: a árvore; clicar na setinha abre/fecha as subpastas sem trocar a categoria selecionada.
- `TagChips`: as tags para filtrar, em botões arredondados que quebram de linha ("ver todas…" para o resto).
- `AllTagsDialog`: a lista completa de tags com caixinhas (para quando há mais tags do que cabem nos chips).
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QAbstractButton, QDialog, QLayout, QLineEdit, QListWidget, QListWidgetItem, QStyle,
                               QStyledItemDelegate, QTreeWidget, QVBoxLayout, QWidget)

from . import theme, ui
from .scanner import normalize

COUNT_ROLE = Qt.UserRole + 5      # quantidade de itens da categoria
COVER_ROLE = Qt.UserRole + 6      # caminho da prévia mais recente ("*" = ícone de grade, da linha "Todas")
HEADER_ROLE = Qt.UserRole + 7     # texto de um título de seção ("Fixadas", "Lista completa"); a linha não é selecionável
PIN_ROLE = Qt.UserRole + 8        # True nas cópias da seção "Fixadas"

ROW_TOP = 40                      # categoria de cima (com miniatura)
ROW_SUB = 34                      # subpasta
ROW_HEAD = 26                     # título de seção
THUMB = 32
CHIP_MAX_SHOWN = 10               # tags mais usadas mostradas como chips (as marcadas aparecem sempre)


def cover_of(category) -> str:
    """Prévia mais recente da categoria (pela data que já vem na leitura da pasta; sem ir ao servidor)."""
    best, best_t = "", -1.0
    for a in category.all_assets():
        if not a.preview:
            continue
        t = getattr(a, "preview_mtime", 0.0) or getattr(a, "added_time", 0.0) or 0.0
        if t > best_t:
            best, best_t = a.preview, t
    return best


# =========================================================================== linha de categoria

class CategoryDelegate(QStyledItemDelegate):
    CHEVRON_W = 30

    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.w = window
        self._bg: dict[str, QColor] = {}

    @staticmethod
    def chevron_rect(rect: QRect) -> QRect:
        return QRect(rect.right() - CategoryDelegate.CHEVRON_W, rect.top(), CategoryDelegate.CHEVRON_W, rect.height())

    def sizeHint(self, option, index):
        if index.data(HEADER_ROLE):
            return QSize(100, ROW_HEAD)
        return QSize(100, ROW_SUB if index.parent().isValid() else ROW_TOP)

    def _paint_header(self, p: QPainter, option, text: str) -> None:
        r = QRectF(option.rect)
        x = r.left() + 10
        if text == "Fixadas":                                      # alfinete
            c = QPointF(x + 5, r.center().y() + 1)
            p.setPen(QPen(theme.LINK, 1.6, Qt.SolidLine, Qt.RoundCap))
            p.setBrush(Qt.NoBrush)
            p.drawLine(QPointF(c.x() + 3, c.y() - 5), QPointF(c.x() - 3, c.y() + 1))
            p.drawLine(QPointF(c.x() - 1, c.y() - 7), QPointF(c.x() + 5, c.y() - 1))
            p.drawLine(QPointF(c.x() - 3, c.y() + 1), QPointF(c.x() - 5, c.y() + 6))
            x += 18
        f = theme.ui_font(8.5)
        f.setBold(True)
        f.setLetterSpacing(QFont.AbsoluteSpacing, 0.8)
        p.setFont(f)
        p.setPen(theme.MUTED)
        p.drawText(QRectF(x, r.top() + 4, r.right() - x, r.height() - 4), Qt.AlignVCenter | Qt.AlignLeft,
                   text.upper())

    def _thumb(self, p: QPainter, box: QRectF, path: str | None) -> None:
        clip = QPainterPath()
        clip.addRoundedRect(box, 8, 8)
        p.save()
        p.setClipPath(clip)
        if path == "*":                                            # "Todas as categorias": ícone de grade
            p.fillRect(box, QColor(255, 236, 210, 28))
            s, gap = 6.5, 3.0
            x0 = box.center().x() - s - gap / 2
            y0 = box.center().y() - s - gap / 2
            p.setPen(Qt.NoPen)
            p.setBrush(theme.LINK)
            for i in range(2):
                for j in range(2):
                    p.drawRoundedRect(QRectF(x0 + i * (s + gap), y0 + j * (s + gap), s, s), 1.8, 1.8)
        else:
            pix = self.w.thumbs.get(path) if path else None
            if pix is not None and not pix.isNull():
                bg = self._bg.get(path)
                if bg is None:
                    from .home_page import edge_color
                    bg = self._bg[path] = edge_color(pix)
                p.fillRect(box, bg)
                from PySide6.QtCore import QSizeF
                sc = QSizeF(pix.size()).scaled(box.size(), Qt.KeepAspectRatio)
                tgt = QRectF(box.center().x() - sc.width() / 2, box.center().y() - sc.height() / 2,
                             sc.width(), sc.height())
                p.drawPixmap(tgt, pix, QRectF(pix.rect()))
            else:
                p.fillRect(box, QColor(255, 236, 210, 14))
        p.restore()
        p.setPen(QPen(QColor(0, 0, 0, 40), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRoundedRect(box.adjusted(0.5, 0.5, -0.5, -0.5), 8, 8)

    def paint(self, p: QPainter, option, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        head = index.data(HEADER_ROLE)
        if head:
            self._paint_header(p, option, head)
            p.restore()
            return
        r = QRectF(option.rect).adjusted(0, 1, -2, -1)
        sub = index.parent().isValid()
        sel = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        has_kids = index.model().hasChildren(index)
        if sub:                                                    # fio das subpastas
            p.setPen(QPen(QColor(255, 230, 200, 36), 1))
            x = option.rect.left() - 7.5
            p.drawLine(QPointF(x, option.rect.top()), QPointF(x, option.rect.bottom() + 1))
        if sel:
            theme.paint_glass(p, r, 10, 1.6)
            bar = QPainterPath()
            bar.addRoundedRect(QRectF(r.left() + 0.5, r.top() + 9, 3, r.height() - 18), 1.5, 1.5)
            p.fillPath(bar, theme.SELECT)
        elif hover:
            hp = QPainterPath()
            hp.addRoundedRect(r, 10, 10)
            p.fillPath(hp, QColor(255, 230, 200, 12))

        x = r.left() + (12 if sub else 8)
        if not sub:
            box = QRectF(x, r.center().y() - THUMB / 2, THUMB, THUMB)
            self._thumb(p, box, index.data(COVER_ROLE))
            x = box.right() + 10
        right = r.right() - 10
        if has_kids:                                               # setinha de abrir/fechar
            c = QPointF(r.right() - self.CHEVRON_W / 2 + 4, r.center().y())
            pen = QPen(theme.MUTED, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            chev = QPainterPath()
            if option.state & QStyle.State_Open:
                chev.moveTo(c.x() - 4, c.y() - 2)
                chev.lineTo(c.x(), c.y() + 2)
                chev.lineTo(c.x() + 4, c.y() - 2)
            else:
                chev.moveTo(c.x() - 2, c.y() - 4)
                chev.lineTo(c.x() + 2, c.y())
                chev.lineTo(c.x() - 2, c.y() + 4)
            p.drawPath(chev)
            right -= self.CHEVRON_W - 8

        count = index.data(COUNT_ROLE)
        cw = 0
        if count is not None:
            f2 = theme.ui_font(9)
            txt = f"{count:,}".replace(",", ".")
            cw = QFontMetrics(f2).horizontalAdvance(txt) + 6
            p.setFont(f2)
            p.setPen(QColor("#f0e6d4") if sel else theme.MUTED)
            p.drawText(QRectF(right - cw, r.top(), cw, r.height()), Qt.AlignVCenter | Qt.AlignRight, txt)
        f = theme.ui_font(9.5 if sub else 10)
        p.setFont(f)
        fm = QFontMetrics(f)
        p.setPen(QColor("#fff6e8") if sel else (theme.TEXT if hover else QColor("#e3d8c6")))
        avail = int(right - cw - x - 6)
        p.drawText(QRectF(x, r.top(), max(avail, 10), r.height()), Qt.AlignVCenter | Qt.AlignLeft,
                   fm.elidedText(index.data(Qt.DisplayRole) or "", Qt.ElideRight, max(avail, 10)))
        p.restore()


class CategoryTree(QTreeWidget):
    """Árvore de categorias: clicar na setinha só abre/fecha, sem trocar a categoria selecionada."""

    def mousePressEvent(self, e):  # noqa: N802
        if e.button() == Qt.LeftButton:
            pos = e.position().toPoint()
            it = self.itemAt(pos)
            if it is not None and it.childCount() > 0 and CategoryDelegate.chevron_rect(
                    self.visualItemRect(it)).contains(pos):
                it.setExpanded(not it.isExpanded())
                e.accept()
                return
        super().mousePressEvent(e)


# =========================================================================== chips de tags

class FlowLayout(QLayout):
    """Itens lado a lado que quebram de linha quando falta largura."""

    def __init__(self, parent=None, hspace: int = 6, vspace: int = 6):
        super().__init__(parent)
        self._items: list = []
        self._h, self._v = hspace, vspace
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):  # noqa: N802
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):  # noqa: N802
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):  # noqa: N802
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def hasHeightForWidth(self):  # noqa: N802
        return True

    def heightForWidth(self, w):  # noqa: N802
        return self._layout(QRect(0, 0, w, 0), True)

    def setGeometry(self, rect):  # noqa: N802
        super().setGeometry(rect)
        self._layout(rect, False)

    def sizeHint(self):  # noqa: N802
        return self.minimumSize()

    def minimumSize(self):  # noqa: N802
        s = QSize()
        for it in self._items:
            s = s.expandedTo(it.minimumSize())
        m = self.contentsMargins()
        return s + QSize(m.left() + m.right(), m.top() + m.bottom())

    def _layout(self, rect: QRect, test: bool) -> int:
        m = self.contentsMargins()
        eff = rect.adjusted(m.left(), m.top(), -m.right(), -m.bottom())
        x, y, line_h = eff.x(), eff.y(), 0
        for it in self._items:
            sz = it.sizeHint()
            if x + sz.width() > eff.right() + 1 and line_h > 0:
                x = eff.x()
                y += line_h + self._v
                line_h = 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), sz))
            x += sz.width() + self._h
            line_h = max(line_h, sz.height())
        return y + line_h - rect.y() + m.bottom()


class Chip(QAbstractButton):
    """Tag como botão arredondado: nome + contagem; marcada = contorno latão e visto."""
    H = 28
    MAX_W = 230

    def __init__(self, text: str, count: int, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.TabFocus)
        self._text, self._count = text, count
        self.setToolTip("Clique para filtrar por esta tag (todas as marcadas precisam estar no item)")
        self.toggled.connect(lambda _on: self.updateGeometry())

    def _parts(self):
        f = theme.ui_font(9.5)
        fm = QFontMetrics(f)
        cnt = str(self._count)
        cw = fm.horizontalAdvance(cnt)
        lead = 26 if self.isChecked() else 11
        room = self.MAX_W - lead - cw - 6 - 11
        name = fm.elidedText(self._text, Qt.ElideRight, max(room, 30))
        return f, fm, name, cnt, cw, lead

    def sizeHint(self):  # noqa: N802
        _f, fm, name, _cnt, cw, lead = self._parts()
        return QSize(lead + fm.horizontalAdvance(name) + 6 + cw + 11, self.H)

    def minimumSizeHint(self):  # noqa: N802
        return self.sizeHint()

    def paintEvent(self, e):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        f, fm, name, cnt, cw, lead = self._parts()
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        on = self.isChecked()
        hover = self.underMouse()
        path = QPainterPath()
        path.addRoundedRect(r, r.height() / 2, r.height() / 2)
        if on:
            p.fillPath(path, QColor(240, 230, 212, 44 if hover else 40))
            p.setPen(QPen(theme.HILITE, 1))
        else:
            p.fillPath(path, QColor(255, 236, 210, 22 if hover else 15))
            p.setPen(QPen(QColor(255, 230, 200, 44), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)
        x = 11.0
        if on:                                                     # visto
            ck = QPainterPath()
            cy = r.center().y()
            ck.moveTo(11, cy)
            ck.lineTo(14.5, cy + 3.5)
            ck.lineTo(20, cy - 3.5)
            p.setPen(QPen(theme.HILITE, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
            p.drawPath(ck)
            x = 26.0
        p.setFont(f)
        p.setPen(QColor("#f0e6d4") if on else theme.TEXT)
        p.drawText(QRectF(x, 0, fm.horizontalAdvance(name) + 2, self.height()), Qt.AlignVCenter | Qt.AlignLeft, name)
        p.setPen(theme.MUTED)
        p.drawText(QRectF(x + fm.horizontalAdvance(name) + 6, 0, cw + 2, self.height()),
                   Qt.AlignVCenter | Qt.AlignLeft, cnt)
        if self.hasFocus():
            p.setPen(QPen(theme.LINK, 2))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)


class TagChips(QWidget):
    """As tags mais usadas (e as marcadas) como chips; "ver todas…" abre a lista completa."""
    toggled = Signal(str, bool)
    show_all = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._flow = FlowLayout(self, 6, 6)

    def set_tags(self, tags: list[tuple[str, int]], active: set[str]) -> None:
        while self._flow.count():
            it = self._flow.takeAt(0)
            w = it.widget()
            if w is not None:
                w.setParent(None)
                w.deleteLater()
        ranked = sorted(tags, key=lambda t: (-t[1], t[0].casefold()))
        shown = ranked[:CHIP_MAX_SHOWN]
        names = {n for n, _ in shown}
        shown += [t for t in ranked[CHIP_MAX_SHOWN:] if t[0] in active and t[0] not in names]
        shown.sort(key=lambda t: (-t[1], t[0].casefold()))
        for name, n in shown:
            chip = Chip(name, n, self)
            chip.setChecked(name in active)
            chip.toggled.connect(lambda on, nm=name: self.toggled.emit(nm, on))
            self._flow.addWidget(chip)
        hidden = len(ranked) - len(shown)
        if hidden > 0:
            b = ui.link_button(f"ver todas ({len(ranked)})…")
            b.setFixedHeight(Chip.H)
            b.clicked.connect(self.show_all.emit)
            self._flow.addWidget(b)
        self.updateGeometry()


class AllTagsDialog(QDialog):
    """Todas as tags da biblioteca com caixinhas (marcar filtra a grade na hora)."""

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self.setWindowTitle("Filtrar por tags")
        self.resize(380, 520)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(10)
        lay.addWidget(ui.heading("Marque as tags: o item precisa ter todas as marcadas.", 10))
        self.find = QLineEdit()
        self.find.setPlaceholderText("Buscar tag…")
        self.find.setClearButtonEnabled(True)
        self.find.textChanged.connect(self._filter)
        lay.addWidget(self.find)
        self.list = QListWidget()
        self.list.setStyleSheet("QListWidget::item{padding:5px 8px; color:#cbbfae; border-radius:7px;}"
                                "QListWidget::item:hover{background:rgba(255,230,200,0.06); color:#f1e9dc;}"
                                "QListWidget::indicator{width:14px; height:14px; border-radius:4px;"
                                " border:1px solid rgba(255,230,200,0.28); background:rgba(255,236,210,0.04);}"
                                "QListWidget::indicator:checked{background:#e3cfa9; border-color:#e3cfa9;}")
        for t, n in window.db.all_tags():
            it = QListWidgetItem(f"{t}  ({n})")
            it.setData(Qt.UserRole, t)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if t in window.active_tags else Qt.Unchecked)
            self.list.addItem(it)
        self.list.itemChanged.connect(window._on_tag_filter)
        lay.addWidget(self.list, 1)

    def _filter(self, text: str) -> None:
        toks = normalize(text).split()
        for i in range(self.list.count()):
            it = self.list.item(i)
            name = normalize(it.data(Qt.UserRole))
            it.setHidden(not all(t in name for t in toks))
