"""Telas da Nuvem (2.0): escolha Local/Nuvem, lista de bibliotecas e a biblioteca remota (só leitura e uso).

A biblioteca remota funciona como a Biblioteca, mas sem nada que altere o computador de quem compartilha:
navegar, buscar, ver prévias e variações, baixar (o modelo fica pronto neste PC) e arrastar para o 3ds Max.
Tudo que passa pela internet roda em ajudantes (segundo_plano); a janela nunca espera a rede.
"""
from __future__ import annotations

import os
import time

from PySide6.QtCore import (QAbstractListModel, QMimeData, QModelIndex, QRectF, QSize, Qt, QTimer, QUrl, Signal)
from PySide6.QtGui import QColor, QDesktopServices, QDrag, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
                               QLabel, QListView, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
                               QPlainTextEdit, QProgressBar, QPushButton, QStackedWidget,
                               QStyle, QStyledItemDelegate, QTextEdit, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import nuvem_motor, segundo_plano, theme, ui
from .config import APP_NAME, Config, version
from .nuvem_cliente import (Catalogo, Desligada, ItemRemoto, Remota, SemAcesso, id_biblioteca, ler_convite,
                            max_do_item)
from .scanner import natural_key, normalize

ALL = "__todas__"
CARD = 168
LIMITE_MINIATURAS = 600


# =========================================================================== conexões salvas

class Conexao:
    """Uma biblioteca da Nuvem salva neste PC: monta o caminho até ela (motor de rede ou endereço local)."""

    def __init__(self, dados: dict):
        self.dados = dados
        self.ident = dados.get("id") or id_biblioteca(dados["h"], dados["k"])
        self.motor: nuvem_motor.Motor | None = None
        self.remota: Remota | None = None
        self.erro = ""
        self.ultimo_erro = ""    # o último erro ao abrir (texto técnico, vai no relatório)
        self.etapa = ""          # o que o ajudante está fazendo agora (mostrado na tela)

    @property
    def nome(self) -> str:
        return self.dados.get("n") or self.dados.get("h", "Biblioteca")

    def preparar(self) -> Remota:
        """Num ajudante: liga o motor (se precisar) e devolve a Remota pronta para pedir coisas."""
        if self.remota is not None and (self.motor is None or self.motor.vivo):
            return self.remota
        if self.dados.get("l"):
            base = "http://" + self.dados["l"]
        else:
            if self.motor is None or not self.motor.vivo:
                self.etapa = "Ligando o motor de rede"
                self.motor = nuvem_motor.Motor("ligar", nuvem_motor.pasta_estado("acesso-" + self.ident),
                                               nuvem_motor.nome_maquina("archiva-acesso"), alvo=self.dados["h"],
                                               authkey=self.dados.get("a", ""))
                if not self.motor.iniciar():
                    raise Desligada(self.motor.erro)
            base = "http://" + self.motor.local
        self.remota = Remota(self.ident, base, self.dados["k"], self.nome)
        return self.remota

    def remota_offline(self) -> Remota:
        """Só para ler o que já está neste PC (catálogo salvo, prévias e modelos baixados)."""
        return self.remota or Remota(self.ident, "http://127.0.0.1:9", self.dados["k"], self.nome)

    def parar(self):
        if self.motor:
            self.motor.parar()
        self.motor = None
        self.remota = None


def conexoes_salvas(cfg: Config) -> list[dict]:
    return cfg.values.setdefault("nuvem_bibliotecas", [])


# =========================================================================== modelo da grade

class ItensModel(QAbstractListModel):
    def __init__(self, janela: "NuvemJanela"):
        super().__init__(janela)
        self.j = janela
        self.itens: list[ItemRemoto] = []

    def set_itens(self, itens):
        self.beginResetModel()
        self.itens = list(itens)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.itens)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        it = self.itens[index.row()]
        if role == Qt.DisplayRole:
            return it.name
        if role == Qt.UserRole:
            return it
        if role == Qt.ToolTipRole:
            return f"{it.name}\n{it.category}" + (f"\nTags: {', '.join(it.tags)}" if it.tags else "")
        return None

    def flags(self, index):
        f = super().flags(index)
        return f | Qt.ItemIsDragEnabled if index.isValid() else f

    def refresh_key(self, key: str):
        for i, it in enumerate(self.itens):
            if it.key == key:
                ix = self.index(i)
                self.dataChanged.emit(ix, ix)
                return


class CartaoDelegate(QStyledItemDelegate):
    def __init__(self, janela: "NuvemJanela"):
        super().__init__(janela)
        self.j = janela

    def sizeHint(self, option, index):
        return QSize(CARD + 20, CARD + 64)

    def paint(self, p: QPainter, opt, index):
        it: ItemRemoto = index.data(Qt.UserRole)
        r = QRectF(opt.rect).adjusted(10, 8, -10, -8)
        img = QRectF(r.left(), r.top(), r.width(), r.width())
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        path = QPainterPath()
        path.addRoundedRect(img, 10, 10)
        pm = self.j.miniatura(it)
        if pm is None:
            p.fillPath(path, QColor(239, 226, 201, 14))
        else:
            p.fillPath(path, QColor(255, 255, 255))
            p.setClipPath(path)
            s = pm.size().scaled(img.size().toSize(), Qt.KeepAspectRatio)
            alvo = QRectF(img.center().x() - s.width() / 2, img.center().y() - s.height() / 2, s.width(), s.height())
            p.drawPixmap(alvo.toRect(), pm)
            p.setClipping(False)
        estado = self.j.estado_item(it)
        cor = {"pronto": theme.OK, "baixando": theme.BUSY, "fila": theme.BUSY}.get(estado, theme.LINK)
        p.setBrush(cor)
        p.setPen(Qt.NoPen)
        p.drawEllipse(QRectF(img.right() - 18, img.top() + 8, 9, 9))
        if opt.state & QStyle.State_Selected:
            theme.paint_selection(p, img.adjusted(-2, -2, 2, 2), 12)
        p.setPen(theme.TEXT)
        p.setFont(theme.ui_font(9.5))
        fm = p.fontMetrics()
        p.drawText(QRectF(r.left() + 2, img.bottom() + 8, r.width() - 4, 18), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(it.name, Qt.ElideRight, int(r.width() - 4)))
        sub = {"pronto": "no seu PC · arraste para o Max", "baixando": f"baixando… {self.j.pct(it)}",
               "fila": "na fila"}.get(estado, "na nuvem" + (f" · {it.fmt.upper()}" if it.fmt else ""))
        p.setPen(theme.MUTED)
        p.setFont(theme.ui_font(8.5))
        p.drawText(QRectF(r.left() + 2, img.bottom() + 26, r.width() - 4, 16), Qt.AlignLeft | Qt.AlignVCenter,
                   p.fontMetrics().elidedText(sub, Qt.ElideRight, int(r.width() - 4)))
        p.restore()


class Grade(QListView):
    def __init__(self, janela: "NuvemJanela"):
        super().__init__()
        self.j = janela
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setSpacing(4)
        self.setSelectionMode(QAbstractItemView.SingleSelection)
        self.setDragEnabled(True)
        self.setDragDropMode(QAbstractItemView.DragOnly)
        self.setFrameShape(QFrame.NoFrame)
        self.setStyleSheet("QListView{background:transparent;}")
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)

    def startDrag(self, actions):
        ix = self.currentIndex()
        if not ix.isValid():
            return
        it = ix.data(Qt.UserRole)
        caminho = self.j.caminho_para_arrastar(it)
        if not caminho:
            return
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(caminho)])
        d = QDrag(self)
        d.setMimeData(md)
        pm = self.j.miniatura(it)
        if pm is not None:
            d.setPixmap(pm.scaledToWidth(96, Qt.SmoothTransformation))
        d.exec(Qt.CopyAction)


# =========================================================================== painel de detalhes

class Detalhes(QWidget):
    def __init__(self, janela: "NuvemJanela"):
        super().__init__()
        self.j = janela
        self.it: ItemRemoto | None = None
        self.setFixedWidth(330)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.previa = QLabel()
        self.previa.setFixedSize(330, 330)
        self.previa.setAlignment(Qt.AlignCenter)
        self.previa.setStyleSheet("background:rgba(239,226,201,0.05); border-radius:12px; color:#75695c;")
        lay.addWidget(self.previa)
        self.nome = QLabel()
        self.nome.setStyleSheet("font-size:14pt;")
        self.nome.setWordWrap(True)
        lay.addWidget(self.nome)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setStyleSheet(f"color:{theme.MUTED.name()};")
        lay.addWidget(self.info)
        self.barra = QProgressBar()
        self.barra.setFixedHeight(6)
        self.barra.setTextVisible(False)
        self.barra.hide()
        lay.addWidget(self.barra)
        bl = QHBoxLayout()
        self.b_baixar = ui.primary(QPushButton("Baixar"))
        self.b_baixar.clicked.connect(lambda: self.it and self.j.baixar(self.it))
        self.b_pasta = QPushButton("Abrir pasta")
        self.b_pasta.clicked.connect(lambda: self.it and self.j.abrir_pasta(self.it))
        self.b_apagar = QPushButton("Tirar do PC")
        self.b_apagar.setToolTip("Apaga só a cópia baixada neste computador (a biblioteca não muda)")
        self.b_apagar.clicked.connect(lambda: self.it and self.j.apagar_copia(self.it))
        for b in (self.b_baixar, self.b_pasta, self.b_apagar):
            bl.addWidget(b)
        bl.addStretch(1)
        lay.addLayout(bl)
        self.dica = QLabel()
        self.dica.setWordWrap(True)
        self.dica.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:9pt;")
        lay.addWidget(self.dica)
        lay.addWidget(ui.heading("Variações", 10))
        self.variacoes = QListWidget()
        self.variacoes.setFixedHeight(110)
        self.variacoes.setDragEnabled(True)
        self.variacoes.startDrag = self._arrastar_variacao
        lay.addWidget(self.variacoes)
        lay.addStretch(1)
        self.mostrar(None)

    def mostrar(self, it: ItemRemoto | None):
        self.it = it
        vis = it is not None
        for w in (self.b_baixar, self.b_pasta, self.b_apagar, self.variacoes):
            w.setVisible(vis)
        if not vis:
            self.previa.setPixmap(QPixmap())
            self.previa.setText("Selecione um modelo")
            self.nome.setText("")
            self.info.setText("")
            self.dica.setText("")
            self.barra.hide()
            return
        self.nome.setText(it.name)
        partes = [it.category.replace("/", " › ")]
        if it.tags:
            partes.append("Tags: " + ", ".join(it.tags))
        self.info.setText("\n".join(partes))
        self.variacoes.clear()
        for v in it.variacoes or []:
            self.variacoes.addItem(QListWidgetItem(v))
        if not it.variacoes:
            self.variacoes.addItem(QListWidgetItem("(conhecidas depois de baixar)" if it.tipo != "folder" else "—"))
        pm = self.j.previa_grande(it)
        if pm is not None:
            self.previa.setPixmap(pm.scaled(self.previa.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.previa.setPixmap(QPixmap())
            self.previa.setText("carregando…" if it.tem_previa else "sem prévia")
        self.atualizar_estado()

    def atualizar_estado(self):
        it = self.it
        if it is None:
            return
        e = self.j.estado_item(it)
        self.b_baixar.setVisible(e not in ("pronto", "baixando", "fila"))
        self.b_pasta.setVisible(e == "pronto")
        self.b_apagar.setVisible(e == "pronto")
        self.barra.setVisible(e in ("baixando", "fila"))
        feito, total = self.j.progresso.get(it.key, (0, 0))
        self.barra.setRange(0, 1000 if total else 0)
        if total:
            self.barra.setValue(int(feito * 1000 / max(total, 1)))
        if e == "pronto":
            self.dica.setText("Arraste o cartão (ou uma variação) para o 3ds Max. As texturas vêm da pasta baixada.")
            pasta = self.j.conexao.remota_offline().baixado(it)
            if pasta and (not it.variacoes or it.tipo != "folder"):
                _p, maxes, _d = max_do_item(pasta)
                if maxes:
                    self.variacoes.clear()
                    for m in maxes:
                        li = QListWidgetItem(os.path.basename(m))
                        li.setData(Qt.UserRole, m)
                        self.variacoes.addItem(li)
        elif e == "baixando":
            self.dica.setText(f"Baixando… {self.j.pct(it)}  (pode continuar navegando)")
        elif e == "fila":
            self.dica.setText("Na fila para baixar")
        else:
            self.dica.setText("Baixe para usar: o modelo fica pronto neste computador e pode ir para o Max.")

    def _arrastar_variacao(self, actions):
        li = self.variacoes.currentItem()
        caminho = li.data(Qt.UserRole) if li else None
        if not caminho or not self.it:
            return
        caminho = self.j.caminho_para_arrastar(self.it, caminho)
        if not caminho:
            return
        md = QMimeData()
        md.setUrls([QUrl.fromLocalFile(caminho)])
        d = QDrag(self.variacoes)
        d.setMimeData(md)
        d.exec(Qt.CopyAction)


# =========================================================================== janela

class NuvemJanela(QMainWindow):
    voltar = Signal()

    def __init__(self, cfg: Config | None = None, parent=None):
        super().__init__(parent)
        segundo_plano.init()
        self.cfg = cfg or Config()
        self.setWindowTitle(f"{APP_NAME} · Nuvem")
        self.resize(1360, 840)
        self.conexoes: dict[str, Conexao] = {}
        self.conexao: Conexao | None = None
        self.catalogo: Catalogo | None = None
        self._minis: dict[str, QPixmap] = {}
        self._grandes: dict[str, QPixmap] = {}
        self._pedidas: set[str] = set()
        self.baixando: dict[str, str] = {}             # chave -> "fila" | "baixando"
        self.progresso: dict[str, tuple[int, int]] = {}
        self._cancelar: set[str] = set()
        self._cat = ALL

        raiz = ui.Root()
        self.setCentralWidget(raiz)
        lay = QVBoxLayout(raiz)
        lay.setContentsMargins(0, 0, 0, 0)
        self.paginas = QStackedWidget()
        lay.addWidget(self.paginas)
        self.paginas.addWidget(self._pagina_lista())
        self.paginas.addWidget(self._pagina_biblioteca())
        self._repintar = QTimer(self, singleShot=True, interval=80)
        self._repintar.timeout.connect(lambda: self.grade.viewport().update())
        self._estado_timer = QTimer(self, interval=4000)
        self._estado_timer.timeout.connect(self._conferir_conexoes)
        self._estado_timer.start()
        self.preencher_lista()

    # ---------------------------------------------------------------- página 1: bibliotecas
    def _pagina_lista(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(40, 36, 40, 28)
        l.setSpacing(14)
        topo = QHBoxLayout()
        self.b_voltar_inicio = QPushButton("‹  Início")
        self.b_voltar_inicio.setProperty("flat", "true")
        self.b_voltar_inicio.clicked.connect(self.voltar.emit)
        topo.addWidget(self.b_voltar_inicio)
        t = QLabel("Nuvem")
        t.setStyleSheet("font-size:20pt;")
        topo.addWidget(t)
        topo.addStretch(1)
        l.addLayout(topo)
        sub = QLabel("Bibliotecas de outros computadores compartilhadas com você.")
        sub.setStyleSheet(f"color:{theme.MUTED.name()};")
        l.addWidget(sub)
        self.lista = QListWidget()
        self.lista.setSpacing(4)
        self.lista.setStyleSheet("QListWidget{background:transparent; border:none;} "
                                 "QListWidget::item{padding:0px; border-radius:12px; "
                                 "background:rgba(239,226,201,0.05); margin-bottom:8px;} "
                                 "QListWidget::item:selected{background:rgba(239,226,201,0.10);}")
        self.lista.itemDoubleClicked.connect(lambda it: self.abrir(it.data(Qt.UserRole)))
        l.addWidget(self.lista, 1)
        bl = QHBoxLayout()
        entrar = QPushButton("Entrar com um convite…")
        entrar.clicked.connect(self.entrar_com_convite)
        self.b_abrir = QPushButton("Abrir")
        self.b_abrir.hide()      # cada linha tem o seu "Abrir"
        remover = QPushButton("Remover deste PC")
        remover.clicked.connect(self.remover_biblioteca)
        bl.addWidget(entrar)
        bl.addWidget(remover)
        bl.addStretch(1)
        bl.addWidget(self.b_abrir)
        l.addLayout(bl)
        self.vazio = QLabel("Nenhuma biblioteca ainda. Peça um convite a quem compartilha e use "
                            "“Entrar com um convite”.")
        self.vazio.setStyleSheet(f"color:{theme.FAINT.name()};")
        l.addWidget(self.vazio)
        return w

    def preencher_lista(self):
        self.lista.clear()
        salvas = conexoes_salvas(self.cfg)
        for d in salvas:
            c = self.conexoes.get(d.get("id")) or Conexao(d)
            self.conexoes[c.ident] = c
            r = c.remota_offline()
            cat = r.catalogo_salvo()
            extra = f"{len(cat.itens)} itens" if cat else "ainda não aberta"
            if cat and cat.recebido:
                extra += f" · atualizada {time.strftime('%d/%m %H:%M', time.localtime(cat.recebido))}"
            if c.erro == "sem acesso":
                extra += " · convite revogado"
            elif c.erro:
                extra += " · desligada na última tentativa"
            it = QListWidgetItem()
            it.setData(Qt.UserRole, c.ident)
            it.setSizeHint(QSize(0, 76))
            self.lista.addItem(it)
            self.lista.setItemWidget(it, self._linha_biblioteca(c, cat, extra))
        self.vazio.setVisible(not salvas)
        self.b_abrir.setEnabled(bool(salvas))
        if salvas and self.lista.currentRow() < 0:
            self.lista.setCurrentRow(0)

    def _linha_biblioteca(self, c: "Conexao", cat, extra: str) -> QWidget:
        w = QWidget()
        w.setObjectName("linhaBib")
        w.setStyleSheet("#linhaBib{background:transparent;}")
        h = QHBoxLayout(w)
        h.setContentsMargins(14, 8, 14, 8)
        h.setSpacing(14)
        capa = QLabel()
        capa.setFixedSize(72, 54)
        capa.setStyleSheet("background:rgba(58,43,33,0.9); border-radius:6px;")
        if cat and cat.itens:   # capa: a prévia mais recente que já está neste PC
            r = c.remota_offline()
            for it in sorted(cat.itens, key=lambda i: -i.added_time)[:30]:
                dados = r.previa(it, 340, so_disco=True)
                if dados:
                    pm = QPixmap()
                    pm.loadFromData(dados)
                    if not pm.isNull():
                        pm = pm.scaled(capa.size(), Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
                        capa.setPixmap(pm.copy((pm.width() - 72) // 2, (pm.height() - 54) // 2, 72, 54))
                        break
        h.addWidget(capa)
        col = QVBoxLayout()
        col.setSpacing(2)
        n = QLabel(c.nome)
        n.setStyleSheet("font-size:12pt;")
        s = QLabel(extra)
        s.setStyleSheet(f"color:{theme.MUTED.name()};")
        col.addStretch(1)
        col.addWidget(n)
        col.addWidget(s)
        col.addStretch(1)
        h.addLayout(col, 1)
        abrir = ui.primary(QPushButton("Abrir"))
        abrir.clicked.connect(lambda _c=False, i=c.ident: self.abrir(i))
        h.addWidget(abrir)
        return w

    def entrar_com_convite(self):
        d = QDialog(self)
        d.setWindowTitle("Entrar com um convite")
        l = QVBoxLayout(d)
        l.setContentsMargins(24, 20, 24, 16)
        l.addWidget(QLabel("Cole aqui o convite que você recebeu (começa com ARCHIVA2-):"))
        caixa = QTextEdit()
        caixa.setFixedHeight(90)
        l.addWidget(caixa)
        erro = QLabel()
        erro.setStyleSheet(f"color:{theme.BAD.name()};")
        l.addWidget(erro)
        bb = QDialogButtonBox()
        ok = ui.primary(bb.addButton("Entrar", QDialogButtonBox.AcceptRole))
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        bb.rejected.connect(d.reject)
        resultado = {}

        def aceitar():
            try:
                resultado.update(ler_convite(caixa.toPlainText()))
            except ValueError as e:
                erro.setText(str(e))
                return
            d.accept()
        ok.clicked.connect(aceitar)
        l.addWidget(bb)
        d.resize(540, 240)
        clip = QApplication.clipboard().text()
        if "ARCHIVA2-" in clip:
            caixa.setPlainText(clip.strip())
        if d.exec() != QDialog.Accepted:
            return
        ident = id_biblioteca(resultado["h"], resultado["k"])
        salvas = conexoes_salvas(self.cfg)
        resultado["id"] = ident
        for i, s in enumerate(salvas):
            if s.get("id") == ident or (s.get("h") == resultado["h"] and s.get("k") == resultado["k"]):
                salvas[i] = resultado
                break
        else:
            salvas.append(resultado)
        self.cfg.save()
        self.conexoes.pop(ident, None)
        self.preencher_lista()
        self.abrir(ident)

    def remover_biblioteca(self):
        it = self.lista.currentItem()
        if not it:
            return
        ident = it.data(Qt.UserRole)
        c = self.conexoes.get(ident)
        if QMessageBox.question(self, "Remover", f"Remover “{c.nome if c else ''}” deste computador?\n\n"
                                "Os modelos que você baixou dela continuam no PC até você apagar a pasta.") \
                != QMessageBox.Yes:
            return
        if c:
            c.parar()
        salvas = conexoes_salvas(self.cfg)
        salvas[:] = [s for s in salvas if s.get("id") != ident]
        self.cfg.save()
        self.conexoes.pop(ident, None)
        self.preencher_lista()

    def _conferir_conexoes(self):
        c = self.conexao
        if c is None or c.motor is None or self.paginas.currentIndex() != 1:
            return
        segundo_plano.run_async(c.motor.estado, self._estado_motor)

    def _estado_motor(self, e: dict):
        if e.get("estado") == "NeedsLogin" and e.get("url_login") and not getattr(self, "_login_aberto", False):
            self._login_aberto = True
            r = QMessageBox.question(self, "Entrar", "Para acessar esta biblioteca, este computador precisa entrar "
                                     "na conta do Tailscale uma vez (o convite não trouxe a chave de acesso).\n\n"
                                     "Abrir a página para entrar?")
            if r == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(e["url_login"]))
        self._ultimo_estado = e
        txt, cor = nuvem_motor.texto_estado(e, "ligar", self.conexao.dados.get("h", "") if self.conexao else "")
        if cor != "ok":
            self.situacao.setText(txt)
        elif self.catalogo is None and self.conexao is not None and self.conexao.etapa:
            # a rede está de pé: mostra em que passo a biblioteca está, em vez de deixar o texto antigo
            self.situacao.setText(f"Rede conectada · {self.conexao.etapa}… ({e.get('segundos', 0)} s)")

    def diagnostico(self):
        """Mostra o que o motor de rede está vendo, para copiar e mandar a quem dá o suporte."""
        c = self.conexao
        if c is None:
            return
        if c.motor is None or not c.motor.vivo:
            e = {"estado": "Parado", "erro": c.motor.erro if c.motor else "O motor de rede ainda não foi ligado."}
        else:
            e = getattr(self, "_ultimo_estado", None) or {"estado": "Sem resposta ainda"}   # atualizado a cada 4 s
        texto = nuvem_motor.relatorio(e, c.dados, "Passo atual: " + (c.etapa or "-") + "\nÚltimo erro ao abrir: " + (c.ultimo_erro or "-") + "\nSituação na tela: " + self.situacao.text())
        d = QDialog(self)
        d.setWindowTitle("Diagnóstico da conexão")
        lay = QVBoxLayout(d)
        lay.setContentsMargins(20, 18, 20, 14)
        ed = QPlainTextEdit(texto)
        ed.setReadOnly(True)
        lay.addWidget(ed, 1)
        if c.motor is not None and c.motor.vivo:
            ed.appendPlainText("\nTestando a conexão com o computador da biblioteca (até 40 s)…")

            def depois(t):
                nonlocal texto
                novo = nuvem_motor.texto_teste(t)
                texto = texto + "\n\n" + novo
                ed.setPlainText(texto)
            segundo_plano.run_async(c.motor.teste, depois, lambda err: ed.appendPlainText(f"O teste falhou: {err}"))
        dica = QLabel("Este relatório não contém chaves nem convites.")
        dica.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:9pt;")
        lay.addWidget(dica)
        bl = QHBoxLayout()
        copiar = QPushButton("Copiar")
        copiar.clicked.connect(lambda: (QApplication.clipboard().setText(texto), copiar.setText("Copiado")))
        sair = QPushButton("Sair da conta e entrar de novo")
        sair.setToolTip("Esquece a conta do Tailscale usada por este computador. Útil se ele entrou na conta errada.")

        def trocar():
            if c.motor is not None and c.motor.vivo:
                c.motor.sair_da_conta()
            self._login_aberto = False
            d.accept()
            self.situacao.setText("Saí da conta. Aguarde: vou pedir para entrar de novo…")
        sair.clicked.connect(trocar)
        fechar = QPushButton("Fechar")
        fechar.clicked.connect(d.accept)
        bl.addWidget(copiar)
        bl.addWidget(sair)
        bl.addStretch(1)
        bl.addWidget(fechar)
        lay.addLayout(bl)
        d.resize(620, 420)
        d.exec()

    # ---------------------------------------------------------------- página 2: biblioteca remota
    def _pagina_biblioteca(self) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        esq = QWidget()
        esq.setFixedWidth(270)
        el = QVBoxLayout(esq)
        el.setContentsMargins(16, 28, 10, 16)
        b = QPushButton("‹  Bibliotecas")
        b.setProperty("flat", "true")
        b.clicked.connect(self.fechar_biblioteca)
        el.addWidget(b, 0, Qt.AlignLeft)
        self.titulo = QLabel()
        self.titulo.setStyleSheet("font-size:14pt;")
        self.titulo.setWordWrap(True)
        el.addWidget(self.titulo)
        self.selo = QLabel("Nuvem · só leitura")
        self.selo.setStyleSheet(f"color:{theme.LINK.name()}; font-size:9pt;")
        el.addWidget(self.selo)
        diag = QPushButton("Diagnóstico da conexão…")
        diag.setProperty("flat", "true")
        diag.clicked.connect(self.diagnostico)
        el.addWidget(diag, 0, Qt.AlignLeft)
        self.arvore = QTreeWidget()
        self.arvore.setHeaderHidden(True)
        self.arvore.setColumnCount(2)
        self.arvore.setFrameShape(QFrame.NoFrame)
        self.arvore.setStyleSheet("QTreeWidget{background:transparent;}")
        self.arvore.itemSelectionChanged.connect(self._mudou_categoria)
        el.addWidget(self.arvore, 1)
        h.addWidget(esq)

        centro = QWidget()
        cl = QVBoxLayout(centro)
        cl.setContentsMargins(24, 28, 16, 12)
        cl.setSpacing(12)
        self.busca = ui.SearchField("Buscar por nome, categoria ou tag")
        self.busca.edit.textChanged.connect(lambda: self._busca_timer.start())
        self._busca_timer = QTimer(self, singleShot=True, interval=180)
        self._busca_timer.timeout.connect(self.filtrar)
        cl.addWidget(self.busca)
        self.situacao = QLabel()
        self.situacao.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:9pt;")
        cl.addWidget(self.situacao)
        self.modelo = ItensModel(self)
        self.grade = Grade(self)
        self.grade.setModel(self.modelo)
        self.grade.setItemDelegate(CartaoDelegate(self))
        self.grade.selectionModel().currentChanged.connect(
            lambda ix, _o: self.detalhes.mostrar(ix.data(Qt.UserRole) if ix.isValid() else None))
        self.grade.doubleClicked.connect(lambda ix: self.baixar(ix.data(Qt.UserRole)))
        cl.addWidget(self.grade, 1)
        h.addWidget(centro, 1)

        dir_ = QWidget()
        dl = QVBoxLayout(dir_)
        dl.setContentsMargins(8, 28, 24, 16)
        self.detalhes = Detalhes(self)
        dl.addWidget(self.detalhes)
        h.addWidget(dir_)
        return w

    def abrir(self, ident: str):
        c = self.conexoes.get(ident)
        if c is None:
            return
        self.conexao = c
        self.catalogo = None
        self._minis.clear()
        self._grandes.clear()
        self._pedidas.clear()
        self.titulo.setText(c.nome)
        self.paginas.setCurrentIndex(1)
        salvo = c.remota_offline().catalogo_salvo()
        if salvo:
            self._mostrar_catalogo(salvo)
            self.situacao.setText(f"Mostrando a lista salva ({time.strftime('%d/%m %H:%M', time.localtime(salvo.recebido))})"
                                  " · conectando…")
        else:
            self.modelo.set_itens([])
            self.arvore.clear()
            self.situacao.setText("Conectando… (a primeira vez pode levar alguns segundos)")

        def buscar():
            c.etapa = "Ligando o motor de rede"
            r = c.preparar()
            c.etapa = "Falando com o computador da biblioteca"
            info = r.info()
            c.etapa = "Baixando a lista de modelos"
            cat = r.catalogo()
            c.etapa = ""
            return cat, info

        def ok(res):
            cat, info = res
            c.erro = ""
            if self.conexao is not c:
                return
            self._mostrar_catalogo(cat)
            papel = info.get("papel") or "leitor"
            self.selo.setText(f"Nuvem · {papel}" + (" · só leitura" if papel == "leitor" else ""))
            self.situacao.setText(f"Conectado · {len(cat.itens)} itens")

        def erro(e):
            if self.conexao is not c:
                return
            c.erro = "sem acesso" if isinstance(e, SemAcesso) else "desligada"
            c.etapa = ""      # senão o aviso de andamento apagaria a mensagem de erro
            c.ultimo_erro = f"{type(e).__name__}: {e}" + (f" · causa: {e.__cause__!r}" if e.__cause__ else "")
            if isinstance(e, SemAcesso):
                self.situacao.setText(str(e))
            elif isinstance(e, Desligada):
                self.situacao.setText(("O computador da biblioteca está desligado ou com o Archiva fechado. "
                                       if salvo else "Não consegui conectar agora. ")
                                      + "Os modelos já baixados continuam disponíveis.")
            else:
                self.situacao.setText(f"Erro ao conectar: {e}")
        segundo_plano.run_async(buscar, ok, erro)

    def fechar_biblioteca(self):
        self.paginas.setCurrentIndex(0)
        self.preencher_lista()

    def _mostrar_catalogo(self, cat: Catalogo):
        sel = self._cat
        self.catalogo = cat
        self.arvore.blockSignals(True)
        self.arvore.clear()
        todas = QTreeWidgetItem(["Todas as categorias", str(len(cat.itens))])
        todas.setData(0, Qt.UserRole, ALL)
        self.arvore.addTopLevelItem(todas)
        alvo = todas

        def add(pai, c):
            nonlocal alvo
            item = QTreeWidgetItem([c.name.capitalize(), str(c.quantidade)])
            item.setData(0, Qt.UserRole, c.key)
            item.setForeground(1, theme.FAINT)
            if c.key == sel:
                alvo = item
            (pai.addChild(item) if pai else self.arvore.addTopLevelItem(item))
            for s in sorted(c.children, key=lambda x: natural_key(x.name)):
                add(item, s)
        for c in sorted(cat.categorias, key=lambda x: natural_key(x.name)):
            add(None, c)
        self.arvore.resizeColumnToContents(1)
        self.arvore.setColumnWidth(0, 200)
        self.arvore.setCurrentItem(alvo)
        self.arvore.blockSignals(False)
        self._cat = alvo.data(0, Qt.UserRole)
        self.filtrar()

    def _mudou_categoria(self):
        it = self.arvore.currentItem()
        self._cat = it.data(0, Qt.UserRole) if it else ALL
        self.filtrar()

    def filtrar(self):
        if not self.catalogo:
            return
        termos = normalize(self.busca.edit.text()).split()
        cat = self._cat
        out = []
        for it in self.catalogo.itens:
            if cat != ALL and not (it.category == cat or it.category.startswith(cat + "/")):
                continue
            if termos and not all(t in it.search_text for t in termos):
                continue
            out.append(it)
        out.sort(key=lambda i: (natural_key(i.category), natural_key(i.name)))
        atual = self.detalhes.it.key if self.detalhes.it else None
        self.modelo.set_itens(out)
        if atual:
            for i, it in enumerate(out):
                if it.key == atual:
                    self.grade.setCurrentIndex(self.modelo.index(i))
                    break

    # ---------------------------------------------------------------- prévias
    def miniatura(self, it: ItemRemoto) -> QPixmap | None:
        pm = self._minis.get(it.key)
        if pm is None and it.tem_previa and it.key not in self._pedidas:
            self._pedir_previa(it, 340, self._minis)
        return pm

    def previa_grande(self, it: ItemRemoto) -> QPixmap | None:
        pm = self._grandes.get(it.key)
        if pm is None and it.tem_previa and ("G" + it.key) not in self._pedidas:
            self._pedir_previa(it, 720, self._grandes)
        return pm or self._minis.get(it.key)

    def _pedir_previa(self, it: ItemRemoto, largura: int, destino: dict):
        c = self.conexao
        if c is None:
            return
        marca = ("G" if destino is self._grandes else "") + it.key
        self._pedidas.add(marca)

        def baixar():
            r = c.remota or c.remota_offline()
            try:
                return r.previa(it, largura)
            except (Desligada, SemAcesso):
                return None

        def pronto(dados):
            if self.conexao is not c:
                return
            if not dados:
                QTimer.singleShot(15000, lambda: self._pedidas.discard(marca))   # tenta de novo depois
                return
            pm = QPixmap()
            pm.loadFromData(dados)
            if pm.isNull():
                return
            if len(destino) > LIMITE_MINIATURAS:
                destino.clear()
                self._pedidas = {m for m in self._pedidas if (m.startswith("G")) != (destino is self._minis)}
            destino[it.key] = pm
            self._repintar.start()
            if self.detalhes.it is not None and self.detalhes.it.key == it.key:
                self.detalhes.mostrar(it)
        segundo_plano.run_async(baixar, pronto)

    # ---------------------------------------------------------------- baixar e usar
    def estado_item(self, it: ItemRemoto) -> str:
        e = self.baixando.get(it.key)
        if e:
            return e
        if self.conexao and self.conexao.remota_offline().baixado(it):
            return "pronto"
        return "nuvem"

    def pct(self, it: ItemRemoto) -> str:
        feito, total = self.progresso.get(it.key, (0, 0))
        if total:
            return f"{feito * 100 // max(total, 1)}%"
        return f"{feito / 1024 ** 2:.0f} MB" if feito else ""

    def baixar(self, it: ItemRemoto | None):
        if it is None or self.conexao is None or self.estado_item(it) != "nuvem":
            return
        c = self.conexao
        self.baixando[it.key] = "fila"
        self.progresso[it.key] = (0, 0)
        self._atualizar(it)
        ultimo = [0.0]

        def avisar(feito, total):
            if time.time() - ultimo[0] > 0.25:
                ultimo[0] = time.time()
                segundo_plano.post(lambda _a: self._progresso(it, feito, total))

        def trabalho():
            r = c.preparar()
            segundo_plano.post(lambda _a: self._comecou(it))
            return r.baixar(it, avisar, lambda: it.key in self._cancelar)

        def ok(_pasta):
            self.baixando.pop(it.key, None)
            self._atualizar(it)
            self.statusTip = f"{it.name} pronto"

        def falhou(e):
            self.baixando.pop(it.key, None)
            self._cancelar.discard(it.key)
            self._atualizar(it)
            if isinstance(e, InterruptedError):
                return
            from .extractor import PasswordError
            if isinstance(e, PasswordError):
                msg = (f"{it.name} está protegido por senha. Cadastre a senha em Configurações › Biblioteca "
                       "› Ver / editar senhas e baixe de novo.")
            elif isinstance(e, (Desligada, SemAcesso)):
                msg = str(e)
            else:
                msg = f"Não consegui baixar {it.name}:\n{e}"
            QMessageBox.warning(self, "Baixar", msg)
        segundo_plano.run_async(trabalho, ok, falhou)

    def _comecou(self, it):
        if it.key in self.baixando:
            self.baixando[it.key] = "baixando"
            self._atualizar(it)

    def _progresso(self, it, feito, total):
        self.progresso[it.key] = (feito, total)
        self._atualizar(it)

    def _atualizar(self, it):
        self.modelo.refresh_key(it.key)
        if self.detalhes.it is not None and self.detalhes.it.key == it.key:
            self.detalhes.atualizar_estado()

    def caminho_para_arrastar(self, it: ItemRemoto, max_file: str | None = None) -> str | None:
        pasta = self.conexao.remota_offline().baixado(it) if self.conexao else None
        if not pasta:
            self.situacao.setText(f"{it.name} ainda não está neste computador. Clique em Baixar (ou dois cliques).")
            return None
        principal, maxes, dirs = max_do_item(pasta)
        mx = max_file or principal
        if not mx:
            self.situacao.setText(f"{it.name}: nenhum arquivo .max dentro do que foi baixado.")
            return None
        from . import max_startup
        max_startup.write_handoff(it.name, mx, dirs)   # o script do Max religa as texturas depois do Merge
        return mx

    def abrir_pasta(self, it: ItemRemoto):
        pasta = self.conexao.remota_offline().baixado(it) if self.conexao else None
        if pasta:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(pasta)))

    def apagar_copia(self, it: ItemRemoto):
        if not self.conexao:
            return
        if QMessageBox.question(self, "Tirar do PC", f"Apagar a cópia de {it.name} baixada neste computador?\n\n"
                                "A biblioteca de origem não muda; dá para baixar de novo.") != QMessageBox.Yes:
            return
        self.conexao.remota_offline().apagar_copia(it)
        self._atualizar(it)

    def closeEvent(self, e):
        for k in list(self.baixando):
            self._cancelar.add(k)
        for c in self.conexoes.values():
            c.parar()
        super().closeEvent(e)


# =========================================================================== tela inicial (Local × Nuvem)

class OpcaoCartao(QFrame):
    clicado = Signal()

    def __init__(self, icone: str, titulo: str, sub: str, nota: str):
        super().__init__()
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(170)
        self._hover = False
        l = QVBoxLayout(self)
        l.setContentsMargins(22, 20, 22, 18)
        l.setSpacing(4)
        ic = QLabel()
        ic.setPixmap(ui.icon_pixmap(icone, theme.LINK, 24, 1.7))
        l.addWidget(ic)
        l.addSpacing(8)
        t = QLabel(titulo)
        t.setStyleSheet("font-size:13pt; background:transparent;")
        l.addWidget(t)
        self.sub = QLabel(sub)
        self.sub.setStyleSheet(f"color:{theme.MUTED.name()}; background:transparent;")
        l.addWidget(self.sub)
        l.addStretch(1)
        self.nota = QLabel(nota)
        self.nota.setWordWrap(True)
        self.nota.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:9pt; background:transparent;")
        l.addWidget(self.nota)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.rect().contains(e.position().toPoint()):
            self.clicado.emit()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        theme.paint_glass(p, QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5), 12, 1.0, self._hover)
        if self._hover:
            theme.paint_selection(p, QRectF(self.rect()).adjusted(1, 1, -1, -1), 12)


class Escolha(QWidget):
    """Tela inicial da 2.0: abrir a biblioteca deste computador ou uma da Nuvem."""
    local = Signal()
    nuvem = Signal()

    def __init__(self, cfg: Config):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setMinimumSize(760, 460)
        self.resize(820, 500)
        l = QVBoxLayout(self)
        l.setContentsMargins(40, 34, 40, 34)
        l.setSpacing(6)
        topo = QHBoxLayout()
        logo = ui.LogoMark()
        logo.setFixedWidth(170)
        topo.addWidget(logo)
        topo.addStretch(1)
        from . import perfil
        p = perfil.load() or {}
        v = QLabel(f"versão {version()}" + (f" · {p.get('nome')}" if p.get("nome") else ""))
        v.setStyleSheet(f"color:{theme.FAINT.name()};")
        topo.addWidget(v, 0, Qt.AlignTop)
        l.addLayout(topo)
        l.addSpacing(10)
        t = QLabel("Onde você quer abrir?")
        t.setStyleSheet("font-size:16pt;")
        l.addWidget(t)
        s = QLabel("Escolha a biblioteca deste computador ou uma compartilhada com você.")
        s.setStyleSheet(f"color:{theme.MUTED.name()};")
        l.addWidget(s)
        l.addSpacing(16)
        h = QHBoxLayout()
        h.setSpacing(16)
        raiz = cfg["library_root"] or "nenhuma pasta escolhida"
        nuvem = cfg.values.get("nuvem") or {}
        nota_local = "Tudo liberado: classificar, organizar, Entrada"
        if nuvem.get("compartilhar"):
            ativos = len([c for c in nuvem.get("convidados", []) if not c.get("revogado")])
            nota_local = f"Compartilhando com {ativos} pessoa(s) enquanto estiver aberto"
        a = OpcaoCartao("computador", "Neste computador", raiz, nota_local)
        a.clicado.connect(self.local.emit)
        n = len(cfg.values.get("nuvem_bibliotecas") or [])
        b = OpcaoCartao("nuvem", "Nuvem",
                        f"{n} biblioteca(s) disponível(is)" if n else "Entrar com um convite",
                        "Ver, buscar, baixar e levar para o Max")
        b.clicado.connect(self.nuvem.emit)
        h.addWidget(a)
        h.addWidget(b)
        l.addLayout(h)
        l.addStretch(1)

    def paintEvent(self, e):
        p = QPainter(self)
        theme.paint_background(p, QRectF(self.rect()))


def mostrar_escolha(cfg: Config) -> bool:
    """A tela inicial aparece para quem já usa a Nuvem (tem biblioteca salva). Quem nunca usou abre direto na
    biblioteca local, como antes; a Nuvem fica no menu lateral."""
    return bool(cfg.values.get("nuvem_bibliotecas"))

