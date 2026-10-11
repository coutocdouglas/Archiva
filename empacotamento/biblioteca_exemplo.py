"""Cria uma biblioteca de exemplo (prévias desenhadas + compactados e pastas) para gravar os tutoriais.

Uso:  python empacotamento/biblioteca_exemplo.py <pasta_destino>
"""
from __future__ import annotations

import os
import random
import shutil
import sys
import zipfile

from PIL import Image, ImageDraw, ImageFilter

S = 1200            # desenha grande e reduz (bordas suaves)
OUT = 600

FUNDOS = [(236, 228, 214), (225, 230, 222), (240, 226, 216), (228, 226, 232), (232, 232, 228), (222, 228, 232),
          (244, 236, 222), (230, 220, 210)]
CORES = [(122, 47, 58), (138, 90, 60), (95, 107, 67), (63, 95, 110), (176, 148, 108), (70, 62, 56),
         (196, 120, 84), (150, 160, 140), (110, 84, 120), (210, 196, 170), (60, 72, 88), (168, 70, 52)]
MADEIRA = [(120, 82, 52), (150, 108, 70), (92, 64, 44), (176, 136, 96), (40, 34, 30)]


def shade(c, k):
    return tuple(max(0, min(255, int(v * k))) for v in c)


def base(bg):
    im = Image.new("RGB", (S, S), bg)
    d = ImageDraw.Draw(im)
    for y in range(S):            # leve degradê vertical
        t = y / S
        d.line((0, y, S, y), fill=shade(bg, 1.03 - 0.07 * t))
    return im


def shadow(im, box, blur=40, alpha=90):
    sh = Image.new("L", im.size, 0)
    ImageDraw.Draw(sh).ellipse(box, fill=alpha)
    sh = sh.filter(ImageFilter.GaussianBlur(blur))
    dark = Image.new("RGB", im.size, (0, 0, 0))
    im.paste(dark, (0, 0), sh)


def rr(d, box, r, fill):
    d.rounded_rectangle(box, r, fill=fill)


def mesa(rng):
    bg = rng.choice(FUNDOS)
    im = base(bg)
    wood = rng.choice(MADEIRA)
    shadow(im, (220, 860, 980, 960))
    d = ImageDraw.Draw(im)
    if rng.random() < 0.5:
        rr(d, (200, 520, 1000, 570), 14, wood)
        rr(d, (200, 560, 1000, 585), 10, shade(wood, 0.75))
        for x in (250, 920):
            rr(d, (x, 585, x + 34, 900), 10, shade(wood, 0.8))
    else:
        d.ellipse((260, 470, 940, 600), fill=wood)
        d.ellipse((260, 500, 940, 620), fill=shade(wood, 0.75))
        d.ellipse((260, 470, 940, 590), fill=wood)
        rr(d, (580, 600, 620, 860), 12, shade(wood, 0.7))
        d.ellipse((470, 850, 730, 900), fill=shade(wood, 0.6))
    return im


def cadeira(rng):
    im = base(rng.choice(FUNDOS))
    c = rng.choice(CORES)
    wood = rng.choice(MADEIRA)
    shadow(im, (330, 870, 870, 950))
    d = ImageDraw.Draw(im)
    rr(d, (420, 230, 790, 560), 60, shade(c, 0.85))
    rr(d, (360, 540, 840, 640), 40, c)
    rr(d, (360, 610, 840, 650), 20, shade(c, 0.7))
    for x0, x1 in ((390, 430), (770, 810)):
        d.polygon([(x0, 650), (x1, 650), (x1 - 10, 900), (x0 - 20, 900)], fill=wood)
    return im


def poltrona(rng):
    im = base(rng.choice(FUNDOS))
    c = rng.choice(CORES)
    shadow(im, (230, 860, 970, 960))
    d = ImageDraw.Draw(im)
    rr(d, (300, 300, 900, 700), 120, shade(c, 0.82))
    rr(d, (220, 480, 400, 820), 80, c)
    rr(d, (800, 480, 980, 820), 80, c)
    rr(d, (360, 600, 840, 820), 60, shade(c, 1.08))
    for x in (290, 880):
        rr(d, (x, 820, x + 26, 900), 8, rng.choice(MADEIRA))
    return im


def sofa(rng):
    im = base(rng.choice(FUNDOS))
    c = rng.choice(CORES)
    shadow(im, (120, 830, 1080, 940))
    d = ImageDraw.Draw(im)
    rr(d, (170, 400, 1030, 700), 70, shade(c, 0.82))
    rr(d, (110, 560, 260, 830), 60, c)
    rr(d, (940, 560, 1090, 830), 60, c)
    rr(d, (240, 640, 600, 800), 40, shade(c, 1.07))
    rr(d, (600, 640, 960, 800), 40, shade(c, 1.03))
    for x in (180, 1000):
        rr(d, (x, 820, x + 22, 880), 8, (40, 34, 30))
    return im


def luminaria(rng):
    im = base(rng.choice(FUNDOS))
    c = rng.choice(CORES + [(230, 214, 180)])
    d = ImageDraw.Draw(im)
    if rng.random() < 0.55:      # pendente
        d.line((600, 0, 600, 420), fill=(40, 34, 30), width=8)
        glow = Image.new("L", im.size, 0)
        ImageDraw.Draw(glow).ellipse((380, 560, 820, 760), fill=120)
        glow = glow.filter(ImageFilter.GaussianBlur(60))
        im.paste(Image.new("RGB", im.size, (255, 236, 190)), (0, 0), glow)
        d = ImageDraw.Draw(im)
        d.pieslice((330, 380, 870, 900), 180, 360, fill=c)
        d.rectangle((330, 638, 870, 650), fill=shade(c, 0.7))
        d.ellipse((560, 630, 640, 690), fill=(255, 240, 200))
    else:                        # de piso
        shadow(im, (420, 900, 780, 960), 30)
        d = ImageDraw.Draw(im)
        d.ellipse((470, 890, 730, 940), fill=(40, 34, 30))
        d.line((600, 910, 600, 360), fill=(40, 34, 30), width=12)
        d.polygon([(470, 200), (730, 200), (800, 400), (400, 400)], fill=c)
        d.polygon([(400, 400), (800, 400), (790, 415), (410, 415)], fill=shade(c, 0.7))
    return im


def vaso(rng):
    im = base(rng.choice(FUNDOS))
    c = rng.choice(CORES)
    shadow(im, (380, 870, 820, 950), 30)
    d = ImageDraw.Draw(im)
    green = rng.choice([(78, 104, 64), (96, 122, 74), (60, 88, 60)])
    for k in range(9):          # folhas
        a = -1.2 + k * 0.3
        import math
        x, y = 600 + math.sin(a) * 320, 470 - math.cos(a) * 300
        d.line((600, 520, x, y), fill=shade(green, 0.8), width=10)
        d.ellipse((x - 70, y - 30, x + 70, y + 30), fill=green)
    pts = [(470, 500), (730, 500), (790, 650), (740, 900), (460, 900), (410, 650)]
    d.polygon(pts, fill=c)
    d.polygon([(470, 500), (560, 500), (520, 650), (500, 900), (460, 900), (410, 650)], fill=shade(c, 1.12))
    d.rectangle((460, 490, 740, 515), fill=shade(c, 0.8))
    return im


def adorno(rng):
    im = base(rng.choice(FUNDOS))
    c = rng.choice(CORES)
    shadow(im, (360, 860, 840, 940), 30)
    d = ImageDraw.Draw(im)
    kind = rng.randrange(3)
    if kind == 0:
        for i, (x, r) in enumerate(((470, 160), (700, 120), (600, 90))):
            y = 860 - r
            d.ellipse((x - r, y - r, x + r, y + r), fill=shade(c, 0.85 + 0.12 * i))
    elif kind == 1:
        rr(d, (520, 380, 680, 880), 70, c)
        d.ellipse((490, 270, 710, 470), fill=shade(c, 1.1))
    else:
        d.polygon([(600, 260), (820, 880), (380, 880)], fill=c)
        d.polygon([(600, 260), (600, 880), (380, 880)], fill=shade(c, 1.12))
    return im


CATS = [("MESAS", "MESA", mesa, 12), ("CADEIRAS", "CADEIRA", cadeira, 14), ("POLTRONAS", "POLTRONA", poltrona, 8),
        ("SOFAS", "SOFA", sofa, 8), ("LUMINARIAS", "LUMINARIA", luminaria, 10), ("VASOS", "VASO", vaso, 10),
        ("ADORNOS", "ADORNO", adorno, 12)]


def save(im, path):
    im.resize((OUT, OUT), Image.LANCZOS).save(path, quality=88)


def model_files(folder, name, rng):
    os.makedirs(os.path.join(folder, "MAPS"), exist_ok=True)
    open(os.path.join(folder, f"{name}_Corona.max"), "w").write("max")
    for t in ("diffuse", "roughness", "normal")[: rng.randrange(1, 4)]:
        open(os.path.join(folder, "MAPS", f"{name.lower().replace(' ', '_')}_{t}.jpg"), "w").write(t)


def main(dest):
    rng = random.Random(7)
    os.makedirs(dest, exist_ok=True)
    for cat, pref, fn, n in CATS:
        cdir = os.path.join(dest, cat)
        os.makedirs(cdir, exist_ok=True)
        for i in range(1, n + 1):
            name = f"{pref} {i:02d}"
            save(fn(rng), os.path.join(cdir, name + ".jpg"))
            if rng.random() < 0.45:              # pasta pronta
                d = os.path.join(cdir, name)
                model_files(d, name.title().replace(" ", "_"), rng)
                shutil.copy(os.path.join(cdir, name + ".jpg"), os.path.join(d, f"{name.title().replace(' ', '_')}_Corona.jpg"))
            else:                                 # compactado
                with zipfile.ZipFile(os.path.join(cdir, name + ".zip"), "w") as z:
                    z.writestr(f"{name}/{name.title().replace(' ', '_')}_Corona.max", "max")
                    z.writestr(f"{name}/maps/textura_{i}.jpg", "jpg")
    ent = os.path.join(dest, "_ENTRADA")
    os.makedirs(ent, exist_ok=True)
    for nome, fn in (("Vaso_Ceramica_Alto", vaso), ("Pendente_Arco_Linho", luminaria), ("Poltrona_Bouclé", poltrona)):
        save(fn(rng), os.path.join(ent, nome + ".jpg"))
        with zipfile.ZipFile(os.path.join(ent, nome + ".zip"), "w") as z:
            z.writestr(f"{nome}/{nome}.max", "max")
            z.writestr(f"{nome}/tex/{nome}_diff.jpg", "jpg")
    print("biblioteca de exemplo criada em", dest)


if __name__ == "__main__":
    main(os.path.abspath(sys.argv[1]))
