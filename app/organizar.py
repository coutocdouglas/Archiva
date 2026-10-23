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

from PySide6.QtCore import Qt
from PySide6.QtGui import QImageReader, QPixmap
from PySide6.QtWidgets import (QApplication, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMenu,
                               QMessageBox, QProgressDialog, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

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
    dup_asset: Asset | None = None


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
            ch.dup_asset = sim[0][0]
            ch.action = "skip"
    prog.setValue(len(changes))


# ------------------------------------------------------------------ aplicar
def apply_changes(w, changes: list[Change], op: str, merge_source: Category | None = None) -> tuple[int, int, list]:
    root = w.cfg["library_root"]
    todo = [c for c in changes if c.action in ("move", "discard")]
    tops = sorted({c.asset.key.split("/")[0] for c in todo} | {c.dest.key.split("/")[0] for c in todo})
    locks = [f"cat:{t}" for t in tops] + sorted({c.asset.key for c in todo})   # categorias + cada item mexido
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
            _remove_empty_tree(merge_source.path)
            if merge_pairs:
                dest = todo[0].dest
                w.log_op(op if op in ("juntar", "absorver") else "juntar", dest.key, dest.key,
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


def _remove_empty_tree(path: str) -> None:
    """Apaga as subpastas que ficaram vazias (de baixo para cima) e depois a pasta. Pasta com qualquer arquivo
    que sobrou (ex.: uma subpasta oculta por alguém em 'Pastas exibidas') fica."""
    for r, _d, _f in sorted(os.walk(path), key=lambda t: -len(t[0])):
        if r != path:
            _remove_if_empty(r)
    _remove_if_empty(path)


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




# ================================================================== parte visual
from PySide6.QtCore import QPointF, QRectF  # noqa: E402
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen  # noqa: E402
from PySide6.QtWidgets import QCheckBox, QScrollArea  # noqa: E402

_PIX: dict[tuple, QPixmap | None] = {}
_EDGE: dict[str, QColor] = {}


def thumb_pixmap(path: str | None, size: int) -> QPixmap | None:
    if not path:
        return None
    k = (path, size)
    if k in _PIX:
        _PIX[k] = _PIX.pop(k)          # mais usada vai para o fim (as do começo saem primeiro)
    else:
        r = QImageReader(path)
        r.setAutoTransform(True)
        sz = r.size()
        if sz.isValid():
            r.setScaledSize(sz.scaled(size * 2, size * 2, Qt.KeepAspectRatio))
        img = r.read()
        _PIX[k] = QPixmap.fromImage(img) if not img.isNull() else None
        while len(_PIX) > 300:
            _PIX.pop(next(iter(_PIX)))
    return _PIX[k]


class Thumb(QWidget):
    """Miniatura com cantos arredondados sobre a cor do próprio fundo (ou um marcador quando não há prévia)."""

    def __init__(self, path: str | None, size: int = 88, radius: float = 12):
        super().__init__()
        self.path, self.r = path, radius
        self.setFixedSize(size, size)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, self.r, self.r)
        pm = thumb_pixmap(self.path, self.width())
        p.setClipPath(path)
        if pm:
            col = _EDGE.get(self.path)
            if col is None:
                from .home_page import edge_color
                col = _EDGE[self.path] = edge_color(pm)
            p.fillRect(r, col)
            sz = pm.size().scaled(r.size().toSize(), Qt.KeepAspectRatio)
            p.drawPixmap(QRectF(r.center().x() - sz.width() / 2, r.center().y() - sz.height() / 2,
                                sz.width(), sz.height()), pm, QRectF(pm.rect()))
        else:
            p.fillRect(r, QColor(255, 236, 210, 14))
            ic = ui.icon_pixmap("pasta", theme.FAINT, max(14, self.width() // 3))
            p.drawPixmap(int(r.center().x() - ic.width() / 4), int(r.center().y() - ic.height() / 4), ic)
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 236, 210, 30), 1))
        p.drawPath(path)


class Arrow(QWidget):
    def __init__(self, width=44, label=""):
        super().__init__()
        self.label = label
        self.setFixedWidth(width)
        self.setMinimumHeight(40)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        y = self.height() / 2
        p.setPen(QPen(theme.HILITE, 1.8, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        x0, x1 = 6, self.width() - 8
        p.drawLine(QPointF(x0, y), QPointF(x1, y))
        p.drawLine(QPointF(x1 - 7, y - 6), QPointF(x1, y))
        p.drawLine(QPointF(x1 - 7, y + 6), QPointF(x1, y))


def _small(text, color=None, size=8.2, spacing=1.2):
    l = QLabel(text)
    l.setStyleSheet(f"color:{(color or theme.FAINT).name()}; font-size:{size}pt; letter-spacing:{spacing}px;")
    return l


def _pill(text, fg, bg):
    l = QLabel(text)
    l.setStyleSheet(f"color:{fg}; background:{bg}; border-radius:9px; padding:2px 9px; font-size:8.6pt;")
    l.setSizePolicy(l.sizePolicy().horizontalPolicy(), l.sizePolicy().verticalPolicy())
    return l


class ChangeCard(ui.Glass):
    """Um item: como está agora → como vai ficar (com miniaturas). mode = 'list' (marcar) ou 'review' (ação)."""

    def __init__(self, page, ch: Change, mode: str = "list"):
        super().__init__(14)
        self.page, self.ch, self.mode = page, ch, mode
        row = QHBoxLayout(self)
        row.setContentsMargins(14, 12, 16, 12)
        row.setSpacing(16)
        if mode == "list":
            self.check = QCheckBox()
            self.check.setToolTip("Incluir na mudança")
            row.addWidget(self.check)
        a = ch.asset
        row.addWidget(Thumb(a.preview, 84))
        src = QVBoxLayout()
        src.setSpacing(3)
        src.addWidget(_small("AGORA"))
        src.addWidget(_small(pretty(a.category), theme.MUTED, 9.4, 0))
        nm = QLabel(a.name)
        nm.setStyleSheet("font-size:12.5pt;")
        src.addWidget(nm)
        src.addWidget(_pill(ch.reason or "fora do padrão", "#26150c", theme.WARN.name()), 0, Qt.AlignLeft)
        src.addStretch(1)
        row.addLayout(src, 3)
        row.addWidget(Arrow())
        dst = QVBoxLayout()
        dst.setSpacing(3)
        same = ch.dest.key == a.category
        dst.addWidget(_small("VAI FICAR (RENOMEADO AQUI)" if same else "VAI PARA"))
        dst.addWidget(_small(pretty(ch.dest.key), theme.MUTED, 9.4, 0))
        nn = QLabel(ch.new_name or "—")
        nn.setStyleSheet(f"font-size:12.5pt; color:{theme.HILITE.name()};")
        dst.addWidget(nn)
        nb = [x for x in ch.dest.assets if x.key != a.key][-4:]
        if nb:
            strip = QHBoxLayout()
            strip.setSpacing(5)
            for x in nb:
                t = Thumb(x.preview, 30, 7)
                t.setToolTip(x.name)
                strip.addWidget(t)
            strip.addSpacing(6)
            strip.addWidget(_small(f"junto de {nb[0].name} … {nb[-1].name}" if len(nb) > 1
                                   else f"junto de {nb[0].name}", theme.FAINT, 8.4, 0))
            strip.addStretch(1)
            dst.addLayout(strip)
        dst.addStretch(1)
        row.addLayout(dst, 3)
        if mode == "review" and ch.dup_asset is not None:
            dup = QVBoxLayout()
            dup.setSpacing(3)
            dup.addWidget(_small("PARECIDO COM", theme.WARN))
            dup.addWidget(Thumb(ch.dup_asset.preview, 60, 9))
            dup.addWidget(_small(ch.dup_asset.name, theme.MUTED, 8.6, 0))
            row.addLayout(dup)
        right = QVBoxLayout()
        right.setSpacing(8)
        if mode == "list":
            self.dest_btn = QPushButton("Trocar destino")
            self.dest_btn.setMenu(page.dest_menu(self.dest_btn, ch))
            right.addWidget(self.dest_btn)
            ign = QPushButton("Ignorar")
            ign.setProperty("flat", True)
            ign.setToolTip("Está certo assim: não mostrar mais este item")
            ign.clicked.connect(lambda: page.ignore(ch))
            right.addWidget(ign)
        else:
            self.combo = QComboBox()
            for label, key in ACTIONS:
                self.combo.addItem(label, key)
            self.combo.setCurrentIndex(self.combo.findData(ch.action))
            self.combo.setMinimumWidth(130)
            right.addWidget(_small("AÇÃO"))
            right.addWidget(self.combo)
        right.addStretch(1)
        row.addLayout(right)


def _scroll_box():
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QScrollArea.NoFrame)
    area.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
    box = QWidget()
    lay = QVBoxLayout(box)
    lay.setContentsMargins(0, 0, 8, 0)
    lay.setSpacing(10)
    area.setWidget(box)
    return area, lay


class ReviewDialog(QDialog):
    """Conferência antes de mexer nos arquivos: um cartão por item, com a ação escolhida em cada um."""

    def __init__(self, parent, title: str, intro: str, changes: list[Change], page=None):
        super().__init__(parent)
        self.changes = changes
        self.setWindowTitle(title)
        self.resize(1200, 760)
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
        area, lay = _scroll_box()
        self.cards = []
        for ch in changes:
            c = ChangeCard(page, ch, "review")
            c.combo.currentIndexChanged.connect(self._count)
            lay.addWidget(c)
            self.cards.append(c)
        lay.addStretch(1)
        outer.addWidget(area, 1)
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
        acts = [c.combo.currentData() for c in self.cards]
        m, d = acts.count("move"), acts.count("discard")
        self.summary.setText(f"{m} para mover e renomear" + (f"  ·  {d} para descartar" if d else "")
                             + f"  ·  {acts.count('skip')} pulado(s).   Nada foi alterado ainda.")
        self.ok.setEnabled(m + d > 0)

    def accept(self):
        for c in self.cards:
            c.ch.action = c.combo.currentData()
        super().accept()


class FolderCard(ui.Glass):
    """Pasta no 'Juntar pastas': escolha, quantidade, padrão de nomes e algumas miniaturas."""

    def __init__(self, page, title: str, principal: bool):
        super().__init__(16)
        self.page, self.principal = page, principal
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 18)
        v.setSpacing(8)
        head = QHBoxLayout()
        head.addWidget(_small(title, theme.HILITE if principal else theme.FAINT, 8.6))
        head.addStretch(1)
        v.addLayout(head)
        self.combo = QComboBox()
        v.addWidget(self.combo)
        self.name = QLabel()
        self.name.setStyleSheet("font-size:17pt;")
        v.addWidget(self.name)
        self.info = QLabel()
        self.info.setStyleSheet(f"color:{theme.MUTED.name()};")
        self.info.setWordWrap(True)
        v.addWidget(self.info)
        self.strip = QHBoxLayout()
        self.strip.setSpacing(8)
        v.addLayout(self.strip)
        v.addStretch(1)
        self.setMinimumHeight(260)

    def show_cat(self, cat: Category | None):
        while self.strip.count():
            it = self.strip.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        if cat is None:
            self.name.setText("—")
            self.info.setText("Escolha uma pasta acima.")
            return
        self.name.setText(pretty(cat.key))
        absorb = not self.principal and bool(cat.children)
        items = cat.all_assets() if absorb else cat.assets
        parsed = [a.name for a in items]
        pat = intake.name_pattern(cat)[0] if items else None
        rng = f"{parsed[0]}  …  {parsed[-1]}" if len(parsed) > 1 else (parsed[0] if parsed else "")
        self.info.setText(f"{len(items)} itens" + (f"  ·  nome dos itens: {pat} NN" if pat else "")
                          + (f"\n{rng}" if rng else "")
                          + (f"\nInclui {len(cat.children)} subpasta(s): "
                             + ", ".join(pretty(c.key.split('/')[-1]) for c in cat.children[:5])
                             + (" …" if len(cat.children) > 5 else "") + " — todas vão juntas." if absorb else "")
                          + ("\nTem subpastas: escolha uma delas." if self.principal and cat.children and not cat.assets
                             else ""))
        for a in items[-6:]:
            t = Thumb(a.preview, 64, 10)
            t.setToolTip(a.name)
            self.strip.addWidget(t)
        self.strip.addStretch(1)


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
        self.seg = ui.Segmented([("Itens fora do lugar", "lugar"), ("Juntar pastas", "juntar"),
                                 ("Possíveis repetidos", "repetidos")])
        self.seg.currentIndexChanged.connect(lambda i: (self.stack.setCurrentIndex(i), self._update_merge()))
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
        l1.setSpacing(12)
        r1 = QHBoxLayout()
        r1.setSpacing(10)
        self.find_btn = ui.primary(QPushButton("Procurar"))
        self.find_btn.clicked.connect(self.scan_misplaced)
        r1.addWidget(self.find_btn)
        self.found = QLabel("Procura itens cujo nome não combina com a pasta (ex.: CAMA 01 dentro de MESAS).")
        self.found.setStyleSheet(f"color:{theme.MUTED.name()};")
        r1.addWidget(self.found, 1)
        self.all_btn = QPushButton("Marcar todos")
        self.all_btn.clicked.connect(lambda: self._check_all(True))
        self.none_btn = QPushButton("Desmarcar")
        self.none_btn.clicked.connect(lambda: self._check_all(False))
        self.move_btn = ui.primary(QPushButton("Conferir marcados…"))
        self.move_btn.clicked.connect(self.review_misplaced)
        for b in (self.all_btn, self.none_btn, self.move_btn):
            r1.addWidget(b)
        l1.addLayout(r1)
        self.area, self.cards_lay = _scroll_box()
        l1.addWidget(self.area, 1)
        self.stack.addWidget(p1)
        self.changes: list[Change] = []
        self.cards: list[ChangeCard] = []

        # ---- juntar pastas
        p2 = QWidget()
        l2 = QVBoxLayout(p2)
        l2.setContentsMargins(0, 0, 0, 0)
        l2.setSpacing(14)
        row = QHBoxLayout()
        row.setSpacing(18)
        self.src_card = FolderCard(self, "PASTA QUE VAI SER JUNTADA (SAI)", False)
        self.dst_card = FolderCard(self, "PASTA PRINCIPAL (FICA)", True)
        mid = QVBoxLayout()
        mid.addStretch(1)
        mid.addWidget(Arrow(90), 0, Qt.AlignHCenter)
        cap = _small("os itens vão para a\nprincipal e ganham\no nome dela", theme.MUTED, 8.8, 0)
        cap.setAlignment(Qt.AlignCenter)
        mid.addWidget(cap)
        swap = QPushButton("⇄  Inverter")
        swap.clicked.connect(self._swap)
        mid.addWidget(swap, 0, Qt.AlignHCenter)
        mid.addStretch(1)
        row.addWidget(self.src_card, 1)
        row.addLayout(mid)
        row.addWidget(self.dst_card, 1)
        l2.addLayout(row)
        for card in (self.src_card, self.dst_card):
            card.combo.currentIndexChanged.connect(self._update_merge)
        l2.addWidget(ui.heading("Como vai ficar", 11))
        self.prev_area, self.prev_lay = _scroll_box()
        l2.addWidget(self.prev_area, 1)
        brow = QHBoxLayout()
        self.merge_info = QLabel()
        self.merge_info.setStyleSheet(f"color:{theme.MUTED.name()};")
        brow.addWidget(self.merge_info, 1)
        self.merge_btn = ui.primary(QPushButton("Conferir e juntar…"))
        self.merge_btn.clicked.connect(self.start_merge)
        brow.addWidget(self.merge_btn)
        l2.addLayout(brow)
        self.stack.addWidget(p2)

        # ---- possíveis repetidos
        from .repetidos import RepetidosPanel
        self.repetidos = RepetidosPanel(self)
        self.stack.addWidget(self.repetidos)

    # ------------------------------------------------------------------ comum
    def refresh(self):
        admin = self.w.is_admin() or self.w.shared.lib is None
        self.locked.setVisible(not admin)
        self.stack.setVisible(admin)
        self.seg.setVisible(admin)
        for cb in (self.src_card.combo, self.dst_card.combo):
            cur = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem("Escolha a pasta…", None)
            for c in self._all_cats_flat():
                cb.addItem(f"{pretty(c.key)}   ({len(c.all_assets())})", c.key)
            i = cb.findData(cur)
            cb.setCurrentIndex(i if i >= 0 else 0)
            cb.blockSignals(False)
        self._update_merge()

    def _all_cats_flat(self) -> list[Category]:
        out, stack = [], list(self.w.categories)
        while stack:
            c = stack.pop(0)
            out.append(c)
            stack[:0] = c.children
        return out

    def _cat(self, key) -> Category | None:
        return self.w.cat_by_key.get(key)

    def dest_menu(self, parent, ch: Change) -> QMenu:
        m = QMenu(parent)
        m.addAction("Renomear aqui mesmo", lambda: self.set_dest(ch, self._cat(ch.asset.category)))
        m.addSeparator()
        fill_category_menu(m, self.w.categories, lambda c: self.set_dest(ch, c))
        return m

    def review(self, changes, title, intro, op, merge_source=None) -> bool:
        plan_names(changes, self.w.categories, self.w.db)
        check_duplicates(changes, self.w.categories, str(self.w.cache_root / "assinaturas.db"), self)
        d = ReviewDialog(self.w, title, intro, changes, self)
        if d.exec() != QDialog.Accepted:
            return False
        moved, disc, errors = apply_changes(self.w, changes, op, merge_source)
        msg = f"{moved} item(ns) movido(s) e renomeado(s)" + (f", {disc} descartado(s)" if disc else "") + "."
        self.w.statusBar().showMessage(msg, 10000)
        if errors:
            QMessageBox.warning(self.w, "Organização", msg + "\n\nAlguns itens tiveram problema:\n\n" + "\n".join(errors))
        return True

    # ------------------------------------------------------------------ itens fora do lugar
    def scan_misplaced(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.changes = find_misplaced(self.w.categories, self.w.db, self.w.db.prefixes())
            plan_names(self.changes, self.w.categories, self.w.db)
        finally:
            QApplication.restoreOverrideCursor()
        self._fill_cards()

    def _fill_cards(self):
        checked = {id(c.ch) for c in self.cards if c.check.isChecked()}
        first = not self.cards
        while self.cards_lay.count():
            it = self.cards_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.cards = []
        moves = [c for c in self.changes if c.dest.key != c.asset.category]
        renames = [c for c in self.changes if c.dest.key == c.asset.category]
        for title, group, default in (("Mover para outra pasta", moves, True),
                                      ("Renomear na própria pasta", renames, False)):
            if not group:
                continue
            self.cards_lay.addWidget(ui.heading(f"{title}  ({len(group)})", 11))
            for ch in group:
                card = ChangeCard(self, ch, "list")
                card.check.setChecked(default if first else id(ch) in checked)
                self.cards_lay.addWidget(card)
                self.cards.append(card)
            self.cards_lay.addSpacing(10)
        self.cards_lay.addStretch(1)
        n = len(self.changes)
        self.found.setText(f"{len(moves)} para mover de pasta  ·  {len(renames)} para renomear." if n else
                           "Nenhum item fora do lugar. Tudo certo!")
        for b in (self.all_btn, self.none_btn, self.move_btn):
            b.setEnabled(n > 0)

    def _check_all(self, on):
        for c in self.cards:
            c.check.setChecked(on)

    def set_dest(self, ch, cat):
        if cat is None:
            return
        for c in self.cards:
            if c.ch is ch:
                c.check.setChecked(True)
        ch.dest = cat
        ch.reason = "escolhido por você" if cat.key != ch.asset.category else "renomear na sequência da pasta"
        plan_names(self.changes, self.w.categories, self.w.db)
        self._fill_cards()

    def ignore(self, ch):
        self.w.db.set_flag(ch.asset.key, IGNORE_FLAG)
        self.changes.remove(ch)
        self._fill_cards()

    def review_misplaced(self):
        sel = [c.ch for c in self.cards if c.check.isChecked()]
        if not sel:
            QMessageBox.information(self, "Organização", "Marque ao menos um item.")
            return
        for ch in sel:
            ch.action, ch.dup_of, ch.dup_asset = "move", "", None
        if self.review(sel, "Conferir itens fora do lugar",
                       "Cada item vai para a pasta indicada com o próximo número livre de lá. Itens parecidos com "
                       "algo que já existe no destino vêm marcados como \"Pular\"; escolha o que fazer em cada um.",
                       "mover"):
            self.scan_misplaced()

    # ------------------------------------------------------------------ juntar pastas
    def _swap(self):
        a, b = self.src_card.combo.currentIndex(), self.dst_card.combo.currentIndex()
        for cb, i in ((self.src_card.combo, b), (self.dst_card.combo, a)):
            cb.blockSignals(True)
            cb.setCurrentIndex(i)
            cb.blockSignals(False)
        self._update_merge()

    def _merge_pair(self):
        return self._cat(self.src_card.combo.currentData()), self._cat(self.dst_card.combo.currentData())

    def _merge_problem(self, src, dst) -> str:
        if not src or not dst:
            return "Escolha as duas pastas."
        if src.key == dst.key:
            return "Escolha pastas diferentes."
        if src.key.startswith(dst.key + "/") or dst.key.startswith(src.key + "/"):
            return "Uma pasta está dentro da outra; escolha pastas separadas."
        if dst.children and not dst.assets:
            return f"{pretty(dst.key)} só tem subpastas: escolha uma delas como principal."
        if not [a for a in src.all_assets() if a.kind != "missing"]:
            return f"{pretty(src.key)} não tem itens para mover."
        return ""

    def _update_merge(self, *_):
        src, dst = self._merge_pair()
        self.src_card.show_cat(src)
        self.dst_card.show_cat(dst)
        while self.prev_lay.count():
            it = self.prev_lay.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
            elif it.layout():
                it.layout().deleteLater()
        prob = self._merge_problem(src, dst)
        self.merge_btn.setEnabled(not prob)
        if prob:
            self.merge_info.setText(prob)
            self.prev_lay.addStretch(1)
            return
        changes = self._merge_changes(src, dst)
        plan_names(changes, self.w.categories, self.w.db)
        for ch in changes[:8]:
            g = ui.Glass(12)
            r = QHBoxLayout(g)
            r.setContentsMargins(12, 8, 14, 8)
            r.setSpacing(14)
            r.addWidget(Thumb(ch.asset.preview, 46, 8))
            a = QLabel(ch.asset.name)
            a.setMinimumWidth(240)
            r.addWidget(a)
            r.addWidget(Arrow(40))
            b = QLabel(ch.new_name)
            b.setStyleSheet(f"color:{theme.HILITE.name()};")
            r.addWidget(b, 1)
            self.prev_lay.addWidget(g)
        if len(changes) > 8:
            self.prev_lay.addWidget(_small(f"e mais {len(changes) - 8} itens…", theme.MUTED, 9.5, 0))
        self.prev_lay.addStretch(1)
        sub = f" (com {len(src.children)} subpasta(s))" if src.children else ""
        self.merge_info.setText(f"{len(changes)} itens de {pretty(src.key)}{sub} vão para {pretty(dst.key)}. "
                                + ("A pasta de origem e as subpastas são apagadas se ficarem vazias."))

    @staticmethod
    def _merge_changes(src, dst) -> list[Change]:
        """Todos os itens da pasta que sai, inclusive das subpastas (em ordem: a própria pasta, depois cada subpasta)."""
        return [Change(x, dst, f"vem de {pretty(x.category)}") for x in src.all_assets() if x.kind != "missing"]

    def start_merge(self):
        src, dst = self._merge_pair()
        if self._merge_problem(src, dst):
            return
        changes = self._merge_changes(src, dst)
        sub = (f" e das {len(src.children)} subpasta(s) dela" if src.children else "")
        if self.review(changes, f"{'Absorver' if src.children else 'Juntar'} {pretty(src.key)} em {pretty(dst.key)}",
                       f"Os {len(changes)} itens de {pretty(src.key)}{sub} vão para {pretty(dst.key)} com o nome "
                       "de lá e os próximos números livres. Itens parecidos com algo que já existe vêm marcados "
                       "como \"Pular\". Dá para desfazer tudo de uma vez pelo histórico.",
                       "absorver" if src.children else "juntar", merge_source=src):
            self.refresh()

    # ------------------------------------------------------------------ "Mover para…" da Biblioteca
    def move_assets(self, assets: list[Asset], dest: Category):
        changes = [Change(a, dest, "movido por você") for a in assets if a.kind != "missing"
                   and a.category != dest.key]
        if not changes:
            QMessageBox.information(self.w, "Mover para", "Os itens escolhidos já estão nessa pasta.")
            return
        self.review(changes, f"Mover para {pretty(dest.key)}",
                    f"{len(changes)} item(ns) vão para {pretty(dest.key)} com os próximos números livres de lá.",
                    "mover")


def fill_category_menu(menu: QMenu, cats: list[Category], on_pick) -> None:
    """Menu com as categorias (as que têm subpastas abrem um submenu)."""
    for c in cats:
        if c.children:
            sub = menu.addMenu(pretty(c.key.split("/")[-1]))
            if c.assets:
                sub.addAction(f"{pretty(c.key.split('/')[-1])} (esta pasta)", lambda c=c: on_pick(c))
                sub.addSeparator()
            fill_category_menu(sub, c.children, on_pick)
        else:
            menu.addAction(pretty(c.key.split("/")[-1]), lambda c=c: on_pick(c))
