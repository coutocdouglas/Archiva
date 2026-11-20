"""Tela de conferência do "Organizar volume" (simulação): mostra para onde vai cada arquivo antes de mexer em nada.

Outros: cada item aparece desmarcado (= manter em "- Outros"); o que a pessoa marcar vai para _DESCARTADOS.
Nada é apagado: tudo pode ser desfeito depois com "Desfazer organização".
"""
from __future__ import annotations

import collections
import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QHeaderView, QLabel, QPushButton, QTabWidget, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import theme, ui
from . import organizar

GROUP_TEXT = {
    organizar.MESH: ("Mesh", "os .max, cada um com a prévia ao lado e a biblioteca Forest Pack"),
    organizar.PROXY: ("Proxy", "proxies que já existiam"),
    organizar.MAPS: ("Maps", "texturas"),
    organizar.PDF: ("PDF", "PDF do volume e capas das espécies"),
    organizar.CAPA: ("Capa do volume", "criada a partir da 1ª página do PDF"),
    organizar.OUTROS: ("Outros", "o que não tem lugar no padrão: você decide"),
    organizar.DESC: ("_DESCARTADOS", "sai da coleção, mas pode ser desfeito"),
}


def human_size(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB".replace(".", ",")
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.0f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def _muted(text: str, size: float = 9.5) -> QLabel:
    lab = QLabel(text)
    lab.setWordWrap(True)
    lab.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:{size}pt;")
    return lab


def _tree(headers: list[str]) -> QTreeWidget:
    t = QTreeWidget()
    t.setHeaderLabels(headers)
    t.setRootIsDecorated(True)
    t.setUniformRowHeights(True)
    t.setAlternatingRowColors(False)
    t.header().setStretchLastSection(False)
    t.header().setSectionResizeMode(0, QHeaderView.Stretch)
    for i in range(1, len(headers)):
        t.header().setSectionResizeMode(i, QHeaderView.ResizeToContents)
    return t


class OrganizarDialog(QDialog):
    def __init__(self, parent, vol_label: str, plano: organizar.Plano):
        super().__init__(parent)
        self.plano = plano
        self.setWindowTitle(f"Organizar · {vol_label}")
        self.resize(1040, 720)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(10)
        t = QLabel(f"Organizar {vol_label}")
        t.setStyleSheet("font-size:18pt;")
        outer.addWidget(t)
        groups = plano.por_grupo()
        if plano.status != "ok":
            outer.addWidget(_muted(plano.motivo, 10.5))
            if plano.conflitos:
                tr = _tree(["Conflito"])
                for c in plano.conflitos[:500]:
                    QTreeWidgetItem(tr, [c])
                outer.addWidget(tr, 1)
            else:
                outer.addStretch(1)
            row = QHBoxLayout()
            row.addStretch(1)
            b = QPushButton("Fechar")
            b.clicked.connect(self.reject)
            row.addWidget(b)
            outer.addLayout(row)
            return
        outer.addWidget(_muted(
            f"Isto é uma simulação: nada foi mexido ainda. Ao clicar em \"Organizar\", os arquivos vão para as pastas "
            f"\"{plano.prefixo} - Mesh / Maps / PDF / Outros\". Nada é apagado: o que sai vai para a pasta "
            f"_DESCARTADOS dentro do volume, e \"Desfazer organização\" volta tudo como estava.", 10))

        tabs = QTabWidget()
        outer.addWidget(tabs, 1)
        tabs.addTab(self._summary(groups), "Resumo")
        self.outros_tree = self._outros(groups[organizar.OUTROS])
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.addWidget(_muted("Tudo aqui fica na pasta Outros (desmarcado = manter). Marque o que quer mandar para "
                             "_DESCARTADOS. Marcar uma pasta marca tudo dentro dela."))
        lay.addWidget(self.outros_tree, 1)
        tabs.addTab(w, f"Outros (você decide) · {len(groups[organizar.OUTROS])}")
        tabs.addTab(self._descartes(groups[organizar.DESC]), f"Vão para _DESCARTADOS · {len(groups[organizar.DESC])}")
        tabs.addTab(self._all(groups), "Todos os movimentos")

        row = QHBoxLayout()
        self.count = _muted("")
        row.addWidget(self.count, 1)
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        row.addWidget(cancel)
        go = ui.primary(QPushButton("Organizar"))
        go.clicked.connect(self.accept)
        row.addWidget(go)
        outer.addLayout(row)
        self.outros_tree.itemChanged.connect(lambda *_: self._update_count())
        self._update_count()

    # ------------------------------------------------------------------ abas
    def _summary(self, groups) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 12, 0, 0)
        lay.setSpacing(8)
        for g, passos in groups.items():
            if not passos:
                continue
            name, desc = GROUP_TEXT[g]
            size = sum(p.tamanho for p in passos)
            copies = sum(1 for p in passos if p.acao == "copiar")
            extra = f" ({copies} prévias copiadas com o nome do .max)" if copies else ""
            box = ui.Glass(12)
            bl = QHBoxLayout(box)
            bl.setContentsMargins(16, 10, 16, 10)
            a = QLabel(name)
            a.setStyleSheet("font-size:11.5pt;")
            a.setMinimumWidth(150)
            bl.addWidget(a)
            bl.addWidget(_muted(desc + extra), 1)
            n = QLabel(f"{len(passos)} {'item' if len(passos) == 1 else 'itens'} · {human_size(size)}")
            n.setStyleSheet(f"color:{theme.TEXT.name()};")
            bl.addWidget(n)
            lay.addWidget(box)
        lay.addStretch(1)
        return w

    def _outros(self, passos) -> QTreeWidget:
        tr = _tree(["Arquivo", "Motivo", "Tamanho"])
        base = os.path.join(self.plano.volume, f"{self.plano.prefixo} - Outros")
        folders: dict[str, QTreeWidgetItem] = {}
        by_folder = collections.defaultdict(list)
        for p in passos:
            rel = os.path.relpath(p.destino, base)
            by_folder[os.path.dirname(rel) or "(raiz do volume)"].append((os.path.basename(rel), p))
        for folder in sorted(by_folder, key=str.casefold):
            items = by_folder[folder]
            top = QTreeWidgetItem(tr, [f"{folder}  ({len(items)})", "", human_size(sum(p.tamanho for _, p in items))])
            top.setFlags(top.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            top.setCheckState(0, Qt.Unchecked)
            folders[folder] = top
            for name, p in sorted(items, key=lambda x: x[0].casefold()):
                it = QTreeWidgetItem(top, [name, p.motivo, human_size(p.tamanho)])
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Unchecked)
                it.setData(0, Qt.UserRole, p.origem)
        return tr

    def _descartes(self, passos) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 10, 0, 0)
        lay.addWidget(_muted("Saem da coleção pelas regras combinadas (versão repetida, cena num volume que já tem as "
                             "malhas, V-Ray quando existe Corona, compactado já extraído, Thumbs.db). Ficam guardados "
                             "em _DESCARTADOS dentro do volume."))
        tr = _tree(["Item", "Motivo", "Tamanho"])
        by_why = collections.defaultdict(list)
        for p in passos:
            by_why[p.motivo].append(p)
        for why, ps in sorted(by_why.items()):
            top = QTreeWidgetItem(tr, [f"{why}  ({len(ps)})", "", human_size(sum(p.tamanho for p in ps))])
            for p in ps:
                rel = os.path.relpath(p.origem, self.plano.volume)
                QTreeWidgetItem(top, [rel + (os.sep if os.path.isdir(p.origem) else ""), why, human_size(p.tamanho)])
            top.setExpanded(len(by_why) <= 4)
        lay.addWidget(tr, 1)
        return w

    def _all(self, groups) -> QWidget:
        tr = _tree(["Origem › destino", "Ação", "Tamanho"])
        verbs = {"mover": "mover", "copiar": "copiar", "escrever": "criar", "descartar": "descartar"}
        for g, passos in groups.items():
            if not passos:
                continue
            top = QTreeWidgetItem(tr, [f"{GROUP_TEXT[g][0]}  ({len(passos)})", "", ""])
            for p in passos[:3000]:
                src = os.path.relpath(p.origem, self.plano.volume) if p.origem else "PDF"
                dst = os.path.relpath(p.destino, os.path.dirname(self.plano.volume))
                QTreeWidgetItem(top, [f"{src}  ›  {dst}", verbs.get(p.acao, p.acao), human_size(p.tamanho)])
        return tr

    # ------------------------------------------------------------------ resultado
    def marked(self) -> set[str]:
        out = set()
        tr = self.outros_tree
        for i in range(tr.topLevelItemCount()):
            top = tr.topLevelItem(i)
            for j in range(top.childCount()):
                it = top.child(j)
                if it.checkState(0) == Qt.Checked:
                    out.add(it.data(0, Qt.UserRole))
        return out

    def _update_count(self):
        n = len(self.marked())
        total = len(self.plano.passos)
        self.count.setText(f"{total} movimentos. " + (f"{n} {'item' if n == 1 else 'itens'} de Outros {'vai' if n == 1 else 'vão'} para _DESCARTADOS." if n else
                                                      "Todos os itens de Outros serão mantidos."))
