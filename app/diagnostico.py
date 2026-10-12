"""Configurações › Biblioteca › Testar biblioteca: confere acesso, gravação, relógio e velocidade da pasta."""
from __future__ import annotations

import os
import statistics
import time
import uuid

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget)

from . import rede, theme, ui

OK, WARN, BAD = "ok", "aviso", "erro"


def _ms(t: float) -> str:
    return f"{t * 1000:.0f} ms" if t < 1 else f"{t:.1f} s"


def run_checks(root: str, lib) -> list[tuple[str, str, str]]:
    """Lista de (situação, título, explicação)."""
    out = []
    # 1. acesso
    t0 = time.time()
    try:
        entries = list(os.scandir(root))
        dt = time.time() - t0
        cats = [e for e in entries if e.is_dir() and not e.name.startswith(("_", ".", "$"))]
        out.append((OK if dt < 1.5 else WARN, "Acesso à pasta",
                    f"{len(cats)} categorias encontradas em {_ms(dt)}."
                    + ("" if dt < 1.5 else " A pasta demorou para responder: a rede pode estar lenta.")))
    except OSError as e:
        return [(BAD, "Acesso à pasta", f"Não foi possível abrir {root} ({e}). Confira se o servidor está "
                                         "ligado e se este computador tem acesso à pasta.")]
    # 2. gravação
    shared = os.path.join(root, rede.DIR)
    probe = os.path.join(shared if os.path.isdir(shared) else root, f"teste_{uuid.uuid4().hex[:6]}.tmp")
    try:
        with open(probe, "w") as f:
            f.write("teste")
        os.remove(probe)
        out.append((OK, "Gravação", "Este computador consegue gravar na biblioteca (tags, travas e histórico "
                                    "funcionam)."))
    except OSError as e:
        out.append((BAD, "Gravação", f"Sem permissão para gravar ({e}). Peça para liberar \"modificar\" nesta "
                                     "pasta do servidor para este usuário; sem isso as tags ficam só aqui e "
                                     "as travas não funcionam."))
    # 3. relógio
    if lib is not None:
        skew = lib.measure_skew()
        lib.skew = skew
        if abs(skew) < 30:
            out.append((OK, "Relógio", "O relógio deste computador está certo em relação ao servidor."))
        else:
            mins = abs(skew) / 60
            lado = "atrasado" if skew > 0 else "adiantado"
            out.append((WARN, "Relógio", f"Este computador está {lado} {mins:.0f} min em relação ao servidor. "
                                         "O Archiva compensa sozinho, mas é bom acertar: Configurações do "
                                         "Windows › Hora e idioma › Sincronizar agora."))
    # 4. velocidade
    sample = [e.path for e in entries[:40]]
    times = []
    for p in sample:
        t = time.time()
        try:
            os.stat(p)
        except OSError:
            pass
        times.append(time.time() - t)
    if times:
        med = statistics.median(times)
        state = OK if med < 0.015 else (WARN if med < 0.08 else BAD)
        txt = {OK: "Rede rápida.", WARN: "Rede um pouco lenta; o Archiva continua usável.",
               BAD: "Rede lenta: abrir e atualizar a biblioteca pode demorar."}[state]
        out.append((state, "Velocidade", f"Cada consulta à pasta leva cerca de {_ms(med)}. {txt}"))
    # 5. categoria maior
    try:
        big = max(cats, key=lambda e: len(os.listdir(e.path))) if cats else None
        if big:
            t = time.time()
            n = len(list(os.scandir(big.path)))
            dt = time.time() - t
            out.append((OK if dt < 2 else WARN, "Leitura de categoria",
                        f"{big.name}: {n} arquivos e pastas listados em {_ms(dt)}."))
    except (OSError, ValueError):
        pass
    # 6. equipe
    if lib is not None:
        users = lib.users()
        admins = [u.get("nome", "?") for u in users.values() if u.get("admin")]
        locks = lib.locks()
        size = sum(os.path.getsize(p) for p in lib.event_files() if os.path.exists(p))
        out.append((OK, "Equipe", f"{len(users)} pessoa(s) usam esta biblioteca; administrador: "
                                  f"{', '.join(admins) or '—'}. {len(locks)} item(ns) em uso agora. "
                                  f"Registros: {size / 1024:.0f} KB."))
    return out


class _Dot(QWidget):
    def __init__(self, state):
        super().__init__()
        self.state = state
        self.setFixedSize(14, 14)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush({OK: theme.OK, WARN: theme.WARN, BAD: theme.BAD}.get(self.state, theme.FAINT))
        p.drawEllipse(QRectF(2, 2, 10, 10))


class TestDialog(QDialog):
    def __init__(self, parent, root: str, lib):
        super().__init__(parent)
        self.root, self.lib = root, lib
        self.setWindowTitle("Testar biblioteca")
        self.setFixedWidth(660)
        self.outer = QVBoxLayout(self)
        self.outer.setContentsMargins(28, 24, 28, 20)
        self.outer.setSpacing(14)
        t = QLabel("Testar biblioteca")
        t.setStyleSheet("font-size:18pt;")
        self.outer.addWidget(t)
        s = QLabel(root if len(root) < 80 else "…" + root[-78:])
        s.setStyleSheet(f"color:{theme.MUTED.name()};")
        s.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.outer.addWidget(s)
        self.box = QVBoxLayout()
        self.box.setSpacing(10)
        self.outer.addLayout(self.box)
        bb = QDialogButtonBox()
        again = bb.addButton("Testar de novo", QDialogButtonBox.ActionRole)
        again.clicked.connect(self.run)
        ui.primary(bb.addButton("Fechar", QDialogButtonBox.AcceptRole))
        bb.accepted.connect(self.accept)
        self.outer.addWidget(bb)
        self.run()

    def run(self):
        while self.box.count():
            it = self.box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            res = run_checks(self.root, self.lib)
        finally:
            QApplication.restoreOverrideCursor()
        for state, title, text in res:
            g = ui.Glass(12)
            row = QHBoxLayout(g)
            row.setContentsMargins(16, 12, 16, 12)
            row.setSpacing(12)
            row.addWidget(_Dot(state), 0, Qt.AlignTop)
            col = QVBoxLayout()
            col.setSpacing(3)
            h = QLabel(title)
            col.addWidget(h)
            d = QLabel(text)
            d.setWordWrap(True)
            d.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:9.6pt;")
            d.ensurePolished()
            d.setMinimumHeight(d.heightForWidth(660 - 56 - 32 - 26) + 2)
            col.addWidget(d)
            row.addLayout(col, 1)
            self.box.addWidget(g)
        self.adjustSize()
