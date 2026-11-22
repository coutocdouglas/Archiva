"""Interface do arrasto para o 3ds Max (etapa 3): o seletor "Versão a importar" do painel lateral e o arrasto
dos cartões do nível 4. A decisão do que vai para o Max fica em arrastar.py."""
from __future__ import annotations

import json

from PySide6.QtCore import QMimeData, QPoint, Qt, QUrl
from PySide6.QtGui import QDrag
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from .. import theme, ui
from ..config import data_dir
from . import arrastar

PREFS_FILE = "vegetacao_arrasto.json"     # em %APPDATA%\GerenciadorAssets3D: só a versão preferida


def load_pref() -> str:
    try:
        v = json.loads((data_dir() / PREFS_FILE).read_text(encoding="utf-8")).get("versao")
        return v if v in (arrastar.MESH, arrastar.PROXY) else arrastar.PROXY
    except (OSError, ValueError, AttributeError):
        return arrastar.PROXY


def save_pref(v: str) -> None:
    try:
        (data_dir() / PREFS_FILE).write_text(json.dumps({"versao": v}), encoding="utf-8")
    except OSError:
        pass


class SeletorVersao(QWidget):
    """"Versão a importar": Mesh | Proxy. Proxy é o padrão; sem proxy pronto, avisa que vai a malha."""

    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(6)
        lay.addWidget(ui.heading("Versão a importar", 9))
        self.seg = ui.Segmented([("Mesh", arrastar.MESH), ("Proxy", arrastar.PROXY)])
        self.preferida = load_pref()
        self.seg.blockSignals(True)
        self.seg.setCurrentIndex(self.seg.findData(self.preferida))
        self.seg.blockSignals(False)
        self.seg.currentIndexChanged.connect(self._changed)
        lay.addWidget(self.seg)
        self.note = QLabel()
        self.note.setWordWrap(True)
        self.note.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:9pt;")
        lay.addWidget(self.note)
        self.hint = QLabel("Arraste o cartão para a viewport do 3ds Max: ele entra sozinho onde você soltar, sem o "
                           "menu Merge. As texturas vêm da pasta Maps do volume.")
        self.hint.setWordWrap(True)
        self.hint.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:9pt;")
        lay.addWidget(self.hint)
        self.arq = None
        try:
            from . import proxy
            proxy.instalar()       # desliga o script de inicialização da 2.0.21, se ele existir
        except Exception:  # noqa: BLE001
            pass

    def _changed(self, i):
        self.preferida = self.seg.options[i][1]
        save_pref(self.preferida)
        self._update()

    def show_file(self, arq):
        self.arq = arq
        self._update()

    def _update(self):
        a = self.arq
        if a is None:
            self.note.setText("")
            return
        from . import proxy
        if arrastar.versao_efetiva(a, self.preferida) == arrastar.PROXY:
            text = "Vai o proxy (Corona Proxy, leve na cena)."
        elif self.preferida == arrastar.PROXY and proxy.pode_criar(a):
            text = ("Ainda não há proxy: vai a malha e, ao soltar, o 3ds Max cria o proxy na pasta "
                    "\"- Proxy\" do volume (precisa do Corona). Depois use Atualizar.")
            r = proxy.resultado(a.path)
            if r and r[0] == "erro":
                text += f"\nÚltima tentativa: {r[1]}"
        elif self.preferida == arrastar.PROXY:
            text = "Ainda não há proxy deste arquivo: vai a malha (Mesh)."
        else:
            text = "Vai a malha original (Mesh)."
        self.note.setText(text)


def start_drag(page, grid) -> None:
    """Chamado pelo startDrag da grade. Só os cartões de arquivo (nível 4) vão para o Max."""
    ix = grid.currentIndex()
    r = ix.data(Qt.UserRole) if ix.isValid() else None
    if not r or "arq" not in r:
        return
    vol, esp, arq = r["vol"], r["esp"], r["arq"]
    path, msg = arrastar.preparar(vol, esp, arq, page.side.versao.preferida)
    try:
        page.w.statusBar().showMessage(msg, 10000)
    except Exception:  # noqa: BLE001
        pass
    if not path:
        return
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(path)])
    drag = QDrag(grid)
    drag.setMimeData(mime)
    pix = page.w.thumbs.get(arq.preview) if arq.preview else None
    if pix and not pix.isNull():
        drag.setPixmap(pix.scaled(96, 96, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        drag.setHotSpot(QPoint(48, 48))
    drag.exec(Qt.CopyAction)
