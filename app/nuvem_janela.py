"""Nuvem (2.0): a biblioteca de outro computador, dentro do Archiva, com o mesmo visual da Biblioteca.

É uma página da janela principal (barra lateral › Nuvem). Só leitura: navegar, buscar, ver prévias (Espaço amplia) e
copiar um modelo para a SUA biblioteca. A cópia vai para a pasta _ENTRADA com o nome archiva_transfer_<n> (mais a
prévia) e depois é classificada como qualquer download. Nada aqui altera o computador de quem compartilha.
Tudo que passa pela internet roda em ajudantes (segundo_plano); a janela nunca espera a rede.
"""
from __future__ import annotations

import os
import threading
import time
from types import SimpleNamespace

from PySide6.QtCore import (QAbstractListModel, QModelIndex, QPoint, QRectF, QSize, QSizeF, Qt, QTimer)
from PySide6.QtGui import (QColor, QDesktopServices, QFontMetrics, QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap,
                           QShortcut)
from PySide6.QtCore import QUrl
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QDialog, QDialogButtonBox, QFrame, QHBoxLayout,
                               QLabel, QListView, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPlainTextEdit,
                               QProgressBar, QPushButton, QScrollArea, QSlider, QSplitter, QStackedWidget, QStyle,
                               QStyledItemDelegate, QTextEdit, QTreeWidgetItem, QVBoxLayout, QWidget)

from . import nuvem_motor, segundo_plano, theme, ui
from .barra_categorias import COUNT_ROLE, COVER_ROLE, CategoryDelegate, CategoryTree
from .config import Config
from .janela import TITLE_H
from .nuvem_cliente import Catalogo, Desligada, ItemRemoto, Remota, SemAcesso, id_biblioteca, ler_convite
from .scanner import natural_key, normalize

ALL = "__todas__"
LIMITE_MINIATURAS = 800


# =========================================================================== indicador online / offline

def bolinha(cor: QColor, d: int = 12) -> QPixmap:
    """Bolinha cheia (com um halo suave) para o indicador de online/offline."""
    esc = 3
    pm = QPixmap(d * esc, d * esc)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    halo = QColor(cor)
    halo.setAlpha(60)
    p.setBrush(halo)
    p.drawEllipse(QRectF(0, 0, d * esc, d * esc))
    p.setBrush(cor)
    m = d * esc * 0.2
    p.drawEllipse(QRectF(m, m, d * esc - 2 * m, d * esc - 2 * m))
    p.end()
    pm = pm.scaled(d, d, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    return pm


def estado_online(c: "Conexao") -> tuple[str, QColor, str]:
    """(palavra, cor, dica) do indicador: verde = online, vermelho = offline, cinza = ainda verificando."""
    if c.online is True:
        return "Online", theme.OK, "Online: o computador da biblioteca está respondendo."
    if c.online is False:
        motivo = ("O convite foi revogado." if c.erro == "sem acesso"
                  else "O computador da biblioteca está desligado, sem internet ou com o Archiva fechado.")
        return "Offline", theme.BAD, "Offline: " + motivo
    return "Verificando…", theme.FAINT, "Verificando se o computador da biblioteca está respondendo…"


# =========================================================================== conexões salvas

class Conexao:
    """Uma biblioteca da Nuvem salva neste PC: monta o caminho até ela (motor de rede ou endereço local)."""

    def __init__(self, dados: dict):
        self.dados = dados
        self.ident = dados.get("id") or id_biblioteca(dados["h"], dados["k"])
        self.motor: nuvem_motor.Motor | None = None
        self.remota: Remota | None = None
        self.erro = ""
        self._retentou = False
        self.ultimo_erro = ""    # o último erro ao abrir (texto técnico, vai no relatório)
        self.etapa = ""          # o que o ajudante está fazendo agora (mostrado na tela)
        self.online: bool | None = None   # None = ainda não verificada; True/False = última resposta do computador da biblioteca
        self.verificando = False
        self._trava = threading.Lock()    # abrir e verificar ao mesmo tempo não ligam dois motores

    @property
    def nome(self) -> str:
        return self.dados.get("n") or self.dados.get("h", "Biblioteca")

    def preparar(self) -> Remota:
        """Num ajudante: liga o motor (se precisar) e devolve a Remota pronta para pedir coisas."""
        with self._trava:
            return self._preparar()

    def _preparar(self) -> Remota:
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
                self._esperar_rede()
            base = "http://" + self.motor.local
        self.remota = Remota(self.ident, base, self.dados["k"], self.nome)
        return self.remota

    def _esperar_rede(self, limite: float = 90.0):
        """Espera o motor entrar na rede e achar o computador da biblioteca antes do primeiro pedido
        (sem isso, o pedido sai cedo demais e volta "Bad Gateway")."""
        t0 = time.time()
        while time.time() - t0 < limite and self.motor is not None and self.motor.vivo:
            e = self.motor.estado()
            if e.get("estado") == "NeedsLogin":
                return                       # a tela avisa que falta a chave; não adianta esperar
            if e.get("estado") == "Running" and e.get("alvo_ok") is True:
                return
            seg = int(time.time() - t0)
            if e.get("estado") == "Running":
                self.etapa = f"Procurando o computador da biblioteca na rede ({seg} s)"
            else:
                self.etapa = f"Entrando na rede do Tailscale ({seg} s)"
            time.sleep(1.0)

    def verificar(self) -> bool:
        """Num ajudante: pergunta ao computador da biblioteca se ele está de pé (pedido leve, /api/info)."""
        try:
            self.preparar().info()
            self.online = True
            if self.erro == "sem acesso":
                self.erro = ""
        except SemAcesso:
            self.online = False
            self.erro = "sem acesso"
        except Exception:  # noqa: BLE001 — qualquer falha de rede conta como offline
            self.online = False
        return self.online

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


# =========================================================================== modelo e cartões

class ItensModel(QAbstractListModel):
    def __init__(self, pagina: "NuvemPage"):
        super().__init__(pagina)
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

    def refresh_key(self, key: str):
        for i, it in enumerate(self.itens):
            if it.key == key:
                ix = self.index(i)
                self.dataChanged.emit(ix, ix)
                return


class CartaoDelegate(QStyledItemDelegate):
    """Cartão igual ao da Biblioteca: prévia com cantos arredondados sobre a cor do próprio fundo, nome e situação."""

    def __init__(self, pagina: "NuvemPage"):
        super().__init__(pagina)
        self.p = pagina
        self._bg: dict[str, QColor] = {}

    def sizeHint(self, option, index):
        s = self.p.tamanho
        return QSize(s + 20, s + 64)

    def paint(self, p: QPainter, option, index):
        it: ItemRemoto = index.data(Qt.UserRole)
        s = self.p.tamanho
        r = QRectF(option.rect).adjusted(10, 8, -10, -8)
        p.save()
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        selecionado = bool(option.state & QStyle.State_Selected)
        hover = bool(option.state & QStyle.State_MouseOver)
        img = QRectF(r.left(), r.top(), r.width(), s)
        path = QPainterPath()
        path.addRoundedRect(img, 12, 12)
        pix = self.p.miniatura(it)
        p.save()
        p.setClipPath(path)
        if pix is not None:
            cor = self._bg.get(it.key)
            if cor is None:
                from .home_page import edge_color
                cor = self._bg[it.key] = edge_color(pix)
            p.fillRect(img, cor)
            sc = QSizeF(pix.size()).scaled(img.size(), Qt.KeepAspectRatio)
            p.drawPixmap(QRectF(img.center().x() - sc.width() / 2, img.center().y() - sc.height() / 2,
                                sc.width(), sc.height()), pix, QRectF(pix.rect()))
        else:
            p.fillRect(img, QColor(255, 236, 210, 12))
            p.setPen(theme.FAINT)
            p.setFont(theme.ui_font(9))
            p.drawText(img, Qt.AlignCenter, "…" if it.tem_previa else "sem prévia")
        p.restore()
        if selecionado:
            theme.paint_selection(p, img, 12)
        elif hover:
            p.setPen(QPen(QColor(227, 207, 169, 110), 1.2))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(img.adjusted(0.6, 0.6, -0.6, -0.6), 12, 12)
        estado = self.p.estado_item(it)
        cor = {"copiado": theme.OK, "copiando": theme.BUSY, "fila": theme.BUSY}.get(estado, theme.LINK)
        p.setPen(QPen(QColor(255, 255, 255, 215), 1.6))
        p.setBrush(cor)
        p.drawEllipse(QRectF(img.right() - 19, img.top() + 9, 10, 10))
        if estado in ("copiando", "fila"):
            faixa = QRectF(img.left(), img.bottom() - 22, img.width(), 22)
            p.save()
            p.setClipPath(path)
            p.fillRect(faixa, QColor(30, 20, 14, 200))
            p.restore()
            p.setPen(theme.TEXT)
            p.setFont(theme.ui_font(8.5))
            txt = "na fila" if estado == "fila" else f"copiando… {self.p.pct(it)}".strip()
            p.drawText(faixa, Qt.AlignCenter, txt)
        f = theme.ui_font(9.8)
        p.setFont(f)
        fm = QFontMetrics(f)
        p.setPen(theme.TEXT)
        p.drawText(QRectF(r.left() + 1, img.bottom() + 8, r.width() - 2, fm.height()), Qt.AlignLeft | Qt.AlignVCenter,
                   fm.elidedText(it.name, Qt.ElideRight, int(r.width() - 2)))
        sub = {"copiado": f"copiado · {self.p.copiado.get(it.key, '')}", "copiando": "copiando…",
               "fila": "na fila"}.get(estado, "na nuvem" + (f" · {it.fmt.upper()}" if it.fmt else ""))
        f2 = theme.ui_font(8.8)
        p.setFont(f2)
        p.setPen(theme.MUTED)
        fm2 = QFontMetrics(f2)
        p.drawText(QRectF(r.left() + 1, img.bottom() + 9 + fm.height(), r.width(), fm2.height()),
                   Qt.AlignLeft | Qt.AlignVCenter, fm2.elidedText(sub, Qt.ElideRight, int(r.width())))
        p.restore()


class Grade(QListView):
    """A grade de modelos. Não há arrastar: para usar um modelo, "Copiar para a minha biblioteca"."""

    def __init__(self):
        super().__init__()
        self.setViewMode(QListView.IconMode)
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)
        self.setDragEnabled(False)
        self.setMouseTracking(True)
        self.setSpacing(0)
        self.setFrameShape(QFrame.NoFrame)
        self.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.verticalScrollBar().setSingleStep(30)
        self.setContextMenuPolicy(Qt.CustomContextMenu)


class Capas:
    """Faz a barra de categorias (que pede prévias por "caminho") buscar as miniaturas da Nuvem."""

    def __init__(self, pagina: "NuvemPage"):
        self.p = pagina

    def get(self, chave):
        it = self.p.por_chave.get(chave)
        return self.p.miniatura(it) if it is not None else None


# =========================================================================== painel de detalhes

class Detalhes(QWidget):
    def __init__(self, pagina: "NuvemPage"):
        super().__init__()
        self.p = pagina
        self.it: ItemRemoto | None = None
        from .main_window import PreviewBox
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 4, 0)
        lay.setSpacing(12)
        self.previa = PreviewBox(pagina.w)
        self.previa.mouseReleaseEvent = lambda e: (e.button() == Qt.LeftButton and self.it is not None
                                                   and self.p.ampliar(self.it))
        self.previa.setCursor(Qt.PointingHandCursor)
        self.previa.setToolTip("Clique (ou Espaço) para ampliar")
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
        self.b_copiar = ui.primary(QPushButton("Copiar para a minha biblioteca"))
        self.b_copiar.setFixedHeight(38)
        self.b_copiar.clicked.connect(lambda: self.p.copiar_selecionados())
        lay.addWidget(self.b_copiar)
        self.b_cancelar = QPushButton("Cancelar a cópia")
        self.b_cancelar.clicked.connect(lambda: self.it and self.p.cancelar(self.it))
        self.b_cancelar.hide()
        lay.addWidget(self.b_cancelar)
        self.dica = QLabel()
        self.dica.setWordWrap(True)
        self.dica.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:9pt;")
        lay.addWidget(self.dica)
        self.t_var = ui.heading("Variações", 10)
        lay.addWidget(self.t_var)
        self.variacoes = QListWidget()
        self.variacoes.setFixedHeight(120)
        self.variacoes.setStyleSheet("QListWidget{color:#d8cfc2; background:transparent; border:none;}")
        self.variacoes.setSelectionMode(QAbstractItemView.NoSelection)
        lay.addWidget(self.variacoes)
        lay.addStretch(1)
        self.mostrar(None)

    def mostrar(self, it: ItemRemoto | None, varios: int = 1):
        self.it = it
        vis = it is not None
        for w in (self.b_copiar, self.t_var, self.variacoes):
            w.setVisible(vis)
        if not vis:
            self.previa.set_pixmap(None, "Selecione um modelo")
            self.nome.setText("")
            self.info.setText("")
            self.dica.setText("Clique num modelo para ver a prévia. Espaço amplia; botão direito copia para a sua "
                              "biblioteca.")
            self.barra.hide()
            self.b_cancelar.hide()
            return
        self.nome.setText(it.name if varios <= 1 else f"{it.name}  +{varios - 1}")
        partes = [it.category.replace("/", " › ")]
        if it.tags:
            partes.append("Tags: " + ", ".join(it.tags))
        self.info.setText("\n".join(partes))
        self.b_copiar.setText("Copiar para a minha biblioteca" if varios <= 1 else f"Copiar {varios} modelos")
        self.variacoes.clear()
        for v in it.variacoes or []:
            self.variacoes.addItem(QListWidgetItem(v))
        vazio = not it.variacoes
        self.t_var.setVisible(not vazio)
        self.variacoes.setVisible(not vazio)
        pm = self.p.previa_grande(it)
        self.previa.set_pixmap(pm, "carregando…" if it.tem_previa else "sem prévia")
        self.atualizar_estado()

    def atualizar_estado(self):
        it = self.it
        if it is None:
            return
        e = self.p.estado_item(it)
        ocupado = e in ("copiando", "fila")
        self.b_copiar.setEnabled(not ocupado)
        self.b_cancelar.setVisible(ocupado)
        self.barra.setVisible(ocupado)
        feito, total = self.p.progresso.get(it.key, (0, 0))
        self.barra.setRange(0, 1000 if total else 0)
        if total:
            self.barra.setValue(int(feito * 1000 / max(total, 1)))
        if e == "copiado":
            self.dica.setText(f"Copiado para a Entrada como {self.p.copiado.get(it.key, '')}. Classifique na aba "
                              "Entrada como qualquer download.")
        elif e == "copiando":
            self.dica.setText(f"Copiando… {self.p.pct(it)}  (pode continuar navegando)")
        elif e == "fila":
            self.dica.setText("Na fila para copiar")
        else:
            self.dica.setText("Vai para a pasta Entrada da sua biblioteca, com o nome archiva_transfer_N e a prévia. "
                              "Depois você classifica onde quiser.")


# =========================================================================== página

class NuvemPage(QWidget):
    """A aba "Nuvem" da janela principal."""

    def __init__(self, janela):
        super().__init__()
        segundo_plano.init()
        self.w = janela
        self.cfg: Config = janela.cfg
        self.conexoes: dict[str, Conexao] = {}
        self.conexao: Conexao | None = None
        self.catalogo: Catalogo | None = None
        self.por_chave: dict[str, ItemRemoto] = {}
        self._minis: dict[str, QPixmap] = {}
        self._grandes: dict[str, QPixmap] = {}
        self._pedidas: set[str] = set()
        self.copiando: dict[str, str] = {}              # chave -> "fila" | "copiando"
        self.copiado: dict[str, str] = {}               # chave -> archiva_transfer_N (nesta sessão)
        self.progresso: dict[str, tuple[int, int]] = {}
        self._cancelar: set[str] = set()
        self._reservados: set[int] = set()
        self._cat = ALL
        self._primeira = True
        self._login_aberto = False
        self._bolinhas: dict[str, tuple[QLabel, QLabel]] = {}   # ident -> (bolinha, palavra) na lista de bibliotecas
        self.tamanho = max(120, min(300, int(self.cfg["thumb_size"] or 168)))

        # ---------------- esquerda: biblioteca escolhida + categorias
        esq = self._coluna_esquerda()
        # ---------------- centro: título, busca e grade (ou boas-vindas)
        centro = self._coluna_centro()
        # ---------------- direita: detalhes
        from .main_window import SideColumn
        dir_ = self.right_col = SideColumn(border_left=True)
        dl = QVBoxLayout(dir_)
        dl.setContentsMargins(28, TITLE_H + 8, 24, 16)
        self.detalhes = Detalhes(self)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setFrameShape(QFrame.NoFrame)
        rolagem.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        rolagem.setStyleSheet("QScrollArea, QScrollArea > QWidget > QWidget {background:transparent;}")
        rolagem.setWidget(self.detalhes)
        dl.addWidget(rolagem)
        dir_.setMinimumWidth(280)

        self.divisor = QSplitter()
        self.divisor.setHandleWidth(1)
        self.divisor.setChildrenCollapsible(False)
        self.divisor.addWidget(esq)
        self.divisor.addWidget(centro)
        self.divisor.addWidget(dir_)
        self.divisor.setStretchFactor(1, 1)
        self.divisor.setSizes([284, 900, 340])
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.paginas = QStackedWidget()
        self.paginas.addWidget(self._pagina_lista())
        self.paginas.addWidget(self.divisor)
        lay.addWidget(self.paginas)

        self._repintar = QTimer(self, singleShot=True, interval=80)
        self._repintar.timeout.connect(self._repintar_tudo)
        self._estado_timer = QTimer(self, interval=4000)
        self._estado_timer.timeout.connect(self._conferir_conexoes)
        self._estado_timer.start()
        self._online_timer = QTimer(self, interval=20000)      # online/offline: confere a cada 20 s
        self._online_timer.timeout.connect(self._verificar_online)
        self._online_timer.start()
        self.corpo.setCurrentIndex(1)
        self._atualizar_seletor()
        self.preencher_lista()

    # ---------------------------------------------------------------- montagem
    def _coluna_esquerda(self) -> QWidget:
        from .main_window import SideColumn
        esq = SideColumn()
        l = QVBoxLayout(esq)
        l.setContentsMargins(14, TITLE_H + 8, 14, 16)
        l.setSpacing(6)
        hh = QHBoxLayout()
        hh.setContentsMargins(12, 0, 8, 0)
        hh.addWidget(ui.heading("Biblioteca da Nuvem", 10))
        hh.addStretch(1)
        l.addLayout(hh)
        self.seletor = QPushButton()
        self.seletor.setCursor(Qt.PointingHandCursor)
        self.seletor.setMinimumHeight(40)
        self.seletor.setStyleSheet("QPushButton{text-align:left; padding:6px 14px; font-size:10.5pt;}")
        self.seletor.clicked.connect(self._menu_bibliotecas)
        l.addWidget(self.seletor)
        sr = QHBoxLayout()
        sr.setContentsMargins(14, 0, 0, 0)
        sr.setSpacing(6)
        self.ponto = QLabel()
        self.ponto.setFixedSize(12, 12)
        self.ponto.setVisible(False)
        sr.addWidget(self.ponto)
        self.palavra = QLabel("")
        self.palavra.setStyleSheet("font-size:9pt;")
        self.palavra.setVisible(False)
        sr.addWidget(self.palavra)
        self.selo = QLabel("")
        self.selo.setStyleSheet(f"color:{theme.LINK.name()}; font-size:9pt;")
        sr.addWidget(self.selo)
        sr.addStretch(1)
        l.addLayout(sr)
        l.addSpacing(6)
        hc = QHBoxLayout()
        hc.setContentsMargins(12, 0, 8, 0)
        hc.addWidget(ui.heading("Categorias", 10))
        hc.addStretch(1)
        self.cat_count = QLabel()
        self.cat_count.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:9pt;")
        hc.addWidget(self.cat_count)
        l.addLayout(hc)
        self.arvore = CategoryTree()
        self.arvore.setHeaderHidden(True)
        self.arvore.setIndentation(14)
        self.arvore.setRootIsDecorated(False)
        self.arvore.setItemDelegate(CategoryDelegate(SimpleNamespace(thumbs=Capas(self)), self.arvore))
        self.arvore.setMouseTracking(True)
        self.arvore.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.arvore.setFrameShape(QFrame.NoFrame)
        self.arvore.currentItemChanged.connect(lambda *_: self._mudou_categoria())
        l.addWidget(self.arvore, 1)
        esq.setMinimumWidth(256)
        return esq

    def _coluna_centro(self) -> QWidget:
        centro = QWidget()
        cl = QVBoxLayout(centro)
        cl.setContentsMargins(36, TITLE_H + 8, 36, 0)
        cl.setSpacing(20)
        trow = QHBoxLayout()
        self.titulo = QLabel("Nuvem")
        self.titulo.setStyleSheet("font-size:21pt;")
        trow.addWidget(self.titulo)
        trow.addStretch(1)
        self.b_atualizar = QPushButton()
        self.b_atualizar.setIcon(ui.icon("atualizar", theme.MUTED, 18))
        self.b_atualizar.setToolTip("Atualizar a lista desta biblioteca")
        self.b_atualizar.setFixedSize(38, 38)
        self.b_atualizar.setCursor(Qt.PointingHandCursor)
        self.b_atualizar.clicked.connect(lambda: self.conexao and self.abrir(self.conexao.ident))
        trow.addWidget(self.b_atualizar, 0, Qt.AlignTop)
        cl.addLayout(trow)
        self.situacao = QLabel()
        self.situacao.setWordWrap(True)
        self.situacao.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:10.5pt;")
        cl.addWidget(self.situacao)
        self.corpo = QStackedWidget()
        cl.addWidget(self.corpo, 1)

        # página 0: boas-vindas (nenhuma biblioteca ainda)
        bv = QWidget()
        bl = QVBoxLayout(bv)
        bl.setAlignment(Qt.AlignCenter)
        bl.setSpacing(12)
        t = QLabel("Acesse a biblioteca de outra pessoa")
        t.setStyleSheet("font-size:15pt;")
        t.setAlignment(Qt.AlignCenter)
        s = QLabel("Cole o convite que você recebeu. Você vê as prévias e copia os modelos que quiser\n"
                   "para a sua biblioteca. Não precisa de conta nem instalar nada.")
        s.setAlignment(Qt.AlignCenter)
        s.setStyleSheet(f"color:{theme.MUTED.name()};")
        entrar = ui.primary(QPushButton("Entrar com um convite…"))
        entrar.setFixedHeight(40)
        entrar.clicked.connect(self.entrar_com_convite)
        como = ui.link_button("Como funciona (passo a passo)")
        como.clicked.connect(lambda: hasattr(self.w, "show_tutorial") and self.w.show_tutorial("nuvem_acessar"))
        bl.addWidget(t)
        bl.addWidget(s)
        bl.addSpacing(6)
        bl.addWidget(entrar, 0, Qt.AlignCenter)
        bl.addWidget(como, 0, Qt.AlignCenter)
        self.corpo.addWidget(bv)

        # página 1: busca + grade
        gr = QWidget()
        gl = QVBoxLayout(gr)
        gl.setContentsMargins(0, 0, 0, 0)
        gl.setSpacing(20)
        brow = QHBoxLayout()
        brow.setSpacing(12)
        self.busca = ui.SearchField("Buscar por nome, categoria ou tag")
        self.busca.setMinimumWidth(220)
        self.busca.edit.textChanged.connect(lambda: self._busca_timer.start())
        self._busca_timer = QTimer(self, singleShot=True, interval=180)
        self._busca_timer.timeout.connect(self.filtrar)
        brow.addWidget(self.busca, 1)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(120, 300)
        self.slider.setValue(self.tamanho)
        self.slider.setFixedWidth(110)
        self.slider.setToolTip("Tamanho dos cartões")
        self.slider.valueChanged.connect(self._mudou_tamanho)
        pequeno = QLabel()
        pequeno.setPixmap(ui.icon_pixmap("biblioteca", theme.FAINT, 13))
        grande = QLabel()
        grande.setPixmap(ui.icon_pixmap("biblioteca", theme.MUTED, 19))
        brow.addSpacing(6)
        brow.addWidget(pequeno)
        brow.addWidget(self.slider)
        brow.addWidget(grande)
        gl.addLayout(brow)
        self.modelo = ItensModel(self)
        self.grade = Grade()
        self.grade.setModel(self.modelo)
        self.grade.setItemDelegate(CartaoDelegate(self))
        self.grade.selectionModel().selectionChanged.connect(self._mudou_selecao)
        self.grade.customContextMenuRequested.connect(self._menu_item)
        self.grade.doubleClicked.connect(lambda ix: self.ampliar(ix.data(Qt.UserRole)))
        self.grade.verticalScrollBar().valueChanged.connect(lambda: self._repintar.start())
        atalho = QShortcut(QKeySequence(Qt.Key_Space), self.grade, context=Qt.WidgetShortcut)
        atalho.activated.connect(self._espaco)
        gl.addWidget(self.grade, 1)
        self.corpo.addWidget(gr)
        return centro

    def _repintar_tudo(self):
        self.grade.viewport().update()
        self.arvore.viewport().update()

    def _mudou_tamanho(self, v: int):
        self.tamanho = v
        self.grade.doItemsLayout()
        self.grade.viewport().update()

    # ---------------------------------------------------------------- bibliotecas salvas
    def _pagina_lista(self) -> QWidget:
        w = QWidget()
        l = QVBoxLayout(w)
        l.setContentsMargins(48, TITLE_H + 8, 48, 28)
        l.setSpacing(14)
        t = QLabel("Nuvem")
        t.setStyleSheet("font-size:21pt;")
        l.addWidget(t)
        sub = QLabel("Bibliotecas de outros computadores compartilhadas com você. Escolha uma para ver os modelos.")
        sub.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:10.5pt;")
        l.addWidget(sub)
        self.lista = QListWidget()
        self.lista.setSpacing(4)
        self.lista.setFrameShape(QFrame.NoFrame)
        self.lista.setStyleSheet("QListWidget{background:transparent; border:none;} "
                                 "QListWidget::item{padding:0px; border-radius:12px; "
                                 "background:rgba(239,226,201,0.05); margin-bottom:8px;} "
                                 "QListWidget::item:selected{background:rgba(239,226,201,0.10);}")
        self.lista.itemDoubleClicked.connect(lambda it: self.abrir(it.data(Qt.UserRole)))
        l.addWidget(self.lista, 1)
        self.vazio = QLabel("Nenhuma biblioteca ainda. Peça um convite a quem compartilha e use "
                            "“Entrar com um convite”. Passo a passo em Aprender › Acessar uma biblioteca da Nuvem.")
        self.vazio.setWordWrap(True)
        self.vazio.setStyleSheet(f"color:{theme.FAINT.name()};")
        l.addWidget(self.vazio)
        bl = QHBoxLayout()
        entrar = ui.primary(QPushButton("Entrar com um convite…"))
        entrar.setFixedHeight(40)
        entrar.clicked.connect(self.entrar_com_convite)
        como = ui.link_button("Como funciona")
        como.clicked.connect(lambda: hasattr(self.w, "show_tutorial") and self.w.show_tutorial("nuvem_acessar"))
        bl.addWidget(entrar)
        bl.addWidget(como)
        bl.addStretch(1)
        l.addLayout(bl)
        return w

    def preencher_lista(self):
        self.lista.clear()
        self._bolinhas.clear()
        salvas = conexoes_salvas(self.cfg)
        for d in salvas:
            c = self.conexoes.get(d.get("id")) or Conexao(d)
            self.conexoes[c.ident] = c
            cat = c.remota_offline().catalogo_salvo()
            extra = f"{len(cat.itens)} modelos" if cat else "ainda não aberta"
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

    def mostrar_lista(self):
        self.preencher_lista()
        self.paginas.setCurrentIndex(0)
        self._verificar_online()

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
        ponto = QLabel()
        ponto.setFixedSize(12, 12)
        palavra = QLabel()
        palavra.setStyleSheet("font-size:9.5pt;")
        self._bolinhas[c.ident] = (ponto, palavra)
        self._pintar_ponto(c)
        titulo = QHBoxLayout()
        titulo.setSpacing(8)
        titulo.addWidget(ponto)
        titulo.addWidget(n)
        titulo.addWidget(palavra)
        titulo.addStretch(1)
        s = QLabel(extra)
        s.setStyleSheet(f"color:{theme.MUTED.name()};")
        col.addStretch(1)
        col.addLayout(titulo)
        col.addWidget(s)
        col.addStretch(1)
        h.addLayout(col, 1)
        abrir = ui.primary(QPushButton("Abrir"))
        abrir.clicked.connect(lambda _c=False, i=c.ident: self.abrir(i))
        h.addWidget(abrir)
        rem = QPushButton("Remover")
        rem.setToolTip("Tira esta biblioteca deste computador")
        rem.clicked.connect(lambda _c=False, i=c.ident: self.remover_biblioteca(i))
        h.addWidget(rem)
        return w

    def _atualizar_seletor(self):
        self.seletor.setText(f"{self.conexao.nome}  ▾" if self.conexao is not None else "Bibliotecas  ▾")
        self.b_atualizar.setVisible(self.conexao is not None)
        self._pintar_ponto(self.conexao)

    # ---------------------------------------------------------------- online / offline
    def _pintar_ponto(self, c: "Conexao | None"):
        """Atualiza a bolinha (verde online, vermelha offline, cinza verificando) desta biblioteca onde ela aparece."""
        if c is None:
            self.ponto.setVisible(False)
            self.palavra.setVisible(False)
            return
        palavra, cor, dica = estado_online(c)
        par = self._bolinhas.get(c.ident)
        if par is not None:
            try:
                par[0].setPixmap(bolinha(cor))
                par[0].setToolTip(dica)
                par[1].setText(palavra)
                par[1].setStyleSheet(f"color:{cor.name()}; font-size:9.5pt;")
                par[1].setToolTip(dica)
            except RuntimeError:       # a linha foi refeita enquanto a resposta chegava
                self._bolinhas.pop(c.ident, None)
        if self.conexao is c:
            self.ponto.setPixmap(bolinha(cor))
            self.ponto.setToolTip(dica)
            self.palavra.setText(palavra)
            self.palavra.setStyleSheet(f"color:{cor.name()}; font-size:9pt;")
            self.palavra.setToolTip(dica)
            self.ponto.setVisible(True)
            self.palavra.setVisible(True)

    def _verificar_online(self, so_lista: bool = False):
        """Confere, num ajudante, se o computador de cada biblioteca está de pé. Na lista, todas; aberta, só a atual."""
        if not self.isVisible():
            return
        if self.paginas.currentIndex() == 0:
            alvo = list(self.conexoes.values())     # as da lista (remover tira da lista e daqui)
        else:
            alvo = [self.conexao]
        for c in alvo:
            if c is None or c.verificando:
                continue
            c.verificando = True

            def feito(_r, c=c):
                c.verificando = False
                self._pintar_ponto(c)
                if self.conexao is c and self.paginas.currentIndex() == 1:
                    if c.online and self.catalogo is None and c.erro == "desligada":
                        self.abrir(c.ident)    # voltou ao ar depois de uma falha: abre de novo sozinho
                    elif self.catalogo is not None and not c.etapa:
                        self.situacao.setText(f"Conectado · {len(self.catalogo.itens)} modelos" if c.online else
                                              "Sem conexão com o computador da biblioteca · mostrando a última lista salva")

            def falhou(_e, c=c):
                c.verificando = False
                c.online = False
                self._pintar_ponto(c)
            segundo_plano.run_async(c.verificar, feito, falhou)

    def _menu_bibliotecas(self):
        salvas = conexoes_salvas(self.cfg)
        m = QMenu(self)
        m.addAction("‹  Todas as bibliotecas").triggered.connect(self.mostrar_lista)
        m.addSeparator()
        for d in salvas:
            c = self.conexoes.get(d.get("id")) or Conexao(d)
            self.conexoes[c.ident] = c
            a = m.addAction(("✔  " if self.conexao is c else "") + c.nome)
            a.setIcon(QIcon(bolinha(estado_online(c)[1], 12)))
            a.setToolTip(estado_online(c)[2])
            a.triggered.connect(lambda _x=False, i=c.ident: self.abrir(i))
        m.addSeparator()
        m.addAction("Entrar com um convite…").triggered.connect(self.entrar_com_convite)
        if self.conexao is not None:
            m.addAction("Diagnóstico da conexão…").triggered.connect(self.diagnostico)
            m.addAction(f"Remover “{self.conexao.nome}” deste PC").triggered.connect(self.remover_biblioteca)
        m.exec(self.seletor.mapToGlobal(QPoint(0, self.seletor.height())))

    def entrar_com_convite(self):
        d = QDialog(self.window())
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
        self.abrir(ident)

    def remover_biblioteca(self, ident: str | None = None):
        c = self.conexoes.get(ident) if ident else self.conexao
        if c is None:
            return
        if QMessageBox.question(self.window(), "Remover", f"Remover “{c.nome}” deste computador?\n\n"
                                "As cópias que você já trouxe para a Entrada continuam lá.") != QMessageBox.Yes:
            return
        c.parar()
        salvas = conexoes_salvas(self.cfg)
        salvas[:] = [x for x in salvas if x.get("id") != c.ident]
        self.cfg.save()
        self.conexoes.pop(c.ident, None)
        if self.conexao is c:
            self.conexao = None
            self.catalogo = None
            self.por_chave.clear()
            self.modelo.set_itens([])
            self.arvore.clear()
            self.detalhes.mostrar(None)
        self.mostrar_lista()

    def mostrar_pagina(self):
        """Ao abrir a aba Nuvem, a primeira tela é a lista de bibliotecas (se nenhuma estiver aberta)."""
        if self.conexao is None:
            self.mostrar_lista()

    def _conferir_conexoes(self):
        c = self.conexao
        if c is None or c.motor is None or not self.isVisible() or self.paginas.currentIndex() != 1:
            return
        segundo_plano.run_async(c.motor.estado, self._estado_motor)

    def _estado_motor(self, e: dict):
        if e.get("estado") == "NeedsLogin" and e.get("url_login") and not getattr(self, "_login_aberto", False):
            self._login_aberto = True
            r = QMessageBox.question(self.window(), "Convite sem chave", "Este convite não trouxe a chave de acesso (ou ela "
                                     "expirou), então este computador pediria uma conta do Tailscale.\n\n"
                                     "O mais simples: peça a quem compartilha um convite novo, criado depois de "
                                     "salvar a chave. Você não precisa de conta.\n\n"
                                     "Quer entrar com uma conta do Tailscale mesmo assim?")
            if r == QMessageBox.Yes:
                QDesktopServices.openUrl(QUrl(e["url_login"]))
        self._ultimo_estado = e
        txt, cor = nuvem_motor.texto_estado(e, "ligar", self.conexao.dados.get("h", "") if self.conexao else "")
        if cor != "ok":
            self.situacao.setText(txt)
        elif self.catalogo is None and self.conexao is not None and self.conexao.etapa:
            # a rede está de pé: mostra em que passo a biblioteca está, em vez de deixar o texto antigo
            self.situacao.setText(f"Rede conectada · {self.conexao.etapa}… ({e.get('segundos', 0)} s)")
        elif (self.catalogo is None and self.conexao is not None and self.conexao.erro == "desligada"
              and e.get("alvo_ok") is True and not self.conexao.etapa and not self.conexao._retentou):
            # a rede ficou pronta depois da falha: tenta abrir de novo sozinho, uma vez
            self.conexao._retentou = True
            self.abrir(self.conexao.ident)

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
        d = QDialog(self.window())
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

    def abrir(self, ident: str):
        c = self.conexoes.get(ident)
        if c is None:
            d = next((s for s in conexoes_salvas(self.cfg) if s.get("id") == ident), None)
            if d is None:
                return
            c = self.conexoes[ident] = Conexao(d)
        self.conexao = c
        self.cfg.values["nuvem_ultima"] = ident
        self.catalogo = None
        self._minis.clear()
        self._grandes.clear()
        self._pedidas.clear()
        self.por_chave.clear()
        self.titulo.setText(c.nome)
        self.selo.setText("Nuvem · só leitura")
        self._atualizar_seletor()
        self.corpo.setCurrentIndex(1)
        self.paginas.setCurrentIndex(1)
        salvo = c.remota_offline().catalogo_salvo()
        if salvo:
            self._mostrar_catalogo(salvo)
            self.situacao.setText(f"Mostrando a lista salva ({time.strftime('%d/%m %H:%M', time.localtime(salvo.recebido))})"
                                  " · conectando…")
        else:
            self.modelo.set_itens([])
            self.arvore.clear()
            self.detalhes.mostrar(None)
            self.situacao.setText("Conectando… (a primeira vez pode levar alguns segundos)")
        c.erro = ""
        c._retentou = False
        self._pintar_ponto(c)

        def buscar():
            c.etapa = "Ligando o motor de rede"
            r = c.preparar()
            c.etapa = "Falando com o computador da biblioteca"
            for tentativa in range(3):          # a primeira conversa pela rede às vezes falha; tenta de novo
                try:
                    info = r.info()
                    break
                except Desligada:
                    if tentativa == 2:
                        raise
                    time.sleep(3)
            c.etapa = "Baixando a lista de modelos"
            cat = r.catalogo()
            c.etapa = ""
            return cat, info

        def ok(res):
            cat, info = res
            c.erro = ""
            c.online = True
            self._pintar_ponto(c)
            if self.conexao is not c:
                return
            self._mostrar_catalogo(cat)
            papel = info.get("papel") or "leitor"
            self.selo.setText(f"Nuvem · {papel}" + (" · só leitura" if papel == "leitor" else ""))
            self.situacao.setText(f"Conectado · {len(cat.itens)} modelos")

        def erro(e):
            if isinstance(e, (SemAcesso, Desligada)):
                c.online = False        # outro tipo de erro (lista, por exemplo) não quer dizer que está offline
            if self.conexao is not c:
                self._pintar_ponto(c)
                return
            c.erro = "sem acesso" if isinstance(e, SemAcesso) else "desligada"
            self._pintar_ponto(c)
            c.etapa = ""      # senão o aviso de andamento apagaria a mensagem de erro
            c.ultimo_erro = f"{type(e).__name__}: {e}" + (f" · causa: {e.__cause__!r}" if e.__cause__ else "")
            if isinstance(e, SemAcesso):
                self.situacao.setText(str(e))
            elif isinstance(e, Desligada):
                self.situacao.setText(("O computador da biblioteca está desligado ou com o Archiva fechado. "
                                       if salvo else "Não consegui conectar agora. ")
                                      + "As prévias já vistas continuam disponíveis.")
            else:
                self.situacao.setText(f"Erro ao conectar: {e}")
        segundo_plano.run_async(buscar, ok, erro)

    # ---------------------------------------------------------------- catálogo, categorias e busca
    def _mostrar_catalogo(self, cat: Catalogo):
        sel = self._cat
        self.catalogo = cat
        self.por_chave = {i.key: i for i in cat.itens}
        capas: dict[str, ItemRemoto] = {}          # categoria -> modelo mais novo com prévia (para a miniatura)
        for i in cat.itens:
            if not i.tem_previa:
                continue
            partes = i.category.split("/")
            for n in range(1, len(partes) + 1):
                k = "/".join(partes[:n])
                atual = capas.get(k)
                if atual is None or i.added_time > atual.added_time:
                    capas[k] = i
        self.arvore.blockSignals(True)
        self.arvore.clear()
        todas = QTreeWidgetItem(["Todas as categorias"])
        todas.setData(0, Qt.UserRole, ALL)
        todas.setData(0, COUNT_ROLE, len(cat.itens))
        todas.setData(0, COVER_ROLE, "*")
        self.arvore.addTopLevelItem(todas)
        alvo = todas

        def add(pai, c):
            nonlocal alvo
            item = QTreeWidgetItem([c.name.capitalize()])
            item.setData(0, Qt.UserRole, c.key)
            item.setData(0, COUNT_ROLE, c.quantidade)
            if pai is None:
                capa = capas.get(c.key)
                item.setData(0, COVER_ROLE, capa.key if capa else None)
            if c.key == sel:
                alvo = item
            (pai.addChild(item) if pai is not None else self.arvore.addTopLevelItem(item))
            for s in sorted(c.children, key=lambda x: natural_key(x.name)):
                add(item, s)
        for c in sorted(cat.categorias, key=lambda x: natural_key(x.name)):
            add(None, c)
        self.cat_count.setText(f"{len(cat.categorias)}")
        self.arvore.setCurrentItem(alvo)
        self.arvore.blockSignals(False)
        self._cat = alvo.data(0, Qt.UserRole)
        self.filtrar()

    def _mudou_categoria(self):
        it = self.arvore.currentItem()
        if it is None:
            return
        self._cat = it.data(0, Qt.UserRole) or ALL
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
        else:
            self.detalhes.mostrar(None)

    def _mudou_selecao(self, *_a):
        sel = self.grade.selectionModel().selectedIndexes()
        if not sel:
            self.detalhes.mostrar(None)
            return
        atual = self.grade.currentIndex()
        ix = atual if atual.isValid() and atual in sel else sel[0]
        self.detalhes.mostrar(ix.data(Qt.UserRole), len(sel))

    def selecionados(self) -> list[ItemRemoto]:
        itens = [ix.data(Qt.UserRole) for ix in sorted(self.grade.selectionModel().selectedIndexes(),
                                                       key=lambda i: i.row())]
        return itens

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

        def buscar():
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
        segundo_plano.run_async(buscar, pronto)

    def _espaco(self):
        ix = self.grade.currentIndex()
        if ix.isValid():
            self.ampliar(ix.data(Qt.UserRole))

    def ampliar(self, it: ItemRemoto | None):
        """Espaço / clique na prévia: abre a prévia grande (a mesma janela da Biblioteca)."""
        c = self.conexao
        if it is None or c is None:
            return
        if not it.tem_previa:
            self.situacao.setText(f"{it.name} não tem prévia.")
            return

        def buscar():
            r = c.remota or c.remota_offline()
            try:
                return r.previa_arquivo(it, 1600)
            except (Desligada, SemAcesso):
                return None

        def pronto(caminho):
            if not caminho:
                self.situacao.setText("Não consegui abrir a prévia agora (sem conexão).")
                return
            from .main_window import ImageViewer
            ImageViewer(self.window(), caminho, it.name).exec()
        segundo_plano.run_async(buscar, pronto)

    # ---------------------------------------------------------------- copiar para a minha biblioteca
    def estado_item(self, it: ItemRemoto) -> str:
        e = self.copiando.get(it.key)
        if e:
            return e
        return "copiado" if it.key in self.copiado else "nuvem"

    def pct(self, it: ItemRemoto) -> str:
        feito, total = self.progresso.get(it.key, (0, 0))
        if total:
            return f"{feito * 100 // max(total, 1)}%"
        return f"{feito / 1024 ** 2:.0f} MB" if feito else ""

    def _menu_item(self, pos):
        ix = self.grade.indexAt(pos)
        if ix.isValid() and not self.grade.selectionModel().isSelected(ix):
            self.grade.setCurrentIndex(ix)
        m = self._montar_menu()
        if m is not None:
            m.exec(self.grade.viewport().mapToGlobal(pos))

    def _montar_menu(self) -> QMenu | None:
        itens = self.selecionados()
        if not itens:
            return None
        m = QMenu(self)
        n = len(itens)
        a = m.addAction("Copiar para a minha biblioteca" if n == 1 else f"Copiar {n} modelos para a minha biblioteca")
        a.triggered.connect(self.copiar_selecionados)
        if n == 1:
            v = m.addAction("Ampliar prévia   (Espaço)")
            v.triggered.connect(lambda: self.ampliar(itens[0]))
        if any(i.key in self.copiando for i in itens):
            m.addSeparator()
            m.addAction("Cancelar a cópia").triggered.connect(lambda: [self.cancelar(i) for i in itens])
        return m

    def _entrada(self) -> str | None:
        raiz = self.cfg["library_root"]
        if not raiz or not os.path.isdir(raiz):
            QMessageBox.information(self.window(), "Copiar para a minha biblioteca",
                                    "Escolha primeiro a sua biblioteca (pasta dos modelos) nas Configurações.")
            return None
        from . import intake
        try:
            return intake.entry_path(raiz)
        except OSError as e:
            QMessageBox.warning(self.window(), "Copiar para a minha biblioteca",
                                f"Não consegui abrir a pasta Entrada:\\n{e}")
            return None

    def _proximo_numero(self) -> int:
        n = int(self.cfg.values.get("nuvem_transferencias") or 0)
        n = max([n] + list(self._reservados)) + 1
        self._reservados.add(n)
        return n

    def copiar_selecionados(self):
        itens = [i for i in self.selecionados() if self.estado_item(i) in ("nuvem", "copiado")]
        if not itens or self.conexao is None:
            return
        entrada = self._entrada()
        if entrada is None:
            return
        for it in itens:
            self.copiar(it, entrada)

    def copiar(self, it: ItemRemoto, entrada: str):
        c = self.conexao
        if c is None or it.key in self.copiando:
            return
        numero = self._proximo_numero()
        self.copiando[it.key] = "fila"
        self.progresso[it.key] = (0, 0)
        self._cancelar.discard(it.key)
        self._atualizar(it)
        ultimo = [0.0]

        def avisar(feito, total):
            if time.time() - ultimo[0] > 0.25:
                ultimo[0] = time.time()
                segundo_plano.post(lambda _a: self._progresso(it, feito, total))

        def trabalho():
            r = c.preparar()
            segundo_plano.post(lambda _a: self._comecou(it))
            n = numero
            while any(f.startswith(f"archiva_transfer_{n}.") for f in os.listdir(entrada)):
                n += 1                                   # nunca sobrescreve o que já está na Entrada
            return n, r.copiar_para_entrada(it, entrada, n, avisar, lambda: it.key in self._cancelar)

        def ok(res):
            n, base = res
            self._reservados.discard(numero)
            self.cfg.values["nuvem_transferencias"] = max(int(self.cfg.values.get("nuvem_transferencias") or 0), n)
            self.cfg.save()
            self.copiando.pop(it.key, None)
            self.copiado[it.key] = base
            self._atualizar(it)
            self.w.statusBar().showMessage(f"{it.name} foi para a Entrada como {base}. Classifique na aba Entrada.",
                                           8000)
            if hasattr(self.w, "entrada"):
                self.w.entrada.refresh()

        def falhou(e):
            self._reservados.discard(numero)
            self.copiando.pop(it.key, None)
            self._cancelar.discard(it.key)
            self._atualizar(it)
            if isinstance(e, InterruptedError):
                return
            if isinstance(e, (Desligada, SemAcesso)):
                msg = str(e)
            else:
                msg = f"Não consegui copiar {it.name}:\\n{e}"
            QMessageBox.warning(self.window(), "Copiar para a minha biblioteca", msg)
        segundo_plano.run_async(trabalho, ok, falhou)

    def cancelar(self, it: ItemRemoto):
        if it.key in self.copiando:
            self._cancelar.add(it.key)

    def _comecou(self, it):
        if it.key in self.copiando:
            self.copiando[it.key] = "copiando"
            self._atualizar(it)

    def _progresso(self, it, feito, total):
        self.progresso[it.key] = (feito, total)
        self._atualizar(it)

    def _atualizar(self, it):
        self.modelo.refresh_key(it.key)
        if self.detalhes.it is not None and self.detalhes.it.key == it.key:
            self.detalhes.atualizar_estado()

    # ---------------------------------------------------------------- ciclo de vida
    def showEvent(self, e):
        super().showEvent(e)
        self.mostrar_pagina()

    def encerrar(self):
        """Ao fechar o programa: para as cópias em andamento e desliga os motores de rede."""
        for k in list(self.copiando):
            self._cancelar.add(k)
        for c in self.conexoes.values():
            c.parar()
