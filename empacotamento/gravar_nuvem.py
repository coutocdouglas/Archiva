"""Grava as animações dos tutoriais da Nuvem (nuvem_compartilhar.webp e nuvem_acessar.webp).

Uso (sem tela):
    QT_QPA_PLATFORM=offscreen QT_SCALE_FACTOR=2 python empacotamento/gravar_nuvem.py <biblioteca_de_exemplo>

Usa as telas reais do Archiva (diálogo de compartilhar, convite, janela da Nuvem) com uma biblioteca de exemplo
e uma chave de mentira. Nada vai para a rede: o acesso é por um servidor local, como no teste da interface.
Cada cena é uma captura de tela; o WebP junta as cenas com uma transição curta.
"""
from __future__ import annotations

import io
import json
import os
import shutil
import sys
import tempfile
import time
import uuid

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, ROOT)
SRC_LIB = os.path.abspath(sys.argv[1])
OUT = os.path.join(ROOT, "app", "recursos", "tutoriais")
os.makedirs(OUT, exist_ok=True)

TMP = tempfile.mkdtemp(prefix="archiva_nuvem_")
LIB = os.path.join(TMP, "MODELOS")
shutil.copytree(SRC_LIB, LIB, ignore=shutil.ignore_patterns("_ARCHIVA"))
os.environ["APPDATA"] = os.path.join(TMP, "ad")
os.environ["LOCALAPPDATA"] = os.path.join(TMP, "lad")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QBuffer, QIODevice, QRectF, Qt  # noqa: E402
from PySide6.QtGui import QColor, QGuiApplication, QImage, QLinearGradient, QPainter, QPainterPath, QPen  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QLineEdit, QMessageBox, QTextEdit  # noqa: E402

from app import perfil  # noqa: E402
from app.config import Config, version  # noqa: E402

perfil.save({"id": uuid.uuid4().hex, "nome": "Marina", "cor": "#5f6b43", "foto": False})
c = Config()
c.values.update(library_root=LIB, tutorial_off=True, versao_vista=version(), check_updates=False, abertura_off=True)
c.save()

app = QApplication(sys.argv)
app.setStyle("Fusion")
from app import theme  # noqa: E402
theme.load_fonts()
app.setFont(theme.ui_font(10))
app.setPalette(theme.palette())
app.setStyleSheet(theme.stylesheet())
QMessageBox.question = staticmethod(lambda *a, **k: QMessageBox.Yes)
QMessageBox.information = staticmethod(lambda *a, **k: None)
QMessageBox.warning = staticmethod(lambda *a, **k: None)

import app.main_window as M  # noqa: E402
from app import nuvem_host, nuvem_janela, nuvem_motor  # noqa: E402
from app.nuvem_cliente import criar_convite, ler_convite  # noqa: E402

CHAVE_FALSA = "tskey-auth-kExemplo1234CNTRL-ExemploExemploExemploExemplo"


def esperar(cond, t=30):
    t0 = time.time()
    while time.time() - t0 < t:
        app.processEvents()
        time.sleep(0.02)
        if cond():
            return True
    return False


# ------------------------------------------------------------------ cenas
W_, H_ = 1280, 800
LARG_MAX, ALT_MAX = 1040, 600


def cena(pix, passo: int, onde: str, texto: str) -> QImage:
    """Põe a captura num quadro 1280×800 com o título do passo."""
    img = QImage(W_, H_, QImage.Format_RGB32)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    p.setRenderHint(QPainter.SmoothPixmapTransform)
    g = QLinearGradient(0, 0, W_, H_)
    g.setColorAt(0, QColor("#2f1a1a"))
    g.setColorAt(1, QColor("#1b1612"))
    p.fillRect(0, 0, W_, H_, g)
    # título do passo
    p.setPen(Qt.NoPen)
    p.setBrush(theme.HILITE)
    p.drawEllipse(60, 38, 40, 40)
    p.setPen(QColor("#26150c"))
    p.setFont(theme.ui_font(15, 700))
    p.drawText(QRectF(60, 38, 40, 40), Qt.AlignCenter, str(passo))
    p.setPen(theme.TEXT)
    p.setFont(theme.ui_font(17, 600))
    p.drawText(QRectF(116, 30, W_ - 180, 30), Qt.AlignLeft | Qt.AlignVCenter, texto)
    p.setPen(theme.MUTED)
    p.setFont(theme.ui_font(10.5))
    p.drawText(QRectF(116, 58, W_ - 180, 24), Qt.AlignLeft | Qt.AlignVCenter, onde)
    # captura
    dpr = pix.devicePixelRatio()
    pm = pix
    if pix.width() / dpr > LARG_MAX or pix.height() / dpr > ALT_MAX:
        pm = pix.scaled(int(LARG_MAX * dpr), int(ALT_MAX * dpr), Qt.KeepAspectRatio, Qt.SmoothTransformation)
        pm.setDevicePixelRatio(dpr)
    wlog, hlog = pm.width() / dpr, pm.height() / dpr
    x, y = (W_ - wlog) / 2, 100 + (H_ - 100 - 30 - hlog) / 2
    sombra = QPainterPath()
    sombra.addRoundedRect(QRectF(x - 2, y + 6, wlog + 4, hlog + 4), 14, 14)
    p.fillPath(sombra, QColor(0, 0, 0, 90))
    caminho = QPainterPath()
    caminho.addRoundedRect(QRectF(x, y, wlog, hlog), 12, 12)
    p.save()
    p.setClipPath(caminho)
    p.drawPixmap(QRectF(x, y, wlog, hlog), pm, QRectF(pm.rect()))
    p.restore()
    p.setPen(QPen(QColor(255, 236, 210, 50), 1))
    p.setBrush(Qt.NoBrush)
    p.drawPath(caminho)
    p.end()
    return img


def para_pil(img: QImage) -> Image.Image:
    buf = QBuffer()
    buf.open(QIODevice.ReadWrite)
    img.save(buf, "PNG")
    return Image.open(io.BytesIO(bytes(buf.data()))).convert("RGB")


def salvar(nome: str, cenas: list[QImage], parado_ms=2600, passo_ms=70, trans=4):
    quadros = [para_pil(i) for i in cenas]
    frames, dur = [], []
    for k, q in enumerate(quadros):
        frames.append(q)
        dur.append(parado_ms)
        prox = quadros[(k + 1) % len(quadros)]
        for t in range(1, trans + 1):
            frames.append(Image.blend(q, prox, t / (trans + 1)))
            dur.append(passo_ms)
    destino = os.path.join(OUT, nome + ".webp")
    frames[0].save(destino, save_all=True, append_images=frames[1:], duration=dur, loop=0, quality=72, method=6)
    print(nome, os.path.getsize(destino) // 1024, "KB", len(frames), "quadros")


# ------------------------------------------------------------------ preparo
w = M.MainWindow()
w.resize(1400, 860)
w.show()
esperar(lambda: w._all_cats and not getattr(w, "_cat_scanning", None), 40)
nuvem_motor.disponivel = lambda: True                       # só para o texto "Conectado" aparecer na captura
nuvem_host.Compartilhamento.consultar_estado = lambda self: None
w.nuvem.cfg["compartilhar"] = True
w.nuvem.cfg["nome"] = "Biblioteca da Marina"
w.nuvem.cfg["authkey"] = ""
erro = w.nuvem.ligar()
esperar(lambda: w.nuvem._rev_publicado == w.data_rev, 20)

capturas: list = []
_orig_exec = QDialog.exec


def exec_captura(self):
    self.show()
    if self.windowTitle() == "Chave de acesso do Tailscale":
        self.findChild(QLineEdit).setText(CHAVE_FALSA)
    QTest.qWait(150)
    capturas.append(self.grab())
    self.hide()
    return QDialog.Rejected


QDialog.exec = exec_captura


def dialogo_compartilhar():
    d = nuvem_host.CompartilharDialog(w)
    d._mostrar_estado({"estado": "Running", "rede": "conta-da-biblioteca@gmail.com"})
    d.show()
    QTest.qWait(200)
    return d


# ------------------------------------------------------------------ quem compartilha
d = dialogo_compartilhar()
host1 = d.grab()
d._editar_authkey()                      # captura o diálogo da chave (com a chave de mentira)
host2 = capturas.pop()
w.nuvem.cfg["authkey"] = CHAVE_FALSA
d._marcar_chave()
nuvem_host._pergunta = lambda *a, **k: ("Rafael", True)
d._novo_convite()                        # captura o "Convite criado"
host3 = capturas.pop()
convite = w.nuvem.criar_convite("Rafael")  # (para o acesso abaixo)
d._preencher()
QTest.qWait(150)
host4 = d.grab()
d.close()

OND_A = "No computador onde está a biblioteca"
salvar("nuvem_compartilhar", [
    cena(host1, 1, OND_A, "Configurações › Biblioteca › Compartilhar pela Nuvem… e ligue o compartilhamento"),
    cena(host2, 2, OND_A, "Cole a chave de acesso do Tailscale (só uma vez)"),
    cena(host3, 3, OND_A, "Crie o convite e copie a linha ARCHIVA2-… para mandar à pessoa"),
    cena(host4, 4, OND_A, "Pronto: quem recebeu aparece na lista e você pode revogar quando quiser"),
])

# ------------------------------------------------------------------ quem acessa
d0 = ler_convite(convite)
conv_local = criar_convite(d0["h"], d0["k"], d0["n"], local=f"127.0.0.1:{w.nuvem.servidor.porta}")
w.tabs.setCurrentWidget(w.nuvem_page)          # 2.0.7: a Nuvem é uma aba da janela principal
nj = w.nuvem_page
esperar(lambda: False, 0.4)
acc1 = w.grab()
# caixa do convite (a captura mostra o convite colado)
_texto_convite = convite


def exec_convite(self):
    self.show()
    if self.windowTitle() == "Entrar com um convite":
        self.findChild(QTextEdit).setPlainText(_texto_convite)
    QTest.qWait(150)
    capturas.append(self.grab())
    self.hide()
    return QDialog.Rejected


QDialog.exec = exec_convite
nj.entrar_com_convite()
acc2 = capturas.pop()
# agora entra de verdade (pelo servidor local) para mostrar a biblioteca
QGuiApplication.clipboard().setText(conv_local)


def exec_aceita(self):
    if self.windowTitle() == "Entrar com um convite":
        self.findChild(QDialogButtonBox).buttons()[0].click()
        return self.result()
    return _orig_exec(self)


QDialog.exec = exec_aceita
nj.entrar_com_convite()
esperar(lambda: nj.catalogo is not None and not nj.catalogo.do_cache, 25)
nj.grade.setCurrentIndex(nj.modelo.index(0))
esperar(lambda: len(nj._minis) >= 8, 15)
app.processEvents()
acc3 = w.grab()
it = nj.modelo.itens[0]
# botão direito: captura o menu e o põe sobre a janela
from PySide6.QtWidgets import QMenu  # noqa: E402
from PySide6.QtGui import QPixmap  # noqa: E402
pos = nj.grade.visualRect(nj.modelo.index(0)).center()
_m = nj._montar_menu()
_m.adjustSize()
_m.show()
QTest.qWait(150)
_menus = [_m.grab()]
_m.hide()
base = w.grab()
if _menus:
    p = QPainter(base)
    destino = nj.grade.viewport().mapTo(w, pos)
    p.setPen(QPen(QColor(255, 230, 200, 70), 1))
    p.setBrush(QColor(30, 22, 17))
    mw, mh = _menus[0].width(), _menus[0].height()
    p.drawRoundedRect(destino.x(), destino.y(), mw, mh, 6, 6)
    p.drawPixmap(destino.x(), destino.y(), _menus[0])
    p.end()
acc4 = base
nj.copiar_selecionados()
esperar(lambda: nj.estado_item(it) == "copiado", 30)
nj.grade.setCurrentIndex(nj.modelo.index(0))
nj.detalhes.mostrar(it)
app.processEvents()
esperar(lambda: False, 0.3)
acc5 = w.grab()

OND_B = "No computador de quem vai acessar"
salvar("nuvem_acessar", [
    cena(acc1, 1, OND_B, "No menu lateral, abra Nuvem › Entrar com um convite…"),
    cena(acc2, 2, OND_B, "Cole a linha ARCHIVA2-… que você recebeu e clique em Entrar"),
    cena(acc3, 3, OND_B, "A biblioteca abre (na primeira vez a conexão pode levar até um minuto). Espaço amplia a prévia"),
    cena(acc4, 4, OND_B, "Botão direito no modelo › Copiar para a minha biblioteca"),
    cena(acc5, 5, OND_B, "Ele vai para a Entrada como archiva_transfer_N, pronto para classificar"),
])
w.nuvem.parar_ao_fechar()
os._exit(0)
