"""Coleções de projeto: juntam os modelos usados num trabalho (ex.: "Apartamento Silva – Sala").

Diferente das tags (que dizem o que o modelo é), a coleção diz onde ele foi usado. Ficam na biblioteca
compartilhada (todos da equipe veem, com quem criou). Nada entra sozinho: a pessoa adiciona pelo painel,
pelo menu do cartão, arrastando o cartão até "Coleções" no menu lateral ou escolhendo na faixa
"Você usou recentemente".
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QKeySequence, QPainter, QPainterPath, QPen, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QCheckBox, QHBoxLayout, QInputDialog, QLabel, QListView,
                               QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton, QStackedWidget,
                               QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from . import theme, ui
from .janela import TITLE_H

RECENT_DAYS = 7


def when(t: float) -> str:
    d = datetime.fromtimestamp(t)
    today = datetime.now().date()
    if d.date() == today:
        return "hoje"
    if (today - d.date()).days == 1:
        return "ontem"
    return f"{d:%d/%m/%Y}"


# ------------------------------------------------------------------ lista de coleções
class _ColModel(QAbstractListModel):
    def __init__(self):
        super().__init__()
        self.rows: list[dict] = []

    def set_rows(self, rows):
        self.beginResetModel()
        self.rows = rows
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        c = self.rows[index.row()]
        if role == Qt.DisplayRole:
            return c["name"]
        if role == Qt.UserRole:
            return c
        if role == Qt.ToolTipRole:
            return c["note"] or None
        return None


class _ColDelegate(QStyledItemDelegate):
    W, H = 250, 322

    def __init__(self, page):
        super().__init__(page)
        self.page = page

    def sizeHint(self, option, index):
        return QSize(self.W, self.H)

    def paint(self, p: QPainter, option, index):
        from .tags_page import draw_preview
        c = index.data(Qt.UserRole)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        hover = bool(option.state & QStyle.State_MouseOver)
        sel = bool(option.state & QStyle.State_Selected)
        r = QRectF(option.rect).adjusted(8, 8, -8, -8)
        theme.paint_glass(p, r, 16, 1.0, hover)
        img = QRectF(r.left() + 10, r.top() + 10, r.width() - 20, r.width() - 20)
        cover = self.page.cover_of(c["id"])
        if cover:
            draw_preview(p, self.page, cover, img, radius=11, zoom=1.03 if hover else 1.0)
        else:
            path = QPainterPath()
            path.addRoundedRect(img, 11, 11)
            p.fillPath(path, QColor(255, 236, 210, 12))
            p.setPen(theme.FAINT)
            p.setFont(theme.ui_font(9.5))
            p.drawText(img, Qt.AlignCenter, "coleção vazia")
        if sel:
            theme.paint_selection(p, img, 11)
        y = img.bottom() + 12
        p.setPen(theme.TEXT)
        f = theme.ui_font(11)
        p.setFont(f)
        p.drawText(QRectF(r.left() + 14, y, r.width() - 28, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f).elidedText(c["name"], Qt.ElideRight, int(r.width() - 28)))
        p.setPen(theme.MUTED)
        p.setFont(theme.ui_font(9))
        who = self.page.user_name(c["created_by"])
        line = f"{c['count']} {'item' if c['count'] == 1 else 'itens'}  ·  {when(c['updated_at'])}"
        p.drawText(QRectF(r.left() + 14, y + 22, r.width() - 28, 18), Qt.AlignLeft | Qt.AlignVCenter, line)
        if who:
            p.setPen(theme.FAINT)
            p.drawText(QRectF(r.left() + 14, y + 40, r.width() - 28, 18), Qt.AlignLeft | Qt.AlignVCenter,
                       f"criada por {who}")
        p.restore()


class _ColView(QListView):
    """Grade de coleções que aceita cartões da Biblioteca soltos em cima de uma coleção."""
    dropped = Signal(str, list)

    def __init__(self):
        super().__init__()
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(4)
        self.setMouseTracking(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(False)
        self.setDragDropMode(QAbstractItemView.DropOnly)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.setContextMenuPolicy(Qt.CustomContextMenu)

    def dragEnterEvent(self, e):
        if e.mimeData().hasFormat(KEYS_MIME):
            e.acceptProposedAction()

    def dragMoveEvent(self, e):
        ix = self.indexAt(e.position().toPoint())
        if e.mimeData().hasFormat(KEYS_MIME) and ix.isValid():
            self.setCurrentIndex(ix)
            e.acceptProposedAction()
        else:
            e.ignore()

    def dropEvent(self, e):
        ix = self.indexAt(e.position().toPoint())
        if ix.isValid() and e.mimeData().hasFormat(KEYS_MIME):
            keys = bytes(e.mimeData().data(KEYS_MIME)).decode("utf-8").split("\n")
            self.dropped.emit(ix.data(Qt.UserRole)["id"], [k for k in keys if k])
            e.acceptProposedAction()


KEYS_MIME = "application/x-archiva-itens"


# ------------------------------------------------------------------ página
class ColecoesPage(QWidget):
    changed = Signal()

    def __init__(self, window):
        super().__init__()
        from .main_window import AssetModel, AssetView, CardDelegate
        self.w = window
        self._bg: dict[str, QColor] = {}
        self.cid: str | None = None
        self.show_archived = False

        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, TITLE_H + 8, 40, 16)
        lay.setSpacing(12)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        # ---- lista
        lst = QWidget()
        ll = QVBoxLayout(lst)
        ll.setContentsMargins(0, 0, 0, 0)
        ll.setSpacing(6)
        head = QHBoxLayout()
        t = QLabel("Coleções")
        t.setStyleSheet("font-size:24pt;")
        head.addWidget(t)
        head.addStretch(1)
        self.seg = ui.Segmented([("Ativas", "on"), ("Arquivadas", "off")])
        self.seg.currentIndexChanged.connect(lambda i: (setattr(self, "show_archived", i == 1), self.refresh()))
        head.addWidget(self.seg, 0, Qt.AlignBottom)
        head.addSpacing(8)
        self.btn_new = ui.primary(QPushButton("Nova coleção"))
        self.btn_new.clicked.connect(lambda: self.new_collection())
        head.addWidget(self.btn_new, 0, Qt.AlignBottom)
        ll.addLayout(head)
        s = QLabel("Junte os modelos usados em cada projeto. Para adicionar: painel da direita na Biblioteca, "
                   "botão direito no cartão, ou arraste o cartão até \"Coleções\" no menu lateral.")
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{theme.MUTED.name()};")
        ll.addWidget(s)
        ll.addSpacing(10)
        self.empty = QLabel("Nenhuma coleção ainda. Clique em \"Nova coleção\" para começar.")
        self.empty.setStyleSheet(f"color:{theme.FAINT.name()}; padding:40px;")
        self.empty.setAlignment(Qt.AlignCenter)
        ll.addWidget(self.empty)
        self.model = _ColModel()
        self.view = _ColView()
        self.view.setModel(self.model)
        self.view.setItemDelegate(_ColDelegate(self))
        self.view.clicked.connect(lambda ix: self.open(ix.data(Qt.UserRole)["id"]))
        self.view.customContextMenuRequested.connect(self._col_menu)
        self.view.dropped.connect(self.add_items)
        ll.addWidget(self.view, 1)
        self.stack.addWidget(lst)

        # ---- coleção aberta
        det = QWidget()
        dl = QHBoxLayout(det)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(6)
        top = QHBoxLayout()
        back = QPushButton("‹  Coleções")
        back.setCursor(Qt.PointingHandCursor)
        back.clicked.connect(self.close_collection)
        top.addWidget(back)
        top.addStretch(1)
        self.btn_menu = QPushButton("Opções")
        self.btn_menu.clicked.connect(lambda: self._detail_menu(self.btn_menu))
        top.addWidget(self.btn_menu)
        left.addLayout(top)
        self.title = QLabel()
        self.title.setStyleSheet("font-size:24pt;")
        left.addWidget(self.title)
        self.sub = QLabel()
        self.sub.setStyleSheet(f"color:{theme.MUTED.name()};")
        left.addWidget(self.sub)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color:{theme.LINK.name()}; padding-top:4px;")
        left.addWidget(self.note)
        left.addSpacing(8)
        self.items_model = AssetModel(window.db)
        self.grid = AssetView(window)
        self.grid.setModel(self.items_model)
        self.grid.setItemDelegate(CardDelegate(window))
        self.grid.setGridSize(QSize())
        self.grid.customContextMenuRequested.connect(self._item_menu)
        self.grid.setFocusPolicy(Qt.StrongFocus)
        left.addWidget(self.grid, 1)
        self.items_empty = QLabel("Coleção vazia. Adicione modelos pela Biblioteca ou pela lista ao lado.")
        self.items_empty.setStyleSheet(f"color:{theme.FAINT.name()}; padding:30px;")
        self.items_empty.setAlignment(Qt.AlignCenter)
        left.addWidget(self.items_empty)
        dl.addLayout(left, 1)

        side = ui.Glass(14)
        side.setFixedWidth(300)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 16, 16, 16)
        sl.setSpacing(10)
        sl.addWidget(ui.heading("Você usou recentemente", 11))
        hint = QLabel(f"Modelos que você arrastou para o 3ds Max nos últimos {RECENT_DAYS} dias e que ainda "
                      "não estão nesta coleção. Marque os que quer e adicione.")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:9.3pt;")
        sl.addWidget(hint)
        self.recent = QListWidget()
        self.recent.setIconSize(QSize(44, 44))
        self.recent.setSpacing(2)
        self.recent.setStyleSheet("QListWidget{background:transparent;border:none;}")
        self.recent.itemChanged.connect(self._update_recent_btn)
        sl.addWidget(self.recent, 1)
        self.recent_empty = QLabel("Nada recente por aqui.")
        self.recent_empty.setStyleSheet(f"color:{theme.FAINT.name()};")
        sl.addWidget(self.recent_empty)
        self.btn_add_recent = ui.primary(QPushButton("Adicionar marcados"))
        self.btn_add_recent.clicked.connect(self._add_recent)
        sl.addWidget(self.btn_add_recent)
        dl.addWidget(side)
        self.stack.addWidget(det)

        sc = QShortcut(QKeySequence(Qt.Key_Delete), self.grid, context=Qt.WidgetShortcut)
        sc.activated.connect(self.remove_selected)

    # ------------------------------------------------------------------ dados
    def user_name(self, uid: str) -> str:
        lib = self.w.shared.lib
        if not uid:
            return ""
        if self.w.profile and uid == self.w.profile.get("id"):
            return "você"
        if lib is None:
            return ""
        return lib.users().get(uid, {}).get("nome", "")

    def bg_of(self, path, pix):
        c = self._bg.get(path)
        if c is None:
            from .home_page import edge_color
            c = self._bg[path] = edge_color(pix)
        return c

    def cover_of(self, cid: str) -> str | None:
        by_key = {a.key: a for a in self.w.all_assets}
        for k in self.w.db.collection_items(cid):
            a = by_key.get(k)
            if a and a.preview:
                return a.preview
        return None

    def refresh(self):
        rows = self.w.db.collections(self.show_archived)
        self.model.set_rows(rows)
        self.empty.setVisible(not rows)
        self.empty.setText("Nenhuma coleção arquivada." if self.show_archived else
                           "Nenhuma coleção ainda. Clique em \"Nova coleção\" para começar.")
        self.view.setVisible(bool(rows))
        if self.cid:
            self._fill_detail()

    # ------------------------------------------------------------------ ações
    def new_collection(self, keys: list[str] | None = None) -> str | None:
        name, ok = QInputDialog.getText(self.w, "Nova coleção", "Nome da coleção (ex.: Apartamento Silva – Sala):")
        if not ok or not name.strip():
            return None
        cid = uuid.uuid4().hex[:12]
        uid = (self.w.profile or {}).get("id", "")
        self.w.db.create_collection(cid, name.strip(), uid)
        if keys:
            self.w.db.add_to_collection(cid, keys, uid)
        self.refresh()
        self.changed.emit()
        return cid

    def add_items(self, cid: str, keys: list[str]):
        if not keys:
            return
        self.w.db.add_to_collection(cid, keys, (self.w.profile or {}).get("id", ""))
        c = self.w.db.collection(cid)
        self.w.statusBar().showMessage(f"{len(keys)} item(ns) adicionado(s) a \"{c['name'] if c else ''}\".", 6000)
        self.refresh()
        self.changed.emit()

    def add_menu(self, menu: QMenu, keys_fn):
        """Preenche um menu "Adicionar à coleção" (usado no painel e no clique direito)."""
        menu.clear()
        cols = self.w.db.collections(False)
        for c in cols[:20]:
            menu.addAction(c["name"], lambda cid=c["id"]: self.add_items(cid, keys_fn()))
        if cols:
            menu.addSeparator()
        menu.addAction("Nova coleção…", lambda: self.new_collection(keys_fn()))

    def open(self, cid: str):
        self.cid = cid
        self.stack.setCurrentIndex(1)
        self._fill_detail()
        self.grid.setFocus()

    def close_collection(self):
        self.cid = None
        self.stack.setCurrentIndex(0)
        self.refresh()

    def _fill_detail(self):
        c = self.w.db.collection(self.cid) if self.cid else None
        if not c:
            self.close_collection()
            return
        by_key = {a.key: a for a in self.w.all_assets}
        keys = self.w.db.collection_items(self.cid)
        assets = [by_key[k] for k in keys if k in by_key]
        missing = len(keys) - len(assets)
        self.items_model.set_assets(assets)
        self.grid.setVisible(bool(assets))
        self.items_empty.setVisible(not assets)
        self.title.setText(c["name"] + ("  (arquivada)" if c["archived"] else ""))
        who = self.user_name(c["created_by"])
        self.sub.setText(f"{len(assets)} {'item' if len(assets) == 1 else 'itens'}"
                         + (f"  ·  {missing} não encontrado(s) na biblioteca" if missing else "")
                         + (f"  ·  criada por {who}" if who else "")
                         + f"  ·  atualizada {when(c['updated_at'])}")
        self.note.setText(c["note"])
        self.note.setVisible(bool(c["note"]))
        self._fill_recent(set(keys), by_key)

    def _fill_recent(self, inside: set, by_key: dict):
        self.recent.blockSignals(True)
        self.recent.clear()
        limit = time.time() - RECENT_DAYS * 86400
        for key, last, _n in self.w.db.recent_uses(80):
            if last < limit or key in inside or key not in by_key:
                continue
            a = by_key[key]
            it = QListWidgetItem(f"{a.name}\n{when(last)}")
            if a.preview:
                from PySide6.QtGui import QIcon, QImageReader, QPixmap
                r = QImageReader(a.preview)
                r.setAutoTransform(True)
                sz = r.size()
                if sz.isValid():
                    r.setScaledSize(sz.scaled(88, 88, Qt.KeepAspectRatio))
                img = r.read()
                if not img.isNull():
                    it.setIcon(QIcon(QPixmap.fromImage(img)))
            it.setData(Qt.UserRole, key)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Unchecked)
            self.recent.addItem(it)
        self.recent.blockSignals(False)
        self.recent_empty.setVisible(self.recent.count() == 0)
        self.recent.setVisible(self.recent.count() > 0)
        self._update_recent_btn()

    def _checked_recent(self) -> list[str]:
        return [self.recent.item(i).data(Qt.UserRole) for i in range(self.recent.count())
                if self.recent.item(i).checkState() == Qt.Checked]

    def _update_recent_btn(self, *_):
        n = len(self._checked_recent())
        self.btn_add_recent.setEnabled(n > 0)
        self.btn_add_recent.setText(f"Adicionar {n} marcado(s)" if n else "Adicionar marcados")

    def _add_recent(self):
        if self.cid:
            self.add_items(self.cid, self._checked_recent())

    def remove_selected(self):
        if not self.cid:
            return
        from .main_window import ASSET_ROLE
        sel = [ix.data(ASSET_ROLE) for ix in self.grid.selectionModel().selectedIndexes()]
        if not sel:
            return
        what = f"\"{sel[0].name}\"" if len(sel) == 1 else f"{len(sel)} itens"
        if QMessageBox.question(self, "Tirar da coleção", f"Tirar {what} desta coleção?\n\n"
                                "O modelo continua na biblioteca; só sai da lista do projeto.") != QMessageBox.Yes:
            return
        self.w.db.remove_from_collection(self.cid, [a.key for a in sel])
        self.refresh()
        self.changed.emit()

    def _item_menu(self, pos):
        if not self.grid.indexAt(pos).isValid():
            return
        m = QMenu(self)
        m.addAction("Mostrar na Biblioteca", self._show_in_library)
        m.addAction("Tirar desta coleção…  (Delete)", self.remove_selected)
        m.exec(self.grid.viewport().mapToGlobal(pos))

    def _show_in_library(self):
        from .main_window import ASSET_ROLE
        ix = self.grid.currentIndex()
        if ix.isValid():
            self.w.show_item(ix.data(ASSET_ROLE).key)

    def _col_menu(self, pos):
        ix = self.view.indexAt(pos)
        if not ix.isValid():
            return
        self._detail_menu(None, ix.data(Qt.UserRole)["id"], self.view.viewport().mapToGlobal(pos))

    def _detail_menu(self, button, cid=None, gpos=None):
        cid = cid or self.cid
        c = self.w.db.collection(cid) if cid else None
        if not c:
            return
        m = QMenu(self)
        m.addAction("Renomear…", lambda: self._rename(cid))
        m.addAction("Anotação (cliente, endereço, observações)…", lambda: self._note(cid))
        m.addAction("Desarquivar" if c["archived"] else "Arquivar", lambda: self._archive(cid, not c["archived"]))
        m.addSeparator()
        m.addAction("Excluir coleção…", lambda: self._delete(cid))
        if gpos is None:
            gpos = button.mapToGlobal(button.rect().bottomLeft())
        m.exec(gpos)

    def _rename(self, cid):
        c = self.w.db.collection(cid)
        name, ok = QInputDialog.getText(self, "Renomear coleção", "Novo nome:", text=c["name"])
        if ok and name.strip():
            self.w.db.rename_collection(cid, name.strip())
            self.refresh()

    def _note(self, cid):
        c = self.w.db.collection(cid)
        text, ok = QInputDialog.getMultiLineText(self, "Anotação", "Cliente, endereço, prazos ou observações:",
                                                 c["note"])
        if ok:
            self.w.db.set_collection_note(cid, text)
            self.refresh()

    def _archive(self, cid, on):
        self.w.db.archive_collection(cid, on)
        if on and self.cid == cid:
            self.close_collection()
        self.refresh()
        self.changed.emit()

    def _delete(self, cid):
        c = self.w.db.collection(cid)
        if QMessageBox.question(self, "Excluir coleção",
                                f"Excluir a coleção \"{c['name']}\"?\n\nOs modelos continuam na biblioteca; "
                                "só a lista do projeto é apagada (para todos da equipe).") != QMessageBox.Yes:
            return
        self.w.db.delete_collection(cid)
        if self.cid == cid:
            self.close_collection()
        self.refresh()
        self.changed.emit()
