"""Tela de conferência do "Organizar volume" (simulação): mostra para onde vai cada arquivo antes de mexer em nada.

Outros: cada item aparece desmarcado (= manter em "- Outros"); o que a pessoa marcar vai para _DESCARTADOS.
Nada é apagado: tudo pode ser desfeito depois com "Desfazer organização".

Visual no estilo do programa: vidro quente, seletor de seções (no lugar das abas do Qt) e um cartão por grupo
com a cor do grupo.
"""
from __future__ import annotations

import collections
import os

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QHeaderView, QLabel, QPushButton, QStackedWidget,
                               QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from .. import theme, ui
from . import organizar

GROUP_TEXT = {
    organizar.MESH: ("Mesh", "os .max, cada um com a prévia ao lado e a biblioteca Forest Pack"),
    organizar.PROXY: ("Proxy", "proxies que já existiam"),
    organizar.MAPS: ("Maps", "texturas"),
    organizar.PDF: ("PDF", "PDF do volume e capas das espécies"),
    organizar.CAPA: ("Capa do volume", "criada a partir da 1ª página do PDF"),
    organizar.OUTROS: ("Outros", "o que não tem lugar no padrão: você decide"),
    organizar.DESC: ("_DESCARTADOS", "sai do volume para a pasta de descartados da coleção"),
}
GROUP_COLOR = {
    organizar.MESH: theme.OK,
    organizar.PROXY: theme.HILITE,
    organizar.MAPS: theme.BUSY,
    organizar.PDF: theme.ORG,
    organizar.CAPA: theme.LINK,
    organizar.OUTROS: theme.WARN,
    organizar.DESC: theme.BAD,
}
# o que cada grupo vira no disco (pasta do volume, ou a pasta de descartados da coleção)
GROUP_FOLDER = {
    organizar.MESH: "{p} - Mesh", organizar.PROXY: "{p} - Mesh\\{p} - Proxy", organizar.MAPS: "{p} - Maps",
    organizar.PDF: "{p} - PDF", organizar.OUTROS: "{p} - Outros",
    organizar.DESC: "{col}\\_DESCARTADOS\\{vol}", organizar.CAPA: "{col}\\{vol}.jpg",
}

STYLE = f"""
QTreeWidget {{ font-size: 10pt; }}
QTreeWidget::item {{ padding: 5px 2px; }}
QHeaderView::section {{ padding: 8px 6px; border-bottom: 1px solid rgba(255,230,200,0.10); }}
"""


def human_size(n: int) -> str:
    if n >= 1024 ** 3:
        return f"{n / 1024 ** 3:.1f} GB".replace(".", ",")
    if n >= 1024 ** 2:
        return f"{n / 1024 ** 2:.0f} MB"
    if n >= 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n} B"


def plural(n: int, um: str, varios: str) -> str:
    return f"{n} {um if n == 1 else varios}"


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
    t.setFrameShape(QFrame.NoFrame)
    t.header().setStretchLastSection(False)
    t.header().setSectionResizeMode(0, QHeaderView.Stretch)
    for i in range(1, len(headers)):
        t.header().setSectionResizeMode(i, QHeaderView.ResizeToContents)
    return t


def _panel(*children, margins=(14, 12, 14, 12), spacing=8) -> ui.Glass:
    """Vidro com o conteúdo dentro (lista, texto, cartões)."""
    box = ui.Glass(14)
    lay = QVBoxLayout(box)
    lay.setContentsMargins(*margins)
    lay.setSpacing(spacing)
    for c in children:
        lay.addWidget(c, 1 if isinstance(c, QTreeWidget) else 0)
    return box


class _Dot(QLabel):
    def __init__(self, color: QColor):
        super().__init__()
        self.setFixedSize(12, 12)
        self.setStyleSheet(f"background:{color.name()}; border-radius:6px;")


class OrganizarDialog(QDialog):
    def __init__(self, parent, vol_label: str, plano: organizar.Plano):
        super().__init__(parent)
        self.plano = plano
        self.vol_label = vol_label
        self.setWindowTitle(f"Organizar · {vol_label}")
        self.setStyleSheet(STYLE)
        self.resize(1040, 740)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(30, 26, 30, 22)
        outer.setSpacing(12)

        head = QVBoxLayout()
        head.setSpacing(2)
        t = QLabel(f"Organizar {vol_label}")
        t.setFont(theme.ui_font(21))
        head.addWidget(t)
        outer.addLayout(head)

        groups = plano.por_grupo()
        if plano.status != "ok":
            self._blocked(outer, head)
            return
        n_total = len(plano.passos)
        head.addWidget(_muted(f"Simulação: nada foi mexido ainda · {plural(n_total, 'movimento', 'movimentos')}", 10.5))
        outer.addWidget(_panel(_muted(
            f"Ao clicar em \"Organizar\", os arquivos vão para as pastas \"{plano.prefixo} - Mesh / Maps / PDF / "
            f"Outros\" dentro do volume. Nada é apagado: o que sai vai para a pasta _DESCARTADOS da coleção, e "
            f"\"Desfazer organização\" volta tudo como estava.", 10), margins=(16, 12, 16, 12)))

        self.outros_tree = self._outros(groups[organizar.OUTROS])
        pages = [
            ("Resumo", self._summary(groups)),
            (f"Outros · {len(groups[organizar.OUTROS])}", self._outros_page()),
            (f"Descartados · {len(groups[organizar.DESC])}", self._descartes(groups[organizar.DESC])),
            ("Todos os movimentos", self._all(groups)),
        ]
        self.seg = ui.Segmented([(name, str(i)) for i, (name, _) in enumerate(pages)])
        row = QHBoxLayout()
        row.addWidget(self.seg)
        row.addStretch(1)
        outer.addLayout(row)
        self.stack = QStackedWidget()
        for _, w in pages:
            self.stack.addWidget(w)
        outer.addWidget(self.stack, 1)
        self.seg.currentIndexChanged.connect(self.stack.setCurrentIndex)

        foot = QHBoxLayout()
        self.count = _muted("", 10)
        foot.addWidget(self.count, 1)
        cancel = QPushButton("Cancelar")
        cancel.setCursor(Qt.PointingHandCursor)
        cancel.clicked.connect(self.reject)
        foot.addWidget(cancel)
        go = ui.primary(QPushButton("Organizar"))
        go.clicked.connect(self.accept)
        foot.addWidget(go)
        outer.addLayout(foot)
        self.outros_tree.itemChanged.connect(lambda *_: self._update_count())
        self._update_count()

    # ------------------------------------------------------------------ bloqueado
    def _blocked(self, outer, head):
        plano = self.plano
        head.addWidget(_muted("Não foi possível organizar agora. Nada foi mexido.", 10.5))
        outer.addWidget(_panel(_muted(plano.motivo, 10.5), margins=(16, 14, 16, 14)))
        if plano.conflitos:
            tr = _tree(["Conflito"])
            for c in plano.conflitos[:500]:
                QTreeWidgetItem(tr, [c])
            outer.addWidget(_panel(tr), 1)
        else:
            outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)
        b = ui.primary(QPushButton("Fechar"))
        b.clicked.connect(self.reject)
        row.addWidget(b)
        outer.addLayout(row)

    # ------------------------------------------------------------------ páginas
    def _folder_of(self, g: str) -> str:
        col = os.path.basename(os.path.dirname(self.plano.volume))
        vol = os.path.basename(self.plano.volume)
        return GROUP_FOLDER[g].format(p=self.plano.prefixo, col=col, vol=vol)

    def _summary(self, groups) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 4, 0, 0)
        lay.setSpacing(9)
        for g, passos in groups.items():
            if not passos:
                continue
            name, desc = GROUP_TEXT[g]
            size = sum(p.tamanho for p in passos)
            copies = sum(1 for p in passos if p.acao == "copiar")
            extra = f" ({copies} prévias copiadas com o nome do .max)" if copies else ""
            box = ui.Glass(14)
            bl = QHBoxLayout(box)
            bl.setContentsMargins(18, 12, 18, 12)
            bl.setSpacing(14)
            bl.addWidget(_Dot(GROUP_COLOR[g]))
            text = QVBoxLayout()
            text.setSpacing(1)
            a = QLabel(name)
            a.setFont(theme.ui_font(12))
            text.addWidget(a)
            text.addWidget(_muted(desc + extra, 9.5))
            bl.addLayout(text, 1)
            dest = QLabel(self._folder_of(g))
            dest.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:9pt;")
            dest.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            bl.addWidget(dest)
            n = QLabel(f"{plural(len(passos), 'item', 'itens')} · {human_size(size)}")
            n.setMinimumWidth(130)
            n.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            bl.addWidget(n)
            lay.addWidget(box)
        lay.addStretch(1)
        return w

    def _outros(self, passos) -> QTreeWidget:
        tr = _tree(["Arquivo", "Motivo", "Tamanho"])
        base = os.path.join(self.plano.volume, f"{self.plano.prefixo} - Outros")
        by_folder = collections.defaultdict(list)
        for p in passos:
            rel = os.path.relpath(p.destino, base)
            by_folder[os.path.dirname(rel) or "(raiz do volume)"].append((os.path.basename(rel), p))
        for folder in sorted(by_folder, key=str.casefold):
            items = by_folder[folder]
            top = QTreeWidgetItem(tr, [f"{folder}  ({len(items)})", "", human_size(sum(p.tamanho for _, p in items))])
            top.setFlags(top.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            top.setCheckState(0, Qt.Unchecked)
            for name, p in sorted(items, key=lambda x: x[0].casefold()):
                it = QTreeWidgetItem(top, [name, p.motivo, human_size(p.tamanho)])
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Unchecked)
                it.setData(0, Qt.UserRole, p.origem)
        return tr

    def _outros_page(self) -> QWidget:
        if not self.outros_tree.topLevelItemCount():
            return _panel(_muted("Nada fora do padrão neste volume."), margins=(18, 16, 18, 16))
        return _panel(_muted("Tudo aqui fica na pasta Outros (desmarcado = manter). Marque o que quer mandar para "
                             "_DESCARTADOS. Marcar uma pasta marca tudo dentro dela."), self.outros_tree)

    def _descartes(self, passos) -> QWidget:
        if not passos:
            return _panel(_muted("Nada sai deste volume pelas regras combinadas."), margins=(18, 16, 18, 16))
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
        where = os.path.join(os.path.basename(os.path.dirname(self.plano.volume)), "_DESCARTADOS",
                             os.path.basename(self.plano.volume))
        return _panel(_muted("Saem do volume pelas regras combinadas (versão repetida, cena num volume que já tem as "
                             "malhas, V-Ray quando existe Corona, compactado já extraído, Thumbs.db). Ficam guardados "
                             f"em {where}"), tr)

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
        return _panel(tr)

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
        tail = (f"{plural(n, 'item', 'itens')} de Outros {'vai' if n == 1 else 'vão'} para _DESCARTADOS." if n
                else "Todos os itens de Outros serão mantidos.")
        self.count.setText(f"{plural(total, 'movimento', 'movimentos')}. {tail}")
