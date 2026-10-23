"""Possíveis repetidos (Organização, só administrador).

Compara as prévias da biblioteca INTEIRA (um repetido pode estar na pasta errada) e mostra cada par lado a
lado: Manter A (B vai para _DESCARTADOS), Manter os dois (o par nunca mais aparece, para a equipe toda) ou
Manter B. Tags e coleções do item que sai passam para o que fica; o que sai fica guardado em
#excluido/<chave> e volta no Desfazer, como em "Excluir item".

Velocidade: as assinaturas (dHash 256 bits + miniatura de cor) ficam no cache local (intake.HashCache).
Primeiro um filtro rápido só pela forma (contagem de bits diferentes), depois a comparação completa
(intake.compare) apenas nos candidatos.
"""
from __future__ import annotations

import os

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QImageReader
from PySide6.QtWidgets import QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from . import intake, theme, ui
from .scanner import Asset

THRESHOLD = 0.97                                  # mais rígido que a Entrada (0.88): aqui é a biblioteca inteira
MAX_BITS = int((1.0 - THRESHOLD) * 256)           # forma: no máximo isso de bits diferentes
PAIR_FLAG = "nao_repetido"


def pair_key(k1: str, k2: str) -> str:
    a, b = sorted((k1, k2))
    return f"#par/{a}|{b}"


def _bits(x: int) -> int:
    try:
        return x.bit_count()
    except AttributeError:       # Python antigo
        return bin(x).count("1")


def find_pairs(assets: list[Asset], cache_path: str, is_ignored, progress=None, stop=None) -> list[tuple]:
    """[(asset_a, asset_b, semelhança)] ordenados do mais parecido para o menos."""
    with_prev = [a for a in assets if a.preview and not a.key.startswith("#")]
    cache = intake.HashCache(cache_path)
    sigs: dict[str, tuple[int, bytes]] = {}
    chunk = 200
    for i in range(0, len(with_prev), chunk):
        if stop and stop():
            return []
        part = with_prev[i:i + chunk]
        sigs.update(cache.get_many([a.preview for a in part], intake.known_of(part)))
        if progress:
            progress(f"Lendo as prévias… {min(i + chunk, len(with_prev))}/{len(with_prev)}")
    items = [(a, sigs[a.preview]) for a in with_prev if a.preview in sigs]
    if progress:
        progress(f"Comparando {len(items)} prévias…")
    out = []
    for i in range(len(items)):
        if stop and stop() and i % 200 == 0:
            return []
        a, sa = items[i]
        ha = sa[0]
        for j in range(i + 1, len(items)):
            b, sb = items[j]
            if _bits(ha ^ sb[0]) > MAX_BITS:
                continue
            if a.key == b.key or os.path.normcase(a.preview) == os.path.normcase(b.preview):
                continue
            s = intake.compare(sa, sb)
            if s >= THRESHOLD and not is_ignored(pair_key(a.key, b.key)):
                out.append((a, b, s))
    out.sort(key=lambda t: -t[2])
    return out


def item_info(a: Asset) -> dict:
    """Tipo, tamanho, número de arquivos e resolução da prévia (lidos no disco)."""
    size = files = 0
    for m in a.members or []:
        try:
            if os.path.isdir(m):
                for dp, _dn, fs in os.walk(m):
                    for f in fs:
                        files += 1
                        try:
                            size += os.path.getsize(os.path.join(dp, f))
                        except OSError:
                            pass
            elif os.path.isfile(m) and m != a.preview:
                files += 1
                size += os.path.getsize(m)
        except OSError:
            pass
    kind = {"folder": "pasta", "archive": "compactado", "max": ".max solto", "missing": "sem modelo"}.get(a.kind, a.kind)
    if a.kind == "archive" and a.archive:
        kind = f"compactado ({os.path.splitext(a.archive)[1].lower()})"
    res = QImageReader(a.preview).size() if a.preview else None
    return {"kind": kind, "size": size, "files": files,
            "res": f"{res.width()} × {res.height()} px" if res is not None and res.isValid() else "sem prévia"}


class PairThread(QThread):
    progress = Signal(str)
    done = Signal(list)              # [(a, b, sim, info_a, info_b)]

    def __init__(self, assets: list[Asset], cache_path: str, ignored: set[str]):
        super().__init__()
        self.assets, self.cache_path, self.ignored = assets, cache_path, ignored
        self.stop = False

    def run(self):
        try:
            pairs = find_pairs(self.assets, self.cache_path, lambda k: k in self.ignored,
                               self.progress.emit, lambda: self.stop)
            out = []
            for n, (a, b, s) in enumerate(pairs, 1):
                if self.stop:
                    return
                self.progress.emit(f"Conferindo os pares… {n}/{len(pairs)}")
                out.append((a, b, s, item_info(a), item_info(b)))
            self.done.emit(out)
        except Exception as e:  # noqa: BLE001
            self.progress.emit(f"Não deu para procurar repetidos: {e}")
            self.done.emit([])


def _mb(n: int) -> str:
    return f"{n / 1024 ** 3:.2f} GB" if n >= 1024 ** 3 else f"{n / 1024 ** 2:.1f} MB"


class PairCard(ui.Glass):
    def __init__(self, panel, a: Asset, b: Asset, sim: float, ia: dict, ib: dict):
        super().__init__(14)
        from .organizar import Thumb, pretty
        self.panel, self.a, self.b = panel, a, b
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(16)

        def side(x: Asset, info: dict, letter: str):
            col = QHBoxLayout()
            col.setSpacing(12)
            col.addWidget(Thumb(x.preview, 132, 12))
            txt = QVBoxLayout()
            txt.setSpacing(3)
            t = QLabel(letter)
            t.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:8.5pt; letter-spacing:1px;")
            txt.addWidget(t)
            nm = QLabel(x.name)
            nm.setStyleSheet("font-size:12pt;")
            txt.addWidget(nm)
            for line in (pretty(x.category), f"{info['kind']} · {info['files']} arquivo(s) · {_mb(info['size'])}",
                         f"prévia {info['res']}"):
                l = QLabel(line)
                l.setWordWrap(True)
                l.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:9pt;")
                txt.addWidget(l)
            txt.addStretch(1)
            col.addLayout(txt, 1)
            return col

        lay.addLayout(side(a, ia, "A"), 1)
        mid = QVBoxLayout()
        mid.addStretch(1)
        pct = QLabel(f"{sim * 100:.0f}%\nparecidas")
        pct.setAlignment(Qt.AlignCenter)
        pct.setStyleSheet(f"color:{theme.HILITE.name()}; font-size:9pt;")
        mid.addWidget(pct)
        mid.addStretch(1)
        lay.addLayout(mid)
        lay.addLayout(side(b, ib, "B"), 1)
        btns = QVBoxLayout()
        btns.setSpacing(6)
        for label, fn in (("Manter A", lambda: panel.keep(self, a, b)),
                          ("Manter os dois", lambda: panel.keep_both(self, a, b)),
                          ("Manter B", lambda: panel.keep(self, b, a))):
            bt = QPushButton(label)
            bt.setMinimumWidth(130)
            bt.clicked.connect(fn)
            btns.addWidget(bt)
        btns.addStretch(1)
        lay.addLayout(btns)


class RepetidosPanel(QWidget):
    count_changed = Signal(int)

    def __init__(self, page):
        super().__init__()
        from .organizar import _scroll_box
        self.page, self.w = page, page.w
        self.th: PairThread | None = None
        self.n = 0
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        r = QHBoxLayout()
        self.btn = ui.primary(QPushButton("Procurar de novo"))
        self.btn.clicked.connect(self.scan)
        r.addWidget(self.btn)
        self.info = QLabel("Compara as prévias da biblioteca inteira. Escolha o que fica em cada par; o que sai vai "
                           "para _DESCARTADOS (apagado depois do prazo do backup) e dá para desfazer pelo histórico.")
        self.info.setWordWrap(True)
        self.info.setStyleSheet(f"color:{theme.MUTED.name()};")
        r.addWidget(self.info, 1)
        lay.addLayout(r)
        self.area, self.cards = _scroll_box()
        lay.addWidget(self.area, 1)

    def scan(self):
        if self.th is not None and self.th.isRunning():
            return
        db = self.w.db
        ignored = {k for k, f in getattr(db, "_flags", set()) if f == PAIR_FLAG}
        self.th = PairThread(list(self.w.all_assets), str(self.w.cache_root / "assinaturas.db"), ignored)
        self.th.progress.connect(self.info.setText)
        self.th.done.connect(self._show)
        self.btn.setEnabled(False)
        self.th.start()

    def stop(self):
        if self.th is not None:
            self.th.stop = True
            self.th.wait(5000)

    def _clear(self):
        while self.cards.count():
            it = self.cards.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _show(self, pairs: list):
        self.btn.setEnabled(True)
        self._clear()
        alive = {x.key for x in self.w.all_assets}
        pairs = [p for p in pairs if p[0].key in alive and p[1].key in alive]
        for p in pairs:
            self.cards.addWidget(PairCard(self, *p))
        self.cards.addStretch(1)
        self.n = len(pairs)
        self.count_changed.emit(self.n)
        self.info.setText(f"{self.n} par(es) de possíveis repetidos. Escolha o que fica em cada um; o que sai vai "
                          "para _DESCARTADOS e dá para desfazer pelo histórico." if self.n else
                          "Nenhum possível repetido na biblioteca.")

    def _done_card(self, card):
        card.setParent(None)
        card.deleteLater()
        self.n = max(0, self.n - 1)
        self.count_changed.emit(self.n)
        if not self.n:
            self.info.setText("Nenhum possível repetido pendente.")

    def keep_both(self, card, a: Asset, b: Asset):
        self.w.db.set_flag(pair_key(a.key, b.key), PAIR_FLAG)
        self._done_card(card)

    def keep(self, card, keep: Asset, drop: Asset):
        if QMessageBox.question(
                self, "Possíveis repetidos",
                f"Manter {keep.name} e tirar {drop.name} da biblioteca?\n\n"
                f"{drop.name} vai para _DESCARTADOS (apagado depois do prazo do backup). As tags e coleções dele "
                f"passam para {keep.name}. Dá para desfazer pelo histórico.") != QMessageBox.Yes:
            return
        root = self.w.cfg["library_root"]
        locked, busy = self.w.try_lock([keep.key, drop.key], "resolvendo repetido")
        try:
            if len(locked) < 2:
                QMessageBox.information(self, "Em uso", "\n".join(busy))
                return
            rec = []
            try:
                intake.discard(drop, root, rec)
            except OSError as e:
                import shutil
                for src, dst in reversed(rec):
                    try:
                        shutil.move(dst, src)
                    except OSError:
                        pass
                QMessageBox.warning(self, "Possíveis repetidos", f"Não deu para tirar {drop.name}: {e}\n\n"
                                    "Nada foi alterado.")
                return
            db = self.w.db
            tags = sorted(db.tags_of(drop.key))
            if tags:
                db.add_tags([keep.key], tags)
            for cid in db.collections_of(drop.key):
                if keep.key not in db.collection_items(cid):
                    db.add_to_collection(cid, [keep.key], getattr(self.w.shared.lib, "uid", "") or "")
            tomb = "#excluido/" + drop.key
            db.move_item_data(drop.key, tomb)
            self.w.log_op("repetido", drop.category, drop.key, f"{drop.name} (ficou {keep.name})", rec,
                          extra={"keys": [[drop.key, tomb]]})
        finally:
            for k in locked:
                self.w.shared.release(k)
        self.w.refresh_category(drop.category.split("/")[0], [drop.key])
        self._done_card(card)
        # outros pares com o item que saiu deixam de valer
        for i in reversed(range(self.cards.count())):
            wdg = self.cards.itemAt(i).widget()
            if isinstance(wdg, PairCard) and drop.key in (wdg.a.key, wdg.b.key):
                self._done_card(wdg)
