"""Aba Entrada — classificar downloads novos para a biblioteca."""
from __future__ import annotations

import os
import subprocess

from PySide6.QtCore import QFileSystemWatcher, QSize, Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QComboBox, QCompleter, QDialog, QDialogButtonBox, QHBoxLayout,
                               QLabel, QListView, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QRadioButton, QButtonGroup, QSplitter, QVBoxLayout, QWidget, QFrame, QApplication)

from . import intake
from . import theme, ui
from .janela import TITLE_H
from .scanner import Asset, Category, scan_category

COL_OK = QColor("#7fb48a")
COL_WARN = QColor("#d6a15e")
COL_BAD = QColor("#d27a6a")


def _fmt(a: Asset) -> str:
    if a.kind == "archive":
        return (a.archive_type or "?").upper()
    if a.kind == "folder":
        return "PASTA"
    if a.kind == "max":
        return "MAX"
    return "SÓ IMAGEM"


# =========================================================================== busca de duplicados em 2º plano

class SimilarThread(QThread):
    done = Signal(str, list)   # (cat_key, [(item_key, [(Asset, score)])])

    def __init__(self, cat_key: str, items: list[Asset], candidates: list[Asset], cache_path: str):
        super().__init__()
        self.cat_key, self.items, self.candidates, self.cache_path = cat_key, items, candidates, cache_path

    def run(self):
        cache = intake.HashCache(self.cache_path)
        out = []
        for it in self.items:
            if it.preview:
                out.append((it.key, intake.find_similar(it.preview, self.candidates, cache)))
            else:
                out.append((it.key, []))
        self.done.emit(self.cat_key, out)


# =========================================================================== diálogo de duplicado

class DuplicateDialog(QDialog):
    KEEP_BOTH, KEEP_NEW, KEEP_OLD, SKIP = range(4)

    def __init__(self, parent, thumbs, new: Asset, matches: list[tuple[Asset, float]]):
        super().__init__(parent)
        self.setWindowTitle("Possível item repetido")
        self.choice = self.SKIP
        self.matches = matches
        lay = QVBoxLayout(self)
        lay.addWidget(QLabel(f"<b>{new.name}</b> parece já existir nesta categoria. Compare as prévias:"))

        row = QHBoxLayout()
        row.addWidget(self._card(thumbs, new.preview, "NOVO", new.name, "#7fb2c9"), 1)
        right = QVBoxLayout()
        self.group = QButtonGroup(self)
        self.existing_img = QLabel()
        self.existing_img.setAlignment(Qt.AlignCenter)
        self.existing_img.setFixedSize(300, 300)
        self.existing_img.setStyleSheet("background:#221b16; border:2px solid #d6a15e; border-radius:10px;")
        right.addWidget(self.existing_img)
        for i, (a, s) in enumerate(matches):
            rb = QRadioButton(f"{a.name}   —   {s * 100:.0f}% parecido")
            self.group.addButton(rb, i)
            right.addWidget(rb)
            if i == 0:
                rb.setChecked(True)
        self.group.idToggled.connect(lambda i, on: on and self._show_existing(thumbs, i))
        self._show_existing(thumbs, 0)
        row.addLayout(right, 1)
        lay.addLayout(row)

        bb = QDialogButtonBox()
        b1 = bb.addButton("Manter os dois", QDialogButtonBox.AcceptRole)
        b2 = bb.addButton("Manter só o NOVO (substitui o existente)", QDialogButtonBox.AcceptRole)
        b3 = bb.addButton("Manter só o EXISTENTE (descarta o novo)", QDialogButtonBox.AcceptRole)
        b4 = bb.addButton("Pular este item", QDialogButtonBox.RejectRole)
        for b, c in ((b1, self.KEEP_BOTH), (b2, self.KEEP_NEW), (b3, self.KEEP_OLD), (b4, self.SKIP)):
            b.clicked.connect(lambda _=False, c=c: self._done(c))
        lay.addWidget(bb)
        note = QLabel("<span style='color:#a89c8c'>O que for descartado vai para "
                      "_BACKUP_COMPACTADOS\\_DESCARTADOS e é apagado depois do prazo do backup. "
                      "Ao substituir, o novo fica com o nome (e as tags) do existente.</span>")
        note.setWordWrap(True)
        lay.addWidget(note)

    def _card(self, thumbs, path, tag, name, color):
        w = QFrame()
        l = QVBoxLayout(w)
        img = QLabel()
        img.setAlignment(Qt.AlignCenter)
        img.setFixedSize(300, 300)
        img.setStyleSheet(f"background:#221b16; border:2px solid {color}; border-radius:10px;")
        if path:
            img.setPixmap(QPixmap(path).scaled(292, 292, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        l.addWidget(img)
        l.addWidget(QLabel(f"<b style='color:{color}'>{tag}</b>  {name}"))
        l.addStretch(1)
        return w

    def _show_existing(self, thumbs, i):
        a = self.matches[i][0]
        if a.preview:
            self.existing_img.setPixmap(QPixmap(a.preview).scaled(292, 292, Qt.KeepAspectRatio, Qt.SmoothTransformation))

    def selected_existing(self) -> Asset:
        return self.matches[max(0, self.group.checkedId())][0]

    def _done(self, c):
        self.choice = c
        self.accept() if c != self.SKIP else self.reject()


# =========================================================================== página

class EntradaPage(QWidget):
    count_changed = Signal(int)

    def __init__(self, window):
        super().__init__()
        from .main_window import ASSET_ROLE, AssetModel, CardDelegate  # evita import circular
        self.w = window
        self.ASSET_ROLE = ASSET_ROLE
        self.items: list[Asset] = []
        self.similar: dict[tuple[str, str], list] = {}   # (item_key, cat_key) -> matches
        self._threads: set[SimilarThread] = set()

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        from .main_window import SideColumn
        left = QWidget()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(40, TITLE_H + 8, 32, 0)
        ll.setSpacing(20)
        top = QHBoxLayout()
        head = QVBoxLayout()
        head.setSpacing(2)
        t = QLabel("Entrada")
        t.setStyleSheet("font-size:21pt;")
        self.info = QLabel()
        self.info.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:10.5pt;")
        self.info.setWordWrap(True)
        head.addWidget(t)
        head.addWidget(self.info)
        top.addLayout(head, 1)
        b_open = QPushButton("Abrir pasta de entrada")
        b_open.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.path())))
        b_ref = QPushButton("Atualizar")
        b_ref.clicked.connect(self.refresh)
        top.addWidget(b_open, 0, Qt.AlignTop)
        top.addWidget(b_ref, 0, Qt.AlignTop)
        ll.addLayout(top)

        split = QSplitter()
        split.setHandleWidth(1)
        split.setChildrenCollapsible(False)
        self.model = AssetModel(window.db)
        self.grid = QListView()
        self.grid.setViewMode(QListView.IconMode)
        self.grid.setResizeMode(QListView.Adjust)
        self.grid.setMovement(QListView.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.grid.setSpacing(0)
        self.grid.setMouseTracking(True)
        self.grid.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.grid.setModel(self.model)

        page = self

        class EntradaDelegate(CardDelegate):
            def status_for(self, a: Asset):
                if a.kind == "missing":
                    return COL_BAD, "", False, False
                if not a.preview:
                    return COL_WARN, "", False, False
                return COL_OK, "", False, False

            def subtitle_for(self, a: Asset, busy, queued):
                f = _fmt(a)
                return {"PASTA": "pasta", "MAX": "arquivo .max", "SÓ IMAGEM": "só a imagem"}.get(f, f"compactado {f}") \
                    + ("" if a.preview else "  ·  sem prévia")

        self.grid.setItemDelegate(EntradaDelegate(window))
        self.grid.selectionModel().selectionChanged.connect(self._on_selection)
        ll.addWidget(self.grid, 1)
        split.addWidget(left)

        # painel de classificação
        panel = SideColumn(border_left=True)
        panel.setMinimumWidth(320)
        pl = QVBoxLayout(panel)
        pl.setContentsMargins(28, TITLE_H + 8, 28, 16)
        pl.setSpacing(10)
        self.preview = QLabel("Selecione um ou mais itens")
        self.preview.setAlignment(Qt.AlignCenter)
        self.preview.setMinimumHeight(240)
        self.preview.setStyleSheet("background:rgba(255,236,210,0.04); border:1px solid rgba(255,230,200,0.08);"
                                   f" border-radius:14px; color:{theme.FAINT.name()};")
        pl.addWidget(self.preview)
        self.title = QLabel()
        self.title.setStyleSheet("font-size:16pt;")
        self.title.setWordWrap(True)
        self.sub = QLabel()
        self.sub.setStyleSheet(f"color:{theme.MUTED.name()};")
        self.sub.setWordWrap(True)
        pl.addWidget(self.title)
        pl.addWidget(self.sub)

        pl.addWidget(self._heading("Mandar para a categoria"))
        self.cat = QComboBox()
        self.cat.setEditable(True)
        self.cat.setInsertPolicy(QComboBox.NoInsert)
        self.cat.lineEdit().setPlaceholderText("Digite ou escolha a categoria…")
        self.cat.currentIndexChanged.connect(self._on_category)
        pl.addWidget(self.cat)
        nrow = QHBoxLayout()
        self.new_name = QLabel()
        self.new_name.setStyleSheet("font-size:11.5pt;")
        self.new_name.setWordWrap(True)
        self.btn_prefix = ui.link_button("alterar nome")
        self.btn_prefix.setToolTip("Mudar o nome usado nos novos itens desta categoria (ex.: TETO em vez de LUMINARIA)")
        self.btn_prefix.clicked.connect(self._change_prefix)
        nrow.addWidget(self.new_name, 1)
        nrow.addWidget(self.btn_prefix, 0, Qt.AlignTop)
        pl.addLayout(nrow)

        pl.addWidget(self._heading("Possíveis repetidos nesta categoria"))
        self.dups = QListWidget()
        self.dups.setViewMode(QListView.IconMode)
        self.dups.setIconSize(QSize(96, 96))
        self.dups.setResizeMode(QListView.Adjust)
        self.dups.setMovement(QListView.Static)
        self.dups.setMaximumHeight(150)
        pl.addWidget(self.dups)
        self.dup_status = QLabel()
        self.dup_status.setStyleSheet(f"color:{theme.MUTED.name()};")
        self.dup_status.setWordWrap(True)
        pl.addWidget(self.dup_status)

        self.btn = ui.primary(QPushButton("Classificar  (Enter)"))
        self.btn.setMinimumHeight(42)
        self.btn.clicked.connect(self.classify)
        pl.addWidget(self.btn)
        row = QHBoxLayout()
        self.btn_discard = QPushButton("Descartar")
        self.btn_discard.setToolTip("Move para _DESCARTADOS (apagado depois do prazo do backup)")
        self.btn_discard.clicked.connect(self.discard_selected)
        self.btn_show = QPushButton("Mostrar no Explorer")
        self.btn_show.clicked.connect(self._reveal)
        row.addWidget(self.btn_discard)
        row.addWidget(self.btn_show)
        pl.addLayout(row)
        pl.addStretch(1)
        split.addWidget(panel)
        split.setStretchFactor(0, 1)
        split.setSizes([1000, 360])
        lay.addWidget(split, 1)

        for seq in ("Return", "Enter"):
            sc = QShortcut(QKeySequence(seq), self)
            sc.setContext(Qt.WidgetWithChildrenShortcut)
            sc.activated.connect(self.classify)

        self.watcher = QFileSystemWatcher(self)
        self.watcher.directoryChanged.connect(lambda _p: self._debounce.start())
        self._debounce = QTimer(self, singleShot=True, interval=1500)
        self._debounce.timeout.connect(self.refresh)
        window.thumbs.changed.connect(self.grid.viewport().update)
        self._update_panel()

    # ----------------------------------------------------------------- util
    def _heading(self, t):
        l = ui.heading(t, 10.5)
        l.setContentsMargins(0, 10, 0, 0)
        return l

    def path(self) -> str:
        return intake.entry_path(self.w.cfg["library_root"])

    def selected(self) -> list[Asset]:
        return [i.data(self.ASSET_ROLE) for i in self.grid.selectionModel().selectedIndexes()]

    # ----------------------------------------------------------------- dados
    def refresh(self):
        root = self.w.cfg["library_root"]
        if not root or not os.path.isdir(root):
            return
        keep = {a.key for a in self.selected()}
        self.items = intake.scan_entry(root)
        self.model.set_assets(self.items)
        sm = self.grid.selectionModel()
        for a in self.items:
            if a.key in keep:
                sm.select(self.model.index(self.model.row_of[a.key]), sm.SelectionFlag.Select)
        p = self.path()
        dirs = [p] + [os.path.join(dp, d) for dp, dn, _ in os.walk(p) for d in dn]
        old = self.watcher.directories()
        if old:
            self.watcher.removePaths(old)
        self.watcher.addPaths(dirs[:200])
        self.info.setText(f"Pasta de entrada: <b>{p}</b>   ·   {len(self.items)} item(ns). "
                          "Coloque aqui os downloads (arquivo + prévia com o mesmo nome).")
        self.count_changed.emit(len(self.items))
        self._update_panel()

    def fill_categories(self):
        cur = self.cat.currentData()
        self.cat.blockSignals(True)
        self.cat.clear()
        self.cat.addItem("", None)
        expand = {e.casefold() for e in self.w.cfg["expand_subfolders"]}
        for top in self.w.categories:
            if top.name.casefold() in expand and top.children:
                # ex.: LUMINARIAS -> só as subpastas imediatas (Luminária pendente, de piso…)
                for ch in top.children:
                    self.cat.addItem(f"{top.name} › {ch.name}", ch.key)
            else:
                self.cat.addItem(top.name, top.key)
        comp = QCompleter([self.cat.itemText(i) for i in range(1, self.cat.count())], self)
        comp.setCaseSensitivity(Qt.CaseInsensitive)
        comp.setFilterMode(Qt.MatchContains)
        self.cat.setCompleter(comp)
        i = self.cat.findData(cur or self.w.cfg["last_entry_category"])
        self.cat.setCurrentIndex(i if i > 0 else 0)
        self.cat.blockSignals(False)
        self._on_category()

    def top_of(self, c: Category) -> Category:
        return self.w.cat_by_key.get(c.key.split("/")[0], c)

    def scope(self, c: Category) -> list[Asset]:
        """Todos os itens da categoria principal (com subpastas): base da numeração e da busca de repetidos."""
        return self.top_of(c).all_assets()

    def _change_prefix(self):
        c = self.category()
        if not c:
            return
        from PySide6.QtWidgets import QInputDialog
        cur = self.w.prefix_for(c.key) or intake.name_pattern(c, self.scope(c))[0] or intake.guess_prefix(c.name)
        txt, ok = QInputDialog.getText(self, "Nome dos itens",
                                       f"Nome dos novos itens em {c.key.replace('/', ' › ')}\n"
                                       "(o número é colocado depois; deixe vazio para voltar ao automático):",
                                       text=cur)
        if not ok:
            return
        self.w.set_prefix(c.key, txt.strip() or None)
        self._update_panel()

    def category(self) -> Category | None:
        key = self.cat.currentData()
        if key is None:  # texto digitado: tenta achar
            txt = self.cat.currentText().strip().casefold()
            for i in range(1, self.cat.count()):
                if self.cat.itemText(i).casefold() == txt:
                    key = self.cat.itemData(i)
        return self.w.cat_by_key.get(key) if key else None

    # ----------------------------------------------------------------- painel
    def _on_selection(self, *_):
        self._update_panel()
        self._check_similar()

    def _on_category(self, *_):
        c = self.category()
        if c:
            self.w.cfg["last_entry_category"] = c.key
        self._update_panel()
        self._check_similar()

    def _update_panel(self):
        sel = self.selected()
        c = self.category()
        self.btn.setEnabled(bool(sel) and c is not None and any(a.kind != "missing" for a in sel))
        self.btn_discard.setEnabled(bool(sel))
        self.btn_show.setEnabled(bool(sel))
        if not sel:
            self.btn_prefix.setVisible(False)
            self.preview.setPixmap(QPixmap())
            self.preview.setText("Selecione um ou mais itens")
            self.title.setText("")
            self.sub.setText("")
            self.new_name.setText("")
            self.dups.clear()
            self.dup_status.setText("")
            return
        if len(sel) == 1:
            a = sel[0]
            pix = self.w.thumbs.get(a.preview)
            if pix:
                self.preview.setPixmap(pix.scaled(self.preview.width() - 8, 300, Qt.KeepAspectRatio,
                                                  Qt.SmoothTransformation))
            else:
                self.preview.setPixmap(QPixmap())
                self.preview.setText("sem prévia")
            self.title.setText(a.name)
            self.sub.setText(f"{_fmt(a)}  ·  " + ", ".join(os.path.basename(m) for m in a.members))
        else:
            self.preview.setPixmap(QPixmap())
            self.preview.setText(f"{len(sel)} itens selecionados")
            self.title.setText(f"{len(sel)} itens")
            self.sub.setText("Todos vão para a mesma categoria, em sequência.")
        if c:
            usable = [a for a in sel if a.kind != "missing"]
            names = intake.next_names(c, max(1, len(usable)), self.w.prefix_for(c.key), self.scope(c))
            txt = names[0] if len(names) == 1 else f"{names[0]}  …  {names[-1]}"
            self.new_name.setText(f"Vai ficar como: <b>{txt}</b>")
            if any(a.kind == "missing" for a in sel):
                self.new_name.setText(self.new_name.text() + "<br><span style='color:#d27a6a'>Itens só com imagem "
                                      "(sem arquivo do modelo) não são classificados.</span>")
        else:
            self.new_name.setText("<span style='color:#a89c8c'>Escolha a categoria acima.</span>")
        self.btn_prefix.setVisible(c is not None)

    def _check_similar(self):
        self.dups.clear()
        sel = [a for a in self.selected() if a.preview]
        c = self.category()
        if not sel or not c:
            self.dup_status.setText("")
            return
        todo = [a for a in sel if (a.key, c.key) not in self.similar]
        if not todo:
            self._show_similar()
            return
        self.dup_status.setText("Comparando com as prévias da categoria…")
        cache = str(self.w.cache_root / "assinaturas.db")
        t = SimilarThread(c.key, todo, self.scope(c), cache)
        t.done.connect(self._on_similar)
        # guarda a referência até a thread terminar (trocar de categoria rápido não pode derrubar o programa)
        self._threads.add(t)
        t.finished.connect(lambda t=t: self._threads.discard(t))
        t.start()

    def _on_similar(self, cat_key: str, results: list):
        for item_key, matches in results:
            self.similar[(item_key, cat_key)] = matches
        c = self.category()
        if c and c.key == cat_key:   # resultado de uma categoria que já não está escolhida: só guarda
            self._show_similar()

    def shutdown(self):
        for t in list(self._threads):
            t.wait(3000)

    def _show_similar(self):
        self.dups.clear()
        c = self.category()
        sel = [a for a in self.selected() if a.preview]
        if not c or not sel:
            return
        n_items = 0
        for a in sel:
            m = self.similar.get((a.key, c.key))
            if m is None:
                continue
            if m:
                n_items += 1
            for ex, s in m:
                it = QListWidgetItem(f"{ex.name}\n{s * 100:.0f}%")
                pix = self.w.thumbs.get(ex.preview)
                if pix:
                    it.setIcon(QIcon(pix))
                it.setToolTip(f"{a.name} ↔ {ex.name}: {s * 100:.0f}% parecido")
                self.dups.addItem(it)
        if n_items:
            self.dup_status.setText(f"<span style='color:#d6a15e'>⚠ {n_items} item(ns) parecem já existir. "
                                    "Ao classificar, você escolhe o que manter.</span>")
        else:
            self.dup_status.setText("<span style='color:#7fb48a'>Nenhum repetido encontrado.</span>")

    # ----------------------------------------------------------------- ações
    def classify(self):
        sel = [a for a in self.selected() if a.kind != "missing"]
        c = self.category()
        if not sel or not c:
            return
        prefix = self.w.prefix_for(c.key)
        if not prefix and intake.name_pattern(c, self.scope(c))[0] is None:
            from PySide6.QtWidgets import QInputDialog
            txt, ok = QInputDialog.getText(self, "Categoria vazia",
                                           f"A categoria {c.name} ainda não tem itens.\n"
                                           "Qual nome os itens devem ter? (o número é colocado depois)",
                                           text=intake.guess_prefix(c.name))
            if not ok or not txt.strip():
                return
            prefix = txt.strip()
            self.w.set_prefix(c.key, prefix)

        # garante a verificação de repetidos antes de mover
        missing = [a for a in sel if a.preview and (a.key, c.key) not in self.similar]
        if missing:
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                cache = intake.HashCache(str(self.w.cache_root / "assinaturas.db"))
                for a in missing:
                    self.similar[(a.key, c.key)] = intake.find_similar(a.preview, self.scope(c), cache)
            finally:
                QApplication.restoreOverrideCursor()

        top = self.top_of(c)
        # trava a categoria (numeração) e os itens da Entrada: duas pessoas não pegam o mesmo número
        cat_lock = f"cat:{top.key}"
        got, busy = self.w.try_lock([cat_lock], "classificando nesta categoria")
        if not got:
            QMessageBox.information(self, "Em uso", "\n".join(busy) + "\n\nTente de novo em instantes.")
            return
        locked, busy_items = self.w.try_lock([a.key for a in sel], "classificando")
        sel = [a for a in sel if a.key in locked]
        try:
            self._classify_locked(sel, c, top, prefix, busy_items)
        finally:
            for k in [cat_lock, *locked]:
                self.w.shared.release(k)

    def _classify_locked(self, sel, c, top, prefix, busy_items):
        root = self.w.cfg["library_root"]

        def fresh_scan():   # numeração sempre lida do disco (categoria inteira, com subpastas)
            t = scan_category(top.path, top.key, top.name, check_layout=False)
            stack, found = [t], None
            while stack:
                x = stack.pop()
                if x.key == c.key:
                    found = x
                stack.extend(x.children)
            return (found or t), t.all_assets()

        fresh, fresh_scope = fresh_scan()
        added, replaced, discarded, errors = [], [], 0, list(busy_items)
        for a in sel:
            matches = self.similar.get((a.key, c.key)) or []
            choice, existing = DuplicateDialog.KEEP_BOTH, None
            if matches:
                dlg = DuplicateDialog(self, self.w.thumbs, a, matches)
                dlg.exec()
                choice = dlg.choice
                existing = dlg.selected_existing()
            if choice == DuplicateDialog.SKIP:
                continue
            try:
                if choice == DuplicateDialog.KEEP_OLD:
                    rec = []
                    intake.discard(a, root, rec)
                    self.w.log_op("descartar", "_ENTRADA", a.key, f"{a.name} (repetido de item da biblioteca)", rec)
                    discarded += 1
                    continue
                if choice == DuplicateDialog.KEEP_NEW and existing is not None:
                    name = existing.name
                    dest = os.path.dirname(existing.members[0]) if existing.members else c.path
                    rec = []
                    trash = intake.discard(existing, root, rec)
                    r = intake.move_into(a, dest, name)
                    if r.ok:
                        replaced.append(name)
                        self.w.db.add_addition(existing.key, a.name)
                        self.w.log_op("substituir", c.key, existing.key, f"{name} pela versão nova ({a.name})",
                                      rec + r.pairs)
                    else:
                        intake.restore(trash, dest)   # devolve o existente
                        errors.append(f"{a.name}: {r.message}")
                    continue
                name = intake.next_names(fresh, 1, prefix, fresh_scope)[0]
                r = intake.move_into(a, c.path, name)
                if r.ok:
                    added.append(name)
                    self.w.db.add_addition(f"{c.key}/{name}", a.name)
                    self.w.log_op("classificar", c.key, f"{c.key}/{name}", f"{a.name} → {name}", r.pairs)
                    fresh, fresh_scope = fresh_scan()
                    if r.left_behind:
                        errors.append(f"{a.name}: imagens extras ficaram na Entrada "
                                      f"({', '.join(os.path.basename(x) for x in r.left_behind)})")
                else:
                    errors.append(f"{a.name}: {r.message}")
            except OSError as e:
                errors.append(f"{a.name}: {e}")

        self.refresh()
        self.w.refresh_category(c.key.split("/")[0])
        parts = []
        if added:
            parts.append(f"{len(added)} adicionado(s) em {c.name}: " + ", ".join(added))
        if replaced:
            parts.append(f"{len(replaced)} substituído(s): " + ", ".join(replaced))
        if discarded:
            parts.append(f"{discarded} descartado(s)")
        self.w.statusBar().showMessage("  ·  ".join(parts) or "Nada foi classificado.", 12000)
        if errors:
            QMessageBox.warning(self, "Entrada", "Alguns itens tiveram problema:\n\n" + "\n".join(errors))

    def discard_selected(self):
        sel = self.selected()
        if not sel:
            return
        if QMessageBox.question(self, "Descartar",
                                f"Descartar {len(sel)} item(ns) da Entrada?\n\nEles vão para _DESCARTADOS e são "
                                "apagados depois do prazo do backup.") != QMessageBox.Yes:
            return
        locked, busy = self.w.try_lock([a.key for a in sel], "descartando")
        try:
            for a in sel:
                if a.key not in locked:
                    continue
                rec = []
                try:
                    intake.discard(a, self.w.cfg["library_root"], rec)
                except OSError as e:
                    QMessageBox.warning(self, "Descartar", f"{a.name}: {e}")
                if rec:
                    self.w.log_op("descartar", "_ENTRADA", a.key, a.name, rec)
        finally:
            for k in locked:
                self.w.shared.release(k)
        if busy:
            QMessageBox.information(self, "Em uso", "\n".join(busy))
        self.refresh()

    def _reveal(self):
        sel = self.selected()
        if sel and sel[0].members:
            self.w.reveal(sel[0].members[0])
