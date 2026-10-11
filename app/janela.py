"""Barra de título integrada + cantos arredondados (Windows 11).

A janela continua sendo uma janela normal do Windows para o sistema: arrastar, encaixar nas laterais
(Aero Snap), maximizar com duplo clique, redimensionar pelas bordas e a sombra continuam funcionando.
O que muda é só que a barra branca do Windows não é desenhada — o programa desenha o próprio fundo até
o topo e mostra os botões – □ × no canto.

Se algo der errado (ou em outro sistema), cai automaticamente na barra normal do Windows, escurecida.
"""
from __future__ import annotations

import os
import sys

from PySide6.QtCore import QEvent, QPoint, QRect, QSize, Qt
from PySide6.QtGui import QColor, QCursor, QPainter, QPen
from PySide6.QtWidgets import QAbstractButton, QHBoxLayout, QWidget

IS_WIN = sys.platform == "win32"


def _diag(text: str) -> None:
    """Registra o que aconteceu com a barra integrada em %APPDATA%\\GerenciadorAssets3D\\diagnostico_janela.txt."""
    try:
        from datetime import datetime
        from .config import data_dir
        p = data_dir() / "diagnostico_janela.txt"
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {text}\n")
    except Exception:  # noqa: BLE001
        pass
TITLE_H = 48          # altura da faixa de arrastar (os botões ficam nela)
EDGE = 6              # borda de redimensionar (px lógicos)

if IS_WIN:
    import ctypes
    from ctypes import wintypes

    class _NCCALCSIZE_PARAMS(ctypes.Structure):
        _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]

    class _MARGINS(ctypes.Structure):
        _fields_ = [("l", ctypes.c_int), ("r", ctypes.c_int), ("t", ctypes.c_int), ("b", ctypes.c_int)]

WM_NCCALCSIZE = 0x0083
WM_NCHITTEST = 0x0084
HTCAPTION, HTLEFT, HTRIGHT, HTTOP, HTTOPLEFT, HTTOPRIGHT, HTBOTTOM, HTBOTTOMLEFT, HTBOTTOMRIGHT = \
    2, 10, 11, 12, 13, 14, 15, 16, 17


def _colorref(hex_rgb: str) -> int:
    c = QColor(hex_rgb)
    return c.red() | (c.green() << 8) | (c.blue() << 16)


def _dwm_set(hwnd: int, attr: int, value: int) -> None:
    v = ctypes.c_int(value)
    ctypes.windll.dwmapi.DwmSetWindowAttribute(wintypes.HWND(hwnd), ctypes.c_uint(attr), ctypes.byref(v),
                                               ctypes.sizeof(v))


def dark_native_titlebar(hwnd: int) -> None:
    """Modo 'barra do Windows': escurece a barra e a borda (Windows 10 2004+/11)."""
    if not IS_WIN:
        return
    try:
        _dwm_set(hwnd, 20, 1)                         # DWMWA_USE_IMMERSIVE_DARK_MODE
        _dwm_set(hwnd, 33, 2)                         # DWMWA_WINDOW_CORNER_PREFERENCE = ROUND
        _dwm_set(hwnd, 35, _colorref("#1a1512"))      # DWMWA_CAPTION_COLOR (Windows 11)
        _dwm_set(hwnd, 36, _colorref("#d8c9b3"))      # DWMWA_TEXT_COLOR
        _dwm_set(hwnd, 34, _colorref("#2a201a"))      # DWMWA_BORDER_COLOR
    except Exception:  # noqa: BLE001
        pass


class FramelessMixin:
    """Misturar numa QMainWindow. Chamar `setup_frame(custom)` antes do show e `finish_frame()` depois."""

    _custom_frame = False

    def setup_frame(self, custom: bool) -> None:
        self._custom_frame = bool(custom and IS_WIN)
        self._diag_events = 0
        if IS_WIN:
            try:
                import PySide6
                from PySide6.QtCore import qVersion
                _diag(f"inicio: custom={self._custom_frame} pedido={custom} PySide6={PySide6.__version__} Qt={qVersion()} "
                      f"Windows={sys.getwindowsversion().build}")
            except Exception:  # noqa: BLE001
                pass
        if self._custom_frame:
            self.setWindowFlags(self.windowFlags() | Qt.FramelessWindowHint | Qt.WindowSystemMenuHint
                                | Qt.WindowMinMaxButtonsHint)

    def finish_frame(self) -> None:
        if not IS_WIN:
            return
        hwnd = int(self.winId())
        if not self._custom_frame:
            dark_native_titlebar(hwnd)
            return
        self._ncc_seen = False
        try:
            u = ctypes.windll.user32
            GWL_STYLE = -16
            get = u.GetWindowLongPtrW if hasattr(u, "GetWindowLongPtrW") else u.GetWindowLongW
            setl = u.SetWindowLongPtrW if hasattr(u, "SetWindowLongPtrW") else u.SetWindowLongW
            get.restype = ctypes.c_ssize_t
            get.argtypes = [wintypes.HWND, ctypes.c_int]
            setl.restype = ctypes.c_ssize_t
            setl.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
            self._orig_style = get(hwnd, GWL_STYLE)
            # devolve à janela sem moldura os estilos que dão encaixe, animação, sombra e redimensionamento
            style = self._orig_style | 0x00040000 | 0x00C00000 | 0x00010000 | 0x00020000 | 0x00080000
            setl(hwnd, GWL_STYLE, style)
            m = _MARGINS(0, 0, 0, 1)
            ctypes.windll.dwmapi.DwmExtendFrameIntoClientArea(wintypes.HWND(hwnd), ctypes.byref(m))
            _dwm_set(hwnd, 20, 1)
            _dwm_set(hwnd, 33, 2)                         # cantos arredondados (Windows 11)
            _dwm_set(hwnd, 34, _colorref("#2a201a"))      # borda fina escura
            u.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001 | 0x0004 | 0x0010)
            if self._ncc_seen:
                _diag(f"barra integrada aplicada (modo Windows, estilo={style:#x})")
            else:
                # o Qt não repassou a mensagem que esconde a barra: desfaz e usa o modo 100% Qt
                setl(hwnd, GWL_STYLE, self._orig_style)
                u.SetWindowPos(wintypes.HWND(hwnd), None, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001 | 0x0004 | 0x0010)
                self._start_qt_mode(hwnd, "mensagem WM_NCCALCSIZE não chegou")
        except Exception:  # noqa: BLE001
            import traceback
            _diag("falhou o modo Windows:\n" + traceback.format_exc())
            try:
                self._start_qt_mode(hwnd, "erro no modo Windows")
            except Exception:  # noqa: BLE001
                _diag("falhou também o modo Qt:\n" + traceback.format_exc())
        self.frame_changed()

    # ---------------- modo 100% Qt (sem mensagens do Windows): arrastar e redimensionar pelo próprio Qt
    def _start_qt_mode(self, hwnd: int, motivo: str) -> None:
        self._qt_mode = True
        self._custom_frame = True
        try:
            _dwm_set(hwnd, 33, 2)                         # cantos arredondados (Windows 11)
            _dwm_set(hwnd, 34, _colorref("#2a201a"))
        except Exception:  # noqa: BLE001
            pass
        self._grips = [_Grip(self, edges) for edges in _GRIP_EDGES]
        self._place_grips()
        from PySide6.QtWidgets import QApplication
        QApplication.instance().installEventFilter(self)
        _diag(f"barra integrada aplicada (modo Qt; motivo: {motivo})")

    def _place_grips(self) -> None:
        if not getattr(self, "_grips", None):
            return
        w, h, g = self.width(), self.height(), EDGE
        maxed = self.isMaximized()
        for gr in self._grips:
            e = gr.edges
            x = 0 if Qt.LeftEdge in e else (w - g if Qt.RightEdge in e else g)
            y = 0 if Qt.TopEdge in e else (h - g if Qt.BottomEdge in e else g)
            gw = g if (Qt.LeftEdge in e or Qt.RightEdge in e) else w - 2 * g
            gh = g if (Qt.TopEdge in e or Qt.BottomEdge in e) else h - 2 * g
            gr.setGeometry(x, y, gw, gh)
            gr.setVisible(not maxed)
            gr.raise_()

    def eventFilter(self, obj, e):  # noqa: N802 — só no modo Qt
        if getattr(self, "_qt_mode", False) and e.type() in (QEvent.MouseButtonPress, QEvent.MouseButtonDblClick) \
                and e.button() == Qt.LeftButton and isinstance(obj, QWidget) and obj.window() is self:
            pos = self.mapFromGlobal(e.globalPosition().toPoint())
            if pos.y() < TITLE_H and self.is_drag_point(pos):
                if e.type() == QEvent.MouseButtonDblClick:
                    self.showNormal() if self.isMaximized() else self.showMaximized()
                else:
                    self.windowHandle().startSystemMove()
                return True
        return super().eventFilter(obj, e)

    def frame_changed(self) -> None:          # sobrescrito pela janela (mostrar/ocultar botões)
        pass

    @property
    def custom_frame(self) -> bool:
        return self._custom_frame

    # chamado pelo Qt com as mensagens do Windows
    def nativeEvent(self, eventType, message):  # noqa: N802
        if not self._custom_frame or getattr(self, "_qt_mode", False):
            return super().nativeEvent(eventType, message)
        try:
            msg = wintypes.MSG.from_address(message.__int__())
            if self._diag_events < 3:
                self._diag_events += 1
                _diag(f"evento: tipo={eventType!r} ({type(eventType).__name__}) msg={msg.message:#x}")
            if not msg.hWnd:
                return False, 0
            if msg.message == WM_NCCALCSIZE:
                self._ncc_seen = True
                if msg.wParam:
                    rect = _NCCALCSIZE_PARAMS.from_address(msg.lParam).rgrc[0]
                else:
                    rect = wintypes.RECT.from_address(msg.lParam)
                u = ctypes.windll.user32
                if u.IsZoomed(msg.hWnd):
                    # maximizada, o Windows deixa a janela 'vazar' pela borda: compensa
                    try:
                        dpi = u.GetDpiForWindow(msg.hWnd)
                        fx = u.GetSystemMetricsForDpi(32, dpi) + u.GetSystemMetricsForDpi(92, dpi)
                        fy = u.GetSystemMetricsForDpi(33, dpi) + u.GetSystemMetricsForDpi(92, dpi)
                    except Exception:  # noqa: BLE001
                        fx = u.GetSystemMetrics(32) + u.GetSystemMetrics(92)
                        fy = u.GetSystemMetrics(33) + u.GetSystemMetrics(92)
                    rect.left += fx
                    rect.top += fy
                    rect.right -= fx
                    rect.bottom -= fy
                return True, (0x0300 if msg.wParam else 0)     # WVR_REDRAW
            if msg.message == WM_NCHITTEST:
                pos = self.mapFromGlobal(QCursor.pos())
                x, y, w, h = pos.x(), pos.y(), self.width(), self.height()
                if not ctypes.windll.user32.IsZoomed(msg.hWnd):
                    left, right, top, bottom = x < EDGE, x >= w - EDGE, y < EDGE, y >= h - EDGE
                    if top and left:
                        return True, HTTOPLEFT
                    if top and right:
                        return True, HTTOPRIGHT
                    if bottom and left:
                        return True, HTBOTTOMLEFT
                    if bottom and right:
                        return True, HTBOTTOMRIGHT
                    if left:
                        return True, HTLEFT
                    if right:
                        return True, HTRIGHT
                    if top:
                        return True, HTTOP
                    if bottom:
                        return True, HTBOTTOM
                if y < TITLE_H and self.is_drag_point(pos):
                    return True, HTCAPTION
        except Exception:  # noqa: BLE001
            if self._diag_events < 6:
                self._diag_events += 1
                import traceback
                _diag("erro em nativeEvent:\n" + traceback.format_exc())
        return super().nativeEvent(eventType, message)

    def is_drag_point(self, pos: QPoint) -> bool:
        """Arrasta quando o ponto está sobre o fundo (não sobre um botão, campo ou lista)."""
        from PySide6.QtWidgets import QAbstractItemView, QComboBox, QLineEdit, QScrollBar, QSlider
        wdg = self.childAt(pos)
        while wdg is not None and wdg is not self:
            if isinstance(wdg, (QAbstractButton, QLineEdit, QComboBox, QSlider, QScrollBar, QAbstractItemView)) \
                    or getattr(wdg, "no_drag", False):
                return False
            wdg = wdg.parentWidget()
        return True


# --------------------------------------------------------------------------- bordas de redimensionar (modo Qt)

_GRIP_EDGES = [Qt.LeftEdge, Qt.RightEdge, Qt.TopEdge, Qt.BottomEdge,
               Qt.TopEdge | Qt.LeftEdge, Qt.TopEdge | Qt.RightEdge,
               Qt.BottomEdge | Qt.LeftEdge, Qt.BottomEdge | Qt.RightEdge]


class _Grip(QWidget):
    def __init__(self, window, edges):
        super().__init__(window)
        self.edges = Qt.Edges(edges)
        self.no_drag = True
        e = self.edges
        if e == (Qt.TopEdge | Qt.LeftEdge) or e == (Qt.BottomEdge | Qt.RightEdge):
            self.setCursor(Qt.SizeFDiagCursor)
        elif e == (Qt.TopEdge | Qt.RightEdge) or e == (Qt.BottomEdge | Qt.LeftEdge):
            self.setCursor(Qt.SizeBDiagCursor)
        elif e in (Qt.Edges(Qt.LeftEdge), Qt.Edges(Qt.RightEdge)):
            self.setCursor(Qt.SizeHorCursor)
        else:
            self.setCursor(Qt.SizeVerCursor)

    def mousePressEvent(self, ev):
        if ev.button() == Qt.LeftButton:
            self.window().windowHandle().startSystemResize(self.edges)


# --------------------------------------------------------------------------- botões – □ ×

class _CaptionButton(QAbstractButton):
    def __init__(self, kind: str, parent=None):
        super().__init__(parent)
        self.kind = kind
        self.setFixedSize(46, 34)
        self.setCursor(Qt.ArrowCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setToolTip({"min": "Minimizar", "max": "Maximizar", "close": "Fechar"}[kind])
        self._hover = False

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = self.rect()
        if self._hover:
            p.fillRect(r, QColor(160, 52, 40, 210) if self.kind == "close" else QColor(255, 236, 210, 22))
        col = QColor("#fff6e8") if self._hover else QColor(200, 188, 172)
        p.setPen(QPen(col, 1.1))
        c = r.center()
        if self.kind == "min":
            p.drawLine(c.x() - 5, c.y(), c.x() + 5, c.y())
        elif self.kind == "max":
            win = self.window()
            if win.isMaximized():
                p.drawRoundedRect(c.x() - 5, c.y() - 3, 8, 8, 1.5, 1.5)
                p.drawLine(c.x() - 3, c.y() - 5, c.x() + 5, c.y() - 5)
                p.drawLine(c.x() + 5, c.y() - 5, c.x() + 5, c.y() + 3)
            else:
                p.drawRoundedRect(c.x() - 5, c.y() - 5, 10, 10, 2, 2)
        else:
            p.drawLine(c.x() - 5, c.y() - 5, c.x() + 5, c.y() + 5)
            p.drawLine(c.x() - 5, c.y() + 5, c.x() + 5, c.y() - 5)


class CaptionButtons(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.no_drag = True
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.b_min = _CaptionButton("min", self)
        self.b_max = _CaptionButton("max", self)
        self.b_close = _CaptionButton("close", self)
        self.b_min.clicked.connect(window.showMinimized)
        self.b_max.clicked.connect(lambda: window.showNormal() if window.isMaximized() else window.showMaximized())
        self.b_close.clicked.connect(window.close)
        for b in (self.b_min, self.b_max, self.b_close):
            lay.addWidget(b)
        self.adjustSize()
