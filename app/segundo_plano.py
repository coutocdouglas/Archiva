"""Trabalho com os arquivos da biblioteca fora da janela.

Regra do Archiva: nada que vá ao servidor roda na thread da janela (na rede, cada acesso leva milissegundos e
a janela deixaria de responder). Use run_async(fn, on_done): fn roda num ajudante e on_done(resultado) volta
para a janela quando terminar.
"""
from __future__ import annotations

import sys
import traceback
from concurrent.futures import ThreadPoolExecutor

from PySide6.QtCore import QObject, Signal

WORKERS = 8
_pool = ThreadPoolExecutor(max_workers=WORKERS, thread_name_prefix="archiva-io")


class _Bridge(QObject):
    call = Signal(object, object)          # função, argumento (sempre chamada na thread da janela)

    def __init__(self):
        super().__init__()
        self.call.connect(self._run)

    @staticmethod
    def _run(fn, arg):
        try:
            fn(arg)
        except Exception:  # noqa: BLE001 — erro na volta não pode derrubar o programa
            traceback.print_exc(file=sys.stderr)


_bridge: _Bridge | None = None


def init() -> None:
    """Chamar uma vez na thread da janela (antes do primeiro run_async)."""
    global _bridge
    if _bridge is None:
        _bridge = _Bridge()


def run_async(fn, on_done=None, on_error=None):
    """Roda fn() num ajudante. on_done(resultado) / on_error(exceção) voltam na thread da janela."""
    init()

    def job():
        try:
            r = fn()
        except Exception as e:  # noqa: BLE001
            if on_error is not None:
                _bridge.call.emit(on_error, e)
            else:
                traceback.print_exc(file=sys.stderr)
            return
        if on_done is not None:
            _bridge.call.emit(on_done, r)
    return _pool.submit(job)


def map_parallel(fn, items, workers: int = WORKERS) -> list:
    """fn(item) para cada item, vários ao mesmo tempo (dentro de um ajudante); devolve na mesma ordem."""
    items = list(items)
    if len(items) <= 1:
        return [fn(x) for x in items]
    with ThreadPoolExecutor(max_workers=min(workers, len(items)), thread_name_prefix="archiva-map") as ex:
        return list(ex.map(fn, items))


def wait(parent, text: str, fn):
    """Roda fn() num ajudante e espera com a janela respondendo (janela de andamento depois de 0,4 s).

    Para ações que a pessoa pediu e cujo resultado o código usa logo em seguida (mover, organizar, comparar…):
    a janela continua se desenhando e não aparece "Não respondendo". fn pode receber um `report(i, n, texto)`
    se tiver o parâmetro `report`. Erros de fn são levantados aqui, na thread da janela.
    """
    import inspect
    import time as _t

    from PySide6.QtCore import QEventLoop, Qt
    from PySide6.QtWidgets import QApplication, QProgressDialog

    state = {"i": 0, "n": 0, "t": text}

    def report(i: int, n: int, t: str | None = None):
        state.update(i=i, n=n)
        if t:
            state["t"] = t

    try:
        takes_report = "report" in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        takes_report = False
    fut = _pool.submit((lambda: fn(report=report)) if takes_report else fn)
    dlg = None
    t0 = _t.monotonic()
    QApplication.setOverrideCursor(Qt.BusyCursor)
    try:
        while not fut.done():
            if dlg is None and _t.monotonic() - t0 > 0.4:
                dlg = QProgressDialog(text, None, 0, 0, parent)
                dlg.setWindowTitle("Archiva")
                dlg.setWindowModality(Qt.WindowModal)
                dlg.setMinimumDuration(0)
                dlg.setAutoClose(False)
                dlg.setAutoReset(False)
                dlg.setCancelButton(None)
                dlg.show()
            if dlg is not None:
                if state["n"]:
                    dlg.setMaximum(state["n"])
                    dlg.setValue(min(state["i"], state["n"]))
                dlg.setLabelText(state["t"])
            # desenha a janela e atende os relógios, mas não aceita cliques/teclas até terminar
            QApplication.processEvents(QEventLoop.ExcludeUserInputEvents)
            _t.sleep(0.015)
    finally:
        QApplication.restoreOverrideCursor()
        if dlg is not None:
            dlg.close()
            dlg.deleteLater()
    return fut.result()
