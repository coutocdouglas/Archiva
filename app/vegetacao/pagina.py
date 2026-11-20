"""Página Vegetação (etapa 1: somente leitura).

Quatro níveis — Coleções › Volumes › Espécies › Arquivos — e a busca por espécie em todas as coleções.
O índice fica em disco (cache) e a página abre na hora; a leitura das pastas roda num ajudante.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QFileDialog, QHBoxLayout, QLabel, QListView, QMenu, QPushButton,
                               QSizePolicy, QStyle, QStyledItemDelegate, QVBoxLayout, QWidget)

from .. import segundo_plano, theme, ui
from ..config import data_dir
from ..janela import TITLE_H
from . import leitor

ui._ICONS.setdefault("vegetacao", '<path d="M12 21V11"/><path d="M12 11C12 7 9 5 5 5c0 4 3 6 7 6z"/>'
                                  '<path d="M12 14c0-3 2-5 6-5 0 3-2 5-6 5z"/>')

CONFIG_FILE = "vegetacao.json"     # em %APPDATA%\GerenciadorAssets3D: pastas das coleções desta pessoa
INDEX_FILE = "vegetacao_indice.json"

TILE_TOP = QColor(255, 236, 210, 16)
TILE_BOTTOM = QColor(255, 236, 210, 6)


def human_size(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB".replace(".", ",")
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.0f} MB"
    return f"{max(1, n // 1024)} KB"


def plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


def show_in_folder(path: str) -> None:
    if sys.platform == "win32":
        subprocess.Popen(f'explorer /select,"{os.path.normpath(path)}"')


def open_file(path: str) -> None:
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 — abre o PDF no leitor padrão


# =========================================================================== configuração (pastas das coleções)

def load_paths() -> list[str] | None:
    try:
        d = json.loads((data_dir() / CONFIG_FILE).read_text(encoding="utf-8"))
        return [p for p in d.get("colecoes", []) if isinstance(p, str)]
    except (OSError, ValueError):
        return None


def save_paths(paths: list[str]) -> None:
    try:
        (data_dir() / CONFIG_FILE).write_text(json.dumps({"colecoes": paths}, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
    except OSError:
        pass


# =========================================================================== grade de cartões

class _CardModel(QAbstractListModel):
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
        r = self.rows[index.row()]
        if role == Qt.DisplayRole:
            return r["title"]
        if role == Qt.UserRole:
            return r
        if role == Qt.ToolTipRole:
            return r.get("tip")
        return None


SIZES = {          # largura do cartão, altura da imagem
    "colecao": (360, 170),
    "volume": (226, 132),
    "especie": (226, 150),
    "arquivo": (226, 150),
}

BADGE = {
    "mesh": (QColor(255, 236, 210, 26), QColor("#cfc3b0")),
    "proxy": (QColor(216, 194, 156, 52), QColor("#e8d5b0")),
    "warn": (theme.rgba(theme.WARN, 0.18), theme.WARN),
    "bad": (theme.rgba(theme.BAD, 0.18), theme.BAD),
}


class _CardDelegate(QStyledItemDelegate):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.mode = "colecao"

    def sizeHint(self, option, index):
        w, h = SIZES[self.mode]
        return QSize(w, h + 76)

    def paint(self, p: QPainter, option, index):
        r = index.data(Qt.UserRole)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        hover = bool(option.state & QStyle.State_MouseOver)
        sel = bool(option.state & QStyle.State_Selected) and self.mode == "arquivo"
        box = QRectF(option.rect).adjusted(7, 7, -7, -7)
        theme.paint_glass(p, box, 14, 1.0, hover)
        img = QRectF(box.left(), box.top(), box.width(), SIZES[self.mode][1])
        self._image(p, img, r.get("img"), r.get("placeholder", "sem prévia"), hover)
        if sel:
            theme.paint_selection(p, box, 14)
        x, w = box.left() + 13, box.width() - 26
        y = img.bottom() + 10
        f = theme.ui_font(12 if self.mode == "colecao" else 10.5)
        f.setItalic(bool(r.get("italic")))
        p.setFont(f)
        p.setPen(theme.TEXT)
        p.drawText(QRectF(x, y, w, 22), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f).elidedText(r["title"], Qt.ElideRight, int(w)))
        f2 = theme.ui_font(9)
        p.setFont(f2)
        badge = r.get("badge")
        bw = 0
        if badge:
            text, kind = badge
            bg, fg = BADGE[kind]
            bw = QFontMetrics(theme.ui_font(8.5)).horizontalAdvance(text) + 18
            br = QRectF(box.right() - 13 - bw, y + 26, bw, 19)
            path = QPainterPath()
            path.addRoundedRect(br, 9.5, 9.5)
            p.fillPath(path, bg)
            p.setFont(theme.ui_font(8.5))
            p.setPen(fg)
            p.drawText(br, Qt.AlignCenter, text)
            p.setFont(f2)
        p.setPen(theme.MUTED)
        p.drawText(QRectF(x, y + 25, w - bw - 8, 20), Qt.AlignLeft | Qt.AlignVCenter,
                   QFontMetrics(f2).elidedText(r.get("sub", ""), Qt.ElideRight, int(w - bw - 8)))
        p.restore()

    def _image(self, p: QPainter, cell: QRectF, path: str | None, placeholder: str, hover: bool):
        clip = QPainterPath()
        clip.addRoundedRect(cell, 14, 14)
        p.save()
        p.setClipPath(clip, Qt.IntersectClip)
        # só o canto de cima é arredondado
        p.setClipRect(cell.adjusted(0, 0, 0, 20), Qt.IntersectClip)
        pix = self.page.w.thumbs.get(path) if path else None
        if pix and not pix.isNull():
            # "object-fit: cover": preenche o espaço e corta as sobras
            s = max(cell.width() / pix.width(), cell.height() / pix.height()) * (1.03 if hover else 1.0)
            tw, th = pix.width() * s, pix.height() * s
            p.drawPixmap(QRectF(cell.center().x() - tw / 2, cell.center().y() - th / 2, tw, th), pix,
                         QRectF(pix.rect()))
        else:
            from PySide6.QtGui import QLinearGradient
            g = QLinearGradient(cell.topLeft(), cell.bottomLeft())
            g.setColorAt(0, TILE_TOP)
            g.setColorAt(1, TILE_BOTTOM)
            p.fillRect(cell, g)
            p.setPen(theme.FAINT)
            p.setFont(theme.ui_font(9))
            p.drawText(cell, Qt.AlignCenter, placeholder if not path or path.lower().endswith(".pdf")
                       else "carregando…")
        p.restore()


class _Grid(QListView):
    def __init__(self):
        super().__init__()
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(2)
        self.setMouseTracking(True)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(24)
        self.setContextMenuPolicy(Qt.CustomContextMenu)
        self.setStyleSheet("QListView{background:transparent;border:none;}")
        self.setCursor(Qt.PointingHandCursor)


# =========================================================================== painel lateral (nível 4)

class _Side(ui.Glass):
    def __init__(self, page):
        super().__init__(14)
        self.page = page
        self.setFixedWidth(320)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(10)
        self.img = QLabel()
        self.img.setFixedHeight(190)
        self.img.setAlignment(Qt.AlignCenter)
        self.img.setStyleSheet("background:rgba(255,236,210,10); border-radius:12px;")
        lay.addWidget(self.img)
        self.title = QLabel()
        f = theme.ui_font(14)
        f.setItalic(True)
        self.title.setFont(f)
        self.title.setWordWrap(True)
        lay.addWidget(self.title)
        self.sub = QLabel()
        self.sub.setWordWrap(True)
        self.sub.setStyleSheet(f"color:{theme.MUTED.name()};")
        lay.addWidget(self.sub)
        from PySide6.QtWidgets import QGridLayout
        self.rows_box = QWidget()
        self.rows = QGridLayout(self.rows_box)
        self.rows.setContentsMargins(0, 4, 0, 0)
        self.rows.setHorizontalSpacing(12)
        self.rows.setVerticalSpacing(6)
        self.rows.setColumnStretch(1, 1)
        lay.addWidget(self.rows_box)
        lay.addSpacing(4)
        self.btn_folder = QPushButton("Mostrar na pasta")
        self.btn_folder.setCursor(Qt.PointingHandCursor)
        self.btn_folder.clicked.connect(lambda: self.arq and show_in_folder(self.arq.path))
        lay.addWidget(self.btn_folder)
        self.btn_pdf = QPushButton("Abrir o PDF do volume")
        self.btn_pdf.setCursor(Qt.PointingHandCursor)
        self.btn_pdf.clicked.connect(lambda: self.vol and self.vol.pdf and open_file(self.vol.pdf))
        lay.addWidget(self.btn_pdf)
        lay.addStretch(1)
        self.arq = None
        self.vol = None

    def show_file(self, vol, esp, arq):
        self.vol, self.arq = vol, arq
        self.title.setText(esp.nome)
        f = self.title.font()
        f.setItalic(not esp.grupo)
        self.title.setFont(f)
        self.sub.setText(f"{vol.rotulo} · {arq.rotulo}")
        tipo = {"mesh": "Malha (mesh)", "cena": "Cena", "conjunto": "Conjunto"}.get(arq.tipo, arq.tipo)
        render = arq.render or ("escolhido pela biblioteca Forest Pack" if arq.forest_pack else "não informado")
        rows = [("Renderizador", render), ("Tipo", tipo), ("Arquivo", human_size(arq.size)),
                ("Proxy", "já existe" if arq.proxy else "ainda não")]
        if arq.forest_pack:
            rows.append(("Forest Pack", "está na biblioteca"))
        while self.rows.count():
            it = self.rows.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for i, (k, v) in enumerate(rows):
            a, b = QLabel(k), QLabel(v)
            a.setStyleSheet(f"color:{theme.MUTED.name()};")
            a.setAlignment(Qt.AlignLeft | Qt.AlignTop)
            b.setAlignment(Qt.AlignRight | Qt.AlignTop)
            b.setWordWrap(True)
            self.rows.addWidget(a, i, 0)
            self.rows.addWidget(b, i, 1)
        name = QLabel(os.path.basename(arq.path))
        name.setWordWrap(True)
        name.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:9pt; padding-top:4px;")
        name.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.rows.addWidget(name, len(rows), 0, 1, 2)
        self.btn_pdf.setVisible(bool(vol.pdf))
        self.refresh_image()

    def refresh_image(self):
        pix = self.page.w.thumbs.get(self.arq.preview) if self.arq and self.arq.preview else None
        if pix and not pix.isNull():
            r = self.img.contentsRect()
            pm = pix.scaled(r.width() * 2, r.height() * 2, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            pm.setDevicePixelRatio(2)
            self.img.setPixmap(pm)
        else:
            self.img.setPixmap(QPixmap())
            self.img.setText("sem prévia" if not (self.arq and self.arq.preview) else "carregando…")


# =========================================================================== página

class VegetacaoPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.w = window
        self.cols: list[leitor.Colecao] = []
        self.paths: list[str] = []
        self.where: tuple = ("inicio",)        # ("inicio",) ("colecao", c) ("volume", c, v) ("especie", c, v, e) ("busca",)
        self.before_search: tuple = ("inicio",)
        self.search_filter = ""                # chave da coleção (vazio = todas)
        self._scanning = False
        self._scanned = False
        self.index_path = os.path.join(str(window.cache_root), INDEX_FILE)

        outer = QHBoxLayout(self)
        outer.setContentsMargins(40, TITLE_H + 8, 32, 16)
        outer.setSpacing(24)
        main = QVBoxLayout()
        main.setSpacing(6)
        outer.addLayout(main, 1)

        self.crumbs = QLabel()
        self.crumbs.setTextFormat(Qt.RichText)
        self.crumbs.linkActivated.connect(self._crumb)
        main.addWidget(self.crumbs)
        head = QHBoxLayout()
        tl = QVBoxLayout()
        tl.setSpacing(2)
        self.title = QLabel("Vegetação")
        self.title.setFont(theme.ui_font(24))
        tl.addWidget(self.title)
        self.sub = QLabel()
        self.sub.setStyleSheet(f"color:{theme.MUTED.name()};")
        tl.addWidget(self.sub)
        head.addLayout(tl, 1)
        self.btn_refresh = QPushButton("Atualizar")
        self.btn_refresh.setToolTip("Ler as pastas das coleções de novo")
        self.btn_refresh.setCursor(Qt.PointingHandCursor)
        self.btn_refresh.clicked.connect(self.rescan)
        head.addWidget(self.btn_refresh, 0, Qt.AlignBottom)
        self.btn_add = ui.primary(QPushButton("Adicionar coleção"))
        self.btn_add.clicked.connect(self.add_collection)
        head.addWidget(self.btn_add, 0, Qt.AlignBottom)
        main.addLayout(head)
        main.addSpacing(10)

        self.search = ui.SearchField("Buscar espécie em todas as coleções, por exemplo Phoenix canariensis")
        self._search_timer = QTimer(self, singleShot=True, interval=220)
        self._search_timer.timeout.connect(self._do_search)
        self.search.edit.textChanged.connect(lambda _: self._search_timer.start())
        main.addWidget(self.search)
        self.chips_row = QHBoxLayout()
        self.chips_row.setSpacing(8)
        self.chips_box = QWidget()
        self.chips_box.setLayout(self.chips_row)
        self.chips_row.setContentsMargins(0, 6, 0, 0)
        main.addWidget(self.chips_box)
        main.addSpacing(6)
        self.section = ui.heading("", 10)
        main.addWidget(self.section)

        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setAlignment(Qt.AlignCenter)
        self.notice.setStyleSheet(f"color:{theme.FAINT.name()}; padding:40px;")
        self.notice.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        main.addWidget(self.notice)

        self.model = _CardModel()
        self.grid = _Grid()
        self.grid.setModel(self.model)
        self.delegate = _CardDelegate(self)
        self.grid.setItemDelegate(self.delegate)
        self.grid.clicked.connect(self._activate)
        self.grid.customContextMenuRequested.connect(self._menu)
        main.addWidget(self.grid, 1)

        self.side = _Side(self)
        outer.addWidget(self.side)
        self.side.hide()

        window.thumbs.changed.connect(self._thumbs_changed)
        self._load()

    # ------------------------------------------------------------------ dados
    def _load(self):
        # nada é procurado sozinho: cada pessoa indica a pasta de cada coleção ("Adicionar coleção")
        self.paths = load_paths() or []
        cached = {os.path.normcase(c.path): c for c in leitor.load_index(self.index_path)}
        self.cols = [cached[os.path.normcase(os.path.normpath(p))] for p in self.paths
                     if os.path.normcase(os.path.normpath(p)) in cached]
        self.go(("inicio",))

    def showEvent(self, e):
        super().showEvent(e)
        if not self._scanned:      # na primeira vez que a página aparece, confere as pastas
            self.rescan()

    def rescan(self):
        if self._scanning:
            return
        self._scanning = True
        self._scanned = True
        self.btn_refresh.setEnabled(False)
        self.btn_refresh.setText("Lendo…")
        paths = list(self.paths)

        def work():
            return [leitor.read_collection(p) for p in paths if os.path.isdir(p)]

        def done(cols):
            self._scanning = False
            self.btn_refresh.setEnabled(True)
            self.btn_refresh.setText("Atualizar")
            self.cols = cols
            leitor.save_index(self.index_path, cols)
            self._rebind()

        def fail(err):
            self._scanning = False
            self.btn_refresh.setEnabled(True)
            self.btn_refresh.setText("Atualizar")
            self.sub.setText(f"Não foi possível ler as coleções ({err}).")

        segundo_plano.run_async(work, done, fail)

    def _rebind(self):
        """Depois de ler de novo, volta para o mesmo lugar (pelas chaves, não pelos objetos antigos)."""
        w = self.where
        target = ("inicio",)
        c = next((c for c in self.cols if len(w) > 1 and c.key == w[1].key), None) if w[0] != "busca" else None
        if c:
            target = ("colecao", c)
            v = next((v for v in c.volumes if len(w) > 2 and v.key == w[2].key), None)
            if v:
                target = ("volume", c, v)
                e = next((e for e in v.especies if len(w) > 3 and e.key == w[3].key), None)
                if e:
                    target = ("especie", c, v, e)
        if w[0] == "busca":
            self._do_search()
        else:
            self.go(target)

    def add_collection(self):
        start = os.path.dirname(self.paths[-1]) if self.paths else ""
        d = QFileDialog.getExistingDirectory(self, "Pasta raiz da coleção (a do Maxtree ou a do Globe Plants)", start)
        if not d:
            return
        d = os.path.normpath(d)
        if any(os.path.normcase(d) == os.path.normcase(p) for p in self.paths):
            return
        self.paths.append(d)
        save_paths(self.paths)
        self.rescan()

    def remove_collection(self, c):
        self.paths = [p for p in self.paths if os.path.normcase(os.path.normpath(p)) != os.path.normcase(c.path)]
        save_paths(self.paths)
        self.cols = [x for x in self.cols if x is not c]
        leitor.save_index(self.index_path, self.cols)
        self.go(("inicio",))

    # ------------------------------------------------------------------ navegação
    def _crumb(self, link: str):
        w = self.where
        if w[0] == "busca":
            self.search.edit.clear()
            return
        self.go(self._level(int(link)))

    LEVELS = ("inicio", "colecao", "volume", "especie")

    def _level(self, n: int) -> tuple:
        """O lugar atual cortado no nível n (0 = início, 1 = coleção, 2 = volume, 3 = espécie)."""
        objs = self.where[1:1 + n]
        return (self.LEVELS[len(objs)],) + tuple(objs)

    def go(self, where: tuple):
        if where[0] == "inicio":
            where = ("inicio",)
        self.where = where
        kind = where[0]
        self.side.setVisible(kind == "especie")
        self.search.setVisible(kind in ("inicio", "busca"))
        self.chips_box.setVisible(kind == "busca")
        self.btn_add.setVisible(kind == "inicio")
        self._set_crumbs()
        rows, mode, notice = [], "colecao", ""
        if kind == "inicio":
            self.title.setText("Vegetação")
            self._title_italic(False)
            self.sub.setText(plural(len(self.cols), "coleção", "coleções") if self.cols else "")
            self.section.setText("Coleções" if self.cols else "")
            rows = [self._col_row(c) for c in self.cols]
            if not self.cols:
                notice = ("Nenhuma coleção de vegetação ainda.\n\nClique em \"Adicionar coleção\" e escolha a pasta "
                          "raiz de cada coleção: uma vez a do Maxtree, outra a do Globe Plants.\nO Archiva só lê as "
                          "pastas que você indicar.") if not self.paths else "Lendo as coleções…"
        elif kind == "colecao":
            c = where[1]
            self.title.setText(c.nome)
            self._title_italic(False)
            self.sub.setText(f"{plural(len(c.volumes), 'volume', 'volumes')} · "
                             f"{plural(c.n_especies, 'espécie', 'espécies')}")
            self.section.setText("Volumes")
            rows, mode = [self._vol_row(c, v) for v in c.volumes], "volume"
        elif kind == "volume":
            c, v = where[1], where[2]
            self.title.setText(v.rotulo)
            self._title_italic(False)
            extra = "" if v.organizado else " · não organizado"
            self.sub.setText(f"{c.nome} · {plural(v.n_especies, 'espécie', 'espécies')} · "
                             f"{plural(v.n_arquivos, 'arquivo', 'arquivos')}{extra}")
            self.section.setText("Espécies" if v.especies else "")
            rows, mode = [self._esp_row(c, v, e) for e in v.especies], "especie"
            if v.status == "compactado":
                notice = f"Este volume ainda está compactado ({v.aviso}).\nA extração entra na etapa \"Organizar\"."
            elif v.status == "corrompido" and not v.especies:
                notice = f"Compactado corrompido ou fora do padrão: {v.aviso}.\nÉ preciso baixar de novo."
            elif v.status == "corrompido":
                self.sub.setText(self.sub.text() + f" · ⚠ {v.aviso}")
        elif kind == "especie":
            c, v, e = where[1], where[2], where[3]
            self.title.setText(e.nome)
            self._title_italic(not e.grupo)
            renders = sorted({a.render for a in e.arquivos if a.render})
            self.sub.setText(" · ".join([v.rotulo] + renders + [plural(len(e.arquivos), "arquivo", "arquivos")]))
            self.section.setText("Arquivos")
            rows, mode = [self._arq_row(v, e, a) for a in e.arquivos], "arquivo"
        self.delegate.mode = mode
        self.model.set_rows(rows)
        self.grid.setVisible(bool(rows))
        self.notice.setVisible(not rows)
        self.notice.setText(notice)
        self.grid.scrollToTop()
        if kind == "especie" and rows:
            self.grid.setCurrentIndex(self.model.index(0))
            self._select(self.model.index(0))
        self.grid.selectionModel().currentChanged.connect(self._select, Qt.UniqueConnection)

    def _title_italic(self, on: bool):
        f = self.title.font()
        f.setItalic(on)
        self.title.setFont(f)

    def _set_crumbs(self):
        link, here, sep = theme.LINK.name(), theme.MUTED.name(), theme.FAINT.name()
        w = self.where
        if w[0] == "busca":
            names = ["Vegetação", "Busca"]
        else:
            names = ["Vegetação"] + [x.nome if i == 0 else (x.rotulo if i == 1 else x.nome)
                                     for i, x in enumerate(w[1:])]
        parts = []
        for i, n in enumerate(names):
            if i == len(names) - 1:
                parts.append(f"<span style='color:{here}'>{n}</span>")
            else:
                parts.append(f"<a href='{i}' style='color:{link}; text-decoration:none'>{n}</a>")
        self.crumbs.setText(f"<span style='color:{sep}'> › </span>".join(parts))
        self.crumbs.setVisible(len(names) > 1)

    def _activate(self, ix):
        r = ix.data(Qt.UserRole)
        if r and r.get("go"):
            self.go(r["go"])

    def _select(self, ix, _prev=None):
        if self.where[0] != "especie" or not ix.isValid():
            return
        r = ix.data(Qt.UserRole)
        self.side.show_file(r["vol"], r["esp"], r["arq"])

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Backspace, Qt.Key_Escape) and self.where[0] not in ("inicio",):
            if self.where[0] == "busca":
                self.search.edit.clear()
            else:
                self.go(self._level(len(self.where) - 2))
            return
        super().keyPressEvent(e)

    # ------------------------------------------------------------------ cartões
    def _col_row(self, c):
        vols = len(c.volumes)
        return {"title": c.nome, "img": c.capa, "go": ("colecao", c), "col": c,
                "sub": f"{plural(vols, 'volume', 'volumes')} · {plural(c.n_especies, 'espécie', 'espécies')}",
                "placeholder": "sem capa", "tip": c.path}

    def _vol_row(self, c, v):
        badge = None
        if v.status == "compactado":
            badge = ("compactado", "warn")
        elif v.status == "corrompido":
            badge = ("corrompido", "bad")
        if not v.especies:
            sub = "não extraído" if v.status == "compactado" else v.aviso
        elif not v.n_especies:      # só cenas / conjuntos (Vol 001)
            sub = f"{' e '.join(e.nome for e in v.especies)} · {plural(v.n_arquivos, 'arquivo', 'arquivos')}"
        else:
            sub = f"{plural(v.n_especies, 'espécie', 'espécies')} · {plural(v.n_arquivos, 'arquivo', 'arquivos')}"
        return {"title": v.rotulo, "img": v.capa, "go": ("volume", c, v), "sub": sub, "badge": badge,
                "placeholder": "capa no PDF" if v.pdf else "sem capa", "tip": v.path}

    def _esp_row(self, c, v, e):
        return {"title": e.nome, "italic": not e.grupo, "img": e.capa, "go": ("especie", c, v, e),
                "sub": plural(len(e.arquivos), "arquivo", "arquivos")}

    def _arq_row(self, v, e, a):
        if a.tipo != "mesh":
            badge = (a.tipo, "mesh")
        else:
            badge = ("mesh + proxy", "proxy") if a.proxy else ("mesh", "mesh")
        return {"title": a.rotulo, "img": a.preview, "sub": human_size(a.size), "badge": badge,
                "vol": v, "esp": e, "arq": a, "tip": os.path.basename(a.path)}

    def _menu(self, pos):
        ix = self.grid.indexAt(pos)
        if not ix.isValid():
            return
        r = ix.data(Qt.UserRole)
        m = QMenu(self)
        if "col" in r:
            c = r["col"]
            m.addAction("Mostrar na pasta", lambda: show_in_folder(c.path))
            m.addSeparator()
            m.addAction("Tirar da Vegetação (não apaga nada)", lambda: self.remove_collection(c))
        elif "arq" in r:
            m.addAction("Mostrar na pasta", lambda: show_in_folder(r["arq"].path))
        elif r.get("go") and r["go"][0] == "volume":
            v = r["go"][2]
            m.addAction("Mostrar na pasta", lambda: show_in_folder(v.path))
            if v.pdf:
                m.addAction("Abrir o PDF do volume", lambda: open_file(v.pdf))
        if not m.isEmpty():
            m.exec(self.grid.viewport().mapToGlobal(pos))

    # ------------------------------------------------------------------ busca
    def _do_search(self):
        text = self.search.edit.text().strip()
        if not text:
            if self.where[0] == "busca":
                self.go(self.before_search)
            return
        if self.where[0] != "busca":
            self.before_search = self.where
        self.where = ("busca",)
        res = leitor.search(self.cols, text)
        counts = {c.key: sum(1 for r in res if r[0] is c) for c in self.cols}
        if self.search_filter and self.search_filter not in counts:
            self.search_filter = ""
        shown = [r for r in res if not self.search_filter or r[0].key == self.search_filter]
        self.side.hide()
        self.search.show()
        self.btn_add.hide()
        self.chips_box.show()
        self._set_crumbs()
        self.title.setText("Busca")
        self._title_italic(False)
        vols = len({r[1].key for r in res})
        self.sub.setText(f"{plural(len(res), 'espécie', 'espécies')} em {plural(vols, 'volume', 'volumes')}"
                         if res else "Nenhuma espécie encontrada")
        self.section.setText("")
        self._fill_chips(len(res), counts)
        rows = [{"title": e.nome, "italic": True, "img": e.capa, "go": ("especie", c, v, e),
                 "sub": f"{v.rotulo} · {c.nome}"} for c, v, e in shown]
        self.delegate.mode = "especie"
        self.model.set_rows(rows)
        self.grid.setVisible(bool(rows))
        self.notice.setVisible(not rows)
        self.notice.setText(f"Nada com \"{text}\". Tente só o gênero (ex.: Chamaedorea) ou parte do nome.")

    def _fill_chips(self, total, counts):
        while self.chips_row.count():
            it = self.chips_row.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        opts = [(f"Todas · {total}", "")] + [(f"{c.nome} · {counts.get(c.key, 0)}", c.key) for c in self.cols]
        seg = ui.Segmented(opts)
        seg.blockSignals(True)
        seg.setCurrentIndex(max(0, seg.findData(self.search_filter)))
        seg.blockSignals(False)
        seg.currentIndexChanged.connect(
            lambda i, s=seg: (setattr(self, "search_filter", s.options[i][1]), QTimer.singleShot(0, self._do_search)))
        self.chips_row.addWidget(seg)
        self.chips_row.addStretch(1)

    # ------------------------------------------------------------------ miniaturas
    def _thumbs_changed(self):
        if self.isVisible():
            self.grid.viewport().update()
            if self.side.isVisible():
                self.side.refresh_image()
