"""Seção Vegetação da aba Tags (etapa 5).

Na tela principal de Tags aparece uma pasta "Vegetação" (quando há tags de plantas ou volumes). Dentro dela,
uma pasta por tag; cada tag abre os cartões das plantas e volumes com ela. Clicar num cartão abre a aba
Vegetação naquele lugar. Renomear/excluir aqui vale só para a Vegetação (a Biblioteca não muda).
"""
from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (QAbstractItemView, QInputDialog, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QMenu, QMessageBox, QStackedWidget, QVBoxLayout, QWidget)

from .. import theme
from . import marcas

KIND = "veg"


def _veg_page(tags_page):
    return getattr(tags_page.w, "vegetacao", None)


def _cover(cols, keys) -> str | None:
    for k in keys:
        w = marcas.resolver(cols, k)
        if not w:
            continue
        img = w[-1].capa
        if img and not img.lower().endswith(".pdf"):
            return img
    return None


def _count_text(cols, keys) -> str:
    esp = vol = 0
    for k in keys:
        w = marcas.resolver(cols, k)
        if w and w[0] == "especie":
            esp += 1
        elif w:
            vol += 1
    parts = []
    if esp:
        parts.append(f"{esp} {'planta' if esp == 1 else 'plantas'}")
    if vol:
        parts.append(f"{vol} {'volume' if vol == 1 else 'volumes'}")
    return "  ·  ".join(parts) or "fora das coleções lidas"


def folder_item(tags_page) -> QListWidgetItem | None:
    """A pasta "Vegetação" da tela principal de Tags (None quando ainda não há tags de vegetação)."""
    from ..tags_page import COUNT_ROLE, COVERS_ROLE, KIND_ROLE, NAME_ROLE
    tm = marcas.todas(tags_page.w.db)
    if not tm:
        return None
    vp = _veg_page(tags_page)
    cols = vp.cols if vp else []
    keys = sorted({k for ks in tm.values() for k in ks})
    it = QListWidgetItem()
    it.setData(KIND_ROLE, KIND)
    it.setData(NAME_ROLE, "Vegetação")
    cov = _cover(cols, keys)
    it.setData(COVERS_ROLE, [cov] if cov else [])
    it.setData(COUNT_ROLE, f"{len(tm)} {'tag' if len(tm) == 1 else 'tags'}  ·  {len(keys)} "
                           f"{'item' if len(keys) == 1 else 'itens'}")
    it.setToolTip("Tags das plantas e volumes da aba Vegetação")
    return it


class VegTagsView(QWidget):
    def __init__(self, tags_page):
        super().__init__()
        from ..tags_page import FolderDelegate
        from .pagina import _CardDelegate, _CardModel, _Grid
        self.tp = tags_page
        self.tag: str | None = None
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack)

        self.folders = QListWidget()
        self.folders.setViewMode(QListView.IconMode)
        self.folders.setResizeMode(QListView.Adjust)
        self.folders.setMovement(QListView.Static)
        self.folders.setGridSize(QSize(FolderDelegate.W, FolderDelegate.H))
        self.folders.setItemDelegate(FolderDelegate(tags_page))
        self.folders.setMouseTracking(True)
        self.folders.setSelectionMode(QAbstractItemView.NoSelection)
        self.folders.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.folders.setStyleSheet("QListWidget{background:transparent; border:none;}")
        self.folders.viewport().setCursor(Qt.PointingHandCursor)
        self.folders.itemClicked.connect(lambda it: self.open_tag(it.data(Qt.UserRole + 1)))
        self.folders.setContextMenuPolicy(Qt.CustomContextMenu)
        self.folders.customContextMenuRequested.connect(self._folders_menu)
        self.empty = QLabel()
        self.empty.setAlignment(Qt.AlignCenter)
        self.empty.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:11pt;")
        fw = QWidget()
        fl = QVBoxLayout(fw)
        fl.setContentsMargins(0, 0, 0, 0)
        fl.addWidget(self.folders)
        fl.addWidget(self.empty)
        self.stack.addWidget(fw)

        self.model = _CardModel()
        self.grid = _Grid()
        self.grid.setModel(self.model)
        self.delegate = _CardDelegate(tags_page)      # o delegado só precisa de page.w.thumbs
        self.delegate.mode = "especie"
        self.grid.setItemDelegate(self.delegate)
        self.grid.setDragEnabled(False)
        self.grid.clicked.connect(self._open_card)
        self.grid.customContextMenuRequested.connect(self._grid_menu)
        self.grid.setToolTip("Clique para abrir na aba Vegetação")
        self.stack.addWidget(self.grid)

    @property
    def db(self):
        return self.tp.w.db

    def _cols(self):
        vp = _veg_page(self.tp)
        return vp.cols if vp else []

    # ------------------------------------------------------------------ telas
    def refresh(self) -> tuple[list, str]:
        """Mostra a tela atual; devolve (migalhas, subtítulo) para a página de Tags."""
        tm = marcas.todas(self.db)
        if self.tag is not None and self.tag not in tm:
            self.tag = None
        cols = self._cols()
        if self.tag is None:
            from ..tags_page import COUNT_ROLE, COVERS_ROLE, KIND_ROLE, NAME_ROLE
            self.stack.setCurrentIndex(0)
            self.folders.clear()
            by_count = self.tp.sort.currentData() == "count"
            order = sorted(tm, key=(lambda t: (-len(tm[t]), t)) if by_count else (lambda t: t))
            for t in order:
                it = QListWidgetItem()
                it.setData(KIND_ROLE, "tag")
                it.setData(NAME_ROLE, t)
                cov = _cover(cols, tm[t])
                it.setData(COVERS_ROLE, [cov] if cov else [])
                it.setData(COUNT_ROLE, _count_text(cols, tm[t]))
                it.setToolTip(t)
                self.folders.addItem(it)
            self.folders.setVisible(bool(tm))
            self.empty.setVisible(not tm)
            self.empty.setText("Ainda não há tags na Vegetação.\nNa aba Vegetação, use o painel da planta ou o "
                               "botão direito › Tags….")
            return [("Vegetação", "veg")], f"{len(tm)} {'tag' if len(tm) == 1 else 'tags'}"
        self.stack.setCurrentIndex(1)
        vp = _veg_page(self.tp)
        rows, fora = [], 0
        for k in tm[self.tag]:
            w = marcas.resolver(cols, k)
            if not w:
                fora += 1
                continue
            if w[0] == "volume":
                r = vp._vol_row(w[1], w[2])
                r["sub"] = f"{w[1].nome} · {r['sub']}"
            else:
                r = vp._esp_row(*w[1:])
                r["sub"] = f"{w[2].rotulo} · {w[1].nome}"
            r["badge"], r["dot"] = None, False
            rows.append(r)
        self.model.set_rows(rows)
        sub = f"{len(rows)} {'item' if len(rows) == 1 else 'itens'}"
        if fora:
            sub += f"  ·  {fora} fora das coleções lidas"
        return [("Vegetação", "veg"), (self.tag, "vegtag")], sub

    def open_tag(self, tag: str):
        self.tag = tag
        self.tp.refresh()

    def back(self) -> bool:
        """Volta um nível; False quando já está na pasta Vegetação (a página de Tags sai da seção)."""
        if self.tag is not None:
            self.tag = None
            return True
        return False

    def _open_card(self, ix):
        r = ix.data(Qt.UserRole)
        vp = _veg_page(self.tp)
        if r and vp:
            vp.open_key(r["key"])

    # ------------------------------------------------------------------ menus
    def _folders_menu(self, pos):
        it = self.folders.itemAt(pos)
        m = QMenu(self)
        if it is None:
            m.addAction("Voltar", self.tp.go_back)
        else:
            t = it.data(Qt.UserRole + 1)
            m.addAction("Abrir", lambda: self.open_tag(t))
            m.addSeparator()
            m.addAction("Renomear tag na Vegetação…", lambda: self._rename(t))
            m.addAction("Excluir tag da Vegetação…", lambda: self._delete(t))
        m.exec(self.folders.viewport().mapToGlobal(pos))

    def _grid_menu(self, pos):
        ix = self.grid.indexAt(pos)
        if not ix.isValid():
            return
        r = ix.data(Qt.UserRole)
        m = QMenu(self)
        m.addAction("Abrir na Vegetação", lambda: self._open_card(ix))
        m.addSeparator()
        m.addAction(f"Tirar a tag “{self.tag}” deste item", lambda: self._untag(r["key"]))
        m.exec(self.grid.viewport().mapToGlobal(pos))

    def _rename(self, tag):
        new, ok = QInputDialog.getText(self, "Renomear tag", f"Novo nome para “{tag}” (só na Vegetação):",
                                       QLineEdit.Normal, tag)
        new = marcas.clean(new) if ok else ""
        if not new or new == tag:
            return
        marcas.renomear(self.db, tag, new)
        if self.tag == tag:
            self.tag = new
        self._changed()

    def _delete(self, tag):
        n = len(marcas.todas(self.db).get(tag, []))
        if QMessageBox.question(self, "Excluir tag",
                                f"Tirar a tag “{tag}” de {n} {'item' if n == 1 else 'itens'} da Vegetação?\n\n"
                                "Nenhum arquivo é alterado e a mesma tag na Biblioteca continua.") != QMessageBox.Yes:
            return
        marcas.excluir(self.db, tag)
        self._changed()

    def _untag(self, key):
        marcas.remover(self.db, [key], self.tag)
        self._changed()

    def _changed(self):
        vp = _veg_page(self.tp)
        if vp:
            vp.marks_changed()
        self.tp.refresh()
