"""Aba Organização (só administrador): juntar pastas e corrigir itens fora do lugar.

As duas ferramentas usam o mesmo motor: uma lista de "mudanças" (item → categoria de destino → nome novo),
mostrada numa tela de conferência antes de mexer em qualquer arquivo. Ao aplicar, cada item é movido e
renomeado (prévia, compactado ou pasta; o .max e as texturas dentro da pasta mantêm o nome), tags e coleções
acompanham, tudo fica no histórico com Desfazer e as categorias envolvidas ficam travadas para a equipe.
"""
from __future__ import annotations

import os
import unicodedata
from collections import Counter
from dataclasses import dataclass

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QImageReader, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout,
                               QLabel, QMenu, QMessageBox, QProgressDialog, QPushButton, QRadioButton,
                               QStackedWidget, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import intake, theme, ui
from .janela import TITLE_H
from .scanner import Asset, Category

IGNORE_FLAG = "ignorar_lugar"
ACTIONS = [("Mover", "move"), ("Pular", "skip"), ("Descartar", "discard")]


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return " ".join(s.replace("_", " ").replace("-", " ").split()).casefold()


def _singular(s: str) -> str:
    return s[:-1] if len(s) > 3 and s.endswith("s") else s


def item_prefix(a: Asset) -> str | None:
    m = intake.NAME_RE.match(a.name.strip())
    return m.group(1).strip() if m and m.group(1).strip() else None


@dataclass
class Change:
    asset: Asset
    dest: Category            # categoria de destino (pode ser a mesma: só renomear)
    reason: str = ""
    new_name: str = ""
    action: str = "move"
    dup_of: str = ""          # nome do possível repetido no destino


# ------------------------------------------------------------------ análise: itens fora do lugar
def leaf_categories(cats: list[Category]) -> list[Category]:
    out = []
    stack = list(cats)
    while stack:
        c = stack.pop(0)
        if c.assets:
            out.append(c)
        stack[:0] = c.children
    return out


def top_of(cat: Category, cats: list[Category]) -> Category:
    top = cat.key.split("/")[0]
    return next((c for c in cats if c.key == top), cat)


def find_misplaced(cats: list[Category], db, prefixes: dict[str, str]) -> list[Change]:
    """Itens cujo nome não segue o padrão da pasta onde estão."""
    leaves = leaf_categories(cats)
    # nome dominante de cada categoria (e o configurado na Entrada) -> categoria
    owner: dict[str, Category] = {}
    expected: dict[str, set[str]] = {}
    for c in leaves:
        exp = set()
        p, _, _ = intake.name_pattern(c)
        if p:
            exp.add(_norm(p))
            owner.setdefault(_norm(p), c)
        if prefixes.get(c.key):
            exp.add(_norm(prefixes[c.key]))
            owner.setdefault(_norm(prefixes[c.key]), c)
        g = _norm(intake.guess_prefix(c.name))
        exp.add(g)
        exp.add(_singular(_norm(c.name)))
        expected[c.key] = exp
    for c in leaves:                               # o nome da categoria também identifica o dono
        owner.setdefault(_singular(_norm(c.name)), c)
    # prefixos comuns na categoria de cima inteira (ex.: LUMINARIA nas subpastas de LUMINARIAS) também valem
    for top in cats:
        scope = top.all_assets()
        cnt = Counter(_norm(p) for p in (item_prefix(a) for a in scope) if p)
        common = {p for p, n in cnt.items() if n >= max(3, 0.2 * len(scope))}
        for c in leaf_categories([top]):
            expected[c.key] |= common

    out = []
    for c in leaves:
        exp = expected[c.key]
        for a in c.assets:
            if db.has_flag(a.key, IGNORE_FLAG) or a.kind == "missing":
                continue
            p = item_prefix(a)
            np_ = _norm(p) if p else ""
            if np_ and (np_ in exp or _singular(np_) in exp):
                continue
            target = owner.get(np_) or owner.get(_singular(np_)) if np_ else None
            if target is not None and target.key != c.key:
                out.append(Change(a, target, f"o nome indica {pretty(target.key)}"))
            else:
                out.append(Change(a, c, "nome fora do padrão da pasta" if p else "nome sem número"))
    return out


def pretty(key: str) -> str:
    return " › ".join(x[:1] + x[1:].lower() if x.isupper() else x for x in key.split("/"))


# ------------------------------------------------------------------ nomes novos + repetidos
def plan_names(changes: list[Change], cats: list[Category], db) -> None:
    """Dá o próximo número livre no destino (em sequência para vários itens indo para a mesma pasta)."""
    prefixes = db.prefixes()
    by_dest: dict[str, list[Change]] = {}
    for ch in changes:
        by_dest.setdefault(ch.dest.key, []).append(ch)
    for key, group in by_dest.items():
        dest = group[0].dest
        scope = top_of(dest, cats).all_assets()
        names = intake.next_names(dest, len(group), prefixes.get(dest.key), scope)
        for ch, nm in zip(group, names):
            ch.new_name = nm


def check_duplicates(changes: list[Change], cats: list[Category], cache_path: str, parent=None) -> None:
    cache = intake.HashCache(cache_path)
    prog = QProgressDialog("Procurando possíveis repetidos…", "Pular", 0, len(changes), parent)
    prog.setWindowTitle("Organização")
    prog.setMinimumDuration(400)
    for i, ch in enumerate(changes):
        prog.setValue(i)
        QApplication.processEvents()
        if prog.wasCanceled():
            break
        if not ch.asset.preview:
            continue
        scope = [a for a in top_of(ch.dest, cats).all_assets() if a.key != ch.asset.key]
        try:
            sim = intake.find_similar(ch.asset.preview, scope, cache)
        except Exception:  # noqa: BLE001
            sim = []
        if sim:
            ch.dup_of = sim[0][0].name
            ch.action = "skip"
    prog.setValue(len(changes))


def _thumb(path: str | None) -> QIcon:
    if not path:
        return QIcon()
    r = QImageReader(path)
    sz = r.size()
    if sz.isValid():
        r.setScaledSize(sz.scaled(72, 72, Qt.KeepAspectRatio))
    img = r.read()
    return QIcon(QPixmap.fromImage(img)) if not img.isNull() else QIcon()


# ------------------------------------------------------------------ tela de conferência
class ReviewDialog(QDialog):
    def __init__(self, parent, title: str, intro: str, changes: list[Change]):
        super().__init__(parent)
        self.changes = changes
        self.setWindowTitle(title)
        self.resize(1060, 640)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(12)
        t = QLabel(title)
        t.setStyleSheet("font-size:18pt;")
        outer.addWidget(t)
        s = QLabel(intro)
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{theme.MUTED.name()};")
        outer.addWidget(s)
        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Item atual", "Vai ficar como", "Observação", "Ação"])
        self.tree.setRootIsDecorated(False)
        self.tree.setIconSize(QSize(40, 40))
        self.tree.setStyleSheet("QTreeWidget::item{padding:4px 2px;}")
        self.combos: list[QComboBox] = []
        for ch in changes:
            it = QTreeWidgetItem([pretty(ch.asset.key), f"{pretty(ch.dest.key)} › {ch.new_name}",
                                  (f"possível repetido de {ch.dup_of}" if ch.dup_of else ch.reason), ""])
            it.setIcon(0, _thumb(ch.asset.preview))
            if ch.dup_of:
                it.setForeground(2, theme.WARN)
            self.tree.addTopLevelItem(it)
            cb = QComboBox()
            for label, key in ACTIONS:
                cb.addItem(label, key)
            cb.setCurrentIndex(cb.findData(ch.action))
            cb.currentIndexChanged.connect(self._count)
            self.tree.setItemWidget(it, 3, cb)
            self.combos.append(cb)
        for i, wdt in enumerate((290, 330, 200)):
            self.tree.setColumnWidth(i, wdt)
        self.tree.header().setStretchLastSection(True)
        outer.addWidget(self.tree, 1)
        row = QHBoxLayout()
        self.summary = QLabel()
        self.summary.setStyleSheet(f"color:{theme.MUTED.name()};")
        row.addWidget(self.summary, 1)
        bb = QDialogButtonBox()
        self.ok = ui.primary(bb.addButton("Aplicar", QDialogButtonBox.AcceptRole))
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        row.addWidget(bb)
        outer.addLayout(row)
        self._count()

    def _count(self, *_):
        acts = [cb.currentData() for cb in self.combos]
        m, d = acts.count("move"), acts.count("discard")
        self.summary.setText(f"{m} para mover e renomear" + (f"  ·  {d} para descartar" if d else "")
                             + f"  ·  {acts.count('skip')} pulado(s).  Nada foi alterado ainda.")
        self.ok.setEnabled(m + d > 0)

    def accept(self):
        for ch, cb in zip(self.changes, self.combos):
            ch.action = cb.currentData()
        super().accept()


# ------------------------------------------------------------------ aplicar
def apply_changes(w, changes: list[Change], op: str, merge_source: Category | None = None) -> tuple[int, int, list]:
    root = w.cfg["library_root"]
    todo = [c for c in changes if c.action in ("move", "discard")]
    tops = sorted({c.asset.key.split("/")[0] for c in todo} | {c.dest.key.split("/")[0] for c in todo})
    locks = [f"cat:{t}" for t in tops]
    got, busy = w.try_lock(locks, "organizando pastas")
    if busy:
        for k in got:
            w.shared.release(k)
        QMessageBox.information(w, "Em uso", "Alguém está mexendo nestas pastas agora:\n\n" + "\n".join(busy)
                                + "\n\nTente de novo em instantes.")
        return 0, 0, []
    moved = discarded = 0
    errors = []
    merge_pairs, merge_keys = [], []
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        for ch in todo:
            a = ch.asset
            if ch.action == "discard":
                rec = []
                try:
                    intake.discard(a, root, rec)
                    w.log_op("descartar", a.category, a.key, f"{a.name} (Organização)", rec)
                    discarded += 1
                except OSError as e:
                    errors.append(f"{a.name}: {e}")
                continue
            r = intake.move_into(a, ch.dest.path, ch.new_name)
            if not r.ok:
                errors.append(f"{a.name}: {r.message}")
                continue
            new_key = f"{ch.dest.key}/{ch.new_name}"
            w.db.move_item_data(a.key, new_key)
            same = ch.dest.key == a.category
            if merge_source is not None:          # juntar pastas: um registro só no fim (desfaz tudo de uma vez)
                merge_pairs += r.pairs
                merge_keys.append([a.key, new_key])
            else:
                w.log_op("renomear" if same else op, ch.dest.key, new_key,
                         f"{a.name} → {ch.new_name}" if same
                         else f"{pretty(a.key)} → {pretty(ch.dest.key)} › {ch.new_name}",
                         r.pairs, extra={"keys": [[a.key, new_key]]})
            moved += 1
            if r.left_behind:
                errors.append(f"{a.name}: imagens extras ficaram na pasta de origem")
        if merge_source is not None:
            _remove_if_empty(merge_source.path)
            if merge_pairs:
                dest = todo[0].dest
                w.log_op("juntar", dest.key, dest.key,
                         f"{pretty(merge_source.key)} → {pretty(dest.key)} ({len(merge_keys)} itens)",
                         merge_pairs, extra={"keys": merge_keys})
    finally:
        QApplication.restoreOverrideCursor()
        for k in got:
            w.shared.release(k)
    for t in tops:
        w.refresh_category(t)
    if merge_source is not None and not os.path.isdir(merge_source.path) and "/" not in merge_source.key:
        w._on_verify_removed(merge_source.key)      # categoria de cima que ficou vazia sai da lista
    w.entrada.fill_categories()
    return moved, discarded, errors


def _remove_if_empty(path: str) -> None:
    """Apaga a pasta de origem só se não sobrou nada (Thumbs.db/desktop.ini não contam)."""
    try:
        rest = [e for e in os.scandir(path)]
        if all(e.is_file() and e.name.casefold() in ("thumbs.db", "desktop.ini") for e in rest):
            for e in rest:
                os.remove(e.path)
            os.rmdir(path)
    except OSError:
        pass


# ------------------------------------------------------------------ página
class OrganizacaoPage(QWidget):
    def __init__(self, window):
        super().__init__()
        self.w = window
        lay = QVBoxLayout(self)
        lay.setContentsMargins(40, TITLE_H + 8, 40, 16)
        lay.setSpacing(8)
        head = QHBoxLayout()
        t = QLabel("Organização")
        t.setStyleSheet("font-size:24pt;")
        head.addWidget(t)
        head.addStretch(1)
        self.seg = ui.Segmented([("Itens fora do lugar", "lugar"), ("Juntar pastas", "juntar")])
        self.seg.currentIndexChanged.connect(lambda i: self.stack.setCurrentIndex(i))
        head.addWidget(self.seg, 0, Qt.AlignBottom)
        lay.addLayout(head)
        sub = QLabel("Ferramentas do administrador para arrumar a biblioteca sem abrir o Explorer. Nada é alterado "
                     "antes da tela de conferência, e tudo pode ser desfeito pelo histórico.")
        sub.setWordWrap(True)
        sub.setStyleSheet(f"color:{theme.MUTED.name()};")
        lay.addWidget(sub)
        lay.addSpacing(10)
        self.locked = QLabel("Só o administrador da biblioteca usa a Organização.")
        self.locked.setStyleSheet(f"color:{theme.FAINT.name()}; padding:40px;")
        self.locked.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.locked)
        self.stack = QStackedWidget()
        lay.addWidget(self.stack, 1)

        # ---- itens fora do lugar
        p1 = QWidget()
        l1 = QVBoxLayout(p1)
        l1.setContentsMargins(0, 0, 0, 0)
        l1.setSpacing(10)
        r1 = QHBoxLayout()
        self.find_btn = ui.primary(QPushButton("Procurar"))
        self.find_btn.clicked.connect(self.scan_misplaced)
        r1.addWidget(self.find_btn)
        self.found = QLabel("Procura itens cujo nome não combina com a pasta (ex.: CAMA 01 dentro de MESAS).")
        self.found.setStyleSheet(f"color:{theme.MUTED.name()};")
        r1.addWidget(self.found, 1)
        self.move_btn = QPushButton("Conferir e mover marcados…")
        self.move_btn.clicked.connect(self.review_misplaced)
        r1.addWidget(self.move_btn)
        l1.addLayout(r1)
        self.list = QTreeWidget()
        self.list.setHeaderLabels(["Item", "Sugestão", "Motivo"])
        self.list.setRootIsDecorated(False)
        self.list.setIconSize(QSize(40, 40))
        self.list.setStyleSheet("QTreeWidget::item{padding:4px 2px;}")
        self.list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._list_menu)
        for i, wdt in enumerate((360, 360, 260)):
            self.list.setColumnWidth(i, wdt)
        l1.addWidget(self.list, 1)
        hint = QLabel("Botão direito num item: escolher outra pasta de destino ou ignorar (não aparece mais).")
        hint.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:9.3pt;")
        l1.addWidget(hint)
        self.stack.addWidget(p1)
        self.changes: list[Change] = []

        # ---- juntar pastas
        p2 = QWidget()
        l2 = QVBoxLayout(p2)
        l2.setContentsMargins(0, 0, 0, 0)
        l2.setSpacing(12)
        g = ui.Glass(14)
        gl = QVBoxLayout(g)
        gl.setContentsMargins(22, 18, 22, 20)
        gl.setSpacing(10)
        gl.addWidget(ui.heading("Juntar duas pastas", 12))
        e = QLabel("Os itens de uma pasta passam para a outra, renomeados na sequência dela (ex.: MATERIAL 05 → "
                   "MATERIAIS E TEXTURAS 41). A pasta que ficar vazia é apagada; se sobrar algo nela, ela fica.")
        e.setWordWrap(True)
        e.setStyleSheet(f"color:{theme.MUTED.name()};")
        gl.addWidget(e)
        self.ca, self.cb = QComboBox(), QComboBox()
        for lbl, cb in (("Pasta A", self.ca), ("Pasta B", self.cb)):
            row = QHBoxLayout()
            ll = QLabel(lbl)
            ll.setFixedWidth(70)
            row.addWidget(ll)
            row.addWidget(cb, 1)
            gl.addLayout(row)
        go = ui.primary(QPushButton("Continuar…"))
        go.clicked.connect(self.start_merge)
        gl.addWidget(go, 0, Qt.AlignRight)
        l2.addWidget(g)
        l2.addStretch(1)
        self.stack.addWidget(p2)

    # ------------------------------------------------------------------ comum
    def refresh(self):
        admin = self.w.is_admin() or self.w.shared.lib is None
        self.locked.setVisible(not admin)
        self.stack.setVisible(admin)
        self.seg.setVisible(admin)
        for cb in (self.ca, self.cb):
            cur = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("", None)
            for c in self._all_cats_flat():
                cb.addItem(f"{pretty(c.key)}   ({len(c.all_assets())})", c.key)
            i = cb.findData(cur)
            cb.setCurrentIndex(i if i >= 0 else 0)
            cb.blockSignals(False)

    def _all_cats_flat(self) -> list[Category]:
        out, stack = [], list(self.w.categories)
        while stack:
            c = stack.pop(0)
            out.append(c)
            stack[:0] = c.children
        return out

    def _cat(self, key) -> Category | None:
        return self.w.cat_by_key.get(key)

    def _review_and_apply(self, changes, title, intro, op, merge_source=None):
        plan_names(changes, self.w.categories, self.w.db)
        check_duplicates(changes, self.w.categories, str(self.w.cache_root / "assinaturas.db"), self)
        d = ReviewDialog(self, title, intro, changes)
        if d.exec() != QDialog.Accepted:
            return False
        moved, disc, errors = apply_changes(self.w, changes, op, merge_source)
        msg = f"{moved} item(ns) movido(s) e renomeado(s)" + (f", {disc} descartado(s)" if disc else "") + "."
        self.w.statusBar().showMessage(msg, 10000)
        if errors:
            QMessageBox.warning(self, "Organização", msg + "\n\nAlguns itens tiveram problema:\n\n" + "\n".join(errors))
        return True

    # ------------------------------------------------------------------ itens fora do lugar
    def scan_misplaced(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.changes = find_misplaced(self.w.categories, self.w.db, self.w.db.prefixes())
        finally:
            QApplication.restoreOverrideCursor()
        self._fill_list()

    def _fill_list(self):
        self.list.clear()
        for ch in self.changes:
            it = QTreeWidgetItem([pretty(ch.asset.key),
                                  ("renomear aqui mesmo" if ch.dest.key == ch.asset.category
                                   else f"mover para {pretty(ch.dest.key)}"), ch.reason])
            it.setIcon(0, _thumb(ch.asset.preview))
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Checked if ch.dest.key != ch.asset.category else Qt.Unchecked)
            self.list.addTopLevelItem(it)
        n = len(self.changes)
        self.found.setText(f"{n} item(ns) com nome fora do padrão da pasta." if n else
                           "Nenhum item fora do lugar. Tudo certo!")
        self.move_btn.setEnabled(n > 0)

    def _list_menu(self, pos):
        it = self.list.itemAt(pos)
        if it is None:
            return
        ch = self.changes[self.list.indexOfTopLevelItem(it)]
        m = QMenu(self)
        dest = m.addMenu("Mover para…")
        for c in self._all_cats_flat():
            if c.assets or not c.children:
                dest.addAction(pretty(c.key), lambda c=c: self._set_dest(ch, it, c))
        m.addAction("Renomear aqui mesmo", lambda: self._set_dest(ch, it, self._cat(ch.asset.category)))
        m.addSeparator()
        m.addAction("Ignorar este item (está certo assim)", lambda: self._ignore(ch))
        m.exec(self.list.viewport().mapToGlobal(pos))

    def _set_dest(self, ch, it, cat):
        if cat is None:
            return
        ch.dest = cat
        it.setText(1, "renomear aqui mesmo" if cat.key == ch.asset.category else f"mover para {pretty(cat.key)}")
        it.setText(2, "escolhido por você")
        it.setCheckState(0, Qt.Checked)

    def _ignore(self, ch):
        self.w.db.set_flag(ch.asset.key, IGNORE_FLAG)
        self.changes.remove(ch)
        self._fill_list()

    def review_misplaced(self):
        sel = [ch for i, ch in enumerate(self.changes)
               if self.list.topLevelItem(i).checkState(0) == Qt.Checked]
        if not sel:
            QMessageBox.information(self, "Organização", "Marque ao menos um item.")
            return
        for ch in sel:
            ch.action, ch.dup_of = "move", ""
        if self._review_and_apply(sel, "Conferir itens fora do lugar",
                                  "Cada item vai para a pasta indicada com o próximo número livre de lá. "
                                  "Itens parecidos com algo que já existe no destino vêm marcados como "
                                  "\"Pular\"; escolha o que fazer em cada um.", "mover"):
            self.scan_misplaced()

    # ------------------------------------------------------------------ juntar pastas
    def start_merge(self):
        a, b = self._cat(self.ca.currentData()), self._cat(self.cb.currentData())
        if not a or not b or a.key == b.key:
            QMessageBox.information(self, "Juntar pastas", "Escolha duas pastas diferentes.")
            return
        if a.key.startswith(b.key + "/") or b.key.startswith(a.key + "/"):
            QMessageBox.information(self, "Juntar pastas", "Uma pasta está dentro da outra; escolha pastas separadas.")
            return
        d = QDialog(self)
        d.setWindowTitle("Qual é a pasta principal?")
        v = QVBoxLayout(d)
        v.setContentsMargins(26, 22, 26, 18)
        v.setSpacing(12)
        q = QLabel("Qual pasta fica (a principal)? Os itens da outra vão para ela, renomeados na sequência dela.")
        q.setWordWrap(True)
        v.addWidget(q)
        grp = QButtonGroup(d)
        ra = QRadioButton(f"{pretty(a.key)}  ({len(a.all_assets())} itens)")
        rb = QRadioButton(f"{pretty(b.key)}  ({len(b.all_assets())} itens)")
        (ra if len(a.all_assets()) >= len(b.all_assets()) else rb).setChecked(True)
        for r in (ra, rb):
            grp.addButton(r)
            v.addWidget(r)
        bb = QDialogButtonBox()
        ui.primary(bb.addButton("Continuar", QDialogButtonBox.AcceptRole))
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        v.addWidget(bb)
        if d.exec() != QDialog.Accepted:
            return
        main, other = (a, b) if ra.isChecked() else (b, a)
        if other.children:
            QMessageBox.information(self, "Juntar pastas",
                                    f"{pretty(other.key)} tem subpastas. Junte primeiro as subpastas, uma de cada vez.")
            return
        dest = main if main.assets or not main.children else None
        if dest is None:
            QMessageBox.information(self, "Juntar pastas", f"{pretty(main.key)} só tem subpastas; escolha uma delas "
                                                           "como principal.")
            return
        changes = [Change(x, dest, f"vem de {pretty(other.key)}") for x in other.assets if x.kind != "missing"]
        if not changes:
            QMessageBox.information(self, "Juntar pastas", f"{pretty(other.key)} não tem itens para mover.")
            return
        self._review_and_apply(changes, f"Juntar {pretty(other.key)} em {pretty(main.key)}",
                               f"Os {len(changes)} itens de {pretty(other.key)} vão para {pretty(main.key)} com os "
                               "próximos números livres. Itens parecidos com algo que já existe vêm marcados "
                               "como \"Pular\".", "juntar", merge_source=other)
        self.refresh()
