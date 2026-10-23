"""Telas de Histórico (administrador: todos; demais: as próprias alterações) e de Pessoas."""
from __future__ import annotations

import time
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QMessageBox,
                               QPushButton, QScrollArea, QVBoxLayout, QWidget)

from . import perfil, segundo_plano, theme, ui
from .compartilhado import OP_NAMES

MAX_ROWS = 400


def when(t: float) -> str:
    d = datetime.fromtimestamp(t)
    today = datetime.now().date()
    if d.date() == today:
        return f"hoje, {d:%H:%M}"
    if (today - d.date()).days == 1:
        return f"ontem, {d:%H:%M}"
    return f"{d:%d/%m/%Y %H:%M}"


class _Row(QWidget):
    def __init__(self, dlg: "HistoryDialog", ev: dict, user: dict):
        super().__init__()
        self.dlg, self.ev = dlg, ev
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(12)
        av = QLabel()
        av.setPixmap(perfil.avatar_pixmap(user, 30))
        av.setFixedSize(30, 30)
        lay.addWidget(av, 0, Qt.AlignTop)
        col = QVBoxLayout()
        col.setSpacing(2)
        verb = OP_NAMES.get(ev.get("op"), ev.get("op", ""))
        what = ev.get("desc") or ev.get("item", "")
        t = QLabel(f"<b>{verb}</b> {what}")
        t.setTextFormat(Qt.RichText)
        t.setWordWrap(True)
        if ev.get("undone"):
            t.setText(f"<s>{verb} {what}</s>  <span style='color:{theme.FAINT.name()}'>(desfeito)</span>")
        col.addWidget(t)
        n = len(ev.get("moves", []))
        sub = QLabel(f"{user.get('nome', '?')}  ·  {ev.get('pc', '')}  ·  {when(float(ev.get('t', 0)))}"
                     + (f"  ·  {n} arquivo(s)" if n else ""))
        sub.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:8.8pt;")
        col.addWidget(sub)
        lay.addLayout(col, 1)
        self.btn = None
        if ev.get("k") == "op" and not ev.get("undone"):
            # "dá para desfazer?" confere os arquivos no servidor: é calculado num ajudante, de cima para baixo
            b = QPushButton("Desfazer")
            b.setEnabled(False)
            b.setToolTip("Conferindo se dá para desfazer…")
            b.clicked.connect(self._undo)
            lay.addWidget(b, 0, Qt.AlignVCenter)
            self.btn = b
            dlg._to_check.append(self)

    def set_undo(self, ok: bool, why: str) -> None:
        try:
            self.btn.setEnabled(ok)
            self.btn.setToolTip(why or "Volta os arquivos para onde estavam antes")
        except RuntimeError:        # a linha já foi trocada (lista recarregada)
            pass

    def _undo(self):
        ev = self.ev
        verb = OP_NAMES.get(ev.get("op"), ev.get("op", "")).lower()
        if QMessageBox.question(self, "Desfazer", f"Desfazer: {verb} {ev.get('desc') or ev.get('item', '')}?\n\n"
                                "Os arquivos voltam para onde estavam antes dessa alteração. "
                                "Pastas criadas por ela vão para _DESCARTADOS.") != QMessageBox.Yes:
            return
        ok, why = self.dlg.w.shared.undo(ev)
        if not ok:
            QMessageBox.warning(self, "Desfazer", f"Não foi possível desfazer: {why}.")
            return
        cat = (ev.get("cat") or "").split("/")[0]
        if cat and cat != "_ENTRADA":
            self.dlg.w.refresh_category(cat)
        self.dlg.w.entrada.refresh()
        w = self.dlg.w
        if not (getattr(w, "_verify", None) and w._verify.isRunning()):
            w._start_verify(w.cfg["library_root"])     # pastas que voltaram a existir aparecem
        self.dlg.reload()


class HistoryDialog(QDialog):
    def __init__(self, window, everyone: bool):
        super().__init__(window)
        self.w = window
        self.everyone = everyone
        self.setWindowTitle("Histórico" if everyone else "Minhas alterações")
        self.resize(760, 640)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 22, 24, 18)
        outer.setSpacing(14)
        head = QHBoxLayout()
        t = QLabel(self.windowTitle())
        t.setStyleSheet("font-size:18pt;")
        head.addWidget(t)
        head.addStretch(1)
        self.who = QComboBox()
        self.who.setMinimumWidth(200)
        self.who.currentIndexChanged.connect(self._fill)
        self.who.setVisible(everyone)
        head.addWidget(self.who)
        outer.addLayout(head)
        s = QLabel("Tudo o que mudou arquivos na biblioteca: extrair, organizar, classificar, descartar e limpar. "
                   "\"Desfazer\" volta os arquivos para onde estavam; só funciona enquanto ninguém mexeu neles "
                   "depois (e, para extrações, enquanto o compactado ainda está no backup).")
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{theme.MUTED.name()};")
        outer.addWidget(s)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.NoFrame)
        outer.addWidget(self.area, 1)
        self._to_check: list = []
        self._gen = 0
        self.finished.connect(self._stop_checks)
        bb = QDialogButtonBox()
        bb.addButton("Fechar", QDialogButtonBox.RejectRole)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)
        self.reload()

    def _stop_checks(self, *_):
        self._gen += 1

    def reload(self):
        shared, everyone = self.w.shared, self.everyone
        lib = shared.lib
        self.users, self.events = segundo_plano.wait(
            self.w, "Lendo o histórico…", lambda: (lib.users() if lib else {}, shared.history(everyone)))
        if self.everyone:
            cur = self.who.currentData()
            self.who.blockSignals(True)
            self.who.clear()
            self.who.addItem("Todas as pessoas", None)
            for uid, u in sorted(self.users.items(), key=lambda x: x[1].get("nome", "").lower()):
                self.who.addItem(u.get("nome", "?"), uid)
            i = self.who.findData(cur)
            self.who.setCurrentIndex(i if i >= 0 else 0)
            self.who.blockSignals(False)
        self._fill()

    def _fill(self):
        uid = self.who.currentData() if self.everyone else None
        evs = [e for e in self.events if not uid or e.get("u") == uid][:MAX_ROWS]
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 8, 0)
        lay.setSpacing(8)
        if not evs:
            e = QLabel("Nenhuma alteração registrada ainda.")
            e.setStyleSheet(f"color:{theme.FAINT.name()}; padding:30px;")
            e.setAlignment(Qt.AlignCenter)
            lay.addWidget(e)
        self._gen += 1
        self._to_check = []
        for ev in evs:
            g = ui.Glass(12)
            gl = QVBoxLayout(g)
            gl.setContentsMargins(0, 0, 0, 0)
            gl.addWidget(_Row(self, ev, self.users.get(ev.get("u"), {"nome": "?"})))
            lay.addWidget(g)
        lay.addStretch(1)
        self.area.setWidget(box)
        self._check_rows()

    def _check_rows(self):
        gen, rows, shared = self._gen, list(self._to_check), self.w.shared
        evs = [r.ev for r in rows]

        def apply(res):
            i, ok, why = res
            if self._gen == gen:
                rows[i].set_undo(ok, why)

        def work():
            for i, ev in enumerate(evs):
                if self._gen != gen:          # lista recarregada ou janela fechada
                    return
                try:
                    ok, why = shared.can_undo(ev)
                except Exception:  # noqa: BLE001
                    ok, why = False, "não consegui conferir os arquivos"
                segundo_plano.post(apply, (i, ok, why))
        if evs:
            segundo_plano.run_async(work)


class PeopleDialog(QDialog):
    """Quem usa esta biblioteca; o administrador escolhe outros administradores."""

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self.setWindowTitle("Pessoas")
        self.setMinimumWidth(560)
        lib = window.shared.lib
        outer = QVBoxLayout(self)
        outer.setContentsMargins(24, 22, 24, 18)
        outer.setSpacing(12)
        t = QLabel("Pessoas desta biblioteca")
        t.setStyleSheet("font-size:18pt;")
        outer.addWidget(t)
        s = QLabel("Administradores veem o histórico de todos e podem desfazer qualquer alteração.")
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{theme.MUTED.name()};")
        outer.addWidget(s)
        self.checks = {}
        for uid, u in sorted(lib.users().items(), key=lambda x: x[1].get("nome", "").lower()):
            g = ui.Glass(12)
            row = QHBoxLayout(g)
            row.setContentsMargins(14, 10, 14, 10)
            row.setSpacing(12)
            av = QLabel()
            av.setPixmap(perfil.avatar_pixmap(u, 34))
            av.setFixedSize(34, 34)
            row.addWidget(av)
            col = QVBoxLayout()
            col.setSpacing(1)
            col.addWidget(QLabel(u.get("nome", "?") + ("  (você)" if uid == lib.uid else "")))
            seen = u.get("visto_em")
            sub = QLabel(f"{u.get('pc', '')}" + (f"  ·  visto {time.strftime('%d/%m %H:%M', time.localtime(seen))}"
                                                 if seen else ""))
            sub.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:8.8pt;")
            col.addWidget(sub)
            row.addLayout(col, 1)
            c = QCheckBox("administrador")
            c.setChecked(lib.is_admin(uid))
            c.toggled.connect(lambda on, uid=uid: self._toggle(uid, on))
            row.addWidget(c)
            self.checks[uid] = c
            outer.addWidget(g)
        bb = QDialogButtonBox()
        bb.addButton("Fechar", QDialogButtonBox.RejectRole)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)

    def _toggle(self, uid, on):
        lib = self.w.shared.lib
        lib.set_admin(uid, on)
        lib.reload_info()
        for u, c in self.checks.items():
            c.blockSignals(True)
            c.setChecked(lib.is_admin(u))
            c.blockSignals(False)
        if not lib.is_admin():
            QMessageBox.information(self, "Pessoas", "Você deixou de ser administrador.")
            self.accept()
