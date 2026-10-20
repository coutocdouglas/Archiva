"""Archiva (Gerenciador de Assets 3D) — ponto de entrada."""
import sys
import traceback
from datetime import datetime


def main():
    from PySide6.QtWidgets import QApplication, QMessageBox

    from app.config import APP_NAME, data_dir
    from app.main_window import MainWindow

    log = data_dir() / "erros.log"

    def hook(exc_type, exc, tb):
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"\n[{datetime.now():%Y-%m-%d %H:%M:%S}]\n{text}")
        except OSError:
            pass
        QMessageBox.critical(None, APP_NAME, f"Ocorreu um erro inesperado:\n\n{exc}\n\nDetalhes salvos em:\n{log}")

    sys.excepthook = hook
    if sys.platform == "win32":
        try:   # ícone e agrupamento próprios na barra de tarefas (em vez do ícone do Python)
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("TILD.Archiva")
        except Exception:  # noqa: BLE001
            pass

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    from app import theme
    theme.load_fonts()
    app.setFont(theme.ui_font(10))
    app.setPalette(theme.palette())
    app.setStyleSheet(theme.stylesheet())

    from PySide6.QtGui import QIcon
    from app.config import app_dir
    app.setWindowIcon(QIcon(str(app_dir() / "app" / "recursos" / "icone.png")))
    abertura = _abrir_abertura()
    try:
        w = MainWindow()
    except Exception:
        if abertura is not None:
            abertura.close()
        raise
    app._janela, app._abertura = w, abertura       # mantém as referências vivas
    if abertura is None:
        w.show()
    else:
        _ligar_abertura(w, abertura)
    sys.exit(app.exec())


def _abrir_abertura():
    """Mostra a tela de abertura só quando o programa vai direto à biblioteca (nada de perguntas no caminho)."""
    import os

    from app import perfil
    from app.config import Config
    try:
        cfg = Config()
        if cfg["abertura_off"] or cfg.first_run or not perfil.load() or not os.path.isdir(cfg["library_root"] or ""):
            return None
        from PySide6.QtWidgets import QApplication

        from app.abertura import Abertura
        a = Abertura()
        a.comecar()
        QApplication.processEvents()
        return a
    except Exception:  # noqa: BLE001 — a abertura é enfeite: se falhar, o programa abre normalmente
        return None


def _ligar_abertura(w, abertura):
    from PySide6.QtCore import QTimer

    from app.abertura import LIMITE_MS

    def mostrar():
        w.show()
        w.raise_()
        w.activateWindow()

    abertura.configurar(mostrar)
    abertura.reiniciar_relogio()                    # a montagem da janela principal não conta na animação
    w.pronto.connect(abertura.terminar)
    QTimer.singleShot(LIMITE_MS, abertura.terminar)  # leitura demorada: abre mesmo assim


if __name__ == "__main__":
    main()
