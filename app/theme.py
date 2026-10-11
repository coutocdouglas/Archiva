"""Identidade visual do Archiva (estilo "Nogueira").

Tudo que é cor, fonte e acabamento fica aqui, para as telas usarem os mesmos valores.
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QFontDatabase, QLinearGradient, QPainter, QPainterPath, QPalette, QPen,
                           QRadialGradient)

APP_TITLE = "Archiva"

# ------------------------------------------------------------------ cores
TEXT = QColor("#f1e9dc")        # texto principal
MUTED = QColor("#a89c8c")       # secundário
FAINT = QColor("#75695c")       # terciário
LOGO = QColor("#efe2c9")        # pergaminho
LINK = QColor("#d8c29c")        # latão suave
HILITE = QColor("#e3cfa9")      # contorno de seleção
BTN_TOP = QColor("#f0e6d4")     # botão principal (pergaminho)
BTN_BOTTOM = QColor("#ddcdb2")
BTN_TEXT = QColor("#26150c")
BASE = QColor("#16120f")        # fundo médio (para quem precisa de cor sólida)
FIELD = QColor("#1d1814")       # campos de texto e listas sólidas
DIALOG = QColor("#1a1512")

OK = QColor("#7fb48a")          # pronto
WARN = QColor("#d6a15e")        # compactado
ORG = QColor("#a993d6")         # fora do padrão
BUSY = QColor("#7fb2c9")        # extraindo / fila
BAD = QColor("#d27a6a")         # sem arquivo

SIDEBAR_STOPS = [(0.0, "#32201a"), (0.20, "#2f1a1a"), (0.42, "#2a1619"), (0.62, "#2a1d18"),
                 (0.82, "#33251d"), (1.0, "#3a2b21")]
BG_STOPS = [(0.0, "#15110e"), (0.30, "#1b1612"), (0.55, "#141210"), (0.80, "#1a1612"), (1.0, "#14110f")]

UI_FAMILY = "ZT Nature"
LOGO_FAMILY = "NauryzRedKeds"
_fonts_ok = False


def rgba(c: QColor, a: float) -> QColor:
    c = QColor(c)
    c.setAlphaF(a)
    return c


# contorno do item selecionado: cobre forte (aparece sobre prévia branca e sobre fundo escuro)
SELECT = QColor("#d9894a")


def paint_selection(p: QPainter, r: QRectF, radius: float = 12) -> None:
    """Anel de seleção: cobre por fora + fio escuro por dentro (separa da imagem clara)."""
    from PySide6.QtGui import QPen
    p.save()
    p.setBrush(Qt.NoBrush)
    p.setPen(QPen(SELECT, 2.6))
    p.drawRoundedRect(r.adjusted(1.3, 1.3, -1.3, -1.3), radius, radius)
    p.setPen(QPen(QColor(20, 13, 8, 150), 1))
    p.drawRoundedRect(r.adjusted(3.1, 3.1, -3.1, -3.1), max(1, radius - 2.2), max(1, radius - 2.2))
    p.restore()


def css(c: QColor) -> str:
    return c.name()


# ------------------------------------------------------------------ fontes
def load_fonts() -> None:
    global _fonts_ok, UI_FAMILY, LOGO_FAMILY
    folder = Path(__file__).resolve().parent / "recursos" / "fontes"
    fams = set()
    for f in sorted(folder.glob("*.ttf")):
        i = QFontDatabase.addApplicationFont(str(f))
        if i >= 0:
            fam = QFontDatabase.applicationFontFamilies(i)
            fams.update(fam)
            if f.name.startswith("Archiva-Logo") and fam:
                LOGO_FAMILY = fam[0]
    _fonts_ok = UI_FAMILY in fams
    if not _fonts_ok:
        UI_FAMILY = "Segoe UI"


def ui_font(pt: float = 10, weight: int = 600) -> QFont:
    f = QFont(UI_FAMILY)
    f.setPointSizeF(pt)
    f.setWeight(QFont.Weight(weight))
    f.setHintingPreference(QFont.PreferNoHinting)
    return f


def logo_font(pt: float = 24) -> QFont:
    f = QFont(LOGO_FAMILY)
    f.setPointSizeF(pt)
    return f


_logo_cache = None


def logo_path():
    """Desenho vetorial do nome 'Archiva' (recursos/logo.json), já em pixels para 26 pt.

    O logotipo vai como desenho, não como fonte: assim o arquivo da fonte não precisa ser distribuído.
    """
    global _logo_cache
    from PySide6.QtGui import QPainterPath
    if _logo_cache is None:
        from PySide6.QtCore import Qt
        import json
        path = QPainterPath()
        try:
            d = json.loads((Path(__file__).resolve().parent / "recursos" / "logo.json").read_text(encoding="utf-8"))
            e = d["e"]
            i = 0
            while i < len(e):
                t, x, y = e[i]
                if t == 0:
                    path.moveTo(x, y)
                elif t == 1:
                    path.lineTo(x, y)
                elif t == 2 and i + 2 < len(e):
                    path.cubicTo(x, y, e[i + 1][1], e[i + 1][2], e[i + 2][1], e[i + 2][2])
                    i += 2
                i += 1
            path.setFillRule(Qt.OddEvenFill if d.get("fill") == "oddeven" else Qt.WindingFill)
        except (OSError, ValueError, KeyError, IndexError):
            path = QPainterPath()
            path.addText(0, 0, logo_font(26), APP_TITLE)
        _logo_cache = path
    return QPainterPath(_logo_cache)


# ------------------------------------------------------------------ pintura
def paint_background(p: QPainter, r: QRectF) -> None:
    """Fundo do programa: grafite quente em faixas diagonais + dois brilhos muito suaves."""
    g = QLinearGradient(r.topLeft(), QPointF(r.left() + r.width(), r.top() + r.width() * 0.40))
    for pos, col in BG_STOPS:
        g.setColorAt(pos, QColor(col))
    p.fillRect(r, g)
    rg = QRadialGradient(QPointF(r.left(), r.top()), max(r.width(), r.height()) * 0.55)
    rg.setColorAt(0.0, rgba(QColor("#603428"), 0.16))
    rg.setColorAt(1.0, rgba(QColor("#603428"), 0.0))
    p.fillRect(r, rg)
    rg2 = QRadialGradient(QPointF(r.right(), r.bottom()), max(r.width(), r.height()) * 0.60)
    rg2.setColorAt(0.0, rgba(QColor("#604832"), 0.12))
    rg2.setColorAt(1.0, rgba(QColor("#604832"), 0.0))
    p.fillRect(r, rg2)


def paint_sidebar(p: QPainter, r: QRectF) -> None:
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    for pos, col in SIDEBAR_STOPS:
        g.setColorAt(pos, QColor(col))
    p.fillRect(r, g)
    p.setPen(QPen(rgba(QColor("#ffe6c8"), 0.07), 1))
    p.drawLine(QPointF(r.right() - 0.5, r.top()), QPointF(r.right() - 0.5, r.bottom()))


def paint_glass(p: QPainter, r: QRectF, radius: float = 12, strength: float = 1.0, hover: bool = False) -> None:
    """Placa de 'vidro quente': creme translúcido, borda fina e brilho de 1 px no topo."""
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    k = 1.35 if hover else 1.0
    g.setColorAt(0.0, QColor(255, 236, 210, int(17 * strength * k)))
    g.setColorAt(1.0, QColor(255, 236, 210, int(8 * strength * k)))
    p.fillPath(path, g)
    p.setPen(QPen(QColor(255, 230, 200, int(22 * strength * (1.3 if hover else 1))), 1))
    p.setBrush(Qt.NoBrush)
    p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
    p.setPen(QPen(QColor(255, 240, 220, int(24 * strength)), 1))
    p.drawLine(QPointF(r.left() + radius, r.top() + 1), QPointF(r.right() - radius, r.top() + 1))


def paint_button(p: QPainter, r: QRectF, radius: float = 10, pressed: bool = False) -> None:
    path = QPainterPath()
    path.addRoundedRect(r, radius, radius)
    g = QLinearGradient(r.topLeft(), r.bottomLeft())
    g.setColorAt(0.0, BTN_TOP.darker(104) if pressed else BTN_TOP)
    g.setColorAt(1.0, BTN_BOTTOM.darker(104) if pressed else BTN_BOTTOM)
    p.fillPath(path, g)


# ------------------------------------------------------------------ estilo global
def palette() -> QPalette:
    pal = QPalette()
    for role, color in {
        QPalette.Window: "#16120f", QPalette.WindowText: TEXT.name(), QPalette.Base: FIELD.name(),
        QPalette.AlternateBase: "#221c17", QPalette.ToolTipBase: "#2a211b", QPalette.ToolTipText: TEXT.name(),
        QPalette.Text: TEXT.name(), QPalette.Button: "#2a221c", QPalette.ButtonText: TEXT.name(),
        QPalette.Highlight: "#5a4030", QPalette.HighlightedText: "#fff6e8", QPalette.PlaceholderText: FAINT.name(),
        QPalette.Link: LINK.name(), QPalette.BrightText: "#ffffff",
    }.items():
        pal.setColor(role, QColor(color))
    return pal


def stylesheet() -> str:
    t, m, f, l = TEXT.name(), MUTED.name(), FAINT.name(), LINK.name()
    seta = (Path(__file__).resolve().parent / "recursos" / "seta.png").as_posix()
    return f"""
* {{ font-family: "{UI_FAMILY}"; font-weight: 600; }}
QWidget {{ color: {t}; }}
QToolTip {{ background: #2a211b; color: {t}; border: 1px solid #4a3a2e; padding: 6px 8px; border-radius: 6px; }}
QDialog, QMessageBox, QInputDialog {{ background: {DIALOG.name()}; }}
QLabel {{ background: transparent; }}
QLineEdit, QPlainTextEdit, QTextEdit {{
    background: rgba(255,236,210,0.045); border: 1px solid rgba(255,230,200,0.10); border-radius: 9px;
    padding: 4px 11px; min-height: 28px; color: {t}; selection-background-color: #6a4c38; }}
QLineEdit:focus, QPlainTextEdit:focus {{ border-color: rgba(227,207,169,0.55); }}
QComboBox {{ background: rgba(255,236,210,0.05); border: 1px solid rgba(255,230,200,0.10); border-radius: 9px;
    padding: 4px 30px 4px 11px; min-height: 28px; color: {t}; }}
QComboBox:hover {{ border-color: rgba(255,230,200,0.22); }}
QComboBox::drop-down {{ border: none; width: 30px; subcontrol-origin: padding; subcontrol-position: center right; }}
QComboBox::down-arrow {{ image: url({seta}); width: 12px; height: 12px; margin-right: 10px; }}
QComboBox::down-arrow:on {{ top: 1px; }}
QComboBox QAbstractItemView {{ background: #221b16; border: 1px solid #3d3027; selection-background-color: #4a3628;
    color: {t}; outline: none; padding: 4px; }}
QPushButton {{ background: rgba(255,236,210,0.06); border: 1px solid rgba(255,230,200,0.12); border-radius: 9px;
    padding: 7px 14px; color: {t}; }}
QPushButton:hover {{ background: rgba(255,236,210,0.11); }}
QPushButton:pressed {{ background: rgba(255,236,210,0.04); }}
QPushButton:disabled {{ color: {f}; }}
QPushButton[primary="true"] {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 {BTN_TOP.name()}, stop:1 {BTN_BOTTOM.name()});
    color: {BTN_TEXT.name()}; border: none; padding: 9px 18px; }}
QPushButton[primary="true"]:hover {{ background: qlineargradient(x1:0,y1:0,x2:0,y2:1, stop:0 #f6eddd, stop:1 #e5d6bd); }}
QPushButton[primary="true"]:disabled {{ background: rgba(240,230,212,0.35); color: rgba(38,21,12,0.6); }}
QPushButton[flat="true"] {{ background: transparent; border: none; color: {l}; padding: 4px 6px; }}
QPushButton[flat="true"]:hover {{ color: #f1dcb8; }}
QMenu {{ background: #221b16; border: 1px solid #3d3027; border-radius: 10px; padding: 6px; }}
QMenu::item {{ padding: 7px 22px 7px 14px; border-radius: 6px; color: {t}; }}
QMenu::item:selected {{ background: #3a2c22; }}
QMenu::item:disabled {{ color: {f}; }}
QMenu::separator {{ height: 1px; background: #3a2e25; margin: 5px 8px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,230,200,0.14); border-radius: 3px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,230,200,0.26); }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px 4px; }}
QScrollBar::handle:horizontal {{ background: rgba(255,230,200,0.14); border-radius: 3px; min-width: 40px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: none; }}
QTreeWidget, QListWidget, QListView, QTreeView {{ background: transparent; border: none; outline: none; }}
QTreeWidget::item, QListWidget::item {{ color: {t}; }}
QTreeView::item:selected, QListView::item:selected {{ background: #3a2c22; color: #fff6e8; }}
QCheckBox {{ spacing: 8px; }}
QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; border: 1px solid rgba(255,230,200,0.3);
    background: rgba(255,236,210,0.05); }}
QCheckBox::indicator:checked {{ background: {HILITE.name()}; border-color: {HILITE.name()}; }}
QProgressBar {{ background: rgba(255,236,210,0.06); border: none; border-radius: 3px; height: 6px; }}
QProgressBar::chunk {{ background: {HILITE.name()}; border-radius: 3px; }}
QStatusBar {{ background: transparent; color: {m}; }}
QStatusBar QLabel {{ color: {m}; }}
QStatusBar::item {{ border: none; }}
QSplitter::handle {{ background: transparent; }}
QSlider::groove:horizontal {{ height: 4px; background: rgba(255,230,200,0.12); border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 14px; margin: -6px 0; border-radius: 7px; background: {HILITE.name()}; }}
QDialogButtonBox QPushButton {{ min-width: 84px; }}
QHeaderView::section {{ background: transparent; color: {m}; border: none; }}
"""
