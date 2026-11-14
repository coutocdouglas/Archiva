"""Compartilhar a biblioteca deste computador pela Nuvem (2.0): servidor + motor de rede + convites.

Tudo o que é do compartilhamento fica na configuração deste PC (cfg["nuvem"]), nunca na pasta da biblioteca:
  nome         nome que os convidados veem ("Biblioteca TILD")
  compartilhar True = o servidor liga junto com o Archiva
  convidados   [{id, nome, papel, hash da chave, criado, revogado}]
  authkey      chave de autenticação do Tailscale (reutilizável) para os convites entrarem sem conta própria

Regras do projeto respeitadas: o banco de tags só é lido aqui, na thread da janela (uma cópia do dicionário em
memória); o retrato (JSON comprimido) é montado num ajudante.
"""
from __future__ import annotations

import time
import uuid

from PySide6.QtCore import QObject, QTimer, Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QGuiApplication
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMessageBox, QPushButton, QTextEdit,
                               QVBoxLayout, QWidget)

from . import nuvem_motor, segundo_plano, theme, ui
from .config import version
from .nuvem_cliente import criar_convite
from .nuvem_servidor import Retrato, Servidor, hash_chave, nova_chave

URL_CHAVES = "https://login.tailscale.com/admin/settings/keys"


class Compartilhamento(QObject):
    """Vive dentro da janela principal. Liga/desliga o servidor e o motor e mantém o retrato atualizado."""
    estado_mudou = Signal(dict)

    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self.servidor: Servidor | None = None
        self.motor: nuvem_motor.Motor | None = None
        self.ultimo_estado: dict = {}
        self._rev_publicado = -1
        self._montando = False
        self._fechado = False
        self._timer = QTimer(self, interval=4000)
        self._timer.timeout.connect(self._talvez_publicar)
        self._estado_timer = QTimer(self, interval=15000)
        self._estado_timer.timeout.connect(self.consultar_estado)

    # ---------------------------------------------------------------- configuração
    @property
    def cfg(self) -> dict:
        return self.w.cfg.values.setdefault("nuvem", {})

    def nome(self) -> str:
        return self.cfg.get("nome") or "Biblioteca de " + ((self.w.profile or {}).get("nome") or "Archiva")

    def convidados(self) -> list[dict]:
        return self.cfg.setdefault("convidados", [])

    def salvar(self):
        self.w.cfg.save()

    # ---------------------------------------------------------------- liga / desliga
    def ligar(self) -> str:
        """Liga o servidor (já) e o motor (num ajudante). Devolve "" ou a mensagem de erro."""
        if self._fechado:
            return ""
        if self.servidor is None:
            self.servidor = Servidor(self.convidados, cache_dir=str(self.w.cache_root / "nuvem_previas"),
                                     registrar=self._registrar)
        porta = self.servidor.iniciar()
        self._rev_publicado = -1
        self._timer.start()
        self._talvez_publicar()
        if not nuvem_motor.disponivel():
            return "O motor de rede não foi encontrado: o compartilhamento só funciona na versão instalada."
        if self.motor is None or not self.motor.vivo:
            self.motor = nuvem_motor.Motor("servir", nuvem_motor.pasta_estado("servidor"), self.nome_rede(),
                                           destino=f"127.0.0.1:{porta}")

            def subir():
                ok = self.motor.iniciar()
                return ok
            segundo_plano.run_async(subir, lambda ok: (self.consultar_estado(), self._estado_timer.start()))
        return ""

    def desligar(self):
        self._timer.stop()
        self._estado_timer.stop()
        if self.motor:
            m, self.motor = self.motor, None
            segundo_plano.run_async(m.parar)
        if self.servidor:
            self.servidor.parar()
        self.ultimo_estado = {"estado": "Parado"}
        self.estado_mudou.emit(self.ultimo_estado)

    def nome_rede(self) -> str:
        n = self.cfg.get("nome_rede")
        if not n:
            n = nuvem_motor.nome_maquina()
            self.cfg["nome_rede"] = n
            self.salvar()
        return n

    def iniciar_se_ligado(self):
        if self.cfg.get("compartilhar") and not self._fechado:
            self.ligar()

    # ---------------------------------------------------------------- retrato
    def _talvez_publicar(self):
        if not self.servidor or not self.servidor.ligado or self._montando:
            return
        if not self.w._all_cats or self._rev_publicado == self.w.data_rev:
            return
        rev = self.w.data_rev
        cats = list(self.w.categories)                      # só as pastas visíveis para quem compartilha
        tags = {k: set(v) for k, v in self.w.db._by_item.items() if v and not k.startswith("#")}
        nome = self.nome()
        self._montando = True

        def montar():
            return Retrato(nome, version(), cats, tags_of=lambda k: tags.get(k, set()), rev=rev)

        def pronto(r):
            self._montando = False
            if self.servidor:
                self.servidor.publicar(r)
                self._rev_publicado = rev

        def falhou(e):
            self._montando = False
        segundo_plano.run_async(montar, pronto, falhou)

    def _registrar(self, op: str, pessoa: str, chave: str):
        pass   # etapa 1: só leitura; o histórico de downloads entra na etapa 2

    # ---------------------------------------------------------------- estado
    def consultar_estado(self):
        m = self.motor
        if m is None:
            return
        segundo_plano.run_async(m.estado, self._novo_estado)

    def _novo_estado(self, e: dict):
        self.ultimo_estado = e
        self.estado_mudou.emit(e)

    # ---------------------------------------------------------------- convites
    def criar_convite(self, nome: str, papel: str = "leitor") -> str:
        chave = nova_chave()
        self.convidados().append({"id": uuid.uuid4().hex[:10], "nome": nome, "papel": papel,
                                  "hash": hash_chave(chave), "criado": time.time()})
        self.salvar()
        return criar_convite(self.nome_rede(), chave, self.nome(), authkey=self.cfg.get("authkey", ""))

    def revogar(self, ident: str):
        for c in self.convidados():
            if c.get("id") == ident:
                c["revogado"] = True
        self.salvar()

    def parar_ao_fechar(self):
        self._fechado = True
        self._timer.stop()
        self._estado_timer.stop()
        if self.motor:
            self.motor.parar()
        if self.servidor:
            self.servidor.parar()


# =========================================================================== tela (Configurações › Nuvem)

class CompartilharDialog(QDialog):
    def __init__(self, window):
        super().__init__(window)
        self.w = window
        self.c: Compartilhamento = window.nuvem
        self.setWindowTitle("Compartilhar pela Nuvem")
        self.setMinimumWidth(640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(28, 24, 28, 20)
        lay.setSpacing(16)
        t = QLabel("Compartilhar esta biblioteca")
        t.setStyleSheet("font-size:16pt;")
        lay.addWidget(t)
        expl = QLabel("Quem recebe um convite vê os modelos, busca, baixa e arrasta para o Max. Nada pode ser "
                      "apagado, movido ou classificado por quem acessa de fora. A biblioteca fica disponível "
                      "enquanto o Archiva estiver aberto neste computador.")
        expl.setWordWrap(True)
        expl.setStyleSheet(f"color:{theme.MUTED.name()};")
        lay.addWidget(expl)

        g = ui.Glass(12)
        f = QFormLayout(g)
        f.setContentsMargins(18, 14, 18, 14)
        f.setVerticalSpacing(10)
        self.ativo = QCheckBox("Compartilhar enquanto o Archiva estiver aberto")
        self.ativo.setChecked(bool(self.c.cfg.get("compartilhar")))
        self.ativo.toggled.connect(self._alternar)
        f.addRow(self.ativo)
        self.nome = QLineEdit(self.c.nome())
        self.nome.editingFinished.connect(self._salvar_nome)
        f.addRow("Nome que os convidados veem", self.nome)
        self.estado = QLabel()
        self.estado.setWordWrap(True)
        self.entrar = ui.primary(QPushButton("Entrar…"))
        self.entrar.clicked.connect(self._entrar)
        self.entrar.hide()
        f.addRow("Conexão", self._linha(self.estado, self.entrar))
        lay.addWidget(g)

        lay.addWidget(ui.heading("Convidados", 11))
        self.lista = QListWidget()
        self.lista.setMinimumHeight(140)
        lay.addWidget(self.lista)
        bl = QHBoxLayout()
        novo = ui.primary(QPushButton("Criar convite…"))
        novo.clicked.connect(self._novo_convite)
        rev = QPushButton("Revogar")
        rev.clicked.connect(self._revogar)
        chave = QPushButton("Chave de acesso do Tailscale…")
        chave.setToolTip("Com ela, quem recebe o convite entra sem criar conta no Tailscale")
        chave.clicked.connect(self._editar_authkey)
        bl.addWidget(novo)
        bl.addWidget(rev)
        bl.addStretch(1)
        bl.addWidget(chave)
        lay.addLayout(bl)

        bb = QDialogButtonBox()
        bb.addButton("Fechar", QDialogButtonBox.RejectRole)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.c.estado_mudou.connect(self._mostrar_estado)
        self._preencher()
        self._mostrar_estado(self.c.ultimo_estado if self.c.cfg.get("compartilhar") else {"estado": "Parado"})
        self.c.consultar_estado()

    def _linha(self, *ws):
        w = QWidget()
        l = QHBoxLayout(w)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(10)
        for x in ws:
            l.addWidget(x, 1 if isinstance(x, QLabel) else 0)
        return w

    def _preencher(self):
        self.lista.clear()
        for cv in self.c.convidados():
            quando = time.strftime("%d/%m/%Y", time.localtime(cv.get("criado", 0)))
            ult = self.c.servidor.acessos.get(cv.get("id")) if self.c.servidor else None
            uso = f" · último acesso {time.strftime('%d/%m %H:%M', time.localtime(ult))}" if ult else ""
            txt = f"{cv.get('nome')}  ·  {cv.get('papel', 'leitor')}  ·  convite de {quando}{uso}"
            if cv.get("revogado"):
                txt += "  ·  revogado"
            it = QListWidgetItem(txt)
            it.setData(Qt.UserRole, cv.get("id"))
            if cv.get("revogado"):
                it.setForeground(theme.FAINT)
            self.lista.addItem(it)

    def _alternar(self, on: bool):
        self.c.cfg["compartilhar"] = on
        self.c.salvar()
        if on:
            erro = self.c.ligar()
            if erro:
                self.estado.setText(erro)
        else:
            self.c.desligar()

    def _salvar_nome(self):
        n = self.nome.text().strip()
        if n:
            self.c.cfg["nome"] = n
            self.c.salvar()
            self.c._rev_publicado = -1

    def _mostrar_estado(self, e: dict):
        if not self.c.cfg.get("compartilhar"):
            self.estado.setText("Desligado")
            self.estado.setStyleSheet(f"color:{theme.FAINT.name()};")
            self.entrar.hide()
            return
        if not nuvem_motor.disponivel():
            self.estado.setText("O motor de rede não foi encontrado: o compartilhamento pela internet só funciona "
                                "na versão instalada.")
            self.estado.setStyleSheet(f"color:{theme.BAD.name()};")
            self.entrar.hide()
            return
        txt, cor = nuvem_motor.texto_estado(e, "servir")
        self.estado.setText(txt)
        self.estado.setStyleSheet("color:%s;" % {"ok": theme.OK, "aviso": theme.WARN, "erro": theme.BAD}[cor].name())
        self.entrar.setVisible(e.get("estado") == "NeedsLogin" and bool(e.get("url_login")))
        self._url = e.get("url_login", "")

    def _entrar(self):
        if getattr(self, "_url", ""):
            QDesktopServices.openUrl(QUrl(self._url))
            QTimer.singleShot(8000, self.c.consultar_estado)

    def _novo_convite(self):
        nome, ok = _pergunta(self, "Novo convite", "Para quem é o convite?", "Nome da pessoa")
        if not ok or not nome.strip():
            return
        texto = self.c.criar_convite(nome.strip())
        self._preencher()
        d = QDialog(self)
        d.setWindowTitle("Convite criado")
        l = QVBoxLayout(d)
        l.setContentsMargins(24, 20, 24, 16)
        aviso = QLabel(f"Mande esta linha para {nome.strip()} (WhatsApp, e-mail…). No Archiva dela, é só abrir "
                       "<b>Nuvem › Entrar com um convite</b> e colar. O convite vale só para essa pessoa: "
                       "você pode revogar quando quiser.")
        aviso.setWordWrap(True)
        l.addWidget(aviso)
        if not self.c.cfg.get("authkey"):
            sem = QLabel("Sem a chave de acesso do Tailscale, a pessoa vai precisar entrar com uma conta própria e "
                         "você compartilha este computador com ela no painel do Tailscale.")
            sem.setWordWrap(True)
            sem.setStyleSheet(f"color:{theme.WARN.name()};")
            l.addWidget(sem)
        caixa = QTextEdit(texto)
        caixa.setReadOnly(True)
        caixa.setFixedHeight(90)
        l.addWidget(caixa)
        bb = QDialogButtonBox()
        cop = ui.primary(bb.addButton("Copiar", QDialogButtonBox.ActionRole))
        cop.clicked.connect(lambda: (QGuiApplication.clipboard().setText(texto), cop.setText("Copiado")))
        bb.addButton("Fechar", QDialogButtonBox.RejectRole)
        bb.rejected.connect(d.reject)
        l.addWidget(bb)
        d.resize(560, 280)
        d.exec()

    def _revogar(self):
        it = self.lista.currentItem()
        if not it:
            return
        if QMessageBox.question(self, "Revogar convite", f"Revogar o acesso de quem usa este convite?\n\n{it.text()}"
                                ) == QMessageBox.Yes:
            self.c.revogar(it.data(Qt.UserRole))
            self._preencher()

    def _editar_authkey(self):
        d = QDialog(self)
        d.setWindowTitle("Chave de acesso do Tailscale")
        l = QVBoxLayout(d)
        l.setContentsMargins(24, 20, 24, 16)
        txt = QLabel("Para quem recebe o convite não precisar criar conta: no painel do Tailscale, em "
                     "<b>Settings › Keys</b>, gere uma <b>auth key</b> marcando <b>Reusable</b> e cole aqui. "
                     "Ela vai junto em cada convite novo (vale no máximo 90 dias; depois gere outra).")
        txt.setWordWrap(True)
        l.addWidget(txt)
        abrir = QPushButton("Abrir o painel de chaves")
        abrir.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(URL_CHAVES)))
        l.addWidget(abrir)
        campo = QLineEdit(self.c.cfg.get("authkey", ""))
        campo.setPlaceholderText("tskey-auth-…")
        campo.setEchoMode(QLineEdit.Password)
        l.addWidget(campo)
        bb = QDialogButtonBox()
        ui.primary(bb.addButton("Salvar", QDialogButtonBox.AcceptRole))
        bb.addButton("Cancelar", QDialogButtonBox.RejectRole)
        bb.accepted.connect(d.accept)
        bb.rejected.connect(d.reject)
        l.addWidget(bb)
        d.resize(520, 220)
        if d.exec() == QDialog.Accepted:
            k = campo.text().strip()
            if k and not k.startswith("tskey-"):
                QMessageBox.warning(self, "Chave", "A chave do Tailscale começa com tskey-auth-.")
                return
            self.c.cfg["authkey"] = k
            self.c.salvar()

    def done(self, r):
        self._salvar_nome()
        try:
            self.c.estado_mudou.disconnect(self._mostrar_estado)
        except (RuntimeError, TypeError):
            pass
        super().done(r)


def _pergunta(parent, titulo: str, texto: str, dica: str = "") -> tuple[str, bool]:
    from PySide6.QtWidgets import QInputDialog
    d = QInputDialog(parent)
    d.setWindowTitle(titulo)
    d.setLabelText(texto)
    d.setTextValue("")
    if dica:
        le = d.findChild(QLineEdit)
        if le:
            le.setPlaceholderText(dica)
    ok = d.exec() == QDialog.Accepted
    return d.textValue(), ok



