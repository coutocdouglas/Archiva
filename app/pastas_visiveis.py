"""Configurações › Biblioteca › Pastas exibidas: marcar/desmarcar quais categorias aparecem no Archiva.

Só esconde (para esta pessoa): nenhum arquivo é movido ou apagado.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QPushButton, QTreeWidget,
                               QTreeWidgetItem, QVBoxLayout)

from . import theme, ui


class VisibleFoldersDialog(QDialog):
    def __init__(self, parent, cats: list, hidden: set[str]):
        super().__init__(parent)
        self.setWindowTitle("Pastas exibidas")
        self.resize(520, 640)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(28, 24, 28, 20)
        outer.setSpacing(12)
        t = QLabel("Pastas exibidas")
        t.setStyleSheet("font-size:18pt;")
        outer.addWidget(t)
        s = QLabel("Desmarque as pastas que você não quer ver no Archiva. Elas somem da Biblioteca, da busca, "
                   "do Início e da Entrada só para você; nenhum arquivo é movido ou apagado.")
        s.setWordWrap(True)
        s.setStyleSheet(f"color:{theme.MUTED.name()};")
        outer.addWidget(s)
        row = QHBoxLayout()
        all_on = QPushButton("Marcar todas")
        all_on.clicked.connect(lambda: self._set_all(Qt.Checked))
        all_off = QPushButton("Desmarcar todas")
        all_off.clicked.connect(lambda: self._set_all(Qt.Unchecked))
        row.addWidget(all_on)
        row.addWidget(all_off)
        row.addStretch(1)
        self.count = QLabel()
        self.count.setStyleSheet(f"color:{theme.FAINT.name()};")
        row.addWidget(self.count)
        outer.addLayout(row)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(22)
        self.tree.setStyleSheet("QTreeWidget{background:transparent;border:none;} QTreeWidget::item{padding:6px 4px;}")
        self.items: list[QTreeWidgetItem] = []

        def add(parent, c):
            n = len(c.all_assets())
            it = QTreeWidgetItem([f"{c.name}   ({n})"])
            it.setData(0, Qt.UserRole, c.key)
            it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
            it.setCheckState(0, Qt.Unchecked if c.key in hidden else Qt.Checked)
            if parent is None:
                self.tree.addTopLevelItem(it)
            else:
                parent.addChild(it)
            self.items.append(it)
            for ch in c.children:
                add(it, ch)

        for c in cats:
            add(None, c)
        self.tree.expandAll()
        self.tree.itemChanged.connect(self._changed)
        outer.addWidget(self.tree, 1)
        bb = QDialogButtonBox()
        ui.primary(bb.addButton("Salvar", QDialogButtonBox.AcceptRole))
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        bb.accepted.connect(self.accept)
        bb.rejected.connect(self.reject)
        outer.addWidget(bb)
        self._changed()

    def _set_all(self, state):
        self.tree.blockSignals(True)
        for it in self.items:
            it.setCheckState(0, state)
        self.tree.blockSignals(False)
        self._changed()

    def _changed(self, *_):
        n = len(self.hidden())
        self.count.setText(f"{n} escondida(s)" if n else "todas visíveis")

    def hidden(self) -> list[str]:
        return [it.data(0, Qt.UserRole) for it in self.items if it.checkState(0) != Qt.Checked]
