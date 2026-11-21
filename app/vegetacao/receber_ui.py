"""Janela "Receber coleções" (2.0.20): lista o que está na pasta de entrada, sugere coleção e nome da pasta do
volume, e move o que a pessoa marcar. A lógica (listar, conferir, mover) fica em receber.py."""
from __future__ import annotations

import os

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from .. import segundo_plano, theme, ui
from ..config import data_dir
from . import receber
from .conferencia import STYLE, _Dot, _muted, _panel, human_size, plural


def pasta_entrada(page, perguntar: bool = True) -> str | None:
    """A pasta de entrada desta pessoa: a escolhida antes, senão _ENTRADAS ao lado das coleções, senão pergunta."""
    cfg = str(data_dir())
    p = receber.load_pasta(cfg)
    if p and os.path.isdir(p):
        return p
    p = receber.sugerir_pasta(page.paths)
    if not p and perguntar:
        start = os.path.dirname(page.paths[0]) if page.paths else ""
        p = QFileDialog.getExistingDirectory(page, "Pasta onde você baixa as coleções novas", start) or None
    if p:
        p = os.path.normpath(p)
        receber.save_pasta(cfg, p)
    return p


class _Linha(ui.Glass):
    """Um pacote: o que é, para qual coleção vai, com que nome de pasta, e se vai agora."""

    def __init__(self, pacote: receber.Pacote, cols, on_change):
        super().__init__(14)
        self.pacote, self.cols, self.on_change = pacote, cols, on_change
        lay = QHBoxLayout(self)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(14)
        self.chk = QCheckBox()
        lay.addWidget(self.chk, 0, Qt.AlignTop)
        info = QVBoxLayout()
        info.setSpacing(3)
        t = QLabel(pacote.nome)
        t.setFont(theme.ui_font(11.5))
        t.setWordWrap(True)
        info.addWidget(t)
        what = "pasta já extraída" if pacote.pasta else plural(len(pacote.itens), "arquivo", "arquivos")
        names = ", ".join(os.path.basename(i) for i in pacote.itens[:4]) + (" …" if len(pacote.itens) > 4 else "")
        info.addWidget(_muted(f"{what} · {human_size(pacote.tamanho)} · {names}", 9))
        self.state = QLabel()
        self.state.setWordWrap(True)
        info.addWidget(self.state)
        lay.addLayout(info, 1)
        dest = QVBoxLayout()
        dest.setSpacing(6)
        self.combo = QComboBox()
        self.combo.addItem("Escolha a coleção…", None)
        for c in cols:
            self.combo.addItem(c.nome, c.path)
        sug = receber.colecao_do_tipo(cols, pacote.tipo)
        if sug is not None:
            self.combo.setCurrentIndex(self.combo.findData(sug.path))
        self.combo.setMinimumWidth(190)
        dest.addWidget(self.combo)
        self.name = QLineEdit(pacote.sugestao)
        self.name.setToolTip("Nome da pasta do volume dentro da coleção")
        self.name.setMinimumWidth(300)
        dest.addWidget(self.name)
        lay.addLayout(dest)
        self.combo.currentIndexChanged.connect(lambda *_: self.update_state())
        self.name.textChanged.connect(lambda *_: self.update_state())
        self.chk.toggled.connect(lambda *_: self.on_change())
        self.update_state(first=True)

    def col_path(self) -> str | None:
        return self.combo.currentData()

    def problema(self) -> str:
        if not self.col_path():
            return "escolha a coleção"
        return receber.conferir(self.pacote, self.col_path(), self.name.text())

    def update_state(self, first: bool = False):
        prob = self.problema()
        avisos = [a for a in self.pacote.avisos if a != "ainda baixando"]
        if prob:
            color, text = (theme.BUSY if self.pacote.baixando else theme.BAD), prob
        elif avisos:
            color, text = theme.WARN, " · ".join(avisos)
        else:
            dest = os.path.join(os.path.basename(self.col_path()), self.name.text().strip())
            existe = os.path.isdir(os.path.join(self.col_path(), self.name.text().strip()))
            color, text = theme.OK, (f"entra na pasta que já existe: {dest}" if existe else f"vai para {dest}")
        self.state.setText(text)
        self.state.setStyleSheet(f"color:{color.name()}; font-size:9.5pt;")
        self.chk.setEnabled(not prob)
        if prob:
            self.chk.setChecked(False)
        elif first:
            # marcado de saída só quando não há dúvida (coleção e número reconhecidos, nada faltando)
            self.chk.setChecked(not avisos)
        self.on_change()


class ReceberDialog(QDialog):
    def __init__(self, page, pasta: str):
        super().__init__(page)
        self.page, self.pasta = page, pasta
        self.setWindowTitle("Receber coleções")
        self.setStyleSheet(STYLE)
        self.resize(1080, 720)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 26, 30, 22)
        outer.setSpacing(12)
        t = QLabel("Receber coleções")
        t.setFont(theme.ui_font(21))
        outer.addWidget(t)
        self.sub = _muted("", 10.5)
        outer.addWidget(self.sub)
        outer.addWidget(_panel(_muted(
            "O que você baixou vai para a pasta da coleção ainda compactado. Depois, na coleção, abra o volume e use "
            "\"Extrair volume…\" e \"Organizar volume…\". Arquivos do mesmo volume (partes do rar, PDF) vão juntos. "
            "Nada é apagado: no mesmo disco os arquivos só mudam de pasta.", 10), margins=(16, 12, 16, 12)))
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
        outer.addWidget(self.scroll, 1)
        foot = QHBoxLayout()
        self.where = _muted("", 9.5)
        foot.addWidget(self.where, 1)
        for text, fn in (("Trocar pasta…", self._trocar), ("Abrir pasta", self._abrir), ("Atualizar", self.fill)):
            b = QPushButton(text)
            b.setCursor(Qt.PointingHandCursor)
            b.clicked.connect(fn)
            foot.addWidget(b)
        foot.addSpacing(16)
        cancel = QPushButton("Fechar")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        foot.addWidget(cancel)
        self.go = ui.primary(QPushButton("Mover"))
        self.go.clicked.connect(self.accept)
        foot.addWidget(self.go)
        outer.addLayout(foot)
        self.linhas: list[_Linha] = []
        self.fill()

    def fill(self):
        self.where.setText(f"Pasta de entrada: {self.pasta}")
        pacotes = receber.listar(self.pasta)
        box = QWidget()
        lay = QVBoxLayout(box)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(9)
        self.linhas = []
        for p in pacotes:
            ln = _Linha(p, self.page.cols, self._count)
            self.linhas.append(ln)
            lay.addWidget(ln)
        if not pacotes:
            lay.addWidget(_panel(_muted("Nada para receber. Baixe os volumes (zip, rar em partes, PDF) nesta pasta e "
                                        "clique em Atualizar.", 10.5), margins=(18, 16, 18, 16)))
        lay.addStretch(1)
        self.scroll.setWidget(box)
        self.sub.setText(plural(len(pacotes), "volume encontrado", "volumes encontrados") + " na pasta de entrada")
        self._count()

    def _count(self):
        if not hasattr(self, "go"):
            return
        n = len(self.escolhidos())
        self.go.setText(f"Mover {plural(n, 'volume', 'volumes')}" if n else "Mover")
        self.go.setEnabled(bool(n))

    def escolhidos(self) -> list[tuple[receber.Pacote, str, str]]:
        return [(ln.pacote, ln.col_path(), ln.name.text().strip()) for ln in getattr(self, "linhas", [])
                if ln.chk.isChecked() and not ln.problema()]

    def _trocar(self):
        p = QFileDialog.getExistingDirectory(self, "Pasta onde você baixa as coleções novas", self.pasta)
        if p:
            self.pasta = os.path.normpath(p)
            receber.save_pasta(str(data_dir()), self.pasta)
            self.fill()

    def _abrir(self):
        QDesktopServices.openUrl(QUrl.fromLocalFile(self.pasta))


def abrir(page) -> None:
    """Botão "Receber coleções…" da aba Vegetação."""
    if not page.cols:
        QMessageBox.information(page, "Receber coleções", "Adicione antes as pastas das coleções (Maxtree, Globe "
                                "Plants) com \"Adicionar coleção\".")
        return
    pasta = pasta_entrada(page)
    if not pasta:
        return
    dlg = ReceberDialog(page, pasta)
    if dlg.exec() != QDialog.Accepted:
        return
    escolhidos = dlg.escolhidos()
    if not escolhidos:
        return

    def work(report):
        feitos, erros = [], []
        for k, (p, col, nome) in enumerate(escolhidos):
            report(k, len(escolhidos), f"Movendo {nome}…")
            try:
                feitos.append(receber.mover(p, col, nome))
            except Exception as e:  # noqa: BLE001 — um volume com problema não impede os outros
                erros.append(f"{nome}: {e}")
        return feitos, erros

    feitos, erros = segundo_plano.wait(page, "Movendo para as coleções…", work)
    msg = ""
    if feitos:
        msg += (f"{plural(len(feitos), 'volume recebido', 'volumes recebidos')}:\n"
                + "\n".join(f"  • {os.path.basename(d)}" for d in feitos)
                + "\n\nAbra cada um na coleção e use \"Extrair volume…\" e depois \"Organizar volume…\".")
    if erros:
        msg += ("\n\n" if msg else "") + "Não movidos (continuam na pasta de entrada):\n" + \
               "\n".join(f"  • {e}" for e in erros)
    (QMessageBox.warning if erros else QMessageBox.information)(page, "Receber coleções", msg)
    page.rescan()
