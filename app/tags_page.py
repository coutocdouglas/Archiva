"""Aba Tags — as tags como pastas (com grupos de um nível), uma prévia de capa e galeria de cada tag."""
from __future__ import annotations

import os

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, QSizeF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QLinearGradient, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QFrame, QHBoxLayout, QInputDialog, QLabel, QLineEdit,
                               QListView, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton,
                               QStackedWidget, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from . import theme, ui
from .database import clean_tag
from .janela import TITLE_H
from .home_page import edge_color
from .scanner import Asset, normalize

ACCENT = QColor("#e3cfa9")
CARD = QColor("#211a15")
CARD_HOVER = QColor("#29211b")
TILE_TOP = QColor("#f4f2ef")        # fundo enquanto a miniatura carrega
TILE_BOTTOM = QColor("#dfdbd5")

KIND_ROLE = Qt.UserRole            # "tag" | "group"
NAME_ROLE = Qt.UserRole + 1
COVERS_ROLE = Qt.UserRole + 2      # [caminho da prévia de capa]
COUNT_ROLE = Qt.UserRole + 3       # texto da quantidade


def tile_gradient(r: QRectF) -> QLinearGradient:
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0.0, TILE_TOP)
    g.setColorAt(1.0, TILE_BOTTOM)
    return g


def draw_preview(p: QPainter, page, path: str | None, cell: QRectF, radius: float = 8, zoom: float = 1.0):
    """Desenha a prévia inteira, como está na pasta, sobre a cor do próprio fundo (sem 'caixa' aparente)."""
    clip = QPainterPath()
    clip.addRoundedRect(cell, radius, radius)
    p.save()
    p.setClipPath(clip, Qt.IntersectClip)
    pix = page.w.thumbs.get(path) if path else None
    if pix:
        p.fillRect(cell, page.bg_of(path, pix))
        sz = QSizeF(pix.size()).scaled(cell.size(), Qt.KeepAspectRatio) * zoom
        tgt = QRectF(cell.center().x() - sz.width() / 2, cell.center().y() - sz.height() / 2, sz.width(), sz.height())
        p.drawPixmap(tgt, pix, QRectF(pix.rect()))
    else:
        p.fillRect(cell, tile_gradient(cell))
    p.restore()


# =========================================================================== pastas (tags e grupos)

class FolderDelegate(QStyledItemDelegate):
    W, H = 236, 262

    def __init__(self, page):
        super().__init__(page)
        self.page = page

    def sizeHint(self, option, index):
        return QSize(self.W, self.H)

    def paint(self, p: QPainter, option, index):
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        kind = index.data(KIND_ROLE)
        hover = bool(option.state & QStyle.State_MouseOver)
        r = QRectF(option.rect).adjusted(9, 9, -9, -9)
        body_col = CARD_HOVER if hover else CARD

        # formato de pasta: aba no alto à esquerda + corpo
        tab_h = 12
        tab = QPainterPath()
        tab.addRoundedRect(QRectF(r.left(), r.top(), r.width() * 0.42, tab_h + 10), 8, 8)
        tab_col = QColor("#8a6a4c") if kind == "group" else body_col.lighter(135)
        if kind == "group":
            tab_col.setAlpha(230)
        p.fillPath(tab, tab_col)
        body = QRectF(r.left(), r.top() + tab_h, r.width(), r.height() - tab_h)
        bp = QPainterPath()
        bp.addRoundedRect(body, 12, 12)
        p.fillPath(bp, body_col)
        if hover:
            p.setPen(QPen(QColor(91, 143, 214, 170), 1.5))
            p.drawPath(bp)

        # capa (uma prévia)
        covers = index.data(COVERS_ROLE) or []
        panel = QRectF(body.left() + 10, body.top() + 10, body.width() - 20, body.height() - 78)
        pp = QPainterPath()
        pp.addRoundedRect(panel, 9, 9)
        p.fillPath(pp, tile_gradient(panel))
        if covers:
            draw_preview(p, self.page, covers[0], panel, radius=9, zoom=1.04 if hover else 1.0)
        if not covers:
            p.setPen(theme.FAINT)
            p.drawText(panel, Qt.AlignCenter, "vazio")

        # textos
        name = index.data(NAME_ROLE) or ""
        x = body.left() + 14
        tw = body.width() - 28
        f = QFont(option.font)
        f.setPointSizeF(12)
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        label = name[:1].upper() + name[1:]
        p.setPen(theme.TEXT)
        p.drawText(QRectF(x, panel.bottom() + 10, tw, fm.height() + 2), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(label, Qt.ElideRight, int(tw)))
        f2 = QFont(option.font)
        f2.setPointSizeF(9.5)
        p.setFont(f2)
        p.setPen(theme.MUTED)
        p.drawText(QRectF(x, panel.bottom() + 12 + fm.height(), tw, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   index.data(COUNT_ROLE) or "")
        if kind == "group":
            f3 = QFont(option.font)
            f3.setPointSizeF(7.5)
            f3.setBold(True)
            p.setFont(f3)
            fm3 = QFontMetrics(f3)
            pill = QRectF(body.right() - fm3.horizontalAdvance("grupo") - 30, panel.bottom() + 14,
                          fm3.horizontalAdvance("grupo") + 16, 18)
            path = QPainterPath()
            path.addRoundedRect(pill, 9, 9)
            p.fillPath(path, QColor(227, 207, 169, 40))
            p.setPen(theme.LOGO)
            p.drawText(pill, Qt.AlignCenter, "grupo")
        p.restore()


# =========================================================================== galeria de uma tag

class GalleryDelegate(QStyledItemDelegate):
    S = 210          # lado da imagem

    def __init__(self, page):
        super().__init__(page)
        self.page = page

    def sizeHint(self, option, index):
        return QSize(self.S + 20, self.S + 66)

    def paint(self, p: QPainter, option, index):
        from .main_window import ASSET_ROLE
        a: Asset = index.data(ASSET_ROLE)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        hover = bool(option.state & QStyle.State_MouseOver)
        sel = bool(option.state & QStyle.State_Selected)
        r = QRectF(option.rect).adjusted(8, 8, -8, -8)
        img = QRectF(r.left(), r.top(), r.width(), r.width())
        draw_preview(p, self.page, a.preview, img, radius=12, zoom=1.035 if hover else 1.0)
        if sel:
            theme.paint_selection(p, img, 12)
        elif hover:
            path = QPainterPath()
            path.addRoundedRect(img.adjusted(0.75, 0.75, -0.75, -0.75), 12, 12)
            p.setPen(QPen(QColor(227, 207, 169, 120), 1.3))
            p.setBrush(Qt.NoBrush)
            p.drawPath(path)

        # estado (pronto / extrair) e capa
        col, label, busy, queued = self.page.w.grid.itemDelegate().status_for(a)
        dot = QRectF(img.right() - 20, img.top() + 10, 10, 10)
        p.setPen(QPen(QColor(255, 255, 255, 200), 1.5))
        p.setBrush(col)
        p.drawEllipse(dot)
        if a.key in self.page.cover_keys:
            badge = QRectF(img.left() + 10, img.top() + 8, 52, 18)
            bp = QPainterPath()
            bp.addRoundedRect(badge, 9, 9)
            p.fillPath(bp, QColor(20, 22, 25, 170))
            f = QFont(option.font)
            f.setPointSizeF(7.5)
            f.setBold(True)
            p.setFont(f)
            p.setPen(QColor("#f5d36b"))
            p.drawText(badge, Qt.AlignCenter, "★ capa")

        f = QFont(option.font)
        f.setPointSizeF(10.5)
        f.setBold(True)
        p.setFont(f)
        fm = QFontMetrics(f)
        p.setPen(theme.TEXT)
        p.drawText(QRectF(r.left() + 4, img.bottom() + 8, r.width() - 8, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(a.name, Qt.ElideRight, int(r.width() - 8)))
        f2 = QFont(option.font)
        f2.setPointSizeF(9)
        p.setFont(f2)
        fm2 = QFontMetrics(f2)
        p.setPen(theme.MUTED)
        from .main_window import pretty_category
        cat = pretty_category(a.category)
        extra = "  ·  compactado" if a.kind == "archive" else ""
        p.drawText(QRectF(r.left() + 4, img.bottom() + 10 + fm.height(), r.width() - 8, fm2.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, fm2.elidedText(cat + extra, Qt.ElideRight, int(r.width() - 8)))
        p.restore()


# =========================================================================== página

class TagsPage(QWidget):
    def __init__(self, window):
        super().__init__()
        from .main_window import AssetModel, AssetView
        self.w = window
        self.group: str | None = None          # grupo aberto (None = nível principal)
        self.tag: str | None = None            # tag aberta na galeria
        self.cover_keys: set[str] = set()
        self._bg: dict[str, QColor] = {}
        self._tagged: dict[str, list[Asset]] = {}

        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, TITLE_H + 8, 40, 12)
        lay.setSpacing(12)

        # cabeçalho: navegação + busca + ações
        top = QHBoxLayout()
        top.setSpacing(10)
        self.back = QPushButton("‹  Voltar")
        self.back.setCursor(Qt.PointingHandCursor)
        self.back.clicked.connect(self.go_back)
        
        self.crumb = QLabel()
        self.crumb.setStyleSheet("font-size:21pt;")
        self.crumb.setTextFormat(Qt.RichText)
        self.crumb.linkActivated.connect(self._crumb_link)
        self.sub = QLabel()
        self.sub.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:10.5pt; padding-top:8px;")
        top.addWidget(self.back)
        top.addWidget(self.crumb)
        top.addWidget(self.sub)
        top.addStretch(1)
        self.find = QLineEdit()
        self.find.setPlaceholderText("Buscar tag…")
        self.find.setClearButtonEnabled(True)
        self.find.setFixedWidth(260)

        self.find.textChanged.connect(lambda: self._find_timer.start())
        self._find_timer = QTimer(self, singleShot=True, interval=150)
        self._find_timer.timeout.connect(self.refresh)
        self.sort = QComboBox()
        self.sort.addItem("Mais itens primeiro", "count")
        self.sort.addItem("Nome (A–Z)", "name")
        self.sort.currentIndexChanged.connect(self.refresh)
        self.new_group = QPushButton("+  Novo grupo")
        self.new_group.setCursor(Qt.PointingHandCursor)
        ui.primary(self.new_group)
        self.new_group.clicked.connect(self._create_group)
        # ações da galeria
        self.lib_btn = QPushButton("Ver na Biblioteca")
        self.lib_btn.setCursor(Qt.PointingHandCursor)
        ui.primary(self.lib_btn)
        self.lib_btn.clicked.connect(lambda: self.w.open_library("all", tag=self.tag))
        self.tag_menu_btn = QPushButton("Opções ▾")
        self.tag_menu_btn.setCursor(Qt.PointingHandCursor)
        
        self.tag_menu_btn.clicked.connect(lambda: self._tag_menu(self.tag).exec(
            self.tag_menu_btn.mapToGlobal(self.tag_menu_btn.rect().bottomLeft())))
        for wdg in (self.find, self.sort, self.new_group, self.lib_btn, self.tag_menu_btn):
            top.addWidget(wdg)
        lay.addLayout(top)

        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        # pastas
        self.folders = QListWidget()
        self.folders.setViewMode(QListView.IconMode)
        self.folders.setResizeMode(QListView.Adjust)
        self.folders.setMovement(QListView.Static)
        self.folders.setGridSize(QSize(FolderDelegate.W, FolderDelegate.H))
        self.folders.setItemDelegate(FolderDelegate(self))
        self.folders.setMouseTracking(True)
        self.folders.setSelectionMode(QAbstractItemView.NoSelection)
        self.folders.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.folders.verticalScrollBar().setSingleStep(30)
        self.folders.setStyleSheet("QListWidget{background:transparent; border:none;}")
        self.folders.viewport().setCursor(Qt.PointingHandCursor)
        self.folders.itemClicked.connect(self._open_item)
        self.folders.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folders.customContextMenuRequested.connect(self._folders_menu)
        self.empty = QLabel("Ainda não há tags.\nNa Biblioteca, selecione itens e digite tags no painel da direita.")
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:11pt;")
        fw = QWidget()
        fl = QVBoxLayout(fw)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(self.folders)
        fl.addWidget(self.empty)
        self.stack.addWidget(fw)

        # galeria
        self.model = AssetModel(self.w.db)
        self.gallery = AssetView(self.w)
        self.gallery.setModel(self.model)
        self.gallery.setItemDelegate(GalleryDelegate(self))
        self.gallery.setSpacing(4)
        self.gallery.setStyleSheet("QListView{background:transparent; border:none;}")
        self.gallery.doubleClicked.connect(lambda idx: self.w.show_item(idx.data(Qt.UserRole + 1).key))
        self.gallery.customContextMenuRequested.connect(self._gallery_menu)
        self.gallery.setToolTip("Arraste para o 3ds Max · duplo clique abre na Biblioteca · botão direito: capa e opções")
        self.stack.addWidget(self.gallery)

        self.w.thumbs.changed.connect(lambda: self._repaint_timer.start())
        self._repaint_timer = QTimer(self, singleShot=True, interval=80)
        self._repaint_timer.timeout.connect(self._repaint)

    @staticmethod
    def _btn_css(flat: bool = False) -> str:
        if flat:
            return ("QPushButton{background:transparent; color:#c3c8ce; border:1px solid #3a3f46; border-radius:9px;"
                    " padding:7px 14px; font-size:13px;} QPushButton:hover{background:#2e3238; color:#fff;}")
        return ("QPushButton{background:#5b8fd6; color:white; border:none; border-radius:9px; padding:8px 16px;"
                " font-weight:600; font-size:13px;} QPushButton:hover{background:#6b9be0;}")

    # ----------------------------------------------------------------- dados auxiliares
    def bg_of(self, path: str, pix: QPixmap) -> QColor:
        if path not in self._bg:
            self._bg[path] = edge_color(pix)
        return self._bg[path]

    @staticmethod
    def _mt(a: Asset) -> float:
        """Data da prévia, lida junto com a listagem da pasta (sem perguntar ao servidor)."""
        if not a.preview:
            return 0.0
        return getattr(a, "preview_mtime", 0.0) or getattr(a, "added_time", 0.0) or 0.0

    def _collect(self):
        self._tagged = {}
        for a in self.w.all_assets:
            for t in self.w.db.tags_of(a.key):
                self._tagged.setdefault(t, []).append(a)

    def covers_for(self, tag: str) -> list[str]:
        """Capa: a escolhida pelo usuário; sem escolha, a prévia mais recente."""
        items = self._tagged.get(tag, [])
        by_key = {a.key: a for a in items}
        out = [by_key[k].preview for k in self.w.db.covers(tag) if k in by_key and by_key[k].preview]
        for a in sorted((a for a in items if a.preview), key=self._mt, reverse=True):
            if len(out) >= 1:
                break
            if a.preview not in out:
                out.append(a.preview)
        return out[:1]

    # ----------------------------------------------------------------- navegação
    def refresh(self):
        self._collect()
        if self.tag is not None and self.tag not in self._tagged:
            self.tag = None
        if self.group is not None and self.group not in self.w.db.groups():
            self.group = None
        if self.tag is not None:
            self._show_gallery()
        else:
            self._show_folders()

    def open_tag(self, tag: str):
        self._collect()
        self.tag = tag
        self.group = self.w.db.group_map().get(tag)
        self.w.tabs.setCurrentWidget(self)
        self._show_gallery()

    def go_back(self):
        if self.tag is not None:
            self.tag = None
        elif self.group is not None:
            self.group = None
        self.refresh()

    def _crumb_link(self, link: str):
        if link == "root":
            self.tag, self.group = None, None
        elif link == "group":
            self.tag = None
        self.refresh()

    def _crumbs(self, *parts):
        css = f"color:{theme.LINK.name()}; text-decoration:none;"
        html = [f'<a href="root" style="{css}">Tags</a>' if len(parts) else "Tags"]
        for i, (label, link) in enumerate(parts):
            label = label[:1].upper() + label[1:]
            if i < len(parts) - 1:
                html.append(f'<a href="{link}" style="{css}">{label}</a>')
            else:
                html.append(label)
        self.crumb.setText('<span style="color:#75695c;">  ›  </span>'.join(html))

    def _set_mode(self, gallery: bool):
        self.stack.setCurrentIndex(1 if gallery else 0)
        for wdg in (self.find, self.sort, self.new_group):
            wdg.setVisible(not gallery)
        self.new_group.setVisible(not gallery and self.group is None)
        self.lib_btn.setVisible(gallery)
        self.tag_menu_btn.setVisible(gallery)
        self.back.setVisible(gallery or self.group is not None)

    def _show_folders(self):
        self._set_mode(False)
        db = self.w.db
        gmap = db.group_map()
        q = normalize(self.find.text()).split()
        by_count = self.sort.currentData() == "count"
        self.folders.clear()

        def tag_item(t):
            n = len(self._tagged[t])
            it = QListWidgetItem()
            it.setData(KIND_ROLE, "tag")
            it.setData(NAME_ROLE, t)
            it.setData(COVERS_ROLE, self.covers_for(t))
            it.setData(COUNT_ROLE, f"{n} {'item' if n == 1 else 'itens'}"
                       + (f"  ·  {gmap[t]}" if q and gmap.get(t) and self.group is None else ""))
            it.setToolTip(f"{t} — {n} {'item' if n == 1 else 'itens'}")
            return it

        def sort_tags(tags):
            return sorted(tags, key=(lambda t: (-len(self._tagged[t]), t)) if by_count else (lambda t: t))

        tags = list(self._tagged)
        if q:                                            # busca: mostra as tags de todos os grupos
            tags = [t for t in tags if all(x in normalize(t) for x in q)]
            groups = [g for g in db.groups() if all(x in normalize(g) for x in q)] if self.group is None else []
        elif self.group is None:
            groups = db.groups()
            tags = [t for t in tags if not gmap.get(t)]
        else:
            groups = []
            tags = [t for t in tags if gmap.get(t) == self.group]
        if self.group is not None and q:
            tags = [t for t in tags if gmap.get(t) == self.group]

        group_rows = []
        for g in groups:
            members = [t for t in self._tagged if gmap.get(t) == g]
            keys = {a.key for t in members for a in self._tagged[t]}
            group_rows.append((g, members, len(keys)))
        if by_count:
            group_rows.sort(key=lambda x: (-x[2], x[0].lower()))
        for g, members, n_items in group_rows:
            covers = []
            for t in sort_tags(members):
                c = self.covers_for(t)
                if c and c[0] not in covers:
                    covers.append(c[0])
                if len(covers) >= 1:
                    break
            it = QListWidgetItem()
            it.setData(KIND_ROLE, "group")
            it.setData(NAME_ROLE, g)
            it.setData(COVERS_ROLE, covers)
            it.setData(COUNT_ROLE, f"{len(members)} {'tag' if len(members) == 1 else 'tags'}  ·  {n_items} itens")
            it.setToolTip(f"Grupo {g}")
            self.folders.addItem(it)
        for t in sort_tags(tags):
            self.folders.addItem(tag_item(t))

        total = len(self._tagged)
        if self.group is None:
            self._crumbs()
            ng = len(db.groups())
            self.sub.setText(f"{total} {'tag' if total == 1 else 'tags'}" + (f"  ·  {ng} {'grupo' if ng == 1 else 'grupos'}" if ng else ""))
        else:
            self._crumbs((self.group, "group"))
            self.sub.setText(f"{len(tags)} {'tag' if len(tags) == 1 else 'tags'} neste grupo")
        has = self.folders.count() > 0
        self.folders.setVisible(has)
        self.empty.setVisible(not has)
        if not has:
            self.empty.setText("Nenhuma tag encontrada." if q else (
                "Este grupo está vazio.\nClique com o botão direito numa tag › Mover para grupo." if self.group
                else "Ainda não há tags.\nNa Biblioteca, selecione itens e digite tags no painel da direita."))

    def _show_gallery(self):
        self._set_mode(True)
        t = self.tag
        items = sorted(self._tagged.get(t, []), key=self._mt, reverse=True)
        self.cover_keys = set(self.w.db.covers(t))
        self.model.set_assets(items)
        parts = [(self.group, "group")] if self.group else []
        self._crumbs(*parts, (t, "tag"))
        n = len(items)
        ready = sum(1 for a in items if a.kind in ("folder", "max"))
        self.sub.setText(f"{n} {'item' if n == 1 else 'itens'}  ·  {ready} "
                         f"{'pronto' if ready == 1 else 'prontos'} para usar")
        self.gallery.scrollToTop()

    def _open_item(self, it: QListWidgetItem):
        if it.data(KIND_ROLE) == "group":
            self.group = it.data(NAME_ROLE)
            self.find.clear()
            self.refresh()
        else:
            self.tag = it.data(NAME_ROLE)
            self.group = self.w.db.group_map().get(self.tag)
            self._show_gallery()

    def _repaint(self):
        if self.isVisible():
            self.folders.viewport().update()
            self.gallery.viewport().update()

    # ----------------------------------------------------------------- menus e ações
    def _folders_menu(self, pos):
        it = self.folders.itemAt(pos)
        m = QMenu(self)
        if it is None:
            if self.group is None:
                m.addAction("Novo grupo…", self._create_group)
            else:
                m.addAction("Voltar", self.go_back)
        elif it.data(KIND_ROLE) == "group":
            g = it.data(NAME_ROLE)
            m.addAction("Abrir", lambda: self._open_item(it))
            m.addAction("Renomear grupo…", lambda: self._rename_group(g))
            m.addSeparator()
            m.addAction("Desfazer grupo (as tags continuam existindo)", lambda: self._delete_group(g))
        else:
            m = self._tag_menu(it.data(NAME_ROLE), with_open=True)
        m.exec(self.folders.viewport().mapToGlobal(pos))

    def _tag_menu(self, tag: str, with_open: bool = False) -> QMenu:
        m = QMenu(self)
        if with_open:
            m.addAction("Abrir galeria", lambda: self.open_tag(tag))
        m.addAction("Ver na Biblioteca", lambda: self.w.open_library("all", tag=tag))
        m.addSeparator()
        m.addAction("Renomear tag…", lambda: self._rename_tag(tag))
        m.addAction("Juntar com outra tag…", lambda: self._merge_tag(tag))
        gm = m.addMenu("Mover para grupo")
        cur = self.w.db.group_map().get(tag)
        for g in self.w.db.groups():
            a = gm.addAction(g, lambda g=g: self._move_to_group(tag, g))
            a.setCheckable(True)
            a.setChecked(g == cur)
        if self.w.db.groups():
            gm.addSeparator()
        gm.addAction("Novo grupo…", lambda: self._move_to_group(tag, None, new=True))
        if cur:
            gm.addAction("Tirar do grupo", lambda: self._move_to_group(tag, None))
        if self.w.db.covers(tag):
            m.addAction("Capa: voltar ao automático", lambda: (self.w.db.remove_cover(tag), self.refresh()))
        m.addSeparator()
        m.addAction("Excluir tag…", lambda: self._delete_tag(tag))
        return m

    def _gallery_menu(self, pos):
        from .main_window import ASSET_ROLE
        idx = self.gallery.indexAt(pos)
        if not idx.isValid():
            return
        sel = [i.data(ASSET_ROLE) for i in self.gallery.selectionModel().selectedIndexes()] or [idx.data(ASSET_ROLE)]
        a: Asset = idx.data(ASSET_ROLE)
        m = QMenu(self)
        m.addAction("Abrir na Biblioteca", lambda: self.w.show_item(a.key))
        m.addAction("Mostrar no Explorer", lambda: self.w.open_location(a))
        if any(x.kind == "archive" for x in sel):
            m.addAction("Extrair para a biblioteca", lambda: self.w.request_extraction([x for x in sel if x.kind == "archive"]))
        m.addSeparator()
        if a.key in self.cover_keys:
            m.addAction("Tirar da capa", lambda: self._cover(a, False))
        else:
            m.addAction("Usar como capa desta tag", lambda: self._cover(a, True))
        m.addSeparator()
        n = len(sel)
        m.addAction(f"Remover a tag “{self.tag}” {'deste item' if n == 1 else f'destes {n} itens'}",
                    lambda: self._untag(sel))
        m.exec(self.gallery.viewport().mapToGlobal(pos))

    def _cover(self, a: Asset, on: bool):
        if on:
            self.w.db.remove_cover(self.tag)          # uma capa só por tag
            self.w.db.add_cover(self.tag, a.key)
        else:
            self.w.db.remove_cover(self.tag, a.key)
        self.cover_keys = set(self.w.db.covers(self.tag))
        self.gallery.viewport().update()

    def _ask(self, title, label, text="") -> str | None:
        v, ok = QInputDialog.getText(self, title, label, QLineEdit.Normal, text)
        return v.strip() if ok and v.strip() else None

    def _changed(self):
        """Avisa o resto do programa que as tags mudaram."""
        w = self.w
        w._rebuild_search_text()
        w.active_tags &= {t for t, _ in w.db.all_tags()}
        w._fill_tag_filter()
        w.details.update_completer()
        w.details.refresh() if w.details.assets else None
        w.grid.viewport().update()
        w.home.cards["tags"].set_value(len(w.db.all_tags()))
        self.refresh()

    def _rename_tag(self, tag):
        new = self._ask("Renomear tag", f"Novo nome para “{tag}”:", tag)
        if not new or clean_tag(new) == tag:
            return
        new = clean_tag(new)
        if new in self._tagged and new != tag:
            if QMessageBox.question(self, "Renomear tag",
                                    f"Já existe a tag “{new}”.\nJuntar “{tag}” com “{new}”?") != QMessageBox.Yes:
                return
        self.w.db.rename_tag(tag, new)
        if self.tag == tag:
            self.tag = new
        self._changed()

    def _merge_tag(self, tag):
        others = sorted(t for t in self._tagged if t != tag)
        if not others:
            QMessageBox.information(self, "Juntar tags", "Não há outra tag para juntar.")
            return
        dst, ok = QInputDialog.getItem(self, "Juntar tags",
                                       f"Os itens de “{tag}” passam a usar a tag:\n(“{tag}” deixa de existir)",
                                       others, 0, True)
        dst = clean_tag(dst) if ok else ""
        if not dst or dst == tag:
            return
        self.w.db.merge_tags(tag, dst)
        if self.tag == tag:
            self.tag = dst
        self._changed()

    def _delete_tag(self, tag):
        n = len(self._tagged.get(tag, []))
        if QMessageBox.question(self, "Excluir tag",
                                f"Excluir a tag “{tag}” de {n} {'item' if n == 1 else 'itens'}?\n\n"
                                "Os modelos não são alterados — só a etiqueta é removida.") != QMessageBox.Yes:
            return
        self.w.db.delete_tag(tag)
        if self.tag == tag:
            self.tag = None
        self._changed()

    def _untag(self, assets):
        self.w.db.remove_tag([a.key for a in assets], self.tag)
        for a in assets:
            self.w.db.remove_cover(self.tag, a.key)
        self._changed()

    def _create_group(self):
        name = self._ask("Novo grupo", "Nome do grupo (ex.: Materiais, Estilos, Cores):")
        if name:
            self.w.db.create_group(name)
            self.refresh()

    def _rename_group(self, g):
        new = self._ask("Renomear grupo", f"Novo nome para o grupo “{g}”:", g)
        if new and new != g:
            self.w.db.rename_group(g, new)
            if self.group == g:
                self.group = new
            self.refresh()

    def _delete_group(self, g):
        if QMessageBox.question(self, "Desfazer grupo",
                                f"Desfazer o grupo “{g}”?\nAs tags dele voltam para a tela principal de Tags "
                                "(nenhuma tag é apagada).") != QMessageBox.Yes:
            return
        self.w.db.delete_group(g)
        if self.group == g:
            self.group = None
        self.refresh()

    def _move_to_group(self, tag, group, new=False):
        if new:
            group = self._ask("Novo grupo", "Nome do grupo (ex.: Materiais, Estilos, Cores):")
            if not group:
                return
            group = self.w.db.create_group(group)
        self.w.db.set_group([tag], group)
        self.refresh()
