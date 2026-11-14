"""Origem do modelo (3DSKY): a ficha que cada bloco guarda sobre de onde veio.

  - Botão direito no bloco › Propriedades… mostra o que o Archiva já sabe do item e a seção **Origem**.
  - Colando o link da página (ou o da imagem) do 3DSKY e clicando em Carregar, o programa lê a página em segundo
    plano e preenche nome original, link, código da primeira imagem e autor; a pessoa confere e salva.
  - A ficha fica no banco da equipe (_ARCHIVA), como as tags: acompanha renomear/mover/excluir/desfazer
    (`move_item_data`) e vai junto com a biblioteca. Nenhum arquivo é gravado nas pastas dos blocos.
  - A busca da Biblioteca passa a achar também por nome original, link, código (inteiro ou só o número) e autor.
Só o administrador (ou o modo local) grava; os demais só veem.
"""
from __future__ import annotations

import html
import os
import re
import time
import urllib.error
import urllib.request
from datetime import datetime
from urllib.parse import urlparse

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (QDialog, QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QVBoxLayout)

from . import segundo_plano, theme, ui
from .scanner import Asset, normalize

SITE = "3dsky"
SITE_NOME = "3DSKY"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
MAX_PAGE = 3 * 1024 * 1024

# "8765287.69ff9ae40ba89" (número da imagem + sufixo), como aparece no fim do endereço da imagem
CODE_RE = re.compile(r"(\d{3,}\.[0-9a-f]{6,})", re.I)
IMG_RE = re.compile(r"/(\d{3,}\.[0-9a-f]{6,})\.(?:jpe?g|png|webp|gif)(?:[?#]|$)", re.I)
SLUG_RE = re.compile(r"/3dmodels/show/([^/?#\s]+)", re.I)


# --------------------------------------------------------------------------- leitura do que a pessoa colou

def parse_input(text: str) -> dict | None:
    """Reconhece o que foi colado. Devolve {"tipo": "pagina", "slug", "url"}, {"tipo": "imagem", "codigo"} ou None."""
    t = (text or "").strip().strip("<>\"' ")
    if not t:
        return None
    if re.fullmatch(r"\d{3,}\.[0-9a-f]{6,}(?:\.(?:jpe?g|png|webp))?", t, re.I):
        return {"tipo": "imagem", "codigo": CODE_RE.search(t).group(1)}
    if "://" not in t and t.lower().startswith(("3dsky.org", "www.3dsky.org", "b4.3dsky.org")):
        t = "https://" + t
    try:
        u = urlparse(t)
    except ValueError:
        return None
    host = (u.hostname or "").lower()
    if not (host == "3dsky.org" or host.endswith(".3dsky.org")):
        return None
    m = SLUG_RE.search(u.path)
    if m:
        slug = m.group(1)
        return {"tipo": "pagina", "slug": slug, "url": canonical_url(slug)}
    m = IMG_RE.search(u.path + ("?" if not u.query else "?" + u.query))
    if m:
        return {"tipo": "imagem", "codigo": m.group(1)}
    return None


def canonical_url(slug: str) -> str:
    return f"https://3dsky.org/3dmodels/show/{slug}"


def slug_of(url: str) -> str:
    m = SLUG_RE.search(url or "")
    return m.group(1) if m else ""


# --------------------------------------------------------------------------- leitura da página (segundo plano)

def _meta(doc: str, prop: str) -> str:
    """Conteúdo de <meta property|name="prop" content="...">, com os atributos em qualquer ordem."""
    p = re.escape(prop)
    for pat in (rf'<meta[^>]+(?:property|name)\s*=\s*["\']{p}["\'][^>]*?content\s*=\s*["\']([^"\']*)["\']',
                rf'<meta[^>]+content\s*=\s*["\']([^"\']*)["\'][^>]*?(?:property|name)\s*=\s*["\']{p}["\']'):
        m = re.search(pat, doc, re.I)
        if m:
            return html.unescape(m.group(1)).strip()
    return ""


def clean_title(t: str) -> str:
    """'Vintage Decorative Set 01 - Decorative set - 3D model' → 'Vintage Decorative Set 01'."""
    t = html.unescape(t or "").strip()
    m = re.search(r"\s[-–|]\s*3D model\s*$", t, re.I)
    if m:
        t = t[:m.start()].strip()
        if " - " in t:                       # sobrou "<nome> - <categoria>"
            t = t.rsplit(" - ", 1)[0].strip()
    return t


def parse_page(doc: str) -> dict:
    """Tira nome, código da primeira imagem e autor do HTML da página do modelo."""
    nome = clean_title(_meta(doc, "og:title") or _meta(doc, "twitter:title"))
    if not nome:
        m = re.search(r"<title[^>]*>(.*?)</title>", doc, re.I | re.S)
        nome = clean_title(m.group(1)) if m else ""
    codigo = ""
    for img in (_meta(doc, "og:image"), _meta(doc, "twitter:image")):
        m = IMG_RE.search(img or "")
        if m:
            codigo = m.group(1)
            break
    if not codigo:
        m = re.search(r"model_images/[0-9/]+/(\d{3,}\.[0-9a-f]{6,})\.(?:jpe?g|png|webp)", doc, re.I)
        codigo = m.group(1) if m else ""
    autor = _meta(doc, "author")
    if not autor:
        m = re.search(r'href\s*=\s*["\'](?:https?://3dsky\.org)?/users/([A-Za-z0-9_.\-]+)["\']', doc)
        autor = m.group(1) if m else ""
    return {"nome_original": nome, "codigo_imagem": codigo, "autor": autor}


def fetch_page(url: str) -> dict:
    """Baixa a página do modelo e lê os dados. Roda num ajudante (nunca na janela). Levanta OSError se falhar."""
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "text/html,*/*;q=0.8",
                                               "Accept-Language": "en-US,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw = resp.read(MAX_PAGE)
            charset = resp.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as e:
        raise OSError(f"o site respondeu {e.code}") from e
    except urllib.error.URLError as e:
        raise OSError(f"sem conexão com o site ({e.reason})") from e
    try:
        doc = raw.decode(charset, "replace")
    except LookupError:
        doc = raw.decode("utf-8", "replace")
    info = parse_page(doc)
    if not (info["nome_original"] or info["codigo_imagem"]):
        raise OSError("a página não trouxe os dados esperados (pode ter pedido uma verificação do navegador)")
    return info


# --------------------------------------------------------------------------- ficha e busca

def make_ficha(old: dict | None, url: str, nome: str, codigo: str, autor: str) -> dict:
    url = (url or "").strip()
    slug = slug_of(url)
    return {
        "fonte": SITE,
        "nome_original": (nome or "").strip(),
        "url": canonical_url(slug) if slug else url,
        "slug": slug,
        "codigo_imagem": (codigo or "").strip(),
        "autor": (autor or "").strip(),
        "registrado_em": (old or {}).get("registrado_em") or time.strftime("%Y-%m-%d"),
    }


def search_text(o: dict | None) -> str:
    """Texto que entra na busca do item (já normalizado): nome original, slug, link, código, número e autor."""
    if not o:
        return ""
    cod = o.get("codigo_imagem", "")
    partes = [o.get("fonte", ""), SITE_NOME if o.get("fonte") == SITE else "", o.get("nome_original", ""),
              o.get("slug", ""), o.get("slug", "").replace("-", " "), o.get("url", ""), cod,
              cod.split(".")[0], o.get("autor", "")]
    return normalize(" ".join(p for p in partes if p))


# --------------------------------------------------------------------------- janela Propriedades

def _tipo_texto(a: Asset) -> str:
    if a.kind == "folder":
        return "Pasta extraída"
    if a.kind == "archive":
        ext = os.path.splitext(a.archive or "")[1].lstrip(".").upper()
        return f"Compactado ({a.archive_type or ext or 'sem extensão'})"
    if a.kind == "max":
        return ".max solto"
    return "Sem arquivo"


def _tamanho(n: float) -> str:
    mb = n / (1024 * 1024)
    return f"{mb / 1024:.2f} GB" if mb >= 1024 else (f"{mb:.1f} MB" if mb >= 1 else f"{n / 1024:.0f} KB")


def _ler_disco(a: Asset) -> tuple[QImage | None, str, str]:
    """No ajudante: miniatura da prévia, texto da prévia e tamanho do arquivo do item (servidor fora da janela)."""
    from . import previa
    img, prev_txt = None, "sem prévia"
    if a.preview:
        r = QImageReader(a.preview)
        r.setAutoTransform(True)
        sz = r.size()
        if sz.isValid():
            r.setScaledSize(sz.scaled(320, 320, Qt.KeepAspectRatio))
        im = r.read()
        img = im if not im.isNull() else None
        prev_txt = previa._size_text(a.preview)
    arq = ""
    alvo = a.archive if a.kind == "archive" else (a.loose_max if a.kind == "max" else None)
    if alvo:
        try:
            arq = _tamanho(os.path.getsize(alvo))
        except OSError:
            arq = ""
    return img, prev_txt, arq


class PropriedadesDialog(QDialog):
    def __init__(self, w, a: Asset):
        super().__init__(w)
        self.w, self.a = w, a
        self.can_edit = bool(w.is_admin() or w.shared.lib is None)
        self._open = True
        self._old = w.db.origin(a.key)
        self.setWindowTitle(f"Propriedades · {a.name}")
        self.setMinimumWidth(760)
        root = QVBoxLayout(self)
        root.setSpacing(12)
        root.addWidget(ui.heading(a.name, 14))

        top = QHBoxLayout()
        top.setSpacing(16)
        self.pic = QLabel("…")
        self.pic.setAlignment(Qt.AlignCenter)
        self.pic.setFixedSize(220, 220)
        self.pic.setStyleSheet("border:1px solid rgba(240,226,201,0.10); border-radius:12px;")
        top.addWidget(self.pic, 0, Qt.AlignTop)
        info = QFormLayout()
        info.setLabelAlignment(Qt.AlignRight)
        info.setHorizontalSpacing(14)
        info.setVerticalSpacing(6)
        self._val: dict[str, QLabel] = {}

        def row(chave: str, rotulo: str, texto: str):
            lb = QLabel(texto)
            lb.setWordWrap(True)
            lb.setTextInteractionFlags(Qt.TextSelectableByMouse)
            self._val[chave] = lb
            cap = QLabel(rotulo)
            cap.setStyleSheet(f"color:{theme.MUTED.name()};")
            info.addRow(cap, lb)

        tags = sorted(w.db.tags_of(a.key))
        nomes = {c["id"]: c["name"] for c in w.db.collections(None)}
        cols = [nomes[c] for c in w.db.collections_of(a.key) if c in nomes]
        row("nome", "Nome na biblioteca", a.name)
        row("cat", "Categoria", a.category.replace("/", " › "))
        row("tipo", "Tipo", _tipo_texto(a))
        row("arq", "Tamanho do arquivo", "lendo…" if a.kind in ("archive", "max") else "—")
        row("prev", "Prévia", "lendo…" if a.preview else "sem prévia")
        row("max", ".max (variações)", str(len(a.max_files)) if a.max_files else "—")
        row("data", "Adicionado em", datetime.fromtimestamp(a.added_time).strftime("%d/%m/%Y")
            if a.added_time > 0 else "—")
        row("tags", "Tags", ", ".join(tags) if tags else "—")
        row("cols", "Coleções", ", ".join(cols) if cols else "—")
        top.addLayout(info, 1)
        root.addLayout(top)

        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color:rgba(240,226,201,0.10);")
        root.addWidget(line)

        root.addWidget(ui.heading(f"Origem · {SITE_NOME}", 11.5))
        if self.can_edit:
            carga = QHBoxLayout()
            self.link_in = QLineEdit()
            self.link_in.setPlaceholderText("Cole aqui o link da página ou da imagem do 3DSKY")
            self.link_in.returnPressed.connect(self._carregar)
            carga.addWidget(self.link_in, 1)
            self.btn_load = QPushButton("Carregar")
            ui.primary(self.btn_load)
            self.btn_load.clicked.connect(self._carregar)
            carga.addWidget(self.btn_load)
            root.addLayout(carga)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{theme.MUTED.name()};")
        root.addWidget(self.status)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(14)
        o = self._old or {}
        self.f_nome = QLineEdit(o.get("nome_original", ""))
        self.f_url = QLineEdit(o.get("url", ""))
        self.f_cod = QLineEdit(o.get("codigo_imagem", ""))
        self.f_autor = QLineEdit(o.get("autor", ""))
        self.f_cod.setPlaceholderText("ex.: 8765287.69ff9ae40ba89 (fim do link da primeira imagem)")
        self.f_url.setPlaceholderText("ex.: https://3dsky.org/3dmodels/show/nome-do-modelo-1")
        for cap, f in (("Nome original", self.f_nome), ("Link da página", self.f_url),
                       ("Código da imagem", self.f_cod), ("Autor", self.f_autor)):
            lb = QLabel(cap)
            lb.setStyleSheet(f"color:{theme.MUTED.name()};")
            f.setReadOnly(not self.can_edit)
            form.addRow(lb, f)
        root.addLayout(form)
        if o.get("registrado_em"):
            r = QLabel(f"Origem registrada em {o['registrado_em']}")
            r.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:8.5pt;")
            root.addWidget(r)
        if not self.can_edit:
            self.status.setText("Só o administrador registra a origem; você pode consultar.")

        b = QHBoxLayout()
        self.btn_open = QPushButton("Abrir página")
        self.btn_open.clicked.connect(self._abrir)
        b.addWidget(self.btn_open)
        if self.can_edit:
            self.btn_clear = QPushButton("Remover origem")
            self.btn_clear.clicked.connect(self._remover)
            self.btn_clear.setVisible(bool(self._old))
            b.addWidget(self.btn_clear)
        b.addStretch(1)
        close = QPushButton("Fechar")
        close.clicked.connect(self.reject)
        b.addWidget(close)
        if self.can_edit:
            self.btn_save = QPushButton("Salvar")
            ui.primary(self.btn_save)
            self.btn_save.clicked.connect(self._salvar)
            b.addWidget(self.btn_save)
        root.addLayout(b)

        self.finished.connect(self._fechou)
        segundo_plano.run_async(lambda: _ler_disco(a), self._disco, lambda e: self._disco(None))

    # -- leitura do disco (volta na janela) ---------------------------------
    def _disco(self, res):
        if not self._open:
            return
        if not res:
            self.pic.setText("—")
            self._val["prev"].setText("não foi possível ler")
            return
        img, prev_txt, arq = res
        if img is not None:
            self.pic.setPixmap(QPixmap.fromImage(img).scaled(216, 216, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.pic.setText("sem prévia")
        self._val["prev"].setText(prev_txt)
        if self.a.kind in ("archive", "max"):
            self._val["arq"].setText(arq or "—")

    def _fechou(self, *_):
        self._open = False

    # -- origem -------------------------------------------------------------
    def _dizer(self, texto: str, cor=None):
        self.status.setStyleSheet(f"color:{(cor or theme.MUTED).name()};")
        self.status.setText(texto)

    def _carregar(self):
        r = parse_input(self.link_in.text())
        if r is None:
            self._dizer("Não reconheci esse link. Use o endereço da página (…/3dmodels/show/…) ou o da imagem "
                        "do 3dsky.org.", theme.WARN)
            return
        if r["tipo"] == "imagem":
            self.f_cod.setText(r["codigo"])
            self._dizer("Código da imagem preenchido. Para trazer o nome, cole também o link da página.", theme.OK)
            return
        self.f_url.setText(r["url"])
        self.btn_load.setEnabled(False)
        self._dizer("Lendo a página do 3DSKY…")
        url = r["url"]
        segundo_plano.run_async(lambda: fetch_page(url), self._lido, self._falhou)

    def _lido(self, info: dict):
        if not self._open:
            return
        self.btn_load.setEnabled(True)
        if info.get("nome_original"):
            self.f_nome.setText(info["nome_original"])
        if info.get("codigo_imagem"):
            self.f_cod.setText(info["codigo_imagem"])
        if info.get("autor"):
            self.f_autor.setText(info["autor"])
        faltou = [n for n, k in (("o nome", "nome_original"), ("o código da imagem", "codigo_imagem"))
                  if not info.get(k)]
        if faltou:
            self._dizer("Li a página, mas não achei " + " e ".join(faltou) + ". Complete à mão e salve.", theme.WARN)
        else:
            self._dizer("Pronto: confira os dados abaixo e clique em Salvar.", theme.OK)

    def _falhou(self, e: Exception):
        if not self._open:
            return
        self.btn_load.setEnabled(True)
        self._dizer(f"Não consegui ler a página ({e}). O link já foi preenchido; digite o nome e o código à mão "
                    "e salve.", theme.WARN)

    def _abrir(self):
        url = self.f_url.text().strip()
        if not url:
            self._dizer("Ainda não há link para abrir.", theme.WARN)
            return
        QDesktopServices.openUrl(QUrl(url))

    def _salvar(self):
        nome, url = self.f_nome.text().strip(), self.f_url.text().strip()
        cod, autor = self.f_cod.text().strip(), self.f_autor.text().strip()
        if not (nome or url or cod):
            self._dizer("Preencha pelo menos o link, o nome ou o código da imagem.", theme.WARN)
            return
        if url and not slug_of(url):
            self._dizer("O link da página deve ser do 3DSKY (…/3dmodels/show/…).", theme.WARN)
            return
        if cod and not CODE_RE.fullmatch(cod):
            self._dizer("O código da imagem tem o formato 8765287.69ff9ae40ba89 (número, ponto e letras/números).",
                        theme.WARN)
            return
        self.w.db.set_origin(self.a.key, make_ficha(self._old, url, nome, cod, autor))
        self.w._rebuild_search_text([self.a])
        self.accept()

    def _remover(self):
        if QMessageBox.question(self, "Remover origem", f"Apagar os dados de origem de {self.a.name}?") \
                != QMessageBox.Yes:
            return
        self.w.db.set_origin(self.a.key, None)
        self.w._rebuild_search_text([self.a])
        self.accept()


def open_properties(w, a: Asset) -> None:
    PropriedadesDialog(w, a).exec()
