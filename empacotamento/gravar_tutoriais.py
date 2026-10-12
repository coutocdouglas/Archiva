"""Grava as animações dos tutoriais usando o próprio Archiva (sem tela, numa cópia de biblioteca de exemplo).

Uso (Linux ou Windows):
    QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2 python empacotamento/gravar_tutoriais.py <biblioteca_de_exemplo> [ids...]

A biblioteca de exemplo é COPIADA para uma pasta temporária (a original não é alterada). Ela precisa ter
algumas categorias com itens compactados (.zip), pastas prontas e uma pasta _ENTRADA com um download.
As animações (.webp) vão para app/recursos/tutoriais.
"""
from __future__ import annotations

import io
import json
import math
import os
import shutil
import sys
import tempfile
import time
import uuid

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
SRC_LIB = os.path.abspath(sys.argv[1])
ONLY = set(sys.argv[2:])
ALL = ["inicio", "buscar", "arrastar", "extrair", "organizar", "entrada", "tags", "equipe", "historico", "atualizar",
       "colecoes", "atalhos"]
if not ONLY:      # cada animação num processo separado (programa limpo a cada gravação)
    import subprocess
    for name in ALL:
        subprocess.run([sys.executable, os.path.abspath(__file__), SRC_LIB, name])
    sys.exit(0)
OUT = os.path.join(ROOT, "app", "recursos", "tutoriais")
os.makedirs(OUT, exist_ok=True)

TMP = tempfile.mkdtemp(prefix="archiva_tut_")
LIB = os.path.join(TMP, "MODELOS")
shutil.copytree(SRC_LIB, LIB, ignore=shutil.ignore_patterns("_ARCHIVA"))
os.environ["APPDATA"] = os.path.join(TMP, "ad")
os.environ["LOCALAPPDATA"] = os.path.join(TMP, "lad")

from PIL import Image, ImageDraw, ImageFilter  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice, QPoint, Qt  # noqa: E402,F401
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from app.config import Config  # noqa: E402
from app import perfil  # noqa: E402

perfil.save({"id": uuid.uuid4().hex, "nome": "Marina", "cor": "#5f6b43", "foto": False})
c = Config()
from app.config import version  # noqa: E402
c.values.update(library_root=LIB, tutorial_off=True, versao_vista=version(), check_updates=False)
c.save()

app = QApplication(sys.argv)
app.setStyle("Fusion")
from app import theme  # noqa: E402
theme.load_fonts()
app.setFont(theme.ui_font(10))
app.setPalette(theme.palette())
app.setStyleSheet(theme.stylesheet())
import app.main_window as M  # noqa: E402
import app.entrada_page as EP  # noqa: E402

QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: None)
M.ReviewDialog.exec = lambda self: None
EP.DuplicateDialog.exec = lambda self: setattr(self, "choice", EP.DuplicateDialog.KEEP_BOTH)

W, H = 1440, 900
OUT_W, OUT_H = 1280, 800
w = M.MainWindow()
w._update_footer = lambda: w.sidebar.footer.setText(f"\\\\SERVIDOR\\MODELOS<br>versão {version()}")
w.resize(W, H)
w.show()


def wait(ms):
    QTest.qWait(ms)


while not w.all_assets:
    wait(200)
wait(800)
w._update_footer()
w.statusBar().clearMessage()


# ------------------------------------------------------------------ gravação
def qimg_to_pil(img):
    buf = QBuffer()
    buf.open(QIODevice.ReadWrite)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGB")


def _cursor_img(scale):
    s = 22 * scale
    im = Image.new("RGBA", (int(s * 1.2), int(s * 1.4)), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    pts = [(0, 0), (0, 17), (4.5, 13), (7.5, 20), (10.5, 18.8), (7.6, 12), (13, 12)]
    pts = [(x * scale * 1.15 + 2, y * scale * 1.15 + 2) for x, y in pts]
    sh = Image.new("RGBA", im.size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).polygon([(x + 2, y + 3) for x, y in pts], fill=(0, 0, 0, 110))
    sh = sh.filter(ImageFilter.GaussianBlur(2))
    im = Image.alpha_composite(sh, im)
    d = ImageDraw.Draw(im)
    d.polygon(pts, fill=(255, 255, 255, 255), outline=(20, 14, 10, 255))
    d.line(pts + [pts[0]], fill=(20, 14, 10, 255), width=max(1, int(scale * 1.2)))
    return im


class Film:
    def __init__(self, name):
        self.name = name
        self.frames: list[tuple[Image.Image, int]] = []
        self.base: Image.Image | None = None
        self.scale = None
        self.cur = (W * 0.5, H * 0.6)
        self.overlays = []          # (PIL RGBA, (x, y) em coordenadas da janela)
        self.drag_img = None
        self.key = ""                # tecla mostrada como etiqueta (tutorial de atalhos)

    def snap(self, extra_widgets=()):
        pm = w.grab()
        img = qimg_to_pil(pm.toImage())
        self.scale = img.width / W
        for wid, pos in extra_widgets:          # janelas separadas (menu, diálogo) coladas por cima
            qi = wid.grab().toImage()
            buf = QBuffer()
            buf.open(QIODevice.ReadWrite)
            qi.save(buf, "PNG")
            rgba = Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA")
            sub = Image.new("RGBA", rgba.size, (27, 22, 18, 255))
            sub.alpha_composite(rgba)
            sub = sub.convert("RGB")
            if sub.width != int(wid.width() * self.scale):
                sub = sub.resize((int(wid.width() * self.scale), int(wid.height() * self.scale)), Image.LANCZOS)
            dim = Image.new("RGB", img.size, (8, 6, 4))
            if getattr(wid, "_dim", False):
                img = Image.blend(img, dim, 0.55)
            img.paste(sub, (int(pos[0] * self.scale), int(pos[1] * self.scale)))
        self.base = img
        return self

    def _compose(self, ripple=0.0):
        img = self.base.copy().convert("RGBA")
        s = self.scale
        if self.drag_img is not None:
            di = self.drag_img
            img.alpha_composite(di, (int(self.cur[0] * s - di.width / 2), int(self.cur[1] * s - di.height / 2)))
        if ripple:
            ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            r = (10 + 26 * ripple) * s
            a = int(150 * (1 - ripple))
            cx, cy = self.cur[0] * s, self.cur[1] * s
            d.ellipse((cx - r, cy - r, cx + r, cy + r), outline=(227, 207, 169, a), width=int(3 * s))
            img = Image.alpha_composite(img, ov)
        if self.key:
            from PIL import ImageFont
            fnt = ImageFont.truetype(os.path.join(ROOT, "app", "recursos", "fontes", "ZTNature-SemiBold.ttf"),
                                     int(26 * s))
            tw = ImageDraw.Draw(img).textlength(self.key, font=fnt)
            bw, bh = tw + 56 * s, 64 * s
            x0, y0 = (img.width - bw) / 2, img.height - bh - 48 * s
            ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
            d = ImageDraw.Draw(ov)
            d.rounded_rectangle((x0, y0, x0 + bw, y0 + bh), radius=int(16 * s), fill=(241, 233, 220, 240),
                                outline=(255, 255, 255, 255), width=max(1, int(s)))
            d.text((x0 + 28 * s, y0 + bh / 2), self.key, font=fnt, fill=(38, 21, 12, 255), anchor="lm")
            img = Image.alpha_composite(img, ov)
        cur = _cursor_img(s)
        img.alpha_composite(cur, (int(self.cur[0] * s - 2), int(self.cur[1] * s - 2)))
        return img.convert("RGB").resize((OUT_W, OUT_H), Image.LANCZOS)

    def hold(self, ms):
        self.frames.append((self._compose(), int(ms)))
        return self

    def move(self, to, ms=650):
        x0, y0 = self.cur
        n = max(2, int(ms / 45))
        for i in range(1, n + 1):
            t = i / n
            e = 0.5 - math.cos(math.pi * t) / 2
            self.cur = (x0 + (to[0] - x0) * e, y0 + (to[1] - y0) * e)
            self.frames.append((self._compose(), int(ms / n)))
        return self

    def click(self):
        for k in range(4):
            self.frames.append((self._compose(ripple=(k + 1) / 5), 55))
        return self

    def save(self):
        imgs = [f for f, _ in self.frames]
        durs = [d for _, d in self.frames]
        path = os.path.join(OUT, f"{self.name}.webp")
        imgs[0].save(path, save_all=True, append_images=imgs[1:], duration=durs, loop=0, quality=72, method=4)
        print(f"{self.name}: {len(imgs)} quadros, {sum(durs) / 1000:.1f} s, {os.path.getsize(path) // 1024} KB")


def center(widget, dx=0, dy=0):
    p = widget.mapTo(w, widget.rect().center())
    return (p.x() + dx, p.y() + dy)


def seg_center(seg, idx):
    r = seg._rects()[idx]
    p = seg.mapTo(w, QPoint(int(r.center().x()), int(r.center().y())))
    return (p.x(), p.y())


def card_center(key):
    m = w.grid.model()
    for i in range(m.rowCount()):
        ix = m.index(i, 0)
        if ix.data(M.ASSET_ROLE).key == key:
            w.grid.scrollTo(ix)
            wait(100)
            r = w.grid.visualRect(ix)
            p = w.grid.viewport().mapTo(w, r.center())
            return ix, (p.x(), p.y() - 20)
    raise KeyError(key)


def select_card(key):
    ix, _ = card_center(key)
    w.grid.setCurrentIndex(ix)
    wait(250)


def type_into(film, edit, text, per=110):
    for ch in text:
        edit.setText(edit.text() + ch)
        wait(60)
        film.snap().hold(per)


def _hide_paths(widget):
    for lbl in widget.findChildren(M.QLabel):
        t = lbl.text()
        if TMP in t or TMP.replace("/", "\\") in t:
            lbl.setText(t.replace(LIB, "\\\\SERVIDOR\\MODELOS").replace("/", "\\") if "<" not in t
                        else t.replace(LIB, "\\\\SERVIDOR\\MODELOS"))


def first(pred):
    return next(a for a in w.all_assets if pred(a))


# ------------------------------------------------------------------ roteiros
def f_inicio():
    f = Film("inicio")
    w.tabs.setCurrentWidget(w.tabs.page("inicio"))
    wait(600)
    f.snap().hold(1400)
    f.move(center(w.sidebar.buttons["biblioteca"])).click()
    w.tabs.setCurrentWidget(w.tabs.page("biblioteca"))
    w.open_library("all")
    wait(500)
    f.snap().hold(900)
    item = w._tree_item("CADEIRAS")
    r = w.cat_tree.visualItemRect(item)
    f.move(center(w.cat_tree.viewport(), r.center().x() - w.cat_tree.viewport().width() // 2,
                  r.center().y() - w.cat_tree.viewport().height() // 2)).click()
    w.cat_tree.setCurrentItem(item)
    wait(500)
    f.snap().hold(1800)
    f.save()


def f_buscar():
    f = Film("buscar")
    w.open_library("all")
    wait(400)
    f.snap().hold(700)
    f.move(center(w.search, -60)).click()
    w.search.setFocus()
    type_into(f, w.search, "cadeira")
    wait(500)
    f.snap().hold(1200)
    f.move(seg_center(w.show_filter, 1)).click()
    w.show_filter.setCurrentIndex(1)
    wait(400)
    f.snap().hold(1300)
    f.move(seg_center(w.show_filter, 0)).click()
    w.show_filter.setCurrentIndex(0)
    w.search.clear()
    wait(400)
    f.snap().hold(900)
    f.save()


def f_arrastar():
    f = Film("arrastar")
    w.open_library("ready")
    wait(500)
    a = first(lambda a: a.kind == "folder" and a.preview)
    ix, pos = card_center(a.key)
    f.snap().hold(600)
    f.move(pos).click()
    w.grid.setCurrentIndex(ix)
    wait(300)
    f.snap().hold(400)
    # viewport do 3ds Max entra pela direita (desenho)
    base = f.base.copy()
    s = f.scale
    vx = int(W * 0.56)

    def viewport(img, prog):
        img = img.copy()
        x0 = int((W - (W - vx) * prog) * s)
        d = ImageDraw.Draw(img)
        d.rectangle((x0, 0, img.width, img.height), fill=(58, 58, 60))
        for gx in range(x0, img.width, int(40 * s)):
            d.line((gx, 0, gx, img.height), fill=(68, 68, 70), width=1)
        for gy in range(0, img.height, int(40 * s)):
            d.line((x0, gy, img.width, gy), fill=(68, 68, 70), width=1)
        d.rectangle((x0, 0, img.width, int(34 * s)), fill=(45, 45, 47))
        d.text((x0 + int(14 * s), int(10 * s)), "3ds Max  ·  [ Perspectiva ]", fill=(210, 210, 210))
        return img

    for k in range(1, 7):
        f.base = viewport(base, k / 6)
        f.hold(45)
    f.base = viewport(base, 1)
    pm = w.thumbs.get(a.preview)
    th = qimg_to_pil(pm.toImage()).convert("RGBA")
    th.thumbnail((int(120 * s), int(120 * s)))
    alpha = Image.new("L", th.size, 200)
    th.putalpha(alpha)
    f.drag_img = th
    f.move((vx + (W - vx) / 2, H * 0.55), 1100)
    f.hold(250)
    f.drag_img = None
    # modelo "aparece" na viewport
    drop = th.copy()
    drop.putalpha(255)
    f.base.paste(drop.convert("RGB"), (int((vx + (W - vx) / 2) * s - drop.width / 2),
                                         int(H * 0.55 * s - drop.height / 2)))
    f.click().hold(1600)
    f.save()


def f_extrair():
    f = Film("extrair")
    a = first(lambda a: a.kind == "archive" and a.archive and a.archive.lower().endswith(".zip"))
    w.open_library("archive", cat_key=a.category.split("/")[0])
    wait(500)
    ix, pos = card_center(a.key)
    f.snap().hold(700)
    f.move(pos).click()
    w.grid.setCurrentIndex(ix)
    wait(400)
    f.snap().hold(800)
    f.move(center(w.details.btn_prepare)).click()
    w.details.btn_prepare.click()
    wait(150)
    f.snap().hold(500)
    t0 = time.time()
    while w.extractions.busy() and time.time() - t0 < 30:
        wait(200)
        f.snap().hold(200)
    wait(800)
    w.show_filter.setCurrentIndex(0)
    wait(300)
    try:
        ix, pos2 = card_center(a.key)
        w.grid.setCurrentIndex(ix)
    except KeyError:
        pass
    wait(400)
    f.snap().hold(1800)
    f.save()


def _make_messy():
    cat = os.path.join(LIB, "ADORNOS")
    src = first(lambda a: a.category == "ADORNOS" and a.preview).preview
    d = os.path.join(cat, "ADORNO 950")
    os.makedirs(os.path.join(d, "Vaso Ceramica", "textures", "4k"), exist_ok=True)
    open(os.path.join(d, "Vaso Ceramica", "Vaso_Ceramica_corona.max"), "w").write("max")
    for n in ("diffuse.jpg", "bump.jpg"):
        open(os.path.join(d, "Vaso Ceramica", "textures", n), "w").write(n)
    open(os.path.join(d, "Vaso Ceramica", "textures", "4k", "rough.png"), "w").write("r")
    shutil.copy(src, os.path.join(cat, "ADORNO 950" + os.path.splitext(src)[1]))
    w.refresh_category("ADORNOS")


def f_organizar():
    _make_messy()
    f = Film("organizar")
    w.open_library("all", cat_key="ADORNOS")
    wait(400)
    f.snap().hold(600)
    f.move(seg_center(w.show_filter, 3)).click()
    w.show_filter.setCurrentIndex(3)
    wait(400)
    f.snap().hold(800)
    ix, pos = card_center("ADORNOS/ADORNO 950")
    f.move(pos).click()
    w.grid.setCurrentIndex(ix)
    wait(400)
    f.snap().hold(1200)
    f.move(center(w.details.btn_organize)).click()
    w.details.btn_organize.click()
    t0 = time.time()
    while w.extractions.busy() and time.time() - t0 < 20:
        wait(150)
    wait(600)
    w.show_filter.setCurrentIndex(0)
    wait(300)
    ix, pos = card_center("ADORNOS/ADORNO 950")
    w.grid.setCurrentIndex(ix)
    wait(400)
    f.snap().hold(2000)
    f.save()


def f_entrada():
    f = Film("entrada")
    e = w.entrada
    w.open_library("all")
    wait(300)
    f.snap().hold(500)
    f.move(center(w.sidebar.buttons["entrada"]), 600).click()
    w.tabs.setCurrentWidget(e)
    e.refresh()
    wait(700)
    _hide_paths(e)
    f.snap().hold(800)
    m = e.grid.model()
    target = None
    for i in range(m.rowCount()):
        a = m.index(i, 0).data(M.ASSET_ROLE)
        if a and a.kind == "archive" and "Pendente" in a.name:
            target = (m.index(i, 0), a)
            break
    ix, a = target
    r = e.grid.visualRect(ix)
    p = e.grid.viewport().mapTo(w, r.center())
    f.move((p.x(), p.y() - 20)).click()
    e.grid.setCurrentIndex(ix)
    wait(400)
    f.snap().hold(700)
    f.move(center(e.cat)).click()
    e.cat.setCurrentIndex(e.cat.findData("LUMINARIAS"))
    wait(500)
    f.snap().hold(1500)
    f.move(center(e.btn)).click()
    e.classify()
    wait(800)
    _hide_paths(e)
    f.snap().hold(1800)
    f.save()


def f_tags():
    f = Film("tags")
    w.open_library("all", cat_key="ADORNOS")
    wait(400)
    a = [x for x in w.all_assets if x.category == "ADORNOS" and x.preview][:2]
    ix, pos = card_center(a[0].key)
    f.snap().hold(600)
    f.move(pos).click()
    w.grid.setCurrentIndex(ix)
    wait(400)
    f.snap().hold(600)
    f.move(center(w.details.tag_input, -80)).click()
    w.details.tag_input.setFocus()
    type_into(f, w.details.tag_input, "cerâmica", 90)
    w.details._add()
    wait(300)
    f.snap().hold(400)
    type_into(f, w.details.tag_input, "sala", 90)
    w.details._add()
    wait(300)
    f.snap().hold(1000)
    f.move(center(w.sidebar.buttons["tags"])).click()
    w.tabs.setCurrentWidget(w.tabs.page("tags"))
    try:
        w.tags_page.refresh()
    except Exception:  # noqa: BLE001
        pass
    wait(700)
    f.snap().hold(1800)
    f.save()


def f_equipe():
    f = Film("equipe")
    w.open_library("all", cat_key="ADORNOS")
    wait(400)
    a = [x for x in w.all_assets if x.category == "ADORNOS" and x.preview][1]
    lib = w.shared.lib
    import hashlib
    h = hashlib.sha1(a.key.casefold().encode()).hexdigest()[:20]
    json.dump({"key": a.key, "u": "outra", "nome": "Bruno", "pc": "CASA DIGITAL 02", "op": "organizando",
               "t": time.time()}, open(os.path.join(lib.root, "travas", h + ".lock"), "w"))
    w.shared.poll_locks()
    wait(400)
    ix, pos = card_center(a.key)
    f.snap().hold(1200)
    f.move(pos).click()
    w.grid.setCurrentIndex(ix)
    wait(400)
    f.snap().hold(1800)
    f.move(center(w.user_chip, -40)).click()
    m = M.QMenu(w)
    m.addAction("Editar perfil…")
    m.addSeparator()
    m.addAction("Minhas alterações…")
    m.addAction("Histórico de todos…")
    m.addAction("Pessoas e administradores…")
    m.show()
    wait(200)
    cp = w.user_chip.mapTo(w, QPoint(8, 0))
    f.snap([(m, (cp.x(), cp.y() - m.height() - 4))]).hold(2000)
    m.close()
    os.remove(os.path.join(lib.root, "travas", h + ".lock"))
    w.shared.poll_locks()
    f.save()


def f_historico():
    from app.historico import HistoryDialog
    _make_messy()
    w.request_organize([first(lambda a: a.key == "ADORNOS/ADORNO 950")])
    t0 = time.time()
    while w.extractions.busy() and time.time() - t0 < 20:
        wait(150)
    wait(500)
    a = first(lambda a: a.kind == "archive" and a.archive and a.archive.lower().endswith(".zip"))
    w.request_extraction([a])
    t0 = time.time()
    while w.extractions.busy() and time.time() - t0 < 20:
        wait(150)
    wait(500)
    f = Film("historico")
    w.open_library("all")
    wait(300)
    f.snap().hold(500)
    f.move(center(w.user_chip, -40)).click()
    d = HistoryDialog(w, False)
    d.resize(760, 600)
    d._dim = True
    d.show()
    wait(500)
    pos = ((W - d.width()) // 2, (H - d.height()) // 2)
    f.snap([(d, pos)]).hold(1500)
    btns = [b for b in d.findChildren(M.QPushButton) if b.text() == "Desfazer" and b.isEnabled()]
    if btns:
        b = btns[0]
        bp = b.mapTo(d, b.rect().center())
        f.move((pos[0] + bp.x(), pos[1] + bp.y())).click()
        f.hold(500)
        row = b.parent()
        while row is not None and not hasattr(row, "ev"):
            row = row.parent()
        if row is not None:
            w.shared.undo(row.ev)
            d.reload()
            wait(400)
            f.snap([(d, pos)]).hold(2000)
    d.close()
    f.save()


def f_atualizar():
    f = Film("atualizar")
    w.open_library("all")
    wait(300)
    w._update_found("1.0.0", "", "Novidades", True)
    wait(300)
    f.snap().hold(1200)
    f.move(center(w.update_btn)).click()
    w.update_btn.setText("Baixando…")
    w.update_btn.setEnabled(False)
    w.progress.setRange(0, 100)
    w.progress.show()
    for v in range(0, 101, 10):
        w.progress.setValue(v)
        wait(40)
        f.snap().hold(160)
    w.update_btn.setText("Instalando…")
    wait(100)
    f.snap().hold(1500)
    w.progress.hide()
    w.update_notice.hide()
    f.save()


def _menu_snap(f, items, anchor_widget, below=True):
    m = M.QMenu(w)
    for t in items:
        m.addSeparator() if t == "-" else m.addAction(t)
    m.show()
    wait(150)
    p = anchor_widget.mapTo(w, QPoint(0, anchor_widget.height() + 4 if below else -m.height() - 4))
    f.snap([(m, (p.x(), p.y()))])
    pos = (p.x(), p.y())
    m.close()
    return pos, m


def f_colecoes():
    uid = w.profile["id"]
    sofas = [a for a in w.all_assets if a.category == "SOFAS"]
    ready = [a for a in w.all_assets if a.kind == "folder"][:6]
    for a in ready:
        w.db.record_use(a.key)
    w.db.create_collection("c1", "Apartamento Silva – Sala", uid)
    w.db.add_to_collection("c1", [sofas[1].key, sofas[2].key], uid)
    w.db.create_collection("c2", "Casa de Campo – Varanda", uid)
    w.db.add_to_collection("c2", [a.key for a in w.all_assets if a.category == "POLTRONAS"][:3], uid)
    f = Film("colecoes")
    w.open_library("all", cat_key="SOFAS")
    wait(400)
    ix, pos = card_center(sofas[0].key)
    f.snap().hold(500)
    f.move(pos).click()
    w.grid.setCurrentIndex(ix)
    wait(400)
    f.snap().hold(600)
    f.move(center(w.details.col_btn)).click()
    mpos, m = _menu_snap(f, ["Apartamento Silva – Sala", "Casa de Campo – Varanda", "-", "Nova coleção…"],
                         w.details.col_btn)
    f.hold(500)
    f.move((mpos[0] + 60, mpos[1] + 16)).click()
    w.colecoes.add_items("c1", [sofas[0].key])
    wait(300)
    f.snap().hold(700)
    f.move(center(w.sidebar.buttons["colecoes"])).click()
    w.tabs.setCurrentWidget(w.tabs.page("colecoes"))
    w.colecoes.refresh()
    wait(600)
    f.snap().hold(1000)
    r = w.colecoes.view.visualRect(w.colecoes.model.index(0))
    p = w.colecoes.view.viewport().mapTo(w, r.center())
    f.move((p.x(), p.y())).click()
    w.colecoes.open("c1")
    wait(600)
    f.snap().hold(900)
    for i in range(2):
        it = w.colecoes.recent.item(i)
        rr = w.colecoes.recent.visualItemRect(it)
        q = w.colecoes.recent.viewport().mapTo(w, rr.topLeft())
        f.move((q.x() + 12, q.y() + rr.height() // 2), 450).click()
        it.setCheckState(Qt.Checked)
        wait(150)
        f.snap().hold(250)
    f.move(center(w.colecoes.btn_add_recent)).click()
    w.colecoes._add_recent()
    wait(500)
    f.snap().hold(1800)
    f.save()


def f_atalhos():
    f = Film("atalhos")
    w.open_library("all", cat_key="POLTRONAS")
    wait(400)
    a = [x for x in w.all_assets if x.category == "POLTRONAS"][1]
    ix, pos = card_center(a.key)
    f.snap().hold(500)
    f.move(pos).click()
    w.grid.setCurrentIndex(ix)
    w.grid.setFocus()
    wait(300)
    f.snap().hold(500)
    f.key = "Espaço"
    f.hold(600)
    d = M.ImageViewer(w, a.preview, a.name)
    d._dim = True
    d.show()
    wait(300)
    f.snap([(d, ((W - d.width()) // 2, (H - d.height()) // 2))]).hold(1500)
    d.close()
    f.key = "Espaço"
    f.snap().hold(500)
    f.key = "Ctrl + F"
    w.search.setFocus()
    f.snap().hold(700)
    f.key = ""
    type_into(f, w.search, "poltrona", 90)
    wait(400)
    f.snap().hold(600)
    f.key = "Ctrl + T"
    w.grid.setCurrentIndex(w.grid.model().index(0, 0))
    w._focus_tags()
    wait(300)
    f.snap().hold(1600)
    f.key = ""
    w.search.clear()
    f.save()


FILMS = [("inicio", f_inicio), ("buscar", f_buscar), ("arrastar", f_arrastar), ("extrair", f_extrair),
         ("organizar", f_organizar), ("entrada", f_entrada), ("tags", f_tags), ("equipe", f_equipe),
         ("historico", f_historico), ("atualizar", f_atualizar), ("colecoes", f_colecoes), ("atalhos", f_atalhos)]

for name, fn in FILMS:
    if ONLY and name not in ONLY:
        continue
    try:
        fn()
    except Exception:  # noqa: BLE001
        import traceback
        traceback.print_exc()

w.close()
shutil.rmtree(TMP, ignore_errors=True)
