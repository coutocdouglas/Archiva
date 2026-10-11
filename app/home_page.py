"""Aba Início — banner de novidades, números da biblioteca, recentes e categorias."""
from __future__ import annotations

import os
import time
from datetime import datetime

from PySide6.QtCore import QEasingCurve, QEvent, QSizeF, QStringListModel, QPointF, QRect, QRectF, QSize, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import (QColor, QFont, QImage, QFontMetrics, QIcon, QImageReader, QLinearGradient, QRadialGradient, QPainter, QPainterPath,
                           QPen, QPixmap)
from PySide6.QtWidgets import (QCompleter, QFrame, QLineEdit, QPushButton, QGridLayout, QHBoxLayout, QLabel, QListView, QListWidget, QListWidgetItem,
                               QScrollArea, QSizePolicy, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget, QAbstractItemView)

from . import theme, ui
from .janela import TITLE_H
from .scanner import Asset

ACCENT = QColor("#e3cfa9")


def when_text(ts: float) -> str:
    d = (datetime.now().date() - datetime.fromtimestamp(ts).date()).days
    if d <= 0:
        return "hoje"
    if d == 1:
        return "ontem"
    if d < 30:
        return f"há {d} dias"
    return datetime.fromtimestamp(ts).strftime("%d/%m/%Y")


def edge_color(pix: QPixmap) -> QColor:
    """Cor do fundo da imagem: média das bordas (as prévias costumam ter fundo liso)."""
    if pix.isNull():
        return QColor("#1b1d20")
    img = pix.toImage().scaled(48, 48, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    pts = [(x, 0) for x in range(48)] + [(x, 47) for x in range(48)] + \
          [(0, y) for y in range(48)] + [(47, y) for y in range(48)]
    cols = sorted((img.pixelColor(x, y) for x, y in pts), key=lambda c: c.lightness())
    mid = cols[len(cols) // 4: len(cols) * 3 // 4]    # descarta os extremos (objeto encostando na borda)
    n = len(mid)
    return QColor(sum(c.red() for c in mid) // n, sum(c.green() for c in mid) // n, sum(c.blue() for c in mid) // n)


def accent_color(pix: QPixmap) -> QColor:
    """Cor média do objeto (ignorando o fundo branco/cinza claro das prévias)."""
    if pix.isNull():
        return QColor("#5b8fd6")
    img = pix.toImage().scaled(40, 40, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    rs = gs = bs = n = 0
    for y in range(img.height()):
        for x in range(img.width()):
            c = img.pixelColor(x, y)
            if c.lightness() > 225 or c.saturation() < 18 and c.lightness() > 190:
                continue
            rs += c.red(); gs += c.green(); bs += c.blue(); n += 1
    if not n:
        return QColor("#5b8fd6")
    col = QColor(rs // n, gs // n, bs // n)
    h, s, l, _ = col.getHsl()
    return QColor.fromHsl(h, min(255, max(60, s + 40)), min(150, max(90, l)))


def load_pixmap(path: str, max_side: int = 900) -> QPixmap:
    r = QImageReader(path)
    r.setAutoTransform(True)
    sz = r.size()
    if sz.isValid() and max(sz.width(), sz.height()) > max_side:
        r.setScaledSize(sz.scaled(max_side, max_side, Qt.KeepAspectRatio))
    img = r.read()
    return QPixmap.fromImage(img) if not img.isNull() else QPixmap()


# =========================================================================== banner

class Banner(QWidget):
    clicked = Signal(object)   # Asset

    def __init__(self, images=None):
        super().__init__()
        self.images = images            # BannerImages (degradê que respeita o objeto), calculado em 2º plano
        if images is not None:
            images.changed.connect(self.update)
        self.setMinimumHeight(400)
        self.setMaximumHeight(400)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMouseTracking(True)
        self.setCursor(Qt.PointingHandCursor)
        self.slides: list[tuple[Asset, str, str]] = []   # (item, selo, texto)
        self.index = 0
        self.prev_index = -1
        self.t = 1.0
        self.hover = False
        self.cache: dict[str, tuple[QPixmap, QPixmap]] = {}
        self.anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=550)
        self.anim.setEasingCurve(QEasingCurve.InOutCubic)
        self.anim.valueChanged.connect(self._tick)
        self.timer = QTimer(self, interval=6000)
        self.timer.timeout.connect(self.next)
        self.timer.start()

    def set_slides(self, slides):
        keys = [s[0].key for s in slides]
        if keys == [s[0].key for s in self.slides]:
            return
        self.slides = slides
        self.index = 0
        self.prev_index = -1
        self.t = 1.0
        self.update()

    def _images(self, a: Asset):
        """(imagem com bordas fundidas, cor de fundo). Enquanto calcula, usa a prévia simples."""
        if not a.preview:
            return QImage(), QColor("#1b1612")
        if self.images is not None:
            got = self.images.get(a.preview)
            if got is not None and not got[0].isNull():
                return got
        if a.preview not in self.cache:
            pix = load_pixmap(a.preview, 820)
            self.cache[a.preview] = (pix.toImage(), edge_color(pix))
            if len(self.cache) > 20:
                self.cache.pop(next(iter(self.cache)))
        return self.cache[a.preview]

    def _is_light(self, i: int) -> bool:
        if not self.slides:
            return False
        return self._images(self.slides[i][0])[1].lightness() > 150

    def _tick(self, v):
        self.t = float(v)
        self.update()

    def go(self, i):
        if not self.slides:
            return
        self.prev_index = self.index
        self.index = i % len(self.slides)
        self.anim.stop()
        self.anim.start()
        self.timer.start()

    def next(self):
        if len(self.slides) > 1 and not self.hover:
            self.go(self.index + 1)

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def _arrow_rects(self):
        r = self.rect()
        y = r.bottom() - 52
        return QRect(r.right() - 100, y, 38, 38), QRect(r.right() - 54, y, 38, 38)

    def _dot_rects(self):
        out = []
        x = 56
        y = self.height() - 36
        for i in range(len(self.slides)):
            w = 22 if i == self.index else 8
            out.append(QRect(x, y, w, 8))
            x += w + 6
        return out

    def mousePressEvent(self, e):
        if not self.slides:
            return
        left, right = self._arrow_rects()
        pos = e.position().toPoint()
        if left.contains(pos):
            self.go(self.index - 1)
            return
        if right.contains(pos):
            self.go(self.index + 1)
            return
        for i, d in enumerate(self._dot_rects()):
            if d.adjusted(-3, -6, 3, 6).contains(pos):
                self.go(i)
                return
        self.clicked.emit(self.slides[self.index][0])

    def _draw_slide(self, p: QPainter, i: int, opacity: float):
        a, tag, sub = self.slides[i]
        r = QRectF(self.rect())
        img, bg = self._images(a)
        light = bg.lightness() > 150
        p.setOpacity(opacity)
        p.fillRect(r, bg)                     # fundo = cor dominante da prévia

        # prévia afastada da borda direita (as bordas já vêm fundidas ao fundo, sem cobrir o objeto)
        img_left = r.right()
        if not img.isNull():
            h = r.height()
            w = img.width() * h / img.height()
            maxw = r.width() * 0.52
            if w > maxw:
                w = maxw
                h = img.height() * w / img.width()
            right = r.right() - r.width() * 0.10
            left = max(r.width() * 0.36, right - w)
            w = right - left
            h = img.height() * w / img.width()
            tgt = QRectF(left, r.center().y() - h / 2, w, h)
            p.drawImage(tgt, img, QRectF(img.rect()))
            img_left = tgt.left()

        title_c = QColor("#1c1712") if light else theme.TEXT
        sub_c = QColor("#4e463d") if light else QColor("#cdbfad")
        meta_c = QColor("#7a7066") if light else theme.MUTED
        x = 56
        text_w = max(r.width() * 0.30, img_left - x - 24)

        # título: diminui a fonte até caber; se ainda não couber, quebra em até 3 linhas
        title = a.name
        head, _, last = title.rpartition(" ")
        if head and len(last) <= 4:                     # não deixa o número sozinho na 2ª linha
            title = head + "\u00a0" + last
        flags = Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap
        f2 = theme.ui_font(34)
        for size in (34, 31, 28, 26, 24, 22):
            f2 = theme.ui_font(size)
            fm2 = QFontMetrics(f2)
            if fm2.horizontalAdvance(title) <= text_w:
                break
            br = fm2.boundingRect(QRect(0, 0, int(text_w), 10000), flags, title)
            if size <= 28 and br.height() <= fm2.lineSpacing() * 2 + 2:
                break
        fm2 = QFontMetrics(f2)
        title_h = min(fm2.boundingRect(QRect(0, 0, int(text_w), 10000), flags, title).height(),
                      fm2.lineSpacing() * 3)

        pill_h, gap1, gap2, cat_h, sub_h = 24, 18, 12, 24, 22
        block = pill_h + gap1 + title_h + gap2 + cat_h + 2 + sub_h
        y = max(36, (r.height() - block) / 2 - 6)

        f = theme.ui_font(8.8, 700)
        p.setFont(f)
        fm = QFontMetrics(f)
        pill = QRectF(x, y, fm.horizontalAdvance(tag) + 24, pill_h)
        pp = QPainterPath()
        pp.addRoundedRect(pill, 12, 12)
        p.fillPath(pp, QColor(42, 23, 13, 222) if light else QColor(255, 236, 210, 40))
        p.setPen(QColor("#fff6e8"))
        p.drawText(pill, Qt.AlignCenter, tag)
        y += pill_h + gap1

        p.setFont(f2)
        p.setPen(title_c)
        p.drawText(QRectF(x, y, text_w, title_h), flags, title)
        y += title_h + gap2

        f3 = theme.ui_font(12)
        p.setFont(f3)
        p.setPen(sub_c)
        fm3 = QFontMetrics(f3)
        from .main_window import pretty_category
        p.drawText(QRectF(x, y, text_w, cat_h), Qt.AlignLeft | Qt.AlignVCenter,
                   fm3.elidedText(pretty_category(a.category), Qt.ElideMiddle, int(text_w)))
        y += cat_h + 2
        p.setFont(theme.ui_font(10.5))
        p.setPen(meta_c)
        p.drawText(QRectF(x, y, text_w, sub_h), Qt.AlignLeft | Qt.AlignVCenter, sub)
        p.setOpacity(1.0)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(self.rect()), 16, 16)
        p.setClipPath(clip)
        if not self.slides:
            theme.paint_glass(p, QRectF(self.rect()), 16)
            p.setPen(theme.MUTED)
            p.setFont(theme.ui_font(12))
            p.drawText(self.rect(), Qt.AlignCenter,
                       "As novidades aparecem aqui.\nClassifique downloads na aba Entrada para vê-los no destaque.")
            return
        if self.prev_index >= 0 and self.t < 1.0:
            self._draw_slide(p, self.prev_index, 1.0)
            self._draw_slide(p, self.index, self.t)
        else:
            self._draw_slide(p, self.index, 1.0)

        # pontos
        for i, d in enumerate(self._dot_rects()):
            path = QPainterPath()
            path.addRoundedRect(QRectF(d), 4, 4)
            if self._is_light(self.index):
                p.fillPath(path, QColor("#2a1d16") if i == self.index else QColor(40, 24, 16, 55))
            else:
                p.fillPath(path, theme.TEXT if i == self.index else QColor(255, 236, 210, 80))
        # setas (só com o mouse em cima)
        if self.hover and len(self.slides) > 1:
            for rr, left in zip(self._arrow_rects(), (True, False)):
                rf = QRectF(rr)
                p.setPen(QPen(QColor(255, 255, 255, 50), 1))
                p.setBrush(QColor(34, 24, 18, 200))
                p.drawEllipse(rf)
                pen = QPen(QColor("#f0f2f4"), 2.2)
                pen.setCapStyle(Qt.RoundCap)
                pen.setJoinStyle(Qt.RoundJoin)
                p.setPen(pen)
                p.setBrush(Qt.NoBrush)
                c = rf.center()
                d = 1 if left else -1
                ch = QPainterPath()
                ch.moveTo(c.x() + 3 * d, c.y() - 7)
                ch.lineTo(c.x() - 4 * d, c.y())
                ch.lineTo(c.x() + 3 * d, c.y() + 7)
                p.drawPath(ch)


# =========================================================================== cartão de número

class StatCard(ui.Glass):
    clicked = Signal()

    def __init__(self, label: str, color: str, hint: str):
        super().__init__(12, 1.0)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip(hint)
        self.color = QColor(color)
        self.label = label
        self.value = "–"

    def set_value(self, n: int):
        self.value = f"{n:,}".replace(",", ".")
        self.update()

    def enterEvent(self, e):
        self.hover = True
        self.update()

    def leaveEvent(self, e):
        self.hover = False
        self.update()

    def mousePressEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(20, 0, -12, 0)
        f = theme.ui_font(19)
        fm = QFontMetrics(f)
        f2 = theme.ui_font(9.5)
        fm2 = QFontMetrics(f2)
        total = fm.height() + 2 + fm2.height()
        y = r.center().y() - total / 2
        p.setFont(f)
        p.setPen(theme.TEXT)
        p.drawText(QRectF(r.left(), y, r.width(), fm.height()), Qt.AlignLeft | Qt.AlignVCenter, self.value)
        y += fm.height() + 2
        p.setPen(Qt.NoPen)
        p.setBrush(self.color)
        p.drawEllipse(QRectF(r.left(), y + fm2.height() / 2 - 3, 6, 6))
        p.setFont(f2)
        p.setPen(theme.MUTED)
        p.drawText(QRectF(r.left() + 13, y, r.width() - 13, fm2.height()), Qt.AlignLeft | Qt.AlignVCenter, self.label)


# =========================================================================== faixa com rolagem elegante

PAGE_BG = QColor("#17130f")
CARD_BG = QColor("#211a15")


class _Fade(QWidget):
    """Esmaecimento na borda da faixa (indica que há mais itens para o lado)."""
    def __init__(self, parent, left: bool):
        super().__init__(parent)
        self.left = left
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def paintEvent(self, e):
        p = QPainter(self)
        g = QLinearGradient(QPointF(0, 0), QPointF(self.width(), 0))
        a = QColor(PAGE_BG); a.setAlpha(255)
        b = QColor(PAGE_BG); b.setAlpha(0)
        g.setColorAt(0.0, a if self.left else b)
        g.setColorAt(1.0, b if self.left else a)
        p.fillRect(self.rect(), g)


class _Arrow(QWidget):
    clicked = Signal()

    def __init__(self, parent, left: bool):
        super().__init__(parent)
        self.left = left
        self.hover = False
        self.setFixedSize(40, 40)
        self.setCursor(Qt.PointingHandCursor)

    def enterEvent(self, e):
        self.hover = True; self.update()

    def leaveEvent(self, e):
        self.hover = False; self.update()

    def mousePressEvent(self, e):
        self.clicked.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        p.setPen(QPen(QColor(255, 255, 255, 40), 1))
        p.setBrush(QColor(48, 52, 58, 245) if self.hover else QColor(30, 33, 37, 225))
        p.drawEllipse(r)
        pen = QPen(QColor("#f0f2f4") if self.hover else QColor("#c3c8ce"), 2.2)
        pen.setCapStyle(Qt.RoundCap); pen.setJoinStyle(Qt.RoundJoin)
        p.setPen(pen)
        c = r.center()
        d = 1 if self.left else -1
        path = QPainterPath()
        path.moveTo(c.x() + 3 * d, c.y() - 7)
        path.lineTo(c.x() - 4 * d, c.y())
        path.lineTo(c.x() + 3 * d, c.y() + 7)
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)


class HStrip(QWidget):
    """Envolve uma lista horizontal: sem barra de rolagem; setas redondas e bordas esmaecidas
    aparecem com o mouse em cima; a roda do mouse também rola para o lado, suavemente."""

    def __init__(self, view):
        super().__init__()
        self.view = view
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addWidget(view)
        view.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        view.setStyleSheet("QListView{background:transparent; border:none;}")
        self.bar = view.horizontalScrollBar()
        self.fades = (_Fade(self, True), _Fade(self, False))
        self.arrows = (_Arrow(self, True), _Arrow(self, False))
        self.arrows[0].clicked.connect(lambda: self.step(-1))
        self.arrows[1].clicked.connect(lambda: self.step(1))
        self.anim = QVariantAnimation(self, duration=420)
        self.anim.setEasingCurve(QEasingCurve.OutCubic)
        self.anim.valueChanged.connect(lambda v: self.bar.setValue(int(v)))
        self.target = 0
        self.hover = False
        self.bar.valueChanged.connect(self._sync)
        self.bar.rangeChanged.connect(self._sync)
        view.viewport().installEventFilter(self)
        self._sync()

    def scroll_to(self, v):
        v = max(self.bar.minimum(), min(self.bar.maximum(), int(v)))
        self.target = v
        self.anim.stop()
        self.anim.setStartValue(self.bar.value())
        self.anim.setEndValue(v)
        self.anim.start()

    def step(self, d):
        base = self.target if self.anim.state() == QVariantAnimation.Running else self.bar.value()
        self.scroll_to(base + d * max(200, int(self.view.viewport().width() * 0.8)))

    def eventFilter(self, obj, e):
        """A roda do mouse continua descendo a página. Só o gesto lateral (touchpad) ou Shift + roda
        passa os itens para o lado."""
        if e.type() == QEvent.Wheel and self.bar.maximum() > 0:
            dx = e.angleDelta().x()
            if not dx and e.modifiers() & Qt.ShiftModifier:
                dx = e.angleDelta().y()
            if dx:
                base = self.target if self.anim.state() == QVariantAnimation.Running else self.bar.value()
                self.scroll_to(base - dx * 1.6)
                return True
        if e.type() == QEvent.Wheel:
            # repassa a roda vertical para a página (senão a lista horizontal 'rouba' o scroll)
            from PySide6.QtWidgets import QApplication, QScrollArea
            p = self.parentWidget()
            while p is not None and not isinstance(p, QScrollArea):
                p = p.parentWidget()
            if p is not None:
                QApplication.sendEvent(p.viewport(), e)
            return True
        return False

    def enterEvent(self, e):
        self.hover = True; self._sync()

    def leaveEvent(self, e):
        self.hover = False; self._sync()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        h = self.height()
        self.fades[0].setGeometry(0, 0, 70, h)
        self.fades[1].setGeometry(self.width() - 70, 0, 70, h)
        y = (h - 40) // 2 - 10
        self.arrows[0].move(10, y)
        self.arrows[1].move(self.width() - 50, y)
        self._sync()

    def _sync(self, *a):
        can_l = self.bar.value() > self.bar.minimum()
        can_r = self.bar.value() < self.bar.maximum()
        self.fades[0].setVisible(False)       # o fundo agora é um degradê: as setas bastam
        self.fades[1].setVisible(False)
        self.arrows[0].setVisible(can_l and self.hover)
        self.arrows[1].setVisible(can_r and self.hover)
        for wdg in (*self.fades, *self.arrows):
            wdg.raise_()


# =========================================================================== cartão de tag

class TagCardDelegate(QStyledItemDelegate):
    """Cartão único: prévia no alto, na cor do próprio fundo, descendo em degradê até o cartão,
    com o nome da tag e a quantidade de itens embaixo."""
    W, H = 210, 250

    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.bg_cache: dict[str, QColor] = {}

    def sizeHint(self, option, index):
        return QSize(self.W, self.H)

    def paint(self, p: QPainter, option, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(option.rect).adjusted(7, 7, -7, -7)
        hover = bool(option.state & QStyle.State_MouseOver)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.setClipPath(path)
        card = QColor("#29211b") if hover else CARD_BG
        p.fillRect(r, card)

        cover = index.data(Qt.UserRole + 1)
        pix = self.page.w.thumbs.get(cover) if cover else None
        img_h = r.height() * 0.80
        if pix and not pix.isNull():
            if cover not in self.bg_cache:
                self.bg_cache[cover] = edge_color(pix)
            bg = self.bg_cache[cover]
            p.fillRect(QRectF(r.left(), r.top(), r.width(), img_h), bg)
            area = QRectF(r.left() + 12, r.top() + 10, r.width() - 24, img_h - 40)
            sz = QSizeF(pix.size()).scaled(area.size(), Qt.KeepAspectRatio)
            if hover:
                sz *= 1.04
            tgt = QRectF(area.center().x() - sz.width() / 2, area.center().y() - sz.height() / 2,
                         sz.width(), sz.height())
            p.drawPixmap(tgt, pix, QRectF(pix.rect()))
        # degradê: a prévia vai se mesclando ao cartão de cima para baixo
        g = QLinearGradient(QPointF(0, r.top() + r.height() * 0.42), QPointF(0, r.top() + r.height() * 0.80))
        for k in range(9):                       # curva suave (sem "faixa" visível no início do degradê)
            t = k / 8
            c = QColor(card)
            c.setAlpha(int(255 * t * t * (3 - 2 * t)))
            g.setColorAt(t, c)
        p.fillRect(QRectF(r.left(), r.top(), r.width(), img_h + 1), g)

        # textos
        tag = index.data(Qt.UserRole) or ""
        n = index.data(Qt.UserRole + 2) or 0
        x = r.left() + 16
        f = QFont(option.font)
        f.setPointSizeF(12.5)
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        p.setPen(theme.TEXT)
        p.drawText(QRectF(x, r.bottom() - 62, r.width() - 32, fm.height() + 4), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(tag[:1].upper() + tag[1:], Qt.ElideRight, int(r.width() - 32)))
        f2 = QFont(option.font)
        f2.setPointSizeF(9.5)
        p.setFont(f2)
        p.setPen(theme.MUTED)
        p.drawText(QRectF(x, r.bottom() - 34, r.width() - 32, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   f"{n} {'item' if n == 1 else 'itens'}")
        p.setClipping(False)
        if hover:
            p.setPen(QPen(QColor(227, 207, 169, 150), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(r.adjusted(0.75, 0.75, -0.75, -0.75), 14, 14)
        p.restore()


# =========================================================================== página

class HomePage(QWidget):
    def __init__(self, window):
        super().__init__()
        from .main_window import AssetModel, AssetView, CardDelegate   # evita import circular
        self.w = window
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        lay = QVBoxLayout(body)
        lay.setContentsMargins(40, TITLE_H + 8, 40, 32)
        lay.setSpacing(22)

        head = QVBoxLayout()
        head.setSpacing(4)
        self.hello = QLabel()
        self.hello.setStyleSheet("font-size:21pt;")
        self.hello_sub = QLabel()
        self.hello_sub.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:10.5pt;")
        head.addWidget(self.hello)
        head.addWidget(self.hello_sub)
        lay.addLayout(head)

        from .banner_img import BannerImages
        self.banner_images = BannerImages(self.w.cache_root)
        self.banner = Banner(self.banner_images)
        self.banner.clicked.connect(lambda a: self.w.show_item(a.key))
        top = QHBoxLayout()
        top.setSpacing(24)
        top.addWidget(self.banner, 7)

        # números
        grid = QGridLayout()
        grid.setSpacing(14)
        self.cards = {}
        specs = [
            ("total", "itens na biblioteca", theme.HILITE.name(), "Abrir a biblioteca", lambda: self.w.open_library("all")),
            ("ready", "prontos para usar", theme.OK.name(), "Ver só os prontos para arrastar", lambda: self.w.open_library("ready")),
            ("archive", "compactados", theme.WARN.name(), "Ver os que precisam ser extraídos", lambda: self.w.open_library("archive")),
            ("layout", "fora do padrão", theme.ORG.name(), "Ver as pastas para organizar", lambda: self.w.open_library("layout")),
            ("entrada", "na Entrada", theme.BUSY.name(), "Abrir a Entrada", lambda: self.w.tabs.setCurrentWidget(self.w.entrada)),
            ("tags", "tags criadas", "#c98fa5", "Abrir as tags", lambda: self.w.tabs.setCurrentWidget(self.w.tags_page)),
        ]
        for i, (key, label, color, hint, fn) in enumerate(specs):
            c = StatCard(label, color, hint)
            c.clicked.connect(fn)
            self.cards[key] = c
            grid.addWidget(c, i // 2, i % 2)
        grid.setContentsMargins(0, 0, 0, 0)
        for r in range(3):
            grid.setRowStretch(r, 1)

        side = QWidget()
        side.setFixedHeight(400)
        col = QVBoxLayout(side)
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(14)
        col.addWidget(self._build_search())
        col.addLayout(grid, 1)
        top.addWidget(side, 3)
        lay.addLayout(top)

        # faixas
        def section(title, link=None, fn=None):
            row = QHBoxLayout()
            h = QLabel(title)
            h.setStyleSheet("font-size:12.5pt; padding-top:8px;")
            row.addWidget(h)
            row.addStretch(1)
            if link:
                b = ui.link_button(link)
                b.clicked.connect(fn)
                row.addWidget(b, 0, Qt.AlignBottom)
            lay.addLayout(row)

        def strip(title):
            section(title, "Ver todos", lambda: self.w.open_library("all"))
            model = AssetModel(self.w.db)
            view = AssetView(self.w)
            view.setModel(model)
            view.setItemDelegate(CardDelegate(self.w, fixed_size=160))
            view.setFlow(QListView.LeftToRight)
            view.setWrapping(False)
            view.setFixedHeight(160 + 64 + 6)
            view.setHorizontalScrollMode(QAbstractItemView.ScrollPerPixel)
            view.setSelectionMode(QAbstractItemView.SingleSelection)
            view.doubleClicked.connect(lambda idx: self.w.show_item(idx.data(Qt.UserRole + 1).key))
            view.setToolTip("Duplo clique abre na biblioteca · arraste direto para o 3ds Max")
            empty = QLabel()
            empty.setStyleSheet(f"color:{theme.MUTED.name()};")
            lay.addWidget(HStrip(view))
            lay.addWidget(empty)
            return model, view, empty

        self.added_model, self.added_view, self.added_empty = strip("Adicionados recentemente")

        section("Tags mais usadas", "Ver todas as tags", lambda: self.w.tabs.setCurrentWidget(self.w.tags_page))
        self.cats = QListWidget()
        self.cats.setViewMode(QListView.IconMode)
        self.cats.setGridSize(QSize(TagCardDelegate.W, TagCardDelegate.H))
        self.cats.setItemDelegate(TagCardDelegate(self))
        self.cats.setResizeMode(QListView.Adjust)
        self.cats.setMovement(QListView.Static)
        self.cats.setMouseTracking(True)
        self.cats.setSelectionMode(QAbstractItemView.NoSelection)
        self.cats.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cats.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.cats.setStyleSheet("QListWidget{background:transparent; border:none;}")
        self.cats.viewport().setCursor(Qt.PointingHandCursor)
        self.cats.itemClicked.connect(lambda it: self.w.tags_page.open_tag(it.data(Qt.UserRole)))
        self.cats.setToolTip("Clique para abrir a galeria da tag")
        self.tags_empty = QLabel("Adicione tags aos itens na Biblioteca (painel da direita) e as mais usadas aparecem aqui.")
        self.tags_empty.setStyleSheet(f"color:{theme.MUTED.name()};")
        lay.addWidget(self.tags_empty)
        lay.addWidget(self.cats)
        lay.addStretch(1)

        self.w.thumbs.changed.connect(self._thumbs_ready)
        self._cover_paths: dict[str, str] = {}

    # ----------------------------------------------------------------- busca
    def _build_search(self) -> QWidget:
        box = ui.SearchField("Buscar na biblioteca", button="Buscar", height=58)
        self.search = box.edit
        self.search.setToolTip("Nome, categoria ou tag (sem precisar de acento). Enter abre a Biblioteca.")
        box.submitted.connect(lambda _t: self._do_search())
        self._completer_model = QStringListModel(self)
        comp = QCompleter(self._completer_model, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        comp.activated.connect(lambda _t: QTimer.singleShot(0, self._do_search))
        self.search.setCompleter(comp)
        return box

    def _do_search(self):
        text = self.search.text().strip()
        self.w.open_library("all", text=text)
        self.search.clear()

    # ----------------------------------------------------------------- dados
    def refresh(self):
        w = self.w
        by_key = {a.key: a for a in w.all_assets}
        mtimes: dict[str, float] = {}

        def mt(a):
            if not a.preview:
                return 0.0
            if a.preview not in mtimes:
                try:
                    mtimes[a.preview] = os.path.getmtime(a.preview)
                except OSError:
                    mtimes[a.preview] = 0.0
            return mtimes[a.preview]
        hour = datetime.now().hour
        greet = "Bom dia" if hour < 12 else ("Boa tarde" if hour < 18 else "Boa noite")
        user = os.environ.get("USERNAME") or os.environ.get("USER") or ""
        self.hello.setText(f"{greet}{', ' + user if user else ''}")

        # novidades: o que entrou pela Entrada; se ainda não houver, os arquivos mais novos da biblioteca
        adds = [(by_key[k], t) for k, t, _ in w.db.recent_additions(40) if k in by_key]
        if adds:
            slides = [(a, "Novidade", f"adicionado {when_text(t)}") for a, t in adds[:8] if a.preview]
            recent = [a for a, _ in adds[:30]]
            n_week = sum(1 for _, t in adds if time.time() - t < 7 * 86400)
            self.hello_sub.setText(f"{n_week} item(ns) novo(s) nos últimos 7 dias." if n_week
                                   else "Nenhum item novo nesta semana.")
        else:
            newest = sorted((a for a in w.all_assets if a.preview), key=mt, reverse=True)[:30]
            slides = [(a, "Recente na biblioteca", f"arquivo de {when_text(mt(a))}") for a in newest[:8]]
            recent = newest
            self.hello_sub.setText("Os itens classificados pela aba Entrada vão aparecer em destaque aqui.")
        self.banner.set_slides(slides)
        self.added_model.set_assets(recent)
        self.added_empty.setVisible(not recent)
        self.added_empty.setText("Nada por aqui ainda.")


        # números
        allx = w.all_assets
        self.cards["total"].set_value(len(allx))
        self.cards["ready"].set_value(sum(1 for a in allx if a.kind in ("folder", "max")))
        self.cards["archive"].set_value(sum(1 for a in allx if a.kind == "archive"))
        self.cards["layout"].set_value(sum(1 for a in allx if w.layout_issues(a)))
        self.cards["entrada"].set_value(len(w.entrada.items))
        self.cards["tags"].set_value(len(w.db.all_tags()))

        # sugestões da busca: tags e nomes de categorias
        cats = {seg for a in allx for seg in a.category.split("/") if seg}
        self._completer_model.setStringList(sorted({t for t, _ in w.db.all_tags()} | cats, key=str.lower))

        # tags mais usadas, com capa (prévia mais recente entre os itens da tag)
        self.cats.clear()
        self._cover_paths.clear()
        tagged: dict[str, list] = {}
        for a in allx:
            for t in w.db.tags_of(a.key):
                tagged.setdefault(t, []).append(a)
        top_tags = sorted(tagged.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:18]
        for tag, items in top_tags:
            cover, best = None, -1.0
            for a in items:
                t = mt(a)
                if a.preview and t > best:
                    best, cover = t, a.preview
            it = QListWidgetItem()
            it.setData(Qt.UserRole, tag)
            it.setData(Qt.UserRole + 1, cover)
            it.setData(Qt.UserRole + 2, len(items))
            it.setToolTip(f"{tag} — {len(items)} {'item' if len(items) == 1 else 'itens'}")
            if cover:
                self._cover_paths[tag] = cover
                w.thumbs.get(cover)          # pede a miniatura
            self.cats.addItem(it)
        self.cats.setVisible(bool(top_tags))
        self.tags_empty.setVisible(not top_tags)
        self._fit_cats()

    def _fit_cats(self):
        if not self.cats.count():
            return
        per_row = max(1, self.cats.viewport().width() // TagCardDelegate.W)
        rows = (self.cats.count() + per_row - 1) // per_row
        self.cats.setFixedHeight(rows * TagCardDelegate.H + 8)

    def _thumbs_ready(self):
        if not self.isVisible():
            return
        self.cats.viewport().update()
        self.added_view.viewport().update()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        QTimer.singleShot(0, self._fit_cats)
