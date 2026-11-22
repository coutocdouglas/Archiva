"""Capa tirada do PDF: fica só a foto da página, sem o título ("Plant Models Vol32"), o logotipo e a margem.

As primeiras páginas dos PDFs da Maxtree são uma folha clara com um título no alto, uma foto grande no meio e o
logotipo embaixo. O recorte procura o maior bloco "cheio" da página: as linhas em que quase toda a largura
não é a cor do fundo (a foto ocupa a largura toda; o título e o logotipo ocupam pouco) e, nessas linhas, as
colunas cheias. Se não achar um bloco claro (página que já é uma foto inteira, ou layout diferente), devolve a
página como estava. Só usa QImage."""
from __future__ import annotations

from PySide6.QtCore import QRect
from PySide6.QtGui import QImage

AMOSTRA = 360            # largura da cópia pequena usada para medir
CHEIA = 0.6              # fração da largura (ou altura) que precisa ser "não fundo"
TOLERANCIA = 14          # diferença máxima (por canal) para um pixel contar como fundo
FOLGA = 2                # linhas/colunas "vazias" toleradas dentro do bloco (fios claros na foto)


def _fundo(small: QImage) -> tuple[int, int, int]:
    """A cor do fundo: a mais comum na borda da página."""
    w, h = small.width(), small.height()
    cont: dict[tuple[int, int, int], int] = {}
    pts = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)] + [(0, y) for y in range(h)] + \
          [(w - 1, y) for y in range(h)]
    for x, y in pts:
        c = small.pixelColor(x, y)
        k = (c.red() // 8, c.green() // 8, c.blue() // 8)
        cont[k] = cont.get(k, 0) + 1
    k = max(cont, key=cont.get)
    return k[0] * 8 + 4, k[1] * 8 + 4, k[2] * 8 + 4


def _maior_trecho(flags: list[bool]) -> tuple[int, int]:
    """O maior trecho de True (aceitando FOLGA falsos no meio). Devolve (início, fim exclusivo)."""
    best = (0, 0)
    i, n = 0, len(flags)
    while i < n:
        if not flags[i]:
            i += 1
            continue
        start, j, last = i, i, i
        gap = 0
        while j < n:
            if flags[j]:
                last, gap = j, 0
            else:
                gap += 1
                if gap > FOLGA:
                    break
            j += 1
        if last + 1 - start > best[1] - best[0]:
            best = (start, last + 1)
        i = last + 1
    return best


def area_da_foto(img: QImage) -> QRect | None:
    """O retângulo da foto na página (em pixels de img), ou None se não houver um bloco claro."""
    if img.isNull() or img.width() < 50 or img.height() < 50:
        return None
    small = img.scaledToWidth(AMOSTRA).convertToFormat(QImage.Format_RGB32)
    w, h = small.width(), small.height()
    br, bg, bb = _fundo(small)
    cheio = [[False] * w for _ in range(h)]
    for y in range(h):
        row = cheio[y]
        for x in range(w):
            c = small.pixelColor(x, y)
            row[x] = abs(c.red() - br) > TOLERANCIA or abs(c.green() - bg) > TOLERANCIA or abs(c.blue() - bb) > TOLERANCIA
    linhas = [sum(r) >= CHEIA * w for r in cheio]
    y0, y1 = _maior_trecho(linhas)
    if y1 - y0 < h * 0.2:
        return None
    cols = [sum(cheio[y][x] for y in range(y0, y1)) >= CHEIA * (y1 - y0) for x in range(w)]
    x0, x1 = _maior_trecho(cols)
    if x1 - x0 < w * 0.3:
        return None
    # céu muito claro no alto da foto não conta como "cheio": estende enquanto a linha tem foto nas DUAS bordas
    # (o título e o logotipo encostam só numa)
    borda = max(2, (x1 - x0) // 30)

    def nas_bordas(y):
        r = cheio[y]
        return any(r[x0:x0 + borda]) and any(r[x1 - borda:x1])
    while y0 > 0 and nas_bordas(y0 - 1):
        y0 -= 1
    while y1 < h and nas_bordas(y1):
        y1 += 1
    if (x1 - x0) * (y1 - y0) > 0.95 * w * h:      # a página já é a foto: nada a cortar
        return None
    s = img.width() / w
    m = 1          # um pixel para dentro (a borda da foto costuma vir misturada com o fundo)
    left, top = int(x0 * s) + m, int(y0 * s) + m
    right, bottom = min(img.width(), int(x1 * s)) - m, min(img.height(), int(y1 * s)) - m
    return QRect(left, top, right - left, bottom - top)


def so_a_foto(img: QImage) -> QImage:
    """A página recortada na foto; a própria página se não houver o que recortar."""
    r = area_da_foto(img)
    return img.copy(r) if r is not None else img
