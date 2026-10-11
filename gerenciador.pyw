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
    w = MainWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
