"""Tela de abertura: a logo do Archiva surge letra por letra enquanto a biblioteca é lida.

Fica na frente da janela principal, que carrega por baixo (escondida). Quando a leitura termina e o tempo mínimo
passou, a janela principal aparece e a abertura esmaece. Se a leitura demorar demais, o programa abre mesmo assim.
"""
from __future__ import annotations

import math
import sys

from PySide6.QtCore import QElapsedTimer, QPointF, QPropertyAnimation, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QApplication, QWidget

from . import theme
from .config import version

LARGURA, ALTURA = 640, 400
MINIMO_MS = 1800        # a abertura fica pelo menos este tempo (a animação das letras leva ~1,6 s)
LIMITE_MS = 8000        # leitura demorada: abre o programa mesmo assim
FADE_MS = 420
AUTOR = "Douglas Couto"


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def _subcaminhos(path: QPainterPath) -> list[QPainterPath]:
    """Cada 'moveTo' começa um traço novo (o PySide6 não traz toSubpaths, então percorre os elementos)."""
    saida: list[QPainterPath] = []
    atual = None
    n = path.elementCount()
    i = 0
    while i < n:
        el = path.elementAt(i)
        t = el.type
        if t == QPainterPath.ElementType.MoveToElement:
            atual = QPainterPath()
            saida.append(atual)
            atual.moveTo(el.x, el.y)
        elif t == QPainterPath.ElementType.LineToElement and atual is not None:
            atual.lineTo(el.x, el.y)
        elif t == QPainterPath.ElementType.CurveToElement and atual is not None and i + 2 < n:
            c2, fim = path.elementAt(i + 1), path.elementAt(i + 2)
            atual.cubicTo(el.x, el.y, c2.x, c2.y, fim.x, fim.y)
            i += 2
        i += 1
    return saida


def _letras() -> list[QPainterPath]:
    """Separa o desenho da logo em letras: partes que se sobrepõem na horizontal (ex.: o miolo do 'a') ficam juntas."""
    partes = [(sp.boundingRect(), sp) for sp in _subcaminhos(theme.logo_path())]
    partes.sort(key=lambda t: t[0].left())
    grupos: list[list] = []        # [esquerda, direita, caminho]
    for r, sp in partes:
        if grupos and r.left() < grupos[-1][1] - 0.3:
            g = grupos[-1]
            g[1] = max(g[1], r.right())
            g[2].addPath(sp)
        else:
            c = QPainterPath()
            c.setFillRule(Qt.OddEvenFill)
            c.addPath(sp)
            grupos.append([r.left(), r.right(), c])
    return [g[2] for g in grupos]


class Abertura(QWidget):
    fechada = Signal()

    def __init__(self):
        super().__init__(None, Qt.SplashScreen | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setFixedSize(LARGURA, ALTURA)
        self._letras = _letras()
        total = QPainterPath()
        for p in self._letras:
            total.addPath(p)
        self._caixa = total.boundingRect()
        self._relogio = QElapsedTimer()
        self._pronto = False
        self._fechando = False
        self._frase = "Lendo a biblioteca"
        self._abrir = lambda: None
        self._timer = QTimer(self, interval=16)
        self._timer.timeout.connect(self._tick)
        tela = QGuiApplication.primaryScreen()
        if tela is not None:
            g = tela.availableGeometry()
            self.move(g.center().x() - LARGURA // 2, g.center().y() - ALTURA // 2)

    # ------------------------------------------------------------ ciclo
    def configurar(self, abrir_janela) -> None:
        """abrir_janela: função que mostra a janela principal (chamada uma vez, quando a abertura sai)."""
        self._abrir = abrir_janela

    def _tick(self) -> None:
        self.update()
        # um diálogo da janela principal (ex.: escolher o que fazer com tags antigas) não pode ficar atrás da abertura
        if not self._fechando and QApplication.activeModalWidget() is not None:
            self._pronto = True
            self._esmaecer()

    def comecar(self) -> None:
        """Mostra a abertura e começa a contar o tempo."""
        self._relogio.start()
        self.show()
        self._cantos_redondos()
        self._timer.start()
        self.update()

    def reiniciar_relogio(self) -> None:
        """A janela principal demora um pouco para montar; a animação conta a partir daqui."""
        self._relogio.restart()

    def tempo_ms(self) -> int:
        return int(self._relogio.elapsed()) if self._relogio.isValid() else 0

    def terminar(self) -> None:
        """Chamado quando a leitura acabou: espera o tempo mínimo, abre a janela principal e esmaece."""
        if self._pronto:
            return
        self._pronto = True
        self._frase = "Abrindo"
        falta = max(0, MINIMO_MS - self.tempo_ms())
        QTimer.singleShot(falta, self._esmaecer)

    def _esmaecer(self) -> None:
        if self._fechando:
            return
        self._fechando = True
        try:
            self._abrir()
        finally:
            self._fade = QPropertyAnimation(self, b"windowOpacity", self)
            self._fade.setDuration(FADE_MS)
            self._fade.setStartValue(1.0)
            self._fade.setEndValue(0.0)
            self._fade.finished.connect(self._fim)
            self._fade.start()

    def _fim(self) -> None:
        self._timer.stop()
        self.close()
        self.fechada.emit()

    def _cantos_redondos(self) -> None:
        if sys.platform != "win32":
            return
        try:
            from .janela import _dwm_set
            _dwm_set(int(self.winId()), 33, 2)       # DWMWA_WINDOW_CORNER_PREFERENCE = ROUND (Windows 11)
        except Exception:  # noqa: BLE001
            pass

    # ------------------------------------------------------------ pintura
    def paintEvent(self, e):  # noqa: N802
        t = self.tempo_ms() / 1000.0
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        p.setRenderHint(QPainter.TextAntialiasing, True)
        r = QRectF(self.rect())
        theme.paint_background(p, r)

        k = 0.5 + 0.5 * math.sin(t * 1.2)       # respiração de luz atrás da logo
        centro = QPointF(r.center().x(), r.center().y() - 10)
        g = QRadialGradient(centro, 250 + 28 * k)
        g.setColorAt(0.0, QColor(140, 60, 50, int(255 * (0.14 + 0.07 * k))))
        g.setColorAt(1.0, QColor(140, 60, 50, 0))
        p.fillRect(r, g)

        self._logo(p, r, t)
        self._rodape(p, r, t)
        p.setPen(QPen(QColor(255, 255, 255, 14), 1))
        p.setBrush(Qt.NoBrush)
        p.drawRect(r.adjusted(0.5, 0.5, -0.5, -0.5))

    def _logo(self, p: QPainter, r: QRectF, t: float) -> None:
        c = self._caixa
        esc = (r.width() * 0.67) / c.width()
        x0 = r.center().x() - c.width() * esc / 2 - c.left() * esc
        y0 = r.center().y() - 10 + c.height() * esc / 2 - c.bottom() * esc   # baseline: base da logo no centro
        cor = QColor(theme.LOGO)
        for i, letra in enumerate(self._letras):
            a = _ease((t - 0.2 - i * 0.15) / 0.65)
            if a <= 0:
                continue
            p.save()
            p.setOpacity(a)
            p.translate(x0, y0 + (1 - a) * 16)
            p.scale(esc, esc)
            p.setPen(Qt.NoPen)
            p.setBrush(cor)
            p.drawPath(letra)
            p.restore()

    def _rodape(self, p: QPainter, r: QRectF, t: float) -> None:
        f = theme.ui_font(9.5)
        p.setFont(f)
        pontos = "." * (1 + int(t * 2) % 3)
        p.setPen(theme.MUTED)
        p.drawText(QRectF(24, r.height() - 40, r.width() / 2, 24), Qt.AlignLeft | Qt.AlignVCenter,
                   self._frase + pontos)
        p.drawText(QRectF(r.width() / 2, r.height() - 40, r.width() / 2 - 24, 24), Qt.AlignRight | Qt.AlignVCenter,
                   AUTOR)
        p.setPen(theme.FAINT)
        p.drawText(QRectF(r.width() / 2, r.height() - 62, r.width() / 2 - 24, 22), Qt.AlignRight | Qt.AlignVCenter,
                   f"v{version()}")
        # linha de andamento: um trecho que corre de um lado ao outro
        pos = (t * 0.45) % 1.5 - 0.25
        faixa = QColor(216, 194, 156)
        p.fillRect(QRectF(0, r.height() - 3, r.width(), 3), QColor(216, 194, 156, 30))
        ini = max(0.0, pos * r.width())
        fim = min(r.width(), pos * r.width() + r.width() * 0.25)
        if fim > ini:
            faixa.setAlpha(190)
            p.fillRect(QRectF(ini, r.height() - 3, fim - ini, 3), faixa)
