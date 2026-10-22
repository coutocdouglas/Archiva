"""Janela principal."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path

from PySide6.QtCore import (QAbstractListModel, QByteArray, QModelIndex, QMimeData, QPoint, QPointF, QRect, QRectF,
                            QSize, QSizeF, Qt,
                            QTimer, QUrl, Signal, QStringListModel)
from PySide6.QtGui import (QAction, QBrush, QColor, QDesktopServices, QDrag, QFont, QFontMetrics, QIcon, QPainter,
                           QPainterPath, QPen, QPixmap, QKeySequence)
from PySide6.QtWidgets import (QTreeWidgetItemIterator, QAbstractItemView, QApplication, QCheckBox, QComboBox, QCompleter, QDialog, QInputDialog,
                               QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit,
                               QListView, QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox,
                               QProgressBar, QPushButton, QSlider, QSplitter, QStyle, QStyledItemDelegate, QTabWidget,
                               QToolBar, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget, QSizePolicy, QStackedWidget,
                               QStatusBar)

from . import extractor, intake
from .config import APP_NAME, Config, app_dir, is_installed, version
from . import atualizador, perfil, rede
from .compartilhado import OP_NAMES, Compartilhado
from . import indice
from . import tutoriais
from .database import TagDB, clean_tag
from . import scanner as scanner_mod
from .scanner import Asset, Category, normalize, scan_category
from . import theme, ui
from .janela import TITLE_H, CaptionButtons, FramelessMixin
from .workers import ExtractionManager, ScanThread, ThumbnailCache

ASSET_ROLE = Qt.UserRole + 1
ALL_KEY = "__todas__"

COL_READY = QColor("#4caf50")
COL_ARCHIVE = QColor("#e0a030")
COL_BUSY = QColor("#3d8bfd")
COL_MISSING = QColor("#e05252")


# =========================================================================== modelo da grade

class AssetModel(QAbstractListModel):
    def __init__(self, db: TagDB):
        super().__init__()
        self.db = db
        self.assets: list[Asset] = []
        self.row_of: dict[str, int] = {}

    def set_assets(self, assets: list[Asset]):
        self.beginResetModel()
        self.assets = assets
        self.row_of = {a.key: i for i, a in enumerate(assets)}
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.assets)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        a = self.assets[index.row()]
        if role == Qt.DisplayRole:
            return a.name
        if role == ASSET_ROLE:
            return a
        if role == Qt.ToolTipRole:
            tags = ", ".join(sorted(self.db.tags_of(a.key))) or "—"
            tip = f"<b>{a.name}</b><br>{a.category}<br>Tags: {tags}"
            if a.issues:
                tip += "<br><span style='color:#e05252'>" + "<br>".join(a.issues) + "</span>"
            return tip
        return None

    def flags(self, index):
        f = super().flags(index)
        return f | Qt.ItemIsDragEnabled if index.isValid() else f

    def refresh_key(self, key: str):
        r = self.row_of.get(key)
        if r is not None:
            idx = self.index(r)
            self.dataChanged.emit(idx, idx)


# =========================================================================== desenho dos cartões

class CardDelegate(QStyledItemDelegate):
    """Cartão da grade: prévia com cantos arredondados sobre a cor do próprio fundo, nome e situação embaixo."""

    def __init__(self, window: "MainWindow", fixed_size: int | None = None):
        super().__init__(window)
        self.w = window
        self.fixed_size = fixed_size
        self._bg: dict[str, QColor] = {}

    def card_size(self) -> int:
        return self.fixed_size or self.w.thumb_size

    def sizeHint(self, option, index):
        s = self.card_size()
        return QSize(s + 20, s + 64)

    def status_for(self, a: Asset):
        busy = self.w.extractions.is_running(a)
        queued = self.w.extractions.is_queued(a)
        if a.kind == "missing":
            return theme.BAD, "!", busy, queued
        if busy or queued:
            return theme.BUSY, "…", busy, queued
        if self.w.extractions.is_ready(a):
            return theme.OK, ("organizar" if self.w.layout_issues(a) else ""), busy, queued
        return theme.WARN, "extrair", busy, queued

    def subtitle_for(self, a: Asset, busy: bool, queued: bool) -> str:
        if busy:
            return "extraindo…"
        if queued:
            return "na fila"
        if a.kind == "missing":
            return "sem arquivo do modelo"
        if self.w.extractions.is_ready(a):
            return "pronto"
        return "compactado"

    def bg_of(self, path: str, pix: QPixmap) -> QColor:
        c = self._bg.get(path)
        if c is None:
            from .home_page import edge_color
            c = self._bg[path] = edge_color(pix)
        return c

    def paint(self, p: QPainter, option, index):
        a: Asset = index.data(ASSET_ROLE)
        s = self.card_size()
        r = QRectF(option.rect).adjusted(10, 8, -10, -8)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        selected = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)

        img = QRectF(r.left(), r.top(), r.width(), s)
        path = QPainterPath()
        path.addRoundedRect(img, 12, 12)
        pix = self.w.thumbs.get(a.preview)
        p.save()
        p.setClipPath(path)
        if pix:
            p.fillRect(img, self.bg_of(a.preview, pix))
            sc = QSizeF(pix.size()).scaled(img.size(), Qt.KeepAspectRatio)
            tgt = QRectF(img.center().x() - sc.width() / 2, img.center().y() - sc.height() / 2, sc.width(), sc.height())
            p.drawPixmap(tgt, pix, QRectF(pix.rect()))
        else:
            p.fillRect(img, QColor(255, 236, 210, 12))
            p.setPen(theme.FAINT)
            p.setFont(theme.ui_font(9))
            p.drawText(img, Qt.AlignCenter, "sem prévia" if not a.preview else "…")
        p.restore()
        if selected:
            theme.paint_selection(p, img, 12)
        elif hover:
            p.setPen(QPen(QColor(227, 207, 169, 110), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(img.adjusted(0.6, 0.6, -0.6, -0.6), 12, 12)

        # situação: bolinha + selo
        col, label, busy, queued = self.status_for(a)
        dot = QRectF(img.right() - 19, img.top() + 9, 10, 10)
        p.setPen(QPen(QColor(255, 255, 255, 215), 1.6))
        p.setBrush(col)
        p.drawEllipse(dot)
        if label and label not in ("!", "…", "extrair"):
            f = theme.ui_font(7.5, 700)
            p.setFont(f)
            tw = QFontMetrics(f).horizontalAdvance(label) + 14
            pill = QRectF(img.left() + 8, img.top() + 7, tw, 17)
            pp = QPainterPath()
            pp.addRoundedRect(pill, 8.5, 8.5)
            p.fillPath(pp, QColor(30, 20, 14, 205))
            p.setPen(QColor("#cdb7ff") if label == "organizar" else theme.LOGO)
            p.drawText(pill, Qt.AlignCenter, label)
        lock = self.w.shared.lock_of(a.key) if not (busy or queued) else None
        if busy or queued or lock:
            band = QRectF(img.left(), img.bottom() - 22, img.width(), 22)
            bp = QPainterPath()
            bp.addRoundedRect(band, 0, 0)
            p.save()
            p.setClipPath(path)
            p.fillRect(band, QColor(30, 20, 14, 200))
            p.restore()
            p.setPen(theme.TEXT)
            p.setFont(theme.ui_font(8.5))
            txt = (f"em uso · {lock.get('nome', '?')}" if lock else ("extraindo…" if busy else "na fila"))
            p.drawText(band, Qt.AlignCenter, QFontMetrics(p.font()).elidedText(txt, Qt.ElideRight, int(band.width() - 10)))

        # nome + situação
        ntags = len(self.w.db.tags_of(a.key)) if not a.key.startswith("_ENTRADA") else 0
        f = theme.ui_font(9.8)
        p.setFont(f)
        fm = QFontMetrics(f)
        name_w = int(r.width() - (26 if ntags else 2))
        p.setPen(theme.TEXT)
        p.drawText(QRectF(r.left() + 1, img.bottom() + 8, name_w, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(a.name, Qt.ElideRight, name_w))
        if ntags:
            p.setPen(theme.LINK)
            p.drawText(QRectF(r.left(), img.bottom() + 8, r.width(), fm.height()), Qt.AlignRight | Qt.AlignVCenter,
                       f"#{ntags}")
        f2 = theme.ui_font(8.8)
        p.setFont(f2)
        p.setPen(theme.MUTED)
        fm2 = QFontMetrics(f2)
        p.drawText(QRectF(r.left() + 1, img.bottom() + 9 + fm.height(), r.width(), fm2.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, fm2.elidedText(self.subtitle_for(a, busy, queued), Qt.ElideRight,
                                                                  int(r.width())))
        p.restore()


# =========================================================================== grade com arrastar

class AssetView(QListView):
    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.w = window
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setMouseTracking(True)
        self.setSpacing(2)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(30)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def startDrag(self, actions):
        idx = self.currentIndex()
        if not idx.isValid():
            return
        a: Asset = idx.data(ASSET_ROLE)
        path = self.w.drag_path_for(a)
        if not path:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path)])
        keys = [ix.data(ASSET_ROLE).key for ix in self.selectionModel().selectedIndexes()] or [a.key]
        mime.setData("application/x-archiva-itens", "\n".join(keys).encode("utf-8"))
        drag = QDrag(self)
        drag.setMimeData(mime)
        pix = self.w.thumbs.get(a.preview)
        if pix:
            drag.setPixmap(pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            drag.setHotSpot(QPoint(48, 48))
        drag.exec(Qt.CopyAction)


# =========================================================================== painel de detalhes

def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", ".")


def pretty(name: str) -> str:
    """'LUMINARIA PENDENTE' -> 'Luminaria pendente' (só na tela; as pastas não mudam)."""
    if not name:
        return name
    if name.isupper() or name.islower():
        name = name.lower()
        return name[:1].upper() + name[1:]
    return name


def pretty_category(cat: str) -> str:
    return "  ›  ".join(pretty(x) for x in cat.split("/"))


class PreviewBox(QWidget):
    """Prévia grande do painel: imagem inteira, cantos arredondados, sobre a cor do próprio fundo."""

    def __init__(self, window):
        super().__init__()
        self.w = window
        self.pix: QPixmap | None = None
        self.text = ""
        self.path: str | None = None
        self.title = ""
        self.setMinimumHeight(220)

    def set_source(self, path: str | None, title: str = ""):
        self.path, self.title = path, title
        self.setCursor(Qt.PointingHandCursor if path else Qt.ArrowCursor)
        self.setToolTip("Clique para ampliar" if path else "")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.path and os.path.exists(self.path):
            ImageViewer(self.window(), self.path, self.title).exec()

    def set_pixmap(self, pix: QPixmap | None, text: str = ""):
        self.pix, self.text = pix, text
        self.update()

    def heightForWidth(self, w):
        return w

    def sizeHint(self):
        return QSize(280, 280)

    def resizeEvent(self, e):
        self.setFixedHeight(max(200, min(340, self.width())))

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect())
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.setClipPath(path)
        if self.pix and not self.pix.isNull():
            from .home_page import edge_color
            p.fillRect(r, edge_color(self.pix))
            sc = QSizeF(self.pix.size()).scaled(r.size(), Qt.KeepAspectRatio)
            p.drawPixmap(QRectF(r.center().x() - sc.width() / 2, r.center().y() - sc.height() / 2, sc.width(), sc.height()),
                         self.pix, QRectF(self.pix.rect()))
        else:
            theme.paint_glass(p, r, 14)
            p.setPen(theme.FAINT)
            p.setFont(theme.ui_font(10))
            p.drawText(r, Qt.AlignCenter, self.text)


class ImageViewer(QDialog):
    """Prévia ampliada numa janela própria: imagem inteira em alta resolução. Clique, Esc ou espaço fecham."""

    def __init__(self, parent, path: str, title: str = ""):
        super().__init__(parent)
        self.setWindowTitle(title or os.path.basename(path))
        self.img = QPixmap(path)
        self.title = title
        scr = (parent.screen() if parent else QApplication.primaryScreen()).availableGeometry()
        maxw, maxh = int(scr.width() * 0.86), int(scr.height() * 0.86)
        if not self.img.isNull():
            sz = self.img.size()
            fit = sz.scaled(maxw - 48, maxh - 92, Qt.KeepAspectRatio)
            # imagem pequena: amplia até 2x (sem passar da tela); grande: reduz para caber
            sz = fit if fit.width() <= sz.width() * 2 else sz * 2
            w, h = max(520, sz.width() + 48), max(420, sz.height() + 92)
        else:
            w, h = 600, 400
        self.resize(w, h)
        self.setMinimumSize(360, 300)
        self.setCursor(Qt.PointingHandCursor)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#17130f"))
        area = QRectF(24, 24, self.width() - 48, self.height() - 92)
        if not self.img.isNull():
            sc = QSizeF(self.img.size()).scaled(area.size(), Qt.KeepAspectRatio)
            tgt = QRectF(area.center().x() - sc.width() / 2, area.center().y() - sc.height() / 2,
                         sc.width(), sc.height())
            path = QPainterPath()
            path.addRoundedRect(tgt, 14, 14)
            p.setClipPath(path)
            p.drawPixmap(tgt, self.img, QRectF(self.img.rect()))
            p.setClipping(False)
        else:
            p.setPen(theme.FAINT)
            p.drawText(area, Qt.AlignCenter, "Não foi possível abrir a imagem.")
        p.setPen(theme.TEXT)
        p.setFont(theme.ui_font(12))
        p.drawText(QRectF(28, self.height() - 60, self.width() - 56, 26), Qt.AlignLeft | Qt.AlignVCenter, self.title)
        p.setPen(theme.FAINT)
        p.setFont(theme.ui_font(9))
        info = f"{self.img.width()} × {self.img.height()} px   ·   clique ou Esc para fechar" if not self.img.isNull() \
            else "Esc para fechar"
        p.drawText(QRectF(28, self.height() - 36, self.width() - 56, 20), Qt.AlignLeft | Qt.AlignVCenter, info)

    def mouseReleaseEvent(self, e):
        self.accept()

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Space, Qt.Key_Return, Qt.Key_Enter):
            self.accept()
        else:
            super().keyPressEvent(e)


def variation_order(files: list[str]) -> list[str]:
    """Ordena as variações juntando cada 'X WIRE' logo depois de 'X' (CHAIR, CHAIR WIRE, OTTOMAN, …)."""
    import re as _re

    def key(f):
        stem = os.path.splitext(os.path.basename(f))[0]
        wire = bool(_re.search(r"[\s_\-]wire(?=[\s_\-]|$)", stem, _re.I))
        base = _re.sub(r"[\s_\-]wire(?=[\s_\-]|$)", "", stem, flags=_re.I)
        return (base.casefold(), wire, stem.casefold())
    return sorted(files, key=key)


class VariationList(QListWidget):
    """Arquivos .max do item com a miniatura de cada um (o .jpg com o mesmo nome, quando existe).
    Arrastar um deles leva aquela variação para o 3ds Max (com o mesmo script de texturas do cartão)."""
    ICON = 64

    def __init__(self, panel):
        super().__init__()
        self.panel = panel
        self.asset: Asset | None = None
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setIconSize(QSize(self.ICON, self.ICON))
        self.setToolTip("Arraste para o 3ds Max · duplo clique mostra no Explorer")
        self.setStyleSheet("QListWidget{color:#d8cfc2; background:transparent; border:none;}"
                           "QListWidget::item{padding:4px 2px; border-radius:8px;}"
                           "QListWidget::item:hover{background:rgba(255,230,200,0.08);}")

    def fill(self, a: Asset, thumbs):
        self.asset = a
        files = a.max_files if a.kind in ("folder", "max") else []
        main = extractor.primary_max(a)
        for f in variation_order(files):
            stem = os.path.splitext(f)[0]
            img = next((stem + e for e in (".jpg", ".jpeg", ".png", ".JPG", ".PNG") if os.path.exists(stem + e)),
                       None) if len(files) > 1 else None
            label = os.path.splitext(os.path.basename(f))[0] + ("   · principal" if f == main and len(files) > 1 else "")
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, f)
            it.setToolTip(f)
            pix = QPixmap(img) if img else None
            if pix is not None and not pix.isNull():
                it.setIcon(QIcon(pix.scaled(self.ICON, self.ICON, Qt.KeepAspectRatio, Qt.SmoothTransformation)))
            self.addItem(it)

    def fit(self):
        n = self.count()
        has_icons = any(not self.item(i).icon().isNull() for i in range(n))
        row = (self.ICON + 10) if has_icons else 26
        self.setFixedHeight(min(4 if has_icons else 6, max(n, 1)) * row + 6)

    def startDrag(self, actions):
        it = self.currentItem()
        if it is None or self.asset is None:
            return
        w = self.panel.w
        path = w.drag_path_for(self.asset, it.data(Qt.UserRole))
        if not path:
            return
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(path)])
        drag = QDrag(self)
        drag.setMimeData(mime)
        if not it.icon().isNull():
            drag.setPixmap(it.icon().pixmap(self.ICON, self.ICON))
        drag.exec(Qt.CopyAction)


class DetailsPanel(QWidget):
    tags_changed = Signal()

    def __init__(self, window: "MainWindow"):
        super().__init__()
        self.w = window
        self.assets: list[Asset] = []
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        self.preview = PreviewBox(window)
        lay.addWidget(self.preview)

        head = QVBoxLayout()
        head.setSpacing(2)
        self.title = QLabel()
        self.title.setStyleSheet("font-size:18pt;")
        self.title.setWordWrap(True)
        self.subtitle = QLabel()
        self.subtitle.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:10.5pt;")
        self.subtitle.setWordWrap(True)
        head.addWidget(self.title)
        head.addWidget(self.subtitle)
        lay.addLayout(head)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.RichText)
        for wdg in (self.title, self.subtitle, self.status):
            wdg.setTextInteractionFlags(Qt.TextSelectableByMouse)
        lay.addWidget(self.status)

        self.hint = QLabel("Arraste o cartão para a viewport do 3ds Max.")
        self.hint.setStyleSheet(f"color:{theme.MUTED.name()};")
        self.hint.setWordWrap(True)
        lay.addWidget(self.hint)

        self.btn_prepare = QPushButton("Extrair para a biblioteca")
        self.btn_prepare.clicked.connect(self._prepare)
        self.btn_organize = QPushButton("Organizar pasta")
        self.btn_organize.clicked.connect(lambda: self.w.request_organize(self.assets))
        self.btn_open = QPushButton("Abrir pasta")
        self.btn_open.clicked.connect(self._open)
        self.btn_compare = QPushButton("Comparar pasta e compactado…")
        self.btn_compare.setToolTip("O item existe como pasta e como compactado: compare e escolha o que fica.")
        self.btn_compare.clicked.connect(lambda: self.assets and self.w.compare_duplicate(self.assets[0]))
        for b in (self.btn_prepare, self.btn_organize, self.btn_compare, self.btn_open):
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumHeight(40)
            lay.addWidget(b)

        lay.addSpacing(6)
        lay.addWidget(ui.heading("Tags", 11.5))
        self.tag_list = QListWidget()
        self.tag_list.setFlow(QListView.LeftToRight)
        self.tag_list.setWrapping(True)
        self.tag_list.setResizeMode(QListView.Adjust)
        self.tag_list.setSpacing(4)
        self.tag_list.setMaximumHeight(110)
        self.tag_list.setToolTip("Clique numa tag para removê-la")
        self.tag_list.setStyleSheet(
            "QListWidget::item{background:rgba(255,230,200,0.07); border:1px solid rgba(255,230,200,0.10);"
            " border-radius:12px; padding:4px 10px; color:#f1e9dc;}"
            "QListWidget::item:hover{background:rgba(255,230,200,0.13);}"
            "QListWidget::item:selected{background:rgba(255,230,200,0.13); color:#fff6e8;}")
        self.tag_list.itemClicked.connect(self._remove_clicked)
        lay.addWidget(self.tag_list)

        self.tag_input = QLineEdit()
        self.tag_input.setPlaceholderText("Adicionar tag e Enter (várias: vírgula)")
        self.completer_model = QStringListModel()
        comp = QCompleter(self.completer_model, self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.tag_input.setCompleter(comp)
        self.tag_input.returnPressed.connect(self._add)
        lay.addWidget(self.tag_input)

        lay.addSpacing(6)
        lay.addWidget(ui.heading("Coleções", 11.5))
        self.col_info = QLabel()
        self.col_info.setWordWrap(True)
        self.col_info.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:9.5pt;")
        lay.addWidget(self.col_info)
        self.col_btn = QPushButton("Adicionar à coleção…")
        self.col_btn.setCursor(Qt.PointingHandCursor)
        self.col_menu = QMenu(self.col_btn)
        self.col_menu.aboutToShow.connect(
            lambda: self.w.colecoes.add_menu(self.col_menu, lambda: [a.key for a in self.assets]))
        self.col_btn.setMenu(self.col_menu)
        lay.addWidget(self.col_btn)

        self.files_head = ui.heading("Arquivos .max", 11.5)
        lay.addWidget(self.files_head)
        self.files_hint = QLabel("Arraste uma variação para a viewport do 3ds Max. O cartão leva a principal.")
        self.files_hint.setWordWrap(True)
        self.files_hint.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:9pt;")
        lay.addWidget(self.files_hint)
        self.files = VariationList(self)
        self.files.itemDoubleClicked.connect(lambda it: self.w.reveal(it.data(Qt.UserRole)))
        lay.addWidget(self.files)
        lay.addStretch(1)
        self.set_assets([])

    def _heading(self, t):
        return ui.heading(t, 11.5)

    def update_completer(self):
        self.completer_model.setStringList([t for t, _ in self.w.db.all_tags()])

    def set_assets(self, assets: list[Asset]):
        if [a.key for a in assets] != [a.key for a in self.assets]:
            self._clear_tag_input()
        self.assets = assets
        enabled = bool(assets)
        for wdg in (self.tag_input, self.tag_list, self.btn_open, self.files):
            wdg.setEnabled(enabled)
        self.refresh()

    def refresh(self):
        a_list = self.assets
        self.tag_list.clear()
        self.files.clear()
        if not a_list:
            self.preview.set_pixmap(None, "Selecione um item")
            self.preview.set_source(None)
            self.title.setText("")
            self.subtitle.setText("")
            self.status.setText("")
            self.hint.setText("Arraste um cartão direto para a viewport do 3ds Max.")
            for b in (self.btn_prepare, self.btn_organize, self.btn_open):
                b.setVisible(False)
            self.col_btn.setEnabled(False)
            self.col_info.setText("")
            self.files_head.setVisible(False)
            self.files.setVisible(False)
            self.files_hint.setVisible(False)
            return
        if len(a_list) == 1:
            a = a_list[0]
            pix = self.w.thumbs.get(a.preview)
            self.preview.set_pixmap(pix, "sem prévia" if not a.preview else "")
            self.preview.set_source(a.preview, a.name)
            self.title.setText(a.name)
            self.subtitle.setText(pretty_category(a.category))
            self.status.setText(self.w.status_html(a))
            self.hint.setText("Arraste o cartão para a viewport do 3ds Max." if self.w.extractions.is_ready(a)
                              else "Extraia para poder arrastar para o 3ds Max.")
            self.files.fill(a, self.w.thumbs)
            tags = sorted(self.w.db.tags_of(a.key))
            counts = {t: 1 for t in tags}
        else:
            self.preview.set_pixmap(None, f"{len(a_list)} itens selecionados")
            self.preview.set_source(None)
            self.title.setText(f"{len(a_list)} itens")
            self.subtitle.setText("Tags adicionadas aqui vão para todos os selecionados")
            self.status.setText("")
            self.hint.setText("")
            counts: dict[str, int] = {}
            for a in a_list:
                for t in self.w.db.tags_of(a.key):
                    counts[t] = counts.get(t, 0) + 1
            tags = sorted(counts)
        n = self.files.count()
        self.files_head.setText(f"Variações ({n})" if n > 1 else "Arquivo .max")
        self.files_head.setVisible(n > 0)
        self.files.setVisible(n > 0)
        self.files_hint.setVisible(n > 1)
        self.files.fit()
        for t in tags:
            label = f"{t}   ✕" if counts[t] == len(a_list) else f"{t} ({counts[t]})   ✕"
            it = QListWidgetItem(label)
            it.setData(Qt.UserRole, t)
            self.tag_list.addItem(it)
        self.tag_list.setVisible(bool(tags))
        if len(a_list) == 1:
            names = {c["id"]: c["name"] for c in self.w.db.collections(None)}
            cols = [names[c] for c in self.w.db.collections_of(a_list[0].key) if c in names]
            self.col_info.setText("Está em: " + ", ".join(cols) if cols else "Ainda não está em nenhuma coleção.")
        else:
            self.col_info.setText(f"{len(a_list)} itens selecionados vão juntos para a coleção.")
        free = [a for a in a_list if not self.w.shared.lock_of(a.key)]
        if len(a_list) == 1 and not free:
            self.hint.setText(f"Em uso: {self.w.lock_text(a_list[0].key)}. Os botões voltam quando terminar. "
                              "Se a pessoa esqueceu aberto, fale com ela.")
        can_prepare = any(a.kind == "archive" and not self.w.extractions.is_queued(a)
                          and not self.w.extractions.is_running(a) for a in free)
        can_org = any(self.w.layout_issues(a) and not self.w.extractions.is_running(a)
                      and not self.w.extractions.is_queued(a) for a in free)
        self.btn_prepare.setVisible(can_prepare)
        self.btn_organize.setVisible(can_org)
        self.btn_compare.setVisible(len(free) == 1 and len(a_list) == 1 and bool(a_list[0].folder)
                                    and bool(a_list[0].dup_archive))
        self.btn_open.setVisible(True)
        self.col_btn.setEnabled(True)
        main = self.btn_prepare if can_prepare else (self.btn_organize if can_org else self.btn_open)
        for b in (self.btn_prepare, self.btn_organize, self.btn_open):
            b.setProperty("primary", b is main)
            b.style().unpolish(b)
            b.style().polish(b)

    def _add(self):
        tags = [clean_tag(t) for t in self.tag_input.text().split(",")]
        tags = [t for t in tags if t]
        if not tags or not self.assets:
            return
        self.w.db.add_tags([a.key for a in self.assets], tags)
        self._clear_tag_input()
        self.update_completer()
        self.refresh()
        self.tags_changed.emit()

    def _clear_tag_input(self):
        # O QCompleter do Qt escreve a sugestão escolhida no campo DEPOIS do Enter; por isso limpa de novo
        # logo em seguida, senão a última tag volta escrita ao passar para outro item.
        self.tag_input.clear()
        QTimer.singleShot(0, self.tag_input.clear)

    def _remove_clicked(self, item: QListWidgetItem):
        tag = item.data(Qt.UserRole)
        self.w.db.remove_tag([a.key for a in self.assets], tag)
        self.update_completer()
        self.refresh()
        self.tags_changed.emit()

    def _prepare(self):
        self.w.request_extraction(self.assets)

    def _open(self):
        if self.assets:
            self.w.open_location(self.assets[0])


# =========================================================================== configurações

class SettingsDialog(QDialog):
    def __init__(self, window: "MainWindow"):
        super().__init__(window)
        self.w = window
        self.setWindowTitle("Configurações")
        self.setMinimumWidth(760)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(18)
        t = QLabel("Configurações")
        t.setStyleSheet("font-size:18pt;")
        outer.addWidget(t)

        def section(title):
            outer.addWidget(ui.heading(title, 11))
            g = ui.Glass(12)
            f = QFormLayout(g)
            f.setContentsMargins(18, 14, 18, 14)
            f.setHorizontalSpacing(18)
            f.setVerticalSpacing(10)
            f.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            outer.addWidget(g)
            return f

        form = section("Biblioteca")
        self.root = QLineEdit(window.cfg["library_root"])
        b1 = QPushButton("Escolher…")
        b1.clicked.connect(lambda: self._pick(self.root))
        b_test = QPushButton("Testar…")
        b_test.setToolTip("Confere acesso, permissão de gravação, relógio e velocidade da pasta")
        b_test.clicked.connect(self._test_library)
        form.addRow("Pasta da biblioteca", self._row(self.root, b1, b_test))
        b_vis = QPushButton("Escolher pastas…")
        b_vis.clicked.connect(lambda: (window.edit_visible_folders(self), self._update_vis_label()))
        self.vis_label = QLabel()
        self.vis_label.setStyleSheet(f"color:{theme.FAINT.name()};")
        form.addRow("Pastas exibidas", self._row(b_vis, self.vis_label))
        self._update_vis_label()
        self.retention = QComboBox()
        for label, minutes in (("1 hora", 60), ("1 dia", 1440), ("7 dias", 10080), ("Nunca apagar", 0)):
            self.retention.addItem(label, minutes)
        idx = self.retention.findData(window.backup_minutes())
        self.retention.setCurrentIndex(idx if idx >= 0 else 0)
        lib = window.shared.lib
        if lib is not None and not lib.is_admin():
            self.retention.setEnabled(False)
            self.retention.setToolTip("Definido pelo administrador; vale para todos que usam esta biblioteca")
        n, size = extractor.backup_size(window.cfg["library_root"]) if window.cfg["library_root"] else (0, 0)
        form.addRow("Apagar backup após", self.retention)
        if lib is not None:
            note = QLabel(f"<span style='color:{theme.FAINT.name()}'>O prazo vale para toda a biblioteca"
                          + (" (só o administrador muda)." if not lib.is_admin() else
                             "; como administrador, você define para todos.") + "</span>")
            note.setWordWrap(True)
            note.setMinimumHeight(note.heightForWidth(430) + 4)
            form.addRow("", note)
        form.addRow("", QLabel(f"<span style='color:{theme.FAINT.name()}'>Backup atual: {n} arquivo(s), "
                               f"{size / 1024 ** 3:.2f} GB em {extractor.BACKUP_DIR}</span>"))
        from . import busca_web
        self.vision = QLineEdit(busca_web.get_key(window))
        self.vision.setEchoMode(QLineEdit.Password)
        self.vision.setPlaceholderText("chave da API (AIza…)")
        self.vision.setToolTip("Chave da Google Cloud Vision para 'Atualizar prévia › Buscar na web'. "
                               "Vale para toda a equipe desta biblioteca.")
        if lib is not None and not lib.is_admin():
            self.vision.setEnabled(False)
            self.vision.setToolTip("Definida pelo administrador; vale para todos que usam esta biblioteca")
        form.addRow("Busca de prévias na web", self.vision)
        self.unwanted = QLineEdit(", ".join(window.cfg["unwanted_ext"]))
        self.unwanted.setToolTip("Depois de extrair, o programa pergunta se quer apagar arquivos com estas extensões")
        form.addRow("Perguntar se apaga", self.unwanted)
        self.pwd_label = QLabel()
        pwd_btn = QPushButton("Ver / editar senhas…")
        pwd_btn.clicked.connect(self._edit_passwords)
        form.addRow(self.pwd_label, pwd_btn)
        self._update_pwd_label()
        tools = window.tools
        txt = ", ".join(f"{k}" for k in tools) or f"<span style='color:{theme.BAD.name()}'>nenhum encontrado</span>"
        form.addRow("Extratores", QLabel(f"<span style='color:{theme.MUTED.name()}'>{txt}</span>"))

        form = section("Uso")
        vers = getattr(window, "max_versions", [])
        mx_txt = ("Texturas automáticas no Merge: ativo no 3ds Max " + ", ".join(vers) + ". Ao arrastar um item e "
                  "escolher Merge, as texturas vêm da pasta do item (resumo no Listener, F11).") if vers else \
            "3ds Max não encontrado neste computador."
        mx_lbl = QLabel(mx_txt)
        mx_lbl.setWordWrap(True)
        mx_lbl.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:9pt;")
        form.addRow("3ds Max", mx_lbl)
        self.size = QSlider(Qt.Horizontal)
        self.size.setRange(120, 300)
        self.size.setValue(window.thumb_size)
        self.size_lbl = QLabel(f"{window.thumb_size} px")
        self.size.valueChanged.connect(lambda v: (self.size_lbl.setText(f"{v} px"), window._set_size(v)))
        form.addRow("Tamanho dos cartões", self._row(self.size, self.size_lbl))
        self.titlebar = QComboBox()
        self.titlebar.addItem("Integrada ao Archiva (cantos arredondados)", "archiva")
        self.titlebar.addItem("Barra padrão do Windows", "windows")
        self.titlebar.setCurrentIndex(0 if window.cfg["titlebar"] != "windows" else 1)
        form.addRow("Barra de título", self.titlebar)
        form.addRow("", QLabel(f"<span style='color:{theme.FAINT.name()}'>A barra de título muda ao abrir o "
                               "programa de novo.</span>"))
        self.intro = QCheckBox("Mostrar as boas-vindas ao abrir o Archiva")
        self.intro.setChecked(not window.cfg["tutorial_off"])
        form.addRow("Tutorial", self.intro)
        self.abertura = QCheckBox("Mostrar a tela de abertura (logo animada) ao abrir o Archiva")
        self.abertura.setChecked(not window.cfg["abertura_off"])
        form.addRow("Abertura", self.abertura)

        form = section("Tags")
        exp = QPushButton("Exportar tags (backup)…")
        exp.clicked.connect(window.export_tags)
        imp = QPushButton("Importar tags…")
        imp.clicked.connect(window.import_tags)
        form.addRow(self._row(exp, imp))

        form = section("Atualizações")
        self.check_upd = QCheckBox("Procurar versão nova ao abrir o programa")
        self.check_upd.setChecked(bool(window.cfg["check_updates"]))
        now = QPushButton("Procurar agora")
        now.clicked.connect(lambda: window.check_updates(manual=True))
        form.addRow(self._row(self.check_upd, now))
        if not is_installed():
            form.addRow("", QLabel(f"<span style='color:{theme.FAINT.name()}'>Você está usando a versão aberta pelo "
                                   ".bat. Atualização automática só na versão instalada.</span>"))

        old = window.cache_root / "modelos"
        if old.exists():
            self.cache_info = QLabel("Há modelos extraídos pela versão 0.1 no cache (C:).")
            clear = QPushButton("Apagar cache da v0.1")
            clear.clicked.connect(self._clear_models)
            form.addRow(self.cache_info, clear)

        about = QLabel(f"<span style='color:{theme.FAINT.name()}'>{theme.APP_TITLE} {version()}  ·  "
                       f"tags em {window.db.path or window.cfg.db_path}  ·  miniaturas em {window.cache_root}</span>")
        about.setWordWrap(True)
        about.setTextInteractionFlags(Qt.TextSelectableByMouse)
        outer.addWidget(about)
        bb = QDialogButtonBox()
        okb = ui.primary(bb.addButton("Salvar", QDialogButtonBox.AcceptRole))
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)
        self._orig_size = window.thumb_size

    def reject(self):
        self.w._set_size(self._orig_size)
        super().reject()

    def _update_vis_label(self):
        n = len(self.w.hidden_keys())
        self.vis_label.setText(f"{n} pasta(s) escondida(s)" if n else "todas visíveis")

    def _test_library(self):
        from .diagnostico import TestDialog
        root = self.root.text().strip()
        lib = self.w.shared.lib if root == self.w.cfg["library_root"] else None
        if not root:
            return
        TestDialog(self, root, lib).exec()

    def _update_pwd_label(self):
        self.pwd_label.setText(f"Senhas de compactados salvas: {len(self.w.passwords)}")

    def _edit_passwords(self):
        text, ok = QInputDialog.getMultiLineText(
            self, "Senhas salvas",
            "Uma senha por linha. Elas são testadas automaticamente quando um arquivo pede senha.\n"
            "(Ficam guardadas sem criptografia nas configurações do programa, só neste computador.)",
            "\n".join(self.w.passwords))
        if ok:
            self.w.passwords[:] = [l.strip() for l in text.splitlines() if l.strip()]
            self.w.cfg.save()
            self._update_pwd_label()

    def _row(self, *widgets):
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(10)
        for x in widgets:
            l.addWidget(x)
        return w

    def _pick(self, edit):
        d = QFileDialog.getExistingDirectory(self, "Escolher pasta", edit.text())
        if d:
            edit.setText(os.path.normpath(d))

    def _clear_models(self):
        if QMessageBox.question(self, "Limpar cache",
                                "Apagar os modelos que a versão 0.1 extraiu no cache (C:)?\n\nA biblioteca NÃO é tocada. Cenas que usaram modelos "
                                "arrastados do cache podem perder as texturas.") \
                == QMessageBox.Yes:
            import shutil
            shutil.rmtree(self.w.cache_root / "modelos", ignore_errors=True)
            self.cache_info.setText("Cache da v0.1 apagado.")
            self.w.grid.viewport().update()


# =========================================================================== estrutura da janela

class Pages(QStackedWidget):
    """Páginas do menu lateral (substitui as antigas abas; mantém a mesma 'API' usada pelo resto do código)."""

    def __init__(self):
        super().__init__()
        self._keys: dict[QWidget, str] = {}
        self._names: dict[QWidget, str] = {}

    def add(self, w: QWidget, key: str, name: str):
        self._keys[w] = key
        self._names[w] = name
        self.addWidget(w)

    def page(self, key: str) -> QWidget | None:
        return next((w for w, k in self._keys.items() if k == key), None)

    def key_of(self, w: QWidget) -> str:
        return self._keys.get(w, "")

    def tabText(self, i: int) -> str:  # noqa: N802
        return self._names.get(self.widget(i), "")


class SideColumn(QWidget):
    """Coluna lateral da Biblioteca: vidro bem suave + linha divisória."""

    def __init__(self, border_left: bool = False):
        super().__init__()
        self.border_left = border_left

    def paintEvent(self, e):
        p = QPainter(self)
        r = QRectF(self.rect())
        p.fillRect(r, QColor(255, 236, 210, 6))
        p.setPen(QPen(QColor(255, 230, 200, 16), 1))
        x = 0.5 if self.border_left else r.right() - 0.5
        p.drawLine(QPointF(x, 0), QPointF(x, r.bottom()))


COUNT_ROLE = Qt.UserRole + 5


class CategoryDelegate(QStyledItemDelegate):
    """Linha de categoria: nome à esquerda, quantidade à direita; selecionada em vidro."""

    def sizeHint(self, option, index):
        return QSize(100, 34)

    def paint(self, p: QPainter, option, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(option.rect).adjusted(0, 1, -2, -1)
        sel = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        if sel:
            theme.paint_glass(p, r, 8, 1.6)
        elif hover:
            path = QPainterPath()
            path.addRoundedRect(r, 8, 8)
            p.fillPath(path, QColor(255, 230, 200, 12))
        name = index.data(Qt.DisplayRole) or ""
        count = index.data(COUNT_ROLE)
        f = theme.ui_font(10)
        p.setFont(f)
        fm = QFontMetrics(f)
        cw = fm.horizontalAdvance(str(count)) + 14 if count is not None else 0
        p.setPen(QColor("#fff6e8") if sel else (theme.TEXT if hover else QColor("#cbbfae")))
        p.drawText(r.adjusted(12, 0, -cw - 6, 0), Qt.AlignVCenter | Qt.AlignLeft,
                   fm.elidedText(name, Qt.ElideRight, int(r.width() - cw - 18)))
        if count is not None:
            p.setFont(theme.ui_font(9))
            p.setPen(theme.HILITE if sel else theme.FAINT)
            p.drawText(r.adjusted(0, 0, -12, 0), Qt.AlignVCenter | Qt.AlignRight, f"{count:,}".replace(",", "."))
        p.restore()


# =========================================================================== janela principal

class MainWindow(FramelessMixin, QMainWindow):
    pronto = Signal()      # a leitura da biblioteca terminou (a tela de abertura espera por isto)

    def __init__(self):
        super().__init__()
        self.cfg = Config()
        self.cache_root = self.cfg.cache_dir
        self.data_rev = 0                  # muda sempre que itens/tags mudam (o Início só se refaz se mudou)
        self.db = TagDB(None)              # aberto de verdade quando a biblioteca é escolhida
        self.shared = Compartilhado(self.db)
        self.db.on_change = self._bump
        self.profile = perfil.load()
        self._bound_root = None
        self._ops: dict[str, str] = {}     # item -> "extrair" | "organizar" (para o histórico)
        self.tools = extractor.find_tool(self.cfg["unrar_path"])
        self.thumb_size = int(self.cfg["thumb_size"])
        self.categories: list[Category] = []     # categorias visíveis (sem as pastas escondidas)
        self._all_cats: list[Category] = []      # todas (índice e conferência usam esta)
        self.cat_by_key: dict[str, Category] = {}
        self.all_assets: list[Asset] = []
        self.current_cat = ALL_KEY
        self.active_tags: set[str] = set()

        self.setWindowTitle(APP_NAME)
        icon = app_dir() / "app" / "recursos" / "icone.png"
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))
        self.resize(1400, 860)

        self.thumbs = ThumbnailCache(self.cache_root)
        scanner_mod.UNWANTED_EXT = extractor._norm_exts(self.cfg["unwanted_ext"])
        self.passwords: list[str] = self.cfg.values.setdefault("passwords", [])
        self.cfg.values["drag_mode"] = "max"   # 1.1.4: único modo (.max puro + texturas pelo script do Max)
        from . import max_startup
        self.max_versions = max_startup.install()
        self._pwd_tries: dict[str, int] = {}
        self.extractions = ExtractionManager(self.cfg["library_root"], self.tools, list(self.cfg["unwanted_ext"]),
                                             self.passwords)
        self.extractions.started.connect(self._on_extract_started)
        self.extractions.finished.connect(self._on_extract_finished)
        self.extractions.batch_done.connect(self._on_batch_done)
        self._backup_timer = QTimer(self, interval=5 * 60 * 1000)
        self._backup_timer.timeout.connect(self._clean_backup)
        self._backup_timer.start()

        self._build_ui()
        self.thumbs.changed.connect(self._on_thumbs_changed)
        self._thumb_timer = QTimer(self, singleShot=True, interval=60)
        self._thumb_timer.timeout.connect(self._repaint_thumbs)

        self._restore_state()
        QTimer.singleShot(0, self.start_scan)

    # ----------------------------------------------------------------- UI
    def _build_ui(self):
        self.setup_frame(self.cfg["titlebar"] != "windows" and os.environ.get("ARCHIVA_BARRA") != "windows")

        # ---------------- busca e filtro (cabeçalho da Biblioteca)
        self.search_box = ui.SearchField("Buscar por nome, categoria ou tag")
        self.search = self.search_box.edit
        self.search.textChanged.connect(lambda: self._search_timer.start())
        self._search_timer = QTimer(self, singleShot=True, interval=180)
        self._search_timer.timeout.connect(self.apply_filter)
        sc = QAction(self)
        sc.setShortcut(QKeySequence("Ctrl+F"))
        sc.triggered.connect(lambda: (self.tabs.setCurrentWidget(self.splitter), self.search.setFocus(),
                                      self.search.selectAll()))
        self.addAction(sc)
        self.show_filter = ui.Segmented([("Todos", "all"), ("Prontos", "ready"), ("Compactados", "archive"),
                                         ("Fora do padrão", "layout")])
        i = self.show_filter.findData(self.cfg["show_filter"])
        self.show_filter.setCurrentIndex(i if i >= 0 else 0)
        self.show_filter.currentIndexChanged.connect(
            lambda: (self.cfg.__setitem__("show_filter", self.show_filter.currentData()), self.apply_filter()))
        f5 = QAction(self)
        f5.setShortcut(QKeySequence("F5"))
        f5.triggered.connect(self.refresh_all)
        self.addAction(f5)

        # ---------------- coluna de categorias + tags
        left = SideColumn()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, TITLE_H + 8, 14, 16)
        ll.setSpacing(6)
        h = ui.heading("Categorias", 10)
        h.setContentsMargins(12, 0, 0, 6)
        ll.addWidget(h)
        self.cat_tree = QTreeWidget()
        self.cat_tree.setHeaderHidden(True)
        self.cat_tree.setIndentation(14)
        self.cat_tree.setRootIsDecorated(False)
        self.cat_tree.setItemDelegate(CategoryDelegate(self.cat_tree))
        self.cat_tree.setMouseTracking(True)
        self.cat_tree.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.cat_tree.currentItemChanged.connect(self._on_category)
        self.cat_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.cat_tree.customContextMenuRequested.connect(self._category_menu)
        self.cat_tree.setToolTip("Botão direito numa categoria: extrair ou organizar tudo dela")
        ll.addWidget(self.cat_tree, 3)
        hl = QHBoxLayout()
        hl.setContentsMargins(12, 10, 4, 2)
        hl.addWidget(ui.heading("Tags", 10))
        self.clear_tags_btn = ui.link_button("limpar")
        self.clear_tags_btn.clicked.connect(self._clear_tag_filter)
        hl.addStretch(1)
        hl.addWidget(self.clear_tags_btn)
        ll.addLayout(hl)
        self.tag_filter = QListWidget()
        self.tag_filter.itemChanged.connect(self._on_tag_filter)
        self.tag_filter.setToolTip("Marque tags para filtrar (todas as marcadas precisam estar no item)")
        self.tag_filter.setStyleSheet("QListWidget::item{padding:5px 8px; color:#a89c8c; border-radius:7px;}"
                                      "QListWidget::item:hover{background:rgba(255,230,200,0.06); color:#f1e9dc;}"
                                      "QListWidget::indicator{width:14px; height:14px; border-radius:4px;"
                                      " border:1px solid rgba(255,230,200,0.28); background:rgba(255,236,210,0.04);}"
                                      "QListWidget::indicator:checked{background:#e3cfa9; border-color:#e3cfa9;}")
        ll.addWidget(self.tag_filter, 2)

        # ---------------- centro: título, busca, filtro e grade
        center = QWidget()
        cl = QVBoxLayout(center)
        cl.setContentsMargins(36, TITLE_H + 8, 36, 0)
        cl.setSpacing(20)
        tl = QVBoxLayout()
        tl.setSpacing(2)
        trow = QHBoxLayout()
        self.lib_title = QLabel("Biblioteca")
        self.lib_title.setStyleSheet("font-size:21pt;")
        trow.addWidget(self.lib_title)
        trow.addStretch(1)
        self.refresh_btn = QPushButton()
        self.refresh_btn.setIcon(ui.icon("atualizar", theme.MUTED, 18))
        self.refresh_btn.setToolTip("Atualizar a biblioteca (F5)")
        self.refresh_btn.setFixedSize(38, 38)
        self.refresh_btn.setCursor(Qt.PointingHandCursor)
        self.refresh_btn.clicked.connect(self.refresh_all)
        trow.addWidget(self.refresh_btn, 0, Qt.AlignTop)
        tl.addLayout(trow)
        self.lib_sub = QLabel()
        self.lib_sub.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:10.5pt;")
        tl.addWidget(self.lib_sub)
        cl.addLayout(tl)
        brow = QHBoxLayout()
        brow.setSpacing(12)
        self.search_box.setMinimumWidth(220)
        brow.addWidget(self.search_box, 1)
        brow.addWidget(self.show_filter)
        self.size_slider = QSlider(Qt.Horizontal)
        self.size_slider.setRange(120, 300)
        self.size_slider.setValue(self.thumb_size)
        self.size_slider.setFixedWidth(110)
        self.size_slider.setToolTip("Tamanho dos cartões")
        self.size_slider.valueChanged.connect(self._set_size)
        size_box = QHBoxLayout()
        size_box.setSpacing(8)
        small = QLabel()
        small.setPixmap(ui.icon_pixmap("biblioteca", theme.FAINT, 13))
        big = QLabel()
        big.setPixmap(ui.icon_pixmap("biblioteca", theme.MUTED, 19))
        size_box.addWidget(small)
        size_box.addWidget(self.size_slider)
        size_box.addWidget(big)
        brow.addSpacing(6)
        brow.addLayout(size_box)
        cl.addLayout(brow)
        self.model = AssetModel(self.db)
        self.grid = AssetView(self)
        self.grid.setModel(self.model)
        self.grid.setItemDelegate(CardDelegate(self))
        self.grid.setSpacing(0)
        self.grid.selectionModel().selectionChanged.connect(self._on_selection)
        self.grid.customContextMenuRequested.connect(self._context_menu)
        self.grid.doubleClicked.connect(lambda idx: self.open_location(idx.data(ASSET_ROLE)))
        self.grid.verticalScrollBar().valueChanged.connect(lambda: self._thumb_timer.start())
        cl.addWidget(self.grid, 1)
        self.count_label = QLabel()           # compatibilidade (texto vai para o subtítulo)

        # ---------------- direita: detalhes
        right = SideColumn(border_left=True)
        rl = QVBoxLayout(right)
        rl.setContentsMargins(28, TITLE_H + 8, 28, 16)
        from PySide6.QtWidgets import QScrollArea
        self.details = DetailsPanel(self)
        self.details.tags_changed.connect(self._on_tags_changed)
        dscroll = QScrollArea()
        dscroll.setWidgetResizable(True)
        dscroll.setFrameShape(QFrame.NoFrame)
        dscroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        dscroll.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget {background:transparent;}")
        dscroll.setWidget(self.details)
        rl.addWidget(dscroll)
        right.setMinimumWidth(280)

        self.splitter = QSplitter()
        self.splitter.setHandleWidth(1)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(left)
        self.splitter.addWidget(center)
        self.splitter.addWidget(right)
        self.splitter.setStretchFactor(1, 1)
        self.splitter.setSizes([230, 900, 340])
        left.setMinimumWidth(190)

        # ---------------- páginas
        from .entrada_page import EntradaPage
        from .home_page import HomePage
        from .tags_page import TagsPage
        self.tabs = Pages()
        self.home = HomePage(self)
        self.tabs.add(self.home, "inicio", "Início")
        self.tabs.add(self.splitter, "biblioteca", "Biblioteca")
        self.tags_page = TagsPage(self)
        self.tabs.add(self.tags_page, "tags", "Tags")
        from .colecoes_page import ColecoesPage
        self.colecoes = ColecoesPage(self)
        self.tabs.add(self.colecoes, "colecoes", "Coleções")
        self.entrada = EntradaPage(self)
        self.tabs.add(self.entrada, "entrada", "Entrada")
        from .organizar import OrganizacaoPage
        self.organizacao = OrganizacaoPage(self)
        self.tabs.add(self.organizacao, "organizacao", "Organização")
        self.organizacao.repetidos.count_changed.connect(
            lambda n: hasattr(self, "sidebar") and "organizacao" in self.sidebar.buttons
            and self.sidebar.buttons["organizacao"].set_badge(n))
        self._dup_timer = QTimer(self, singleShot=True)
        self._dup_timer.timeout.connect(self._scan_dups)
        self.aprender = tutoriais.AprenderPage(self)
        self.aprender.open_tutorial.connect(self.show_tutorial)
        self.tabs.add(self.aprender, "aprender", "Aprender")
        self.sidebar = ui.Sidebar([("inicio", "Início", "inicio"), ("biblioteca", "Biblioteca", "biblioteca"),
                                   ("tags", "Tags", "tags"), ("colecoes", "Coleções", "colecoes"),
                                   ("entrada", "Entrada", "entrada"), ("organizacao", "Organização", "organizar"),
                                   ("aprender", "Aprender", "aprender")])
        self.sidebar.navigate.connect(lambda k: self.tabs.setCurrentWidget(self.tabs.page(k)))
        # soltar cartões em "Coleções" no menu lateral: escolhe a coleção num menu
        self._col_drop = self.sidebar.buttons["colecoes"]
        self._col_drop.setAcceptDrops(True)
        self._col_drop.installEventFilter(self)
        self._setup_shortcuts()
        self.sidebar.settings.clicked.connect(self.open_settings)
        self.user_chip = perfil.UserChip()
        self.user_chip.clicked.connect(self._user_menu)
        lay = self.sidebar.layout()
        lay.insertWidget(lay.indexOf(self.sidebar.settings), self.user_chip)
        self._update_user_chip()
        self.shared.tags_changed.connect(self._on_shared_tags)
        self.shared.items_changed.connect(self._on_shared_items)
        self.shared.locks_changed.connect(self._on_locks_changed)
        self.entrada.count_changed.connect(lambda n: (self.sidebar.buttons["entrada"].set_badge(n), self._bump()))
        self.tabs.currentChanged.connect(self._on_tab)
        self._update_footer()

        root = ui.Root()
        hl = QHBoxLayout(root)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(0)
        hl.addWidget(self.sidebar)
        col = QVBoxLayout()
        col.setContentsMargins(0, 0, 0, 0)
        col.setSpacing(0)
        col.addWidget(self.tabs, 1)
        self._status = QStatusBar()
        self._status.setSizeGripEnabled(False)
        self._status.setContentsMargins(24, 0, 12, 4)
        col.addWidget(self._status)
        hl.addLayout(col, 1)
        self.setCentralWidget(root)
        self.caption = CaptionButtons(self, root)
        self.caption.setVisible(False)
        self.sidebar.set_current("inicio")

        self.progress = QProgressBar()
        self.progress.setMaximumWidth(220)
        self.progress.setFixedHeight(6)
        self.progress.setTextVisible(False)
        self.progress.hide()
        self._status.addPermanentWidget(self.progress)

        self.update_notice = QWidget()
        ul = QHBoxLayout(self.update_notice)
        ul.setContentsMargins(0, 0, 8, 0)
        ul.setSpacing(10)
        self.update_lbl = QLabel()
        self.update_lbl.setStyleSheet(f"color:{theme.HILITE.name()};")
        self.update_btn = ui.primary(QPushButton("Atualizar"))
        self.update_btn.setFixedHeight(26)
        self.update_btn.clicked.connect(self._do_update)
        self.update_later = QPushButton("Depois")
        self.update_later.setProperty("flat", "true")
        self.update_later.setFixedHeight(26)
        self.update_later.clicked.connect(self.update_notice.hide)
        ul.addWidget(self.update_lbl)
        ul.addWidget(self.update_btn)
        ul.addWidget(self.update_later)
        self.update_notice.hide()
        self._status.addPermanentWidget(self.update_notice)
        self._update_info = None

    def statusBar(self):  # noqa: N802 — barra de mensagens dentro da área de conteúdo
        return self._status

    def frame_changed(self):
        self.caption.setVisible(self.custom_frame)
        self._place_caption()

    def _place_caption(self):
        if hasattr(self, "caption"):
            self.caption.move(self.centralWidget().width() - self.caption.width() - 6, 6)
            self.caption.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_caption()
        self._place_grips()

    def changeEvent(self, e):
        super().changeEvent(e)
        if hasattr(self, "caption"):
            self.caption.update()
        self._place_grips()

    def showEvent(self, e):
        super().showEvent(e)
        if not getattr(self, "_frame_done", False):
            self._frame_done = True
            QTimer.singleShot(0, self.finish_frame)
            if self.cfg["check_updates"]:
                QTimer.singleShot(5000, self.check_updates)

    # ----------------------------------------------------------------- atualização (GitHub)
    def check_updates(self, manual: bool = False):
        if getattr(self, "_upd_check", None) and self._upd_check.isRunning():
            return
        t = atualizador.CheckThread(version(), self.cfg["github_token"])
        t.found.connect(lambda v, url, notes: self._update_found(v, url, notes, manual))
        if manual:
            t.uptodate.connect(lambda v: self.statusBar().showMessage(
                f"Você já está na versão mais recente ({version()}).", 6000))
            t.failed.connect(lambda err: self.statusBar().showMessage(
                "Não foi possível consultar o GitHub agora (sem internet ou acesso negado).", 8000))
        self._upd_check = t
        t.start()

    def _update_found(self, ver, url, notes, manual):
        if not manual and ver == self.cfg["skip_version"]:
            return
        self._update_info = (ver, url, notes)
        self.update_lbl.setText(f"Archiva {ver} disponível")
        self.update_lbl.setToolTip(notes or "")
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Atualizar" if is_installed() else "Baixar")
        self.update_notice.show()

    def _do_update(self):
        if not self._update_info:
            return
        ver, url, notes = self._update_info
        if not is_installed():
            QDesktopServices.openUrl(QUrl(atualizador.PAGE))
            return
        if self.extractions.busy():
            QMessageBox.information(self, "Atualizar", "Espere as extrações em andamento terminarem para atualizar.")
            return
        self.update_btn.setEnabled(False)
        self.update_btn.setText("Baixando…")
        self.progress.setRange(0, 0)
        self.progress.show()
        d = atualizador.DownloadThread(url, ver, self.cfg["github_token"])
        d.progress.connect(lambda got, total: (self.progress.setRange(0, max(total, 1)), self.progress.setValue(got)))
        d.done.connect(self._install_update)
        d.failed.connect(self._update_failed)
        self._upd_dl = d
        d.start()

    def _update_failed(self, err):
        self.progress.hide()
        self.update_btn.setEnabled(True)
        self.update_btn.setText("Tentar de novo")
        self.statusBar().showMessage(f"Falha ao baixar a atualização: {err}", 10000)

    def _install_update(self, path):
        self.progress.hide()
        self.update_btn.setText("Instalando…")
        if atualizador.run_installer(path):
            self.close()
            QApplication.quit()

    def _update_footer(self):
        root = self.cfg["library_root"] or "sem biblioteca"
        self.sidebar.footer.setText(f"{root}<br>versão {version()}")

    def _restore_state(self):
        g = self.cfg["window_geometry"]
        if g:
            self.restoreGeometry(QByteArray.fromBase64(g.encode()))
        s = self.cfg["splitter_state"]
        if s:
            self.splitter.restoreState(QByteArray.fromBase64(s.encode()))

    def closeEvent(self, e):
        try:
            self.organizacao.repetidos.stop()
        except Exception:  # noqa: BLE001
            pass
        self.cfg.values["window_geometry"] = bytes(self.saveGeometry().toBase64()).decode()
        self.cfg.values["splitter_state"] = bytes(self.splitter.saveState().toBase64()).decode()
        self.cfg.values["thumb_size"] = self.thumb_size
        self.cfg.save()
        if getattr(self, "_verify", None) and self._verify.isRunning():
            self._verify.requestInterruption()
            self._verify.wait(2000)
        else:
            self._save_index()
        self.thumbs.cancel_pending()
        self.entrada.shutdown()
        self.shared.unbind()
        super().closeEvent(e)

    # ----------------------------------------------------------------- leitura
    def ensure_profile(self) -> dict:
        while not self.profile:
            d = perfil.ProfileDialog(self, first=True)
            if d.exec() == QDialog.Accepted:
                self.profile = d.result_profile()
            else:   # fechou sem preencher: usa o nome do computador (pode trocar depois)
                import uuid
                self.profile = {"id": uuid.uuid4().hex, "nome": perfil.computer_name(), "cor": perfil.CORES[0],
                                "foto": False, "pc": perfil.computer_name()}
                perfil.save(self.profile)
        self._update_user_chip()
        return self.profile

    def start_scan(self, full: bool = False):
        self.ensure_profile()
        root = self.cfg["library_root"]
        if not root or not os.path.isdir(root):
            if not getattr(self, "_welcomed", False):
                self._welcomed = True
                m = QMessageBox(self)
                m.setWindowTitle(APP_NAME)
                if root:
                    m.setText("<b>A pasta da biblioteca não foi encontrada</b>")
                    m.setInformativeText(f"{root}<br><br>O disco pode estar desconectado. Escolha a pasta de novo "
                                         "ou feche e conecte o disco.")
                else:
                    m.setText(f"<b>Olá, {self.profile.get('nome', '')}</b>")
                    m.setInformativeText("Agora escolha a pasta da biblioteca de modelos 3D, aquela com uma pasta "
                                         "por categoria (ex.: ADORNOS, CADEIRAS, LUMINARIAS…). Pode ser no seu "
                                         "computador ou no servidor (ex.: \\\\SERVIDOR\\MODELOS).<br><br>"
                                         "Nada nela é alterado sem você pedir (extrair, organizar, classificar).")
                ui.primary(m.addButton("Escolher pasta…", QMessageBox.AcceptRole))
                m.addButton("Agora não", QMessageBox.RejectRole)
                m.exec()
                go = m.buttonRole(m.clickedButton()) == QMessageBox.AcceptRole
            else:
                go = True
            d = QFileDialog.getExistingDirectory(self, "Pasta da biblioteca de modelos", root or "") if go else ""
            if not d:
                self.statusBar().showMessage("Nenhuma biblioteca escolhida. Escolha em Configurações › Biblioteca.")
                return
            self.cfg["library_root"] = os.path.normpath(d)
            root = self.cfg["library_root"]
        if getattr(self, "_scan", None) and self._scan.isRunning():
            return
        if self._bound_root != root:
            self._bind_library(root)
        if getattr(self, "_verify", None) and self._verify.isRunning():
            self._verify.requestInterruption()
            self._verify.wait(3000)
        self._index_file = indice.cache_file(self.cache_root, root)
        cached = None if full else indice.load(self._index_file, root)
        if cached:
            # abre na hora com o índice salvo e confere em segundo plano só o que mudou
            cats, self._sigs = cached
            self._on_scanned(cats, from_index=True)
            self._start_verify(root)
            return
        self.progress.setRange(0, 0)
        self.progress.show()
        self.statusBar().showMessage(f"Lendo {root}…")
        self._scan = ScanThread(root)
        self._scan.progress.connect(lambda i, n, name: (self.progress.setRange(0, n), self.progress.setValue(i),
                                                        self.statusBar().showMessage(f"Lendo {name}…  ({i}/{n})")))
        self._scan.done.connect(self._on_scanned)
        self._scan.failed.connect(self._scan_failed)
        self._scan.start()

    def _scan_failed(self, msg: str):
        self.pronto.emit()
        QMessageBox.warning(self, "Erro ao ler biblioteca", msg)

    def _bind_library(self, root: str):
        self.statusBar().showMessage("Lendo tags e histórico da biblioteca…")
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            ok = self.shared.bind(root, self.profile)
            lib = self.shared.lib
            if ok and lib.is_admin() and lib.option("backup_minutes") is None:
                try:      # o prazo do backup do administrador passa a valer para a biblioteca toda
                    lib.set_option("backup_minutes", int(self.cfg["backup_minutes"]))
                except OSError:
                    pass
            if ok and not self.db.prefixes() and self.cfg["prefixes"]:
                for k, v in dict(self.cfg["prefixes"]).items():   # nomes da Entrada passam a valer para todos
                    self.db.set_prefix(k, v)
        finally:
            QApplication.restoreOverrideCursor()
        self._bound_root = root
        self._update_user_chip()
        if not ok:
            QMessageBox.warning(self, "Biblioteca", self.shared.error + "\n\nAs tags ficam só neste computador "
                                "até a pasta poder ser gravada.")
        if self.shared.offer_old_tags:
            QTimer.singleShot(800, self._offer_old_tags)

    def _offer_old_tags(self):
        if QMessageBox.question(self, "Tags", "Esta biblioteca já tem tags de outras pessoas.\n\nQuer juntar a elas "
                                "as tags que você tinha neste computador?") == QMessageBox.Yes:
            n = self.shared.import_old_tags()
            self._on_shared_tags()
            self.statusBar().showMessage(f"Tags de {n} marcação(ões) juntadas à biblioteca.", 8000)
        else:
            self.shared.offer_old_tags = False

    # ----------------------------------------------------------------- pessoas / compartilhamento
    def backup_minutes(self) -> int:
        """Prazo do backup: o da biblioteca (definido pelo administrador) ou, sem biblioteca compartilhada, o local."""
        lib = self.shared.lib
        v = lib.option("backup_minutes") if lib is not None else None
        return int(v if v is not None else self.cfg["backup_minutes"])

    def prefix_for(self, cat_key: str) -> str | None:
        return self.db.prefixes().get(cat_key)

    def set_prefix(self, cat_key: str, prefix: str | None) -> None:
        self.db.set_prefix(cat_key, prefix)

    def is_admin(self) -> bool:
        return bool(self.shared.lib and self.shared.lib.is_admin())

    def _update_user_chip(self):
        if not hasattr(self, "user_chip"):
            return
        if hasattr(self, "sidebar") and "organizacao" in self.sidebar.buttons:
            # Organização mexe em muitos arquivos de uma vez: só o administrador vê
            self.sidebar.buttons["organizacao"].setVisible(self.is_admin() or self.shared.lib is None)
        if not self.profile:
            self.user_chip.setVisible(False)
            return
        self.user_chip.setVisible(True)
        self.user_chip.set_user(self.profile, "administrador" if self.is_admin() else "")

    def _user_menu(self):
        m = QMenu(self)
        m.addAction("Editar perfil…", self.edit_profile)
        m.addSeparator()
        m.addAction("Minhas alterações…", lambda: self.open_history(False))
        if self.is_admin():
            m.addAction("Histórico de todos…", lambda: self.open_history(True))
            m.addAction("Pessoas e administradores…", self.open_people)
        m.exec(self.user_chip.mapToGlobal(QPoint(8, -m.sizeHint().height() - 4)))

    def edit_profile(self):
        d = perfil.ProfileDialog(self, self.profile)
        if d.exec() == QDialog.Accepted:
            self.profile = d.result_profile()
            if self.shared.lib:
                try:
                    self.shared.lib.publish_profile(self.profile, perfil.avatar_png_bytes(self.profile))
                    self.shared.profile = self.profile
                except OSError:
                    pass
            self._update_user_chip()

    def open_history(self, everyone: bool):
        if not self.shared.active:
            QMessageBox.information(self, "Histórico", "Escolha a biblioteca primeiro.")
            return
        from .historico import HistoryDialog
        HistoryDialog(self, everyone).exec()

    def open_people(self):
        from .historico import PeopleDialog
        PeopleDialog(self).exec()
        self._update_user_chip()

    def _on_shared_tags(self):
        self.data_rev += 1
        self._rebuild_search_text()
        self._fill_tag_filter()
        self.details.update_completer()
        self.details.refresh()
        self.grid.viewport().update()
        for page in (getattr(self, "home", None), getattr(self, "tags_page", None), getattr(self, "colecoes", None)):
            if page is not None and hasattr(page, "refresh"):
                try:
                    page.refresh()
                except Exception:  # noqa: BLE001
                    pass

    def _on_shared_items(self, cats: list):
        if getattr(self, "_scan", None) and self._scan.isRunning():
            return
        for c in cats:
            self.refresh_category(c)
        self.entrada.refresh()

    def _on_locks_changed(self):
        self.grid.viewport().update()
        self.details.refresh()
        if hasattr(self.entrada, "grid"):
            self.entrada.grid.viewport().update()

    def lock_text(self, key: str) -> str:
        info = self.shared.lock_of(key)
        if not info:
            return ""
        return self.lock_who(info)

    @staticmethod
    def lock_who(info: dict | None) -> str:
        """'Maria (PC-02) está extraindo desde 13:40' — quem está com o item e há quanto tempo."""
        info = info or {}
        quem = info.get("nome") or "?"
        if info.get("pc"):
            quem += f" ({info['pc']})"
        txt = f"{quem} está {info.get('op', 'mexendo')}"
        t = info.get("t")
        if isinstance(t, (int, float)) and t > 0:
            try:
                from datetime import datetime
                dt = datetime.fromtimestamp(t)
                hoje = dt.date() == datetime.now().date()
                txt += " desde " + dt.strftime("%H:%M" if hoje else "%d/%m %H:%M")
            except (OSError, OverflowError, ValueError):
                pass
        return txt

    def try_lock(self, keys: list[str], op: str) -> tuple[list[str], list[str]]:
        """Trava cada chave; devolve (travadas, mensagens de quem já está usando)."""
        got, busy = [], []
        for k in keys:
            ok, info = self.shared.acquire(k, op)
            if ok:
                got.append(k)
            else:
                nome = ("categoria " + k[4:]) if k.startswith("cat:") else k.split("/")[-1]
                busy.append(f"{nome}: {self.lock_who(info)}")
        return got, busy

    def log_op(self, *a, **kw):
        return self.shared.log_op(*a, **kw)

    def _start_verify(self, root: str):
        self.statusBar().showMessage("Conferindo mudanças na biblioteca…")
        self.progress.setRange(0, 0)
        self.progress.show()
        v = indice.VerifyThread(root, list(self._all_cats), dict(self._sigs))
        v.changed.connect(self._on_verify_changed)
        v.removed.connect(self._on_verify_removed)
        v.finished_ok.connect(self._on_verify_done)
        self._verify = v
        v.start()

    def _on_verify_changed(self, new: Category, sig: str):
        self._sigs[new.key] = sig
        self._replace_category(new)

    def _on_verify_removed(self, key: str):
        self._sigs.pop(key, None)
        self._all_cats = [c for c in self._all_cats if c.key != key]
        self._replace_category(None)

    def schedule_dups(self, ms: int):
        """Procura possíveis repetidos em segundo plano (só para quem vê a Organização)."""
        if hasattr(self, "_dup_timer"):
            self._dup_timer.start(ms)

    def _scan_dups(self):
        if not (self.is_admin() or self.shared.lib is None) or not self.all_assets:
            return
        if (getattr(self, "_scan", None) and self._scan.isRunning()) or \
                (getattr(self, "_verify", None) and self._verify.isRunning()):
            self._dup_timer.start(10000)
            return
        self.organizacao.repetidos.scan()

    def _on_verify_done(self, n: int):
        self.schedule_dups(4000)
        self.progress.hide()
        self._save_index()
        self.statusBar().showMessage(self._summary() + (f"  ·  {n} categoria(s) atualizada(s)" if n else ""), 8000)
        if n:
            self.entrada.fill_categories()
            self.home.refresh()

    def _save_index(self):
        f = getattr(self, "_index_file", None)
        if f and self._all_cats:
            indice.save(f, self.cfg["library_root"], self._all_cats, dict(getattr(self, "_sigs", {})))

    def _summary(self) -> str:
        n_issue = sum(1 for a in self.all_assets if a.issues)
        n_layout = sum(1 for a in self.all_assets if self.layout_issues(a))
        n_arch = sum(1 for a in self.all_assets if a.kind == "archive")
        return (f"{len(self.all_assets)} itens em {len(self.categories)} categorias"
                + (f"  ·  {n_arch} compactados" if n_arch else "")
                + (f"  ·  {n_layout} fora do padrão" if n_layout else "")
                + (f"  ·  {n_issue} com problema" if n_issue else ""))

    def _on_scanned(self, cats: list[Category], from_index: bool = False):
        self.data_rev += 1
        self.progress.hide()
        if not from_index:
            self._sigs = indice.all_signatures(self.cfg["library_root"], cats)
            self._save_index()
        self.extractions.library_root = self.cfg["library_root"]
        if not self.extractions.busy():
            extractor.clean_temp(self.cfg["library_root"])
            self._clean_backup()
        self._all_cats = cats
        self._apply_visibility()
        self._rebuild_search_text()
        self._fill_category_tree()
        self._fill_tag_filter()
        self.details.update_completer()
        self.entrada.fill_categories()
        self.entrada.refresh()
        self.home.refresh()
        self.statusBar().showMessage(self._summary())
        self.apply_filter()
        if not getattr(self, "_intro_done", False):
            self._intro_done = True
            QTimer.singleShot(500, self._intro)
        self.schedule_dups(6000)
        self.pronto.emit()

    # ----------------------------------------------------------------- tutoriais
    def _intro(self):
        """Boas-vindas (até a pessoa desligar) ou, depois de atualizar, só o que é novo."""
        if not self.isVisible():          # a tela de abertura ainda está na frente: espera a janela aparecer
            QTimer.singleShot(300, self._intro)
            return
        last = self.cfg["versao_vista"]
        cur = version()
        self.cfg["versao_vista"] = cur
        self._update_learn_badge()
        if not self.cfg["tutorial_off"]:
            self.show_onboarding()
        elif last and last != cur:
            novos = [t["id"] for t in tutoriais.newer_than(last)]
            if novos:
                self._overlay(novos, f"Novidades da versão {cur}")
            else:
                self.statusBar().showMessage(f"Archiva atualizado para a versão {cur}.", 8000)

    def _overlay(self, ids, kicker, optout=False, start=0):
        old = getattr(self, "_tut", None)
        if old is not None:
            try:
                old.finish()
            except RuntimeError:
                pass
        ov = tutoriais.TutorialOverlay(self.centralWidget(), ids, kicker, show_optout=optout,
                                       optout_checked=True, start=start)
        ov.viewed.connect(self._mark_viewed)
        if optout:
            ov.closed.connect(lambda: self.cfg.__setitem__("tutorial_off", ov.optout.isChecked()))
        self.caption.raise_()
        self._tut = ov
        return ov

    def show_onboarding(self, manual: bool = False):
        self._overlay(tutoriais.BOAS_VINDAS, "Boas-vindas ao Archiva", optout=not manual)

    def show_tutorial(self, tid: str):
        t = tutoriais.BY_ID.get(tid)
        if not t:
            return
        ids = [x["id"] for x in tutoriais.TUTORIAIS if x["grupo"] == t["grupo"]]
        self._overlay(ids, t["grupo"], start=ids.index(tid))

    def _mark_viewed(self, tid: str):
        seen = list(self.cfg["tutoriais_vistos"] or [])
        if tid not in seen:
            seen.append(tid)
            self.cfg["tutoriais_vistos"] = seen
            self._update_learn_badge()
            self.aprender.refresh()

    def _update_learn_badge(self):
        seen = list(self.cfg["tutoriais_vistos"] or [])
        n = sum(1 for t in tutoriais.TUTORIAIS if tutoriais.is_new(t, version(), seen))
        self.sidebar.buttons["aprender"].set_badge(n)

    def _rebuild_search_text(self, assets=None):
        for a in (assets or self.all_assets):
            a.search_text = normalize(" ".join([a.name, a.category, *self.db.tags_of(a.key)]))

    def _fill_category_tree(self):
        prev = self.current_cat
        self.cat_tree.blockSignals(True)
        self.cat_tree.clear()
        top = QTreeWidgetItem(["Todas"])
        top.setData(0, Qt.UserRole, ALL_KEY)
        top.setData(0, COUNT_ROLE, len(self.all_assets))
        self.cat_tree.addTopLevelItem(top)
        select = top

        def add(parent, c: Category):
            nonlocal select
            it = QTreeWidgetItem([pretty(c.name)])
            it.setData(0, Qt.UserRole, c.key)
            it.setData(0, COUNT_ROLE, len(c.all_assets()))
            parent.addChild(it) if isinstance(parent, QTreeWidgetItem) else self.cat_tree.addTopLevelItem(it)
            if c.key == prev:
                select = it
            for ch in c.children:
                add(it, ch)

        for c in self.categories:
            add(self.cat_tree, c)
        self.cat_tree.expandAll()
        self.cat_tree.setCurrentItem(select)
        self.cat_tree.blockSignals(False)
        self.current_cat = select.data(0, Qt.UserRole)

    def _fill_tag_filter(self):
        self.tag_filter.blockSignals(True)
        self.tag_filter.clear()
        for t, n in self.db.all_tags():
            it = QListWidgetItem(f"{t}  ({n})")
            it.setData(Qt.UserRole, t)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if t in self.active_tags else Qt.Unchecked)
            self.tag_filter.addItem(it)
        self.active_tags &= {t for t, _ in self.db.all_tags()}
        self.tag_filter.blockSignals(False)

    # ----------------------------------------------------------------- filtro
    def apply_filter(self):
        if self.current_cat == ALL_KEY:
            pool = self.all_assets
        else:
            c = self.cat_by_key.get(self.current_cat)
            pool = c.all_assets() if c else []
        tokens = normalize(self.search.text()).split()
        out = []
        for a in pool:
            mode = self.show_filter.currentData()
            if mode == "issues" and not a.issues:
                continue
            if mode == "layout" and not self.layout_issues(a):
                continue
            if mode == "archive" and a.kind != "archive":
                continue
            if mode == "ready" and a.kind not in ("folder", "max"):
                continue
            if self.active_tags and not self.active_tags <= self.db.tags_of(a.key):
                continue
            if tokens and not all(t in a.search_text for t in tokens):
                continue
            out.append(a)
        sel = {a.key for a in self.selected_assets()}
        self.thumbs.cancel_pending()
        self.model.set_assets(out)
        if sel:
            sm = self.grid.selectionModel()
            for a in out:
                if a.key in sel:
                    sm.select(self.model.index(self.model.row_of[a.key]), sm.SelectionFlag.Select)
        self.details.set_assets(self.selected_assets())
        c = self.cat_by_key.get(self.current_cat)
        self.lib_title.setText(pretty(c.name) if c else "Todas as categorias")
        ready = sum(1 for a in out if a.kind in ("folder", "max"))
        n = len(out)
        txt = (f"{fmt_int(n)} {'item' if n == 1 else 'itens'}, "
               f"{fmt_int(ready)} {'pronto' if ready == 1 else 'prontos'} para usar")
        if self.active_tags:
            txt += "  ·  tags: " + ", ".join(sorted(self.active_tags))
        self.lib_sub.setText(txt)

    def _on_category(self, cur, _prev):
        if cur:
            self.current_cat = cur.data(0, Qt.UserRole)
            self.apply_filter()
            self.grid.scrollToTop()

    def _on_tag_filter(self, item):
        t = item.data(Qt.UserRole)
        if item.checkState() == Qt.Checked:
            self.active_tags.add(t)
        else:
            self.active_tags.discard(t)
        self.apply_filter()

    def _clear_tag_filter(self):
        self.active_tags.clear()
        self._fill_tag_filter()
        self.apply_filter()

    def _on_tags_changed(self):
        self.data_rev += 1
        if hasattr(self, "home"):
            self.home.cards["tags"].set_value(len(self.db.all_tags()))
        self._rebuild_search_text(self.details.assets)
        self._fill_tag_filter()
        for a in self.details.assets:
            self.model.refresh_key(a.key)

    # ----------------------------------------------------------------- seleção
    def selected_assets(self) -> list[Asset]:
        return [i.data(ASSET_ROLE) for i in self.grid.selectionModel().selectedIndexes()] if self.grid.selectionModel() else []

    def _on_selection(self, *_):
        self.details.set_assets(self.selected_assets())

    # ----------------------------------------------------------------- arrastar
    def drag_path_for(self, a: Asset, max_file: str | None = None) -> str | None:
        if a.kind == "missing":
            self.statusBar().showMessage(f"{a.name}: arquivo do modelo não encontrado.", 6000)
            return None
        if a.kind == "archive":
            self.statusBar().showMessage(f"{a.name} está compactado. Use 'Extrair para a biblioteca' primeiro.", 8000)
            return None
        mx = max_file or extractor.primary_max(a)
        if not mx:
            self.statusBar().showMessage(f"{a.name}: nenhum arquivo .max encontrado dentro.", 6000)
            return None
        from . import max_startup
        max_startup.write_handoff(a.name, mx, extractor.map_dirs(a))   # o script do Max religa depois do Merge
        self.db.record_use(a.key)
        return mx

    # ----------------------------------------------------------------- extração para a biblioteca
    def request_extraction(self, assets: list[Asset]):
        todo = [a for a in assets if a.kind == "archive"
                and not self.extractions.is_queued(a) and not self.extractions.is_running(a)]
        if not todo:
            return
        if not self.tools and any(a.archive_type != "zip" for a in todo):
            QMessageBox.warning(self, "Extrair", "WinRAR ou 7-Zip não foi encontrado neste computador.\n"
                                "Instale o WinRAR ou o 7-Zip (gratuito) para extrair arquivos RAR.")
            return
        if len(todo) > 1:
            size = sum(os.path.getsize(a.archive) for a in todo if a.archive and os.path.exists(a.archive))
            mins = self.backup_minutes()
            keep = ("Os compactados originais vão para a pasta de backup e são apagados de lá depois de "
                    + {60: "1 hora", 1440: "1 dia", 10080: "7 dias"}.get(mins, f"{mins} minutos") + "."
                    if mins > 0 else "Os compactados originais vão para a pasta de backup (não são apagados).")
            if QMessageBox.question(
                    self, "Extrair para a biblioteca",
                    f"Extrair {len(todo)} itens ({size / 1024 ** 3:.1f} GB compactados)?\n\n"
                    f"Cada um vira uma pasta com o .max e a pasta MAPS, ao lado da prévia.\n{keep}\n\n"
                    "Você pode continuar usando o programa enquanto extrai.") != QMessageBox.Yes:
                return
        locked, busy = self.try_lock([a.key for a in todo], "extraindo")
        todo = [a for a in todo if a.key in locked]
        for a in todo:
            self._ops[a.key] = "extrair"
        n = self.extractions.enqueue(todo)
        self.statusBar().showMessage(f"{n} item(ns) na fila de extração.")
        if busy:
            QMessageBox.information(self, "Em uso", "Estes itens estão sendo alterados por outra pessoa:\n\n"
                                    + "\n".join(busy))
        for a in todo:
            self.model.refresh_key(a.key)
        self.details.refresh()

    def request_organize(self, assets: list[Asset]):
        todo = [a for a in assets if self.layout_issues(a)
                and not self.extractions.is_queued(a) and not self.extractions.is_running(a)]
        if not todo:
            return
        if len(todo) > 1:
            if QMessageBox.question(
                    self, "Organizar pastas",
                    f"Organizar {len(todo)} pastas no padrão?\n\n"
                    "• .max na raiz da pasta, com uma cópia da prévia com o mesmo nome\n"
                    "• todo o resto dentro de MAPS (nenhuma textura é renomeada)\n"
                    "• cópias idênticas de arquivos são removidas\n\n"
                    "No fim, você revisa o que pode ser apagado (V-Ray, FBX, OBJ).") != QMessageBox.Yes:
                return
        locked, busy = self.try_lock([a.key for a in todo], "organizando")
        todo = [a for a in todo if a.key in locked]
        for a in todo:
            self._ops[a.key] = "organizar"
        n = self.extractions.enqueue(todo, op="organize")
        self.statusBar().showMessage(f"{n} pasta(s) na fila para organizar.")
        if busy:
            QMessageBox.information(self, "Em uso", "Estas pastas estão sendo alteradas por outra pessoa:\n\n"
                                    + "\n".join(busy))
        for a in todo:
            self.model.refresh_key(a.key)
        self.details.refresh()

    def _on_extract_started(self, key):
        self.model.refresh_key(key)
        done, total = self.extractions.done_count(), self.extractions.total
        self.progress.setRange(0, total)
        self.progress.setValue(done)
        self.progress.show()
        self.statusBar().showMessage(f"Processando {key.split('/')[-1]}…  ({done + 1} de {total})")

    def _on_extract_finished(self, res):
        if res.needs_password and self._ask_password(res):
            return
        if res.ok and res.used_password and res.used_password not in self.passwords:
            self.passwords.insert(0, res.used_password)  # senha nova que funcionou: guarda para os próximos
            self.cfg.save()
        self._pwd_tries.pop(res.key, None)
        op = self._ops.pop(res.key, "extrair")
        if res.ok:
            extra = {"base": rede.rel(self.cfg["library_root"], res.dest)} if op == "organizar" and res.dest else None
            self.log_op(op, res.category, res.key, res.name, res.moves, res.created, extra)
        self.shared.release(res.key)
        if res.ok:
            self.refresh_category(res.category.split("/")[0])
            self.statusBar().showMessage(f"{res.name} pronto.", 4000)
        else:
            self.model.refresh_key(res.key)
            self.statusBar().showMessage(f"{res.name}: {res.message}", 10000)
        self.details.refresh()

    def _ask_password(self, res) -> bool:
        """Pede a senha e recoloca o item na fila. Retorna False se o usuário cancelar."""
        asset = next((a for a in self.all_assets if a.key == res.key), None)
        if asset is None:
            return False
        tries = self._pwd_tries.get(res.key, 0)
        msg = (f"<b>{res.name}</b> está protegido por senha.<br><br>"
               + ("<span style='color:#e05252'>A senha digitada não funcionou. Tente de novo.</span><br><br>" if tries
                  else (f"As {len(self.passwords)} senha(s) salva(s) não serviram.<br><br>" if self.passwords else ""))
               + "Digite a senha (ela fica salva e será testada automaticamente nos próximos arquivos):")
        dlg = QInputDialog(self)
        dlg.setWindowTitle("Arquivo com senha")
        dlg.setLabelText(msg)
        dlg.setTextEchoMode(QLineEdit.Normal)
        dlg.setOkButtonText("Extrair")
        dlg.setCancelButtonText("Pular este item")
        dlg.resize(460, 160)
        if dlg.exec() != QDialog.Accepted or not dlg.textValue():
            res.message = "Arquivo protegido por senha (pulado)."
            self._pwd_tries.pop(res.key, None)
            return False
        self._pwd_tries[res.key] = tries + 1
        try:
            self.extractions.results.remove(res)
        except ValueError:
            pass
        self.extractions.enqueue([asset], extra_password=dlg.textValue(), retry=True)
        self.model.refresh_key(res.key)
        return True

    def _on_batch_done(self, results: list):
        self.progress.hide()
        ok = [r for r in results if r.ok]
        fail = [r for r in results if not r.ok]
        review = [r for r in ok if r.vray_to_suggest or r.unwanted or r.warnings]
        if review or fail:
            ReviewDialog(self, ok, fail).exec()
        self.statusBar().showMessage(f"Extração concluída: {len(ok)} ok" + (f", {len(fail)} com erro" if fail else ""), 8000)

    def forget_image(self, path: str | None):
        """Esquece a imagem guardada na memória (miniatura e banner) para ela ser lida de novo."""
        if not path:
            return
        self.thumbs.reload([path])
        if hasattr(self, "home"):
            self.home.banner_images.mem.pop(path, None)

    def refresh_category(self, top_key: str):
        """Relê só uma categoria (depois de extrair) e atualiza a tela."""
        self.__dict__.pop("_maps_count", None)
        old = next((c for c in self._all_cats if c.key == top_key), None)
        if not old:
            return
        # prévias podem ter sido trocadas (aqui, por outra pessoa ou por um desfazer): relê as imagens dela
        pre = os.path.normcase(os.path.join(old.path, ""))
        self.thumbs.reload([k for k in list(self.thumbs.mem) if os.path.normcase(k).startswith(pre)])
        if hasattr(self, "home"):
            bm = self.home.banner_images.mem
            for k in [k for k in bm if os.path.normcase(k).startswith(pre)]:
                bm.pop(k, None)
        self.schedule_dups(20000)
        new = scan_category(old.path, old.key, old.name)
        if hasattr(self, "_sigs"):
            self._sigs[new.key] = indice.signature(new, new.path)
        self._replace_category(new)
        if not (getattr(self, "_verify", None) and self._verify.isRunning()):
            QTimer.singleShot(1500, self._save_index)

    def _replace_category(self, new: Category | None):
        """Coloca a categoria relida no lugar da antiga (ou acrescenta, se for nova) e atualiza a tela."""
        self.data_rev += 1
        self.__dict__.pop("_maps_count", None)
        if new is not None:
            i = next((k for k, c in enumerate(self._all_cats) if c.key == new.key), None)
            if i is None:
                self._all_cats.append(new)
                from .scanner import natural_key
                self._all_cats.sort(key=lambda c: natural_key(c.name))
            else:
                self._all_cats[i] = new
        self._apply_visibility()
        self._rebuild_search_text(new.all_assets() if new is not None else None)
        self._fill_category_tree()
        self.apply_filter()

    def _clean_backup(self):
        root = self.cfg["library_root"]
        if root and os.path.isdir(root):
            extractor.clean_backup(root, self.backup_minutes())
            intake.clean_discarded(root, self.backup_minutes())

    def eventFilter(self, obj, e):  # noqa: N802
        if obj is getattr(self, "_col_drop", None):
            from PySide6.QtCore import QEvent
            t = e.type()
            if t in (QEvent.DragEnter, QEvent.DragMove) and e.mimeData().hasFormat("application/x-archiva-itens"):
                e.acceptProposedAction()
                obj.setDown(True)
                return True
            if t == QEvent.DragLeave:
                obj.setDown(False)
                return True
            if t == QEvent.Drop and e.mimeData().hasFormat("application/x-archiva-itens"):
                obj.setDown(False)
                keys = [k for k in bytes(e.mimeData().data("application/x-archiva-itens")).decode("utf-8")
                        .split("\n") if k]
                e.acceptProposedAction()
                m = QMenu(self)
                head = m.addAction(f"Adicionar {len(keys)} item(ns) a…" if len(keys) > 1 else "Adicionar a…")
                head.setEnabled(False)
                sub = QMenu(m)
                self.colecoes.add_menu(sub, lambda: keys)
                for act in sub.actions():
                    m.addAction(act)
                m.exec(obj.mapToGlobal(QPoint(obj.width() - 20, obj.height() // 2)))
                return True
        return super().eventFilter(obj, e)

    def _setup_shortcuts(self):
        from PySide6.QtGui import QShortcut

        def viewer_for(view):
            ix = view.currentIndex()
            if ix.isValid():
                a = ix.data(ASSET_ROLE)
                if a and a.preview and os.path.exists(a.preview):
                    ImageViewer(self, a.preview, a.name).exec()

        for view in (self.grid, self.colecoes.grid, self.entrada.grid):
            sc = QShortcut(QKeySequence(Qt.Key_Space), view, context=Qt.WidgetShortcut)
            sc.activated.connect(lambda v=view: viewer_for(v))
        sc = QShortcut(QKeySequence(Qt.Key_Delete), self.entrada.grid, context=Qt.WidgetShortcut)
        sc.activated.connect(self.entrada.discard_selected)
        tagk = QAction(self)
        tagk.setShortcut(QKeySequence("Ctrl+T"))
        tagk.triggered.connect(self._focus_tags)
        self.addAction(tagk)

    def _focus_tags(self):
        self.tabs.setCurrentWidget(self.splitter)
        if self.details.assets:
            self.details.tag_input.setFocus()
        else:
            self.statusBar().showMessage("Selecione um ou mais itens para colocar tags.", 4000)

    # ----------------------------------------------------------------- pastas escondidas (por pessoa)
    def hidden_keys(self) -> set[str]:
        root = os.path.normcase(os.path.normpath(self.cfg["library_root"] or ""))
        return set((self.cfg["pastas_ocultas"] or {}).get(root, []))

    def set_hidden_keys(self, keys) -> None:
        root = os.path.normcase(os.path.normpath(self.cfg["library_root"] or ""))
        d = dict(self.cfg["pastas_ocultas"] or {})
        d[root] = sorted(keys)
        self.cfg["pastas_ocultas"] = d

    def _apply_visibility(self):
        """Monta a lista visível (sem as pastas que a pessoa escondeu) e os atalhos por chave."""
        import copy
        hidden = self.hidden_keys()

        def keep(c: Category):
            if c.key in hidden:
                return None
            kids = [k for k in (keep(ch) for ch in c.children) if k is not None]
            if kids == c.children:
                return c
            n = copy.copy(c)
            n.children = kids
            return n

        self.categories = [k for k in (keep(c) for c in self._all_cats) if k is not None]
        self.cat_by_key = {}
        self.all_assets = []

        def walk(c: Category):
            self.cat_by_key[c.key] = c
            for ch in c.children:
                walk(ch)

        for c in self.categories:
            walk(c)
            self.all_assets.extend(c.all_assets())
        self.data_rev += 1

    def edit_visible_folders(self, parent=None):
        from .pastas_visiveis import VisibleFoldersDialog
        d = VisibleFoldersDialog(parent or self, self._all_cats, self.hidden_keys())
        if d.exec() != QDialog.Accepted:
            return
        self.set_hidden_keys(d.hidden())
        self._apply_visibility()
        self._rebuild_search_text()
        self._fill_category_tree()
        self._fill_tag_filter()
        self.entrada.fill_categories()
        self.home.refresh()
        self.apply_filter()
        n = len(d.hidden())
        self.statusBar().showMessage(f"{n} pasta(s) escondida(s)." if n else "Todas as pastas estão visíveis.", 6000)

    def _bump(self):
        self.data_rev += 1

    def _on_tab(self, i):
        self.sidebar.set_current(self.tabs.key_of(self.tabs.widget(i)))
        if self.tabs.widget(i) is self.entrada:
            self.entrada.refresh()
        elif self.tabs.widget(i) is self.home:
            if getattr(self.home, "_rev", -1) != self.data_rev:     # só refaz se algo mudou
                self.home.refresh()
        elif self.tabs.widget(i) is getattr(self, "tags_page", None):
            self.tags_page.refresh()
        elif self.tabs.widget(i) is getattr(self, "colecoes", None):
            self.colecoes.refresh()
        elif self.tabs.widget(i) is getattr(self, "organizacao", None):
            self.organizacao.refresh()

    def _tree_item(self, key):
        # sem QTreeWidgetItemIterator: no PySide6 ele deixava a árvore instável e o programa fechava
        # ao recriar a lista de categorias (depois de extrair/classificar)
        stack = [self.cat_tree.topLevelItem(i) for i in range(self.cat_tree.topLevelItemCount())]
        while stack:
            item = stack.pop(0)
            if item.data(0, Qt.UserRole) == key:
                return item
            stack[:0] = [item.child(i) for i in range(item.childCount())]
        return None

    def open_library(self, mode: str = "all", cat_key: str | None = None, tag: str | None = None,
                     text: str = ""):
        """Abre a aba Biblioteca com um filtro (usado pelos cartões, busca e tags da página inicial)."""
        self.search.blockSignals(True)
        self.search.setText(text)
        self.search.blockSignals(False)
        self.active_tags.clear()
        if tag:
            self.active_tags.add(tag)
        self._fill_tag_filter()
        i = self.show_filter.findData(mode)
        self.show_filter.blockSignals(True)
        self.show_filter.setCurrentIndex(i if i >= 0 else 0)
        self.show_filter.blockSignals(False)
        self.cfg.values["show_filter"] = self.show_filter.currentData()
        item = self._tree_item(cat_key or ALL_KEY)
        self.tabs.setCurrentWidget(self.splitter)
        if item is not None and item is not self.cat_tree.currentItem():
            self.cat_tree.setCurrentItem(item)   # dispara apply_filter
        else:
            self.apply_filter()
        self.grid.scrollToTop()

    def show_item(self, key: str):
        """Abre o item na Biblioteca, selecionado (clique no banner / recentes)."""
        a = next((x for x in self.all_assets if x.key == key), None)
        if a is None:
            return
        self.open_library("all", a.category)
        r = self.model.row_of.get(key)
        if r is not None:
            idx = self.model.index(r)
            self.grid.selectionModel().select(idx, self.grid.selectionModel().SelectionFlag.ClearAndSelect)
            self.grid.setCurrentIndex(idx)
            self.grid.scrollTo(idx, QAbstractItemView.PositionAtCenter)

    def refresh_all(self):
        self.start_scan(full=True)
        self.entrada.refresh()

    def status_html(self, a: Asset) -> str:
        ok, warn, busy, bad, org = (theme.OK.name(), theme.WARN.name(), theme.BUSY.name(), theme.BAD.name(),
                                    theme.ORG.name())
        if a.kind == "missing":
            st = f"<span style='color:{bad}'>sem arquivo do modelo</span>"
        elif self.extractions.is_running(a):
            st = f"<span style='color:{busy}'>extraindo para a biblioteca…</span>"
        elif self.extractions.is_queued(a):
            st = f"<span style='color:{busy}'>na fila de extração</span>"
        elif self.extractions.is_ready(a):
            st = f"<span style='color:{ok}'>pronto para arrastar</span>"
        else:
            st = f"<span style='color:{warn}'>compactado ({(a.archive_type or '').upper()}), precisa extrair</span>"
        rows = [("Situação", st)]
        mx = extractor.primary_max(a) if a.kind in ("folder", "max") else None
        if mx:
            n = len(a.max_files)
            rows.append(("Arquivo", os.path.basename(mx) + (f"  ·  {n} variações" if n > 1 else "")))
        if a.folder:
            cache = self.__dict__.setdefault("_maps_count", {})
            if a.folder not in cache:
                maps = os.path.join(a.folder, "MAPS")
                try:
                    cache[a.folder] = sum(len(fs) for _r, _d, fs in os.walk(maps)) if os.path.isdir(maps) else 0
                except OSError:
                    cache[a.folder] = 0
            nm = cache[a.folder]
            if nm:
                rows.append(("Texturas", f"MAPS, {nm} arquivo{'s' if nm != 1 else ''}"))
        elif a.archive:
            try:
                rows.append(("Tamanho", f"{os.path.getsize(a.archive) / 1024 ** 2:.0f} MB"))
            except OSError:
                pass
        faint = theme.FAINT.name()
        html = "<table cellspacing='0' cellpadding='3'>" + "".join(
            f"<tr><td style='color:{faint}; padding-right:16px'>{k}</td><td>{v}</td></tr>" for k, v in rows) + "</table>"
        li = self.layout_issues(a)
        if li:
            html += (f"<p style='color:{org}; margin-top:8px'>Pasta fora do padrão:<br>"
                     + "<br>".join("• " + i for i in li) + "</p>")
        if a.issues:
            html += f"<p style='color:{warn}'>" + "<br>".join("⚠ " + i for i in a.issues) + "</p>"
        return html

    def layout_issues(self, a: Asset) -> list[str]:
        """Motivos de 'fora do padrão', menos o que o usuário já decidiu manter (V-Ray/FBX)."""
        if not a.layout_issues:
            return []
        if self.db.has_flag(a.key, "manter_extras"):
            return [i for i in a.layout_issues
                    if not i.startswith("Versão V-Ray") and not i.startswith("Arquivos desnecessários")]
        return a.layout_issues

    # ----------------------------------------------------------------- ações
    def reveal(self, path: str | None):
        if not path:
            return
        if os.name == "nt":
            subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(path)))

    def open_location(self, a: Asset):
        if a is None:
            return
        self.reveal(extractor.primary_max(a) or a.folder or a.archive or a.loose_max or a.preview)

    def _context_menu(self, pos):
        idx = self.grid.indexAt(pos)
        if not idx.isValid():
            return
        a: Asset = idx.data(ASSET_ROLE)
        sel = self.selected_assets() or [a]
        m = QMenu(self)
        archives = [x for x in sel if x.kind == "archive"]
        messy = [x for x in sel if self.layout_issues(x)]
        if archives:
            m.addAction(f"Extrair para a biblioteca ({len(archives)})" if len(archives) > 1
                        else "Extrair para a biblioteca", lambda: self.request_extraction(archives))
        if messy:
            m.addAction(f"Organizar pasta ({len(messy)})" if len(messy) > 1 else "Organizar pasta",
                        lambda: self.request_organize(messy))
        if archives or messy:
            m.addSeparator()
        m.addAction("Mostrar no Explorer", lambda: self.open_location(a))
        if a.preview:
            m.addAction("Abrir imagem de prévia", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(a.preview)))
        mx = extractor.primary_max(a)
        if mx:
            m.addAction("Copiar caminho do .max", lambda: QApplication.clipboard().setText(mx))
        m.addSeparator()
        m.addAction("Editar tags…", lambda: self.details.tag_input.setFocus())
        cm = m.addMenu("Adicionar à coleção")
        self.colecoes.add_menu(cm, lambda: [x.key for x in sel])
        m.addSeparator()
        from .organizar import fill_category_menu
        mv = m.addMenu("Mover para…")
        fill_category_menu(mv, self.categories, lambda c: self.organizacao.move_assets(sel, c))
        if len(sel) == 1:
            pv = m.addMenu("Atualizar prévia")
            from . import previa
            pv.addAction("Buscar no PC…", lambda: previa.update_from_pc(self, a))
            from . import busca_web
            pv.addAction("Buscar na web…", lambda: busca_web.search(self, a))
        if len(sel) == 1 and a.folder and a.dup_archive:
            m.addAction("Comparar pasta e compactado…", lambda: self.compare_duplicate(a))
        if self.is_admin() or self.shared.lib is None:
            m.addSeparator()
            m.addAction(f"Excluir {len(sel)} itens…" if len(sel) > 1 else "Excluir item…",
                        lambda: self.delete_assets(sel))
        m.exec(self.grid.viewport().mapToGlobal(pos))

    def compare_duplicate(self, a: Asset):
        from . import duplicado
        duplicado.resolve(self, a)

    def delete_assets(self, assets: list[Asset]):
        """Exclui itens da biblioteca (só administrador). Vão para _DESCARTADOS; tags e coleções saem junto
        e voltam se a exclusão for desfeita pelo histórico."""
        assets = [x for x in assets if x.members]
        if not assets or not (self.is_admin() or self.shared.lib is None):
            return
        box = QMessageBox(self)
        box.setWindowTitle("Excluir da biblioteca")
        box.setIcon(QMessageBox.Warning)
        if len(assets) == 1 and assets[0].preview:
            pm = QPixmap(assets[0].preview)
            if not pm.isNull():
                box.setIconPixmap(pm.scaled(140, 140, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        nomes = ", ".join(x.name for x in assets[:6]) + (f" e mais {len(assets) - 6}" if len(assets) > 6 else "")
        mins = self.backup_minutes()
        prazo = ({60: "1 hora", 1440: "1 dia", 10080: "7 dias"}.get(mins, f"{mins} minutos")
                 if mins > 0 else "")
        box.setText(f"Tem certeza que quer excluir {nomes}?")
        box.setInformativeText(
            "O item some da biblioteca, das tags e das coleções para todos da equipe.\n\n"
            "Os arquivos vão para _BACKUP_COMPACTADOS\\_DESCARTADOS"
            + (f" e são apagados de vez depois de {prazo}." if prazo else ".")
            + " Até lá, dá para desfazer pelo Histórico.")
        yes = box.addButton("Excluir", QMessageBox.DestructiveRole)
        box.addButton("Cancelar", QMessageBox.RejectRole)
        box.exec()
        if box.clickedButton() is not yes:
            return
        root = self.cfg["library_root"]
        locked, busy = self.try_lock([x.key for x in assets], "excluindo")
        errors, tops = [], set()
        try:
            for x in assets:
                if x.key not in locked:
                    continue
                rec = []
                try:
                    intake.discard(x, root, rec)
                except OSError as e:
                    errors.append(f"{x.name}: {e}")
                    for src, dst in reversed(rec):          # devolve o que já tinha saído
                        try:
                            shutil.move(dst, src)
                        except OSError:
                            pass
                    continue
                tomb = "#excluido/" + x.key            # tags e coleções ficam guardadas aqui até o desfazer
                self.db.move_item_data(x.key, tomb)
                self.log_op("excluir", x.category, x.key, f"{x.name} excluído", rec, extra={"keys": [[x.key, tomb]]})
                tops.add(x.category.split("/")[0])
        finally:
            for k in locked:
                self.shared.release(k)
        for t in tops:
            self.refresh_category(t)
        msgs = busy + errors
        if msgs:
            QMessageBox.information(self, "Excluir", "Alguns itens não foram excluídos:\n\n" + "\n".join(msgs))

    def _category_menu(self, pos):
        it = self.cat_tree.itemAt(pos)
        if not it:
            return
        key = it.data(0, Qt.UserRole)
        pool = self.all_assets if key == ALL_KEY else (self.cat_by_key[key].all_assets() if key in self.cat_by_key else [])
        archives = [a for a in pool if a.kind == "archive"]
        m = QMenu(self)
        act = m.addAction(f"Extrair todos os compactados ({len(archives)})", lambda: self.request_extraction(archives))
        act.setEnabled(bool(archives))
        messy = [a for a in pool if self.layout_issues(a)]
        act2 = m.addAction(f"Organizar pastas fora do padrão ({len(messy)})", lambda: self.request_organize(messy))
        act2.setEnabled(bool(messy))
        if key != ALL_KEY and key in self.cat_by_key:
            m.addAction("Abrir pasta da categoria",
                        lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.cat_by_key[key].path)))
        m.exec(self.cat_tree.viewport().mapToGlobal(pos))

    def _set_size(self, v):
        self.thumb_size = v
        self.cfg.values["thumb_size"] = v
        if hasattr(self, "size_slider") and self.size_slider.value() != v:
            self.size_slider.blockSignals(True)
            self.size_slider.setValue(v)
            self.size_slider.blockSignals(False)
        self.grid.setGridSize(QSize())
        self.model.layoutChanged.emit()

    def _on_thumbs_changed(self):
        if not self._thumb_timer.isActive():
            self._thumb_timer.start()

    def _repaint_thumbs(self):
        self.grid.viewport().update()
        if len(self.details.assets) == 1:
            self.details.refresh()

    def export_tags(self):
        p, _ = QFileDialog.getSaveFileName(self, "Exportar tags", "tags_biblioteca.json", "JSON (*.json)")
        if p:
            n = self.db.export_json(Path(p))
            QMessageBox.information(self, "Exportar tags", f"{n} itens com tags exportados.")

    def import_tags(self):
        p, _ = QFileDialog.getOpenFileName(self, "Importar tags", "", "JSON (*.json)")
        if p:
            try:
                n = self.db.import_json(Path(p))
            except Exception as e:  # noqa: BLE001
                QMessageBox.warning(self, "Importar tags", f"Arquivo inválido: {e}")
                return
            self._rebuild_search_text()
            self._fill_tag_filter()
            self.details.update_completer()
            self.grid.viewport().update()
            QMessageBox.information(self, "Importar tags", f"Tags importadas para {n} itens.")

    def open_settings(self):
        d = SettingsDialog(self)
        if d.exec() != QDialog.Accepted:
            return
        self.cfg.values["backup_minutes"] = int(d.retention.currentData())
        if self.shared.lib is not None and self.shared.lib.is_admin():
            try:
                self.shared.lib.set_option("backup_minutes", int(d.retention.currentData()))
            except OSError:
                pass
        self.cfg.values["thumb_size"] = self.thumb_size
        key = d.vision.text().strip()
        if self.shared.lib is not None:
            if self.shared.lib.is_admin():
                try:
                    self.shared.lib.set_option("vision_key", key)
                except OSError:
                    pass
        else:
            self.cfg.values["vision_key"] = key
        self.cfg.values["titlebar"] = d.titlebar.currentData()
        self.cfg.values["tutorial_off"] = not d.intro.isChecked()
        self.cfg.values["abertura_off"] = not d.abertura.isChecked()
        self.cfg.values["check_updates"] = d.check_upd.isChecked()
        self.entrada.fill_categories()
        exts = [e.strip().lower() for e in d.unwanted.text().replace(";", ",").split(",") if e.strip()]
        self.cfg.values["unwanted_ext"] = [e if e.startswith(".") else "." + e for e in exts]
        self.extractions.unwanted_ext = list(self.cfg["unwanted_ext"])
        scanner_mod.UNWANTED_EXT = extractor._norm_exts(self.cfg["unwanted_ext"])
        root_changed = d.root.text().strip() != self.cfg["library_root"]
        self.cfg.values["library_root"] = d.root.text().strip()
        self.extractions.library_root = self.cfg["library_root"]
        self.cfg.save()
        self._clean_backup()
        self._update_footer()
        if root_changed:
            self.start_scan()

    def about(self):  # mantido por compatibilidade (o "Sobre" agora fica nas Configurações)
        QMessageBox.about(self, "Sobre", f"<b>{APP_NAME}</b> v{version()}<br><br>"
                          f"Biblioteca: {self.cfg['library_root']}<br>"
                          f"Miniaturas: {self.cache_root}<br>"
                          f"Banco de tags: {self.cfg.db_path}<br><br>"
                          "O programa só altera a biblioteca quando você usa <b>Extrair para a biblioteca</b>: "
                          "cria a pasta do modelo e move o compactado para "
                          f"{extractor.BACKUP_DIR}.")


# =========================================================================== revisão pós-extração

class ReviewDialog(QDialog):
    """Depois de extrair: sugere apagar versões V-Ray (quando há Corona junto) e FBX/OBJ."""

    def __init__(self, window: MainWindow, ok: list, fail: list):
        super().__init__(window)
        self.w = window
        self.setWindowTitle("Concluído — revisar")
        self.resize(760, 560)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 18)
        lay.setSpacing(14)

        if fail:
            msg = f"<b style='color:{theme.BAD.name()}'>Não foi possível concluir:</b><br>" + "<br>".join(
                f"• {r.name}: {r.message}" for r in fail)
            lbl = QLabel(msg)
            lbl.setWordWrap(True)
            lbl.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(lbl)

        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.checks: list[QTreeWidgetItem] = []
        for r in ok:
            if not (r.vray_to_suggest or r.unwanted or r.warnings):
                continue
            top = QTreeWidgetItem([r.name])
            f = top.font(0)
            f.setBold(True)
            top.setFont(0, f)
            self.tree.addTopLevelItem(top)
            if r.vray_to_suggest:
                g = QTreeWidgetItem(["Versões V-Ray (existe versão Corona junto) — apagar?"])
                top.addChild(g)
                for p in r.vray_to_suggest:
                    self._check(g, p, r.key)
            if r.unwanted:
                g = QTreeWidgetItem(["Arquivos " + "/".join(sorted({os.path.splitext(p)[1].upper()[1:] for p in r.unwanted}))
                                     + " — apagar?"])
                top.addChild(g)
                for p in r.unwanted:
                    self._check(g, p, r.key)
            for wmsg in r.warnings:
                top.addChild(QTreeWidgetItem(["⚠ " + wmsg]))
            top.setExpanded(True)
            for i in range(top.childCount()):
                top.child(i).setExpanded(True)
        if self.tree.topLevelItemCount():
            lay.addWidget(QLabel("Marque o que deseja <b>apagar</b> (os itens desmarcados ficam):"))
            lay.addWidget(self.tree, 1)

        bb = QDialogButtonBox()
        if self.checks:
            ui.primary(bb.addButton("Apagar marcados", QDialogButtonBox.AcceptRole))
            bb.addButton("Manter tudo", QDialogButtonBox.RejectRole)
        else:
            ui.primary(bb.addButton("OK", QDialogButtonBox.AcceptRole))
        bb.accepted.connect(self._apply)
        bb.rejected.connect(self._keep_all)
        lay.addWidget(bb)

    def _keep_all(self):
        self._remember_kept(all_kept=True)
        self.reject()

    def _remember_kept(self, all_kept: bool = False):
        """Itens em que o usuário escolheu manter V-Ray/FBX/OBJ não ficam mais marcados como 'fora do padrão'."""
        for it in self.checks:
            if all_kept or it.checkState(0) != Qt.Checked:
                self.w.db.set_flag(it.data(0, Qt.UserRole + 1), "manter_extras")
        self.w.grid.viewport().update()

    def _check(self, parent, path, key=None):
        it = QTreeWidgetItem([os.path.relpath(path, os.path.dirname(os.path.dirname(path)))])
        it.setData(0, Qt.UserRole, path)
        it.setData(0, Qt.UserRole + 1, key)
        it.setToolTip(0, path)
        it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
        it.setCheckState(0, Qt.Checked)
        parent.addChild(it)
        self.checks.append(it)

    def _apply(self):
        self._remember_kept()
        removed, errors, cats = 0, [], set()
        root = self.w.cfg["library_root"]
        bucket = os.path.join(root, intake.DISCARD_DIR, time.strftime("%Y%m%d-%H%M%S") + "__limpeza")
        per_item: dict[str, list] = {}

        def discard(path, key):     # vai para _DESCARTADOS (dá para desfazer até o prazo do backup)
            dst = os.path.join(bucket, os.path.relpath(path, root))
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            os.replace(path, dst)
            per_item.setdefault(key or os.path.dirname(path), []).append((path, dst))

        for it in self.checks:
            if it.checkState(0) != Qt.Checked:
                continue
            p = it.data(0, Qt.UserRole)
            key = it.data(0, Qt.UserRole + 1)
            try:
                discard(p, key)
                removed += 1
                if p.lower().endswith(".max"):  # leva junto a imagem com o mesmo nome do .max apagado
                    stem = os.path.splitext(p)[0]
                    for e in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG"):
                        if os.path.exists(stem + e):
                            try:
                                discard(stem + e, key)
                            except OSError:
                                pass
                d = os.path.dirname(p)
                while os.path.basename(d).upper() != "MAPS" and (os.sep + "MAPS" + os.sep) in (d.upper() + os.sep):
                    try:
                        os.rmdir(d)  # só remove se ficou vazia
                    except OSError:
                        break
                    d = os.path.dirname(d)
                cats.add(os.path.relpath(p, self.w.cfg["library_root"]).split(os.sep)[0])
            except OSError as e:
                errors.append(f"{os.path.basename(p)}: {e}")
        for key, moves in per_item.items():
            cat = key.rsplit("/", 1)[0] if "/" in key else ""
            self.w.log_op("limpar", cat, key, f"{key.split('/')[-1]} ({len(moves)} arquivo(s))", moves)
        for c in cats:
            self.w.refresh_category(c)
        if errors:
            QMessageBox.warning(self, "Revisar", "Alguns arquivos não puderam ser apagados:\n" + "\n".join(errors))
        if removed:
            self.w.statusBar().showMessage(f"{removed} arquivo(s) apagado(s).", 6000)
        self.accept()
