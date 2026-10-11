"""Tutoriais: boas-vindas ao abrir, página "Aprender" e "Novidades" depois de atualizar.

Cada tutorial tem uma animação curta (recursos/tutoriais/<id>.webp, gravada do próprio Archiva pelo
roteiro empacotamento/gravar_tutoriais.py) e um texto. Para acrescentar um tutorial numa versão nova:
coloque um item em TUTORIAIS com 'desde' = a versão; ele aparece com o selo "Novo" e entra no
"Novidades" de quem atualizar.
"""
from __future__ import annotations

from PySide6.QtCore import QEvent, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QImageReader, QLinearGradient, QMovie, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QSizePolicy, QVBoxLayout, QWidget)

from . import theme, ui
from .config import app_dir

GRUPOS = ["Primeiros passos", "Organizar a biblioteca", "Trabalho em equipe"]

TUTORIAIS = [
    dict(id="inicio", grupo="Primeiros passos", desde="0.10.0",
         titulo="Conheça o Archiva",
         resumo="Início, menu lateral e categorias.",
         intro="O Archiva organiza a sua biblioteca de modelos 3D sem mudar o jeito que ela já é guardada: "
               "as mesmas pastas por categoria, só que fáceis de ver, achar e usar.",
         passos=["No <b>Início</b> estão os modelos que entraram por último, os que você usou há pouco e as "
                 "tags mais usadas.",
                 "Na <b>Biblioteca</b> fica tudo. Clique numa categoria à esquerda para ver só ela; o número ao "
                 "lado mostra quantos itens tem.",
                 "Selecione um cartão para ver, à direita, a prévia, a situação do item e os arquivos .max."],
         dica="O menu lateral leva também para Tags, Entrada e Aprender. Configurações fica embaixo, ao lado "
              "do seu perfil."),
    dict(id="buscar", grupo="Primeiros passos", desde="0.10.0",
         titulo="Encontrar um modelo",
         resumo="Busca por nome, categoria ou tag.",
         intro="A busca procura ao mesmo tempo no nome do item, na categoria e nas tags. Não precisa acertar "
               "acento nem maiúscula.",
         passos=["Digite na caixa de busca: a lista se ajusta enquanto você escreve.",
                 "Use os filtros <b>Todos · Prontos · Compactados · Fora do padrão</b> para ver só o que "
                 "interessa agora.",
                 "Combine com uma categoria à esquerda para fechar ainda mais a busca."],
         dica="Várias palavras juntas filtram mais: “cadeira madeira” mostra só cadeiras com a tag madeira."),
    dict(id="arrastar", grupo="Primeiros passos", desde="0.10.0",
         titulo="Levar para o 3ds Max",
         resumo="Arraste o cartão direto para a viewport.",
         intro="Itens <b>prontos</b> (com a bolinha verde) vão direto do Archiva para a cena, sem procurar "
               "arquivo em pasta nenhuma.",
         passos=["Clique e segure o cartão do item.",
                 "Arraste até a viewport do 3ds Max e solte.",
                 "O Max pergunta se quer abrir, juntar à cena (Merge) ou referenciar (XRef)."],
         dica="Em Configurações › Uso, escolha “Merge com texturas” para o modelo já entrar apontando para a "
              "própria pasta MAPS."),
    dict(id="extrair", grupo="Organizar a biblioteca", desde="0.10.0",
         titulo="Extrair compactados",
         resumo="Transforme .rar e .zip em pasta pronta para usar.",
         intro="Modelos baixados chegam compactados. O Archiva extrai e já deixa tudo no padrão da "
               "biblioteca, ao lado da prévia.",
         passos=["Selecione um ou vários itens <b>compactados</b> (bolinha laranja).",
                 "Clique em <b>Extrair para a biblioteca</b>. Dá para continuar usando o programa enquanto "
                 "ele trabalha.",
                 "No fim, o item vira uma pasta com o .max na raiz e as texturas em MAPS."],
         dica="O compactado original vai para o backup por um tempo, e as senhas que já funcionaram são "
              "testadas sozinhas nos próximos."),
    dict(id="organizar", grupo="Organizar a biblioteca", desde="0.10.0",
         titulo="Organizar pastas fora do padrão",
         resumo="Deixe todas as pastas iguais, sem perder nada.",
         intro="Pastas montadas à mão costumam ficar diferentes umas das outras. O Archiva arruma cada uma "
               "dentro dela mesma, sem renomear nenhuma textura.",
         passos=["Clique no filtro <b>Fora do padrão</b> para ver só as pastas que precisam de ajuste.",
                 "Selecione e clique em <b>Organizar pasta</b>.",
                 "No fim, revise o que pode ser removido: versões V-Ray, FBX e OBJ que não serão usadas."],
         dica="O que for removido na revisão vai para _DESCARTADOS, então ainda dá para desfazer pelo "
              "histórico."),
    dict(id="entrada", grupo="Organizar a biblioteca", desde="0.10.0",
         titulo="Receber downloads novos",
         resumo="Classifique o que chegou na Entrada.",
         intro="A pasta <b>_ENTRADA</b> é a porta da biblioteca: tudo que chega novo passa por ela antes de "
               "ganhar nome e lugar.",
         passos=["Salve o download (compactado + imagem com o mesmo nome) em _ENTRADA.",
                 "Na página <b>Entrada</b>, selecione o item e escolha a categoria.",
                 "Clique em <b>Classificar</b>: ele ganha o próximo número (ex.: LUMINARIA 11) e vai para o "
                 "lugar certo."],
         dica="Se a imagem parecer com algo que já existe na categoria, o Archiva avisa antes, para não "
              "guardar o mesmo modelo duas vezes."),
    dict(id="tags", grupo="Organizar a biblioteca", desde="0.10.0",
         titulo="Tags e grupos",
         resumo="Marque modelos para achar depois.",
         intro="Tags são etiquetas livres, como “madeira”, “sala” ou “cliente X”. Um item pode ter quantas "
               "precisar.",
         passos=["Selecione um ou vários itens na Biblioteca.",
                 "No painel da direita, escreva a tag e aperte <b>Enter</b>. Para várias de uma vez, separe "
                 "por vírgula.",
                 "Na página <b>Tags</b>, cada tag vira uma pasta: dá para juntar em grupos, renomear e "
                 "escolher a capa."],
         dica="As tags valem para todos que usam a mesma biblioteca, então combine com a equipe um jeito "
              "de nomear."),
    dict(id="equipe", grupo="Trabalho em equipe", desde="0.10.0",
         titulo="Trabalhar em equipe",
         resumo="Biblioteca no servidor, tags de todos e itens em uso.",
         intro="Várias pessoas podem usar a mesma biblioteca ao mesmo tempo, no escritório ou pelo servidor, "
               "sem atrapalhar umas às outras.",
         passos=["Tags, grupos, capas e novidades são os mesmos para todos e se atualizam sozinhos em poucos "
                 "segundos.",
                 "Quando alguém está extraindo, organizando ou classificando um item, ele aparece "
                 "<b>em uso</b> com o nome da pessoa.",
                 "Os botões desse item voltam assim que a pessoa termina."],
         dica="Clique no seu perfil, no menu lateral, para trocar o nome, a cor ou a foto."),
    dict(id="historico", grupo="Trabalho em equipe", desde="0.10.0",
         titulo="Histórico e desfazer",
         resumo="Volte atrás numa alteração.",
         intro="Tudo que muda arquivos na biblioteca fica registrado: quem fez, de qual computador e quando.",
         passos=["Clique no seu perfil e escolha <b>Minhas alterações</b>.",
                 "Encontre a alteração e clique em <b>Desfazer</b>: os arquivos voltam para onde estavam.",
                 "O administrador vê o histórico de todos e também pode desfazer."],
         dica="Só dá para desfazer enquanto ninguém mexeu nos mesmos arquivos depois; extrações, enquanto "
              "o compactado ainda está no backup."),
    dict(id="atualizar", grupo="Trabalho em equipe", desde="0.10.0",
         titulo="Atualizações",
         resumo="Versões novas chegam sozinhas.",
         intro="O Archiva confere sozinho, ao abrir, se saiu uma versão nova.",
         passos=["Quando houver, aparece <b>Atualizar</b> no rodapé.",
                 "Um clique baixa, instala e reabre o programa em menos de um minuto.",
                 "Suas configurações, tags e o histórico continuam iguais."],
         dica="O que chegar de novo em cada versão aparece aqui em Aprender, com o selo Novo."),
]

CARD_W = 300
BOAS_VINDAS = ["inicio", "buscar", "arrastar", "extrair", "entrada", "tags", "equipe"]
BY_ID = {t["id"]: t for t in TUTORIAIS}


def _v(s: str) -> tuple:
    import re
    return tuple(int(x) for x in re.findall(r"\d+", s or ""))[:3] or (0,)


def anim_path(tid: str) -> str:
    return str(app_dir() / "app" / "recursos" / "tutoriais" / f"{tid}.webp")


def is_new(t: dict, current: str, seen: list) -> bool:
    return _v(t["desde"])[:2] == _v(current)[:2] and t["id"] not in seen


def newer_than(version: str) -> list[dict]:
    return [t for t in TUTORIAIS if _v(t["desde"]) > _v(version)]


_thumbs: dict[str, QPixmap] = {}


def thumbnail(tid: str) -> QPixmap | None:
    if tid not in _thumbs:
        r = QImageReader(anim_path(tid))
        n = r.imageCount()
        if n > 2:                       # um quadro do meio (o primeiro é parecido em todos)
            r.jumpToImage(int(n * 0.6))
        img = r.read()
        _thumbs[tid] = QPixmap.fromImage(img) if not img.isNull() else None
    return _thumbs[tid]


# ------------------------------------------------------------------ animação com cantos arredondados
class AnimView(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.movie: QMovie | None = None
        self.tid = ""

    def set_tutorial(self, tid: str):
        if self.movie:
            self.movie.stop()
            self.movie.deleteLater()
        self.tid = tid
        self.movie = QMovie(anim_path(tid))
        self.movie.setCacheMode(QMovie.CacheAll)
        self.movie.frameChanged.connect(self.update)
        if self.movie.isValid():
            self.movie.start()
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 14, 14)
        p.setClipPath(path)
        pm = self.movie.currentPixmap() if self.movie and self.movie.isValid() else QPixmap()
        if not pm.isNull():
            sz = pm.size().scaled(self.size(), Qt.KeepAspectRatioByExpanding)
            p.drawPixmap(QRectF((self.width() - sz.width()) / 2, (self.height() - sz.height()) / 2,
                                sz.width(), sz.height()), pm, QRectF(pm.rect()))
        else:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0, QColor("#2f1a1a"))
            g.setColorAt(1, QColor("#1b1612"))
            p.fillPath(path, g)
            p.drawPixmap(int(r.center().x() - 24), int(r.center().y() - 24),
                         ui.icon_pixmap("aprender", theme.MUTED, 48, 1.4))
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 236, 210, 40), 1))
        p.setBrush(Qt.NoBrush)
        p.drawPath(path)


class _Dots(QWidget):
    def __init__(self):
        super().__init__()
        self.n, self.i = 1, 0
        self.setFixedHeight(12)

    def set(self, n, i):
        self.n, self.i = n, i
        self.setFixedWidth(max(1, n - 1) * 12 + 16)
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        x = 0.0
        for k in range(self.n):
            w = 16 if k == self.i else 6
            p.setBrush(theme.HILITE if k == self.i else QColor(255, 236, 210, 55))
            p.drawRoundedRect(QRectF(x, 3, w, 6), 3, 3)
            x += w + 6


class _Card(QFrame):
    """Cartão opaco do tutorial (mesmo fundo do programa, borda clara)."""

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 20, 20)
        g = QLinearGradient(r.topLeft(), r.bottomRight())
        g.setColorAt(0, QColor("#221a15"))
        g.setColorAt(1, QColor("#17130f"))
        p.fillPath(path, g)
        p.setPen(QPen(QColor(255, 236, 210, 38), 1))
        p.drawPath(path)


TEXT_W = 430


class _Step(QWidget):
    """Passo numerado: número num círculo + texto."""

    def __init__(self, n: int, text: str):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        num = QLabel(str(n))
        num.setFixedSize(26, 26)
        num.setAlignment(Qt.AlignCenter)
        num.setStyleSheet(f"color:{theme.HILITE.name()}; font-size:9.5pt; border:1px solid "
                          f"rgba(227,207,169,0.55); border-radius:13px; background:rgba(227,207,169,0.07);")
        lay.addWidget(num, 0, Qt.AlignTop)
        lbl = QLabel(f"<p style='line-height:145%'>{text}</p>")
        lbl.setWordWrap(True)
        lbl.setTextFormat(Qt.RichText)
        lbl.setStyleSheet(f"color:{theme.TEXT.name()}; font-size:10.4pt; margin-top:2px;")
        lay.addWidget(lbl, 1)


class _Tip(QFrame):
    """Caixa de dica com filete dourado à esquerda."""

    def __init__(self, text: str):
        super().__init__()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 14, 16, 15)
        lay.setSpacing(5)
        h = QLabel("Dica")
        h.setStyleSheet(f"color:{theme.HILITE.name()}; font-size:9pt;")
        lay.addWidget(h)
        t = QLabel(f"<p style='line-height:140%'>{text}</p>")
        t.setWordWrap(True)
        t.setTextFormat(Qt.RichText)
        t.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:9.8pt;")
        lay.addWidget(t)

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        path = QPainterPath()
        path.addRoundedRect(r, 12, 12)
        p.fillPath(path, QColor(255, 236, 210, 13))
        p.setPen(QPen(QColor(255, 236, 210, 28), 1))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(theme.HILITE)
        p.drawRoundedRect(QRectF(r.left() + 8, r.top() + 14, 3, r.height() - 28), 1.5, 1.5)


class TutorialOverlay(QWidget):
    """Escurece a janela e mostra os tutoriais um por um (boas-vindas, novidades ou um tutorial avulso)."""
    closed = Signal()
    viewed = Signal(str)

    def __init__(self, host: QWidget, ids: list[str], kicker: str, show_optout: bool = False,
                 optout_checked: bool = True, start: int = 0):
        super().__init__(host)
        self.host = host
        self.ids = [i for i in ids if i in BY_ID]
        self.kicker = kicker
        self.i = max(0, min(start, len(self.ids) - 1))
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setFocusPolicy(Qt.StrongFocus)

        self.card = _Card(self)
        outer = QVBoxLayout(self.card)
        outer.setContentsMargins(40, 28, 36, 30)
        outer.setSpacing(24)
        top = QHBoxLayout()
        self.kick = QLabel()
        self.kick.setStyleSheet(f"color:{theme.LINK.name()}; font-size:9.5pt; letter-spacing:0.6px;")
        top.addWidget(self.kick)
        top.addStretch(1)
        x = QPushButton()
        x.setIcon(ui.icon("fechar", theme.MUTED, 18))
        x.setIconSize(QSize(18, 18))
        x.setFixedSize(34, 34)
        x.setProperty("flat", True)
        x.setCursor(Qt.PointingHandCursor)
        x.setToolTip("Fechar (Esc)")
        x.clicked.connect(self.finish)
        top.addWidget(x)
        outer.addLayout(top)

        body = QHBoxLayout()
        body.setSpacing(46)
        self.anim = AnimView()
        self.anim.setFixedSize(600, 375)
        body.addWidget(self.anim, 0, Qt.AlignVCenter)
        self.textcol = QWidget()
        self.textcol.setFixedWidth(TEXT_W)
        self.col = QVBoxLayout(self.textcol)
        self.col.setContentsMargins(0, 0, 0, 0)
        self.col.setSpacing(0)
        body.addWidget(self.textcol, 0, Qt.AlignTop)
        outer.addLayout(body, 1)

        bottom = QHBoxLayout()
        bottom.setSpacing(12)
        self.optout = QCheckBox("Não mostrar ao abrir o Archiva (fica em Aprender)")
        self.optout.setChecked(optout_checked)
        self.optout.setVisible(show_optout)
        bottom.addWidget(self.optout)
        bottom.addStretch(1)
        self.dots = _Dots()
        bottom.addWidget(self.dots)
        bottom.addSpacing(10)
        self.back = QPushButton("Voltar")
        self.back.clicked.connect(lambda: self.go(self.i - 1))
        self.next = ui.primary(QPushButton("Próximo"))
        self.next.setMinimumWidth(130)
        self.next.clicked.connect(lambda: self.go(self.i + 1) if self.i < len(self.ids) - 1 else self.finish())
        bottom.addWidget(self.back)
        bottom.addWidget(self.next)
        outer.addLayout(bottom)

        host.installEventFilter(self)
        self.setGeometry(host.rect())
        self.go(self.i)
        self.show()
        self.raise_()
        self.setFocus()

    def go(self, i: int):
        if not self.ids:
            return
        self.i = max(0, min(i, len(self.ids) - 1))
        t = BY_ID[self.ids[self.i]]
        n = len(self.ids)
        self.kick.setText(f"{self.kicker}  ·  {self.i + 1} de {n}" if n > 1 else self.kicker)
        self._fill_text(t)
        self.anim.set_tutorial(t["id"])
        self.dots.set(n, self.i)
        self.dots.setVisible(n > 1)
        self.back.setVisible(self.i > 0)
        self.next.setText("Próximo" if self.i < n - 1 else ("Começar" if self.optout.isVisible() else "Fechar"))
        self.viewed.emit(t["id"])
        self._place()
        from PySide6.QtCore import QTimer
        QTimer.singleShot(0, self._place)

    def _fill_text(self, t: dict):
        while self.col.count():
            it = self.col.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        title = QLabel(t["titulo"])
        title.setWordWrap(True)
        title.setStyleSheet("font-size:22pt;")
        self.col.addWidget(title)
        self.col.addSpacing(12)
        intro = QLabel(f"<p style='line-height:150%'>{t['intro']}</p>")
        intro.setWordWrap(True)
        intro.setTextFormat(Qt.RichText)
        intro.setStyleSheet(f"color:{theme.MUTED.name()}; font-size:10.6pt;")
        self.col.addWidget(intro)
        self.col.addSpacing(26)
        head = QLabel("COMO FAZER")
        head.setStyleSheet(f"color:{theme.LINK.name()}; font-size:8.3pt; letter-spacing:1.6px;")
        self.col.addWidget(head)
        self.col.addSpacing(14)
        for k, passo in enumerate(t["passos"], 1):
            self.col.addWidget(_Step(k, passo))
            self.col.addSpacing(14)
        if t.get("dica"):
            self.col.addSpacing(10)
            self.col.addWidget(_Tip(t["dica"]))
        for wdg in self.textcol.findChildren(QWidget):     # aplica fonte/estilo antes de medir a altura
            wdg.ensurePolished()

    def _place(self):
        if not self.width():
            return
        cw = max(860, min(1160, self.width() - 64))
        aw = cw - 40 - 36 - 46 - TEXT_W
        self.anim.setFixedSize(aw, int(aw / 1.6))
        self.card.setFixedWidth(cw)
        self.col.invalidate()
        col_h = self.col.totalHeightForWidth(TEXT_W) if self.col.hasHeightForWidth() else self.col.sizeHint().height()
        bottom_h = max(self.next.sizeHint().height(), 34)
        h = 28 + 34 + 24 + max(self.anim.height(), col_h) + 24 + bottom_h + 30
        self.card.setFixedHeight(min(h, self.height() - 40))
        self.card.move((self.width() - self.card.width()) // 2, (self.height() - self.card.height()) // 2)

    def finish(self):
        if self.anim.movie:
            self.anim.movie.stop()
        self.host.removeEventFilter(self)
        self.hide()
        self.closed.emit()
        self.deleteLater()

    def eventFilter(self, obj, ev):
        if obj is self.host and ev.type() == QEvent.Resize:
            self.setGeometry(self.host.rect())
        return False

    def resizeEvent(self, e):
        self._place()

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Escape:
            self.finish()
        elif e.key() in (Qt.Key_Right, Qt.Key_Return, Qt.Key_Enter):
            self.next.click()
        elif e.key() == Qt.Key_Left and self.i > 0:
            self.go(self.i - 1)

    def mousePressEvent(self, e):
        if not self.card.geometry().contains(e.position().toPoint()):
            self.finish()

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(8, 6, 4, 175))


# ------------------------------------------------------------------ página Aprender
class _TutorialCard(QWidget):
    clicked = Signal(str)

    def __init__(self, t: dict, new: bool):
        super().__init__()
        self.t, self.new = t, new
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(CARD_W, int((CARD_W - 20) / 1.6) + 100)
        self._hover = False

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.clicked.emit(self.t["id"])

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)
        r = QRectF(self.rect()).adjusted(1, 1, -1, -1)
        theme.paint_glass(p, r, 16, 1.0, self._hover)
        img = QRectF(r.left() + 10, r.top() + 10, r.width() - 20, (r.width() - 20) / 1.6)
        path = QPainterPath()
        path.addRoundedRect(img, 11, 11)
        p.save()
        p.setClipPath(path)
        pm = thumbnail(self.t["id"])
        if pm:
            p.fillPath(path, QColor(20, 15, 12))
            sz = pm.size().scaled(img.size().toSize(), Qt.KeepAspectRatio)
            p.drawPixmap(QRectF(img.center().x() - sz.width() / 2, img.center().y() - sz.height() / 2,
                                sz.width(), sz.height()), pm, QRectF(pm.rect()))
        else:
            p.fillPath(path, QColor(255, 236, 210, 14))
        p.restore()
        # botão de play
        c = img.center()
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(20, 14, 10, 170 if self._hover else 120))
        p.drawEllipse(c, 22, 22)
        tri = QPainterPath()
        tri.moveTo(c.x() - 6, c.y() - 9)
        tri.lineTo(c.x() + 10, c.y())
        tri.lineTo(c.x() - 6, c.y() + 9)
        tri.closeSubpath()
        p.fillPath(tri, QColor("#f1e9dc"))
        if self.new:
            f = theme.ui_font(7.5, 700)
            p.setFont(f)
            pill = QRectF(img.left() + 8, img.top() + 8, 46, 18)
            pp = QPainterPath()
            pp.addRoundedRect(pill, 9, 9)
            p.fillPath(pp, theme.HILITE)
            p.setPen(QColor("#26150c"))
            p.drawText(pill, Qt.AlignCenter, "Novo")
        y = img.bottom() + 12
        p.setPen(theme.TEXT)
        p.setFont(theme.ui_font(11))
        p.drawText(QRectF(r.left() + 14, y, r.width() - 28, 22), Qt.AlignLeft | Qt.AlignVCenter, self.t["titulo"])
        p.setPen(theme.MUTED)
        p.setFont(theme.ui_font(9.2))
        p.drawText(QRectF(r.left() + 14, y + 24, r.width() - 28, 40), Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                   self.t["resumo"])


class AprenderPage(QWidget):
    open_tutorial = Signal(str)

    def __init__(self, window):
        super().__init__()
        self.w = window
        lay = QVBoxLayout(self)
        from .janela import TITLE_H
        lay.setContentsMargins(40, TITLE_H + 8, 40, 24)
        lay.setSpacing(6)
        head = QHBoxLayout()
        t = QLabel("Aprender")
        t.setStyleSheet("font-size:24pt;")
        head.addWidget(t)
        head.addStretch(1)
        self.tour = ui.primary(QPushButton("Ver as boas-vindas"))
        self.tour.clicked.connect(lambda: self.w.show_onboarding(manual=True))
        head.addWidget(self.tour, 0, Qt.AlignBottom)
        lay.addLayout(head)
        s = QLabel("Tutoriais curtos de cada parte do Archiva. A cada atualização, o que for novo aparece aqui "
                   "com o selo Novo.")
        s.setStyleSheet(f"color:{theme.MUTED.name()};")
        lay.addWidget(s)
        lay.addSpacing(14)
        self.area = QScrollArea()
        self.area.setWidgetResizable(True)
        self.area.setFrameShape(QScrollArea.NoFrame)
        self.area.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
        lay.addWidget(self.area, 1)
        self._cols = 0
        self.refresh()

    def refresh(self):
        seen = list(self.w.cfg["tutoriais_vistos"] or [])
        from .config import version
        cur = version()
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 10, 10)
        v.setSpacing(10)
        cols = max(1, (self.area.viewport().width() - 10) // (CARD_W + 16))
        self._cols = cols
        for g in GRUPOS:
            items = [t for t in TUTORIAIS if t["grupo"] == g]
            if not items:
                continue
            v.addWidget(ui.heading(g, 11))
            grid = QGridLayout()
            grid.setHorizontalSpacing(16)
            grid.setVerticalSpacing(16)
            for k, t in enumerate(items):
                c = _TutorialCard(t, is_new(t, cur, seen))
                c.clicked.connect(self.open_tutorial.emit)
                grid.addWidget(c, k // cols, k % cols)
            grid.setColumnStretch(cols, 1)
            v.addLayout(grid)
            v.addSpacing(14)
        v.addStretch(1)
        self.area.setWidget(box)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        cols = max(1, (self.area.viewport().width() - 10) // (CARD_W + 16))
        if cols != self._cols:
            self.refresh()

    def showEvent(self, e):
        super().showEvent(e)
        self.refresh()
