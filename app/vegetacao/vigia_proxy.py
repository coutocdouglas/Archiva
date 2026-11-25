"""Depois de um arrasto que pediu proxy (2.0.29): vigia a pasta "- Proxy" e, quando o 3ds Max grava o .max do proxy,
marca o arquivo como "mesh + proxy" na página e no índice em disco, sem precisar de Atualizar.

O Max cria o proxy depois do Merge, fora do Archiva; o único sinal é o arquivo aparecer (proxy.destino). A vigia
confere a cada 2 s e desiste depois de 10 minutos ou quando o Max responde "erro" em proxy_resultado.txt.
"""
from __future__ import annotations

import os
import time

from PySide6.QtCore import QObject, QTimer

from . import leitor, proxy

INTERVALO_MS = 2000
PRAZO_S = 600


def _mesmo(a: str, b: str) -> bool:
    return os.path.normcase(os.path.normpath(a)) == os.path.normcase(os.path.normpath(b))


class VigiaProxy(QObject):
    def __init__(self, page):
        super().__init__(page)
        self.page = page
        self.pendentes: dict[str, tuple[str, float]] = {}    # chave (normcase) → (caminho da malha, prazo)
        self.timer = QTimer(self)
        self.timer.setInterval(INTERVALO_MS)
        self.timer.timeout.connect(self._conferir)

    def vigiar(self, mesh_path: str) -> None:
        self.pendentes[os.path.normcase(os.path.normpath(mesh_path))] = (mesh_path, time.monotonic() + PRAZO_S)
        self.timer.start()

    def _arquivos(self, mesh_path: str):
        """Os Arquivo da página com este caminho (procura em page.cols: uma releitura pode ter trocado os objetos)."""
        for c in getattr(self.page, "cols", []) or []:
            for v in c.volumes:
                for e in v.especies:
                    for a in e.arquivos:
                        if _mesmo(a.path, mesh_path):
                            yield a

    def _conferir(self) -> None:
        agora = time.monotonic()
        feitos = False
        for chave, (mesh, prazo) in list(self.pendentes.items()):
            dst = proxy.destino(mesh)
            if os.path.isfile(dst):
                for a in self._arquivos(mesh):
                    a.proxy = dst
                del self.pendentes[chave]
                feitos = True
                continue
            r = proxy.resultado(mesh)
            if agora > prazo or (r and r[0] == "erro"):
                del self.pendentes[chave]
        if not self.pendentes:
            self.timer.stop()
        if feitos:
            self._mostrar()

    def _mostrar(self) -> None:
        page = self.page
        try:
            leitor.save_index(page.index_path, page.cols)
        except Exception:  # noqa: BLE001
            pass
        if getattr(page, "where", ("inicio",))[0] != "especie":
            return
        linha = page.grid.currentIndex().row()
        barra = page.grid.verticalScrollBar().value()
        page.go(page.where)
        if 0 <= linha < page.model.rowCount():
            page.grid.setCurrentIndex(page.model.index(linha))
            page._select(page.model.index(linha))
        page.grid.verticalScrollBar().setValue(barra)


def vigiar(page, mesh_path: str) -> None:
    v = getattr(page, "_vigia_proxy", None)
    if v is None:
        v = page._vigia_proxy = VigiaProxy(page)
    v.vigiar(mesh_path)
