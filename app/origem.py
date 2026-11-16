"""Origem do modelo (3DSKY, Design Connected…): a ficha que cada bloco guarda sobre de onde veio.

  - Botão direito no bloco › Propriedades… mostra o que o Archiva já sabe do item e a seção **Origem**.
  - **3DSKY pelo código:** o arquivo baixado do 3DSKY tem como nome um código (ex.: 9332998.6af59838593cc). A busca
    do site (3dsky.org/3dmodels?query=<código>) acha o modelo; a página é lida e só vale se o código aparecer nas
    imagens dela. A Entrada guarda o nome original do download, então os blocos que passaram por ela já têm o código.
  - **Por imagem (Google Vision, a mesma chave da busca de prévias):** "Google · Design Connected" filtra as páginas
    desse site; "Google · geral" mostra todas. A pessoa escolhe a página, confere (a imagem da página aparece ao lado)
    e salva. O Design Connected não tem código: só imagem.
  - **Link:** colar o link da página (3DSKY ou outro site) ou o da imagem do 3DSKY e clicar em Carregar.
  - Em lote: botão direito em vários blocos › "Preencher origem pelo código guardado…" (lista de conferência).
  - A ficha fica no banco da equipe (_ARCHIVA), como as tags: acompanha renomear/mover/excluir/desfazer
    (`move_item_data`) e vai com a biblioteca. Nenhum arquivo é gravado nas pastas dos blocos.
  - A busca da Biblioteca acha por nome original, link, código (inteiro ou só o número), autor e site.
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
from urllib.parse import quote, urlparse

from PySide6.QtCore import QThread, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices, QImage, QImageReader, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QFormLayout, QFrame, QHBoxLayout, QHeaderView, QLabel,
                               QLineEdit, QListWidget, QListWidgetItem, QMenu, QMessageBox, QPushButton,
                               QScrollArea, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from . import segundo_plano, theme, ui
from .scanner import Asset, normalize, strip_key

SITE = "3dsky"
FONTES = {"3dsky": "3DSKY", "designconnected": "Design Connected", "outro": "Outro site"}
SEARCH_URL = "https://3dsky.org/3dmodels?query="
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
MAX_PAGE = 3 * 1024 * 1024
MAX_IMG = 3 * 1024 * 1024
LOTE_PAUSA = 1.5               # segundos entre um pedido e outro no lote (sem sobrecarregar o site)
# A busca por imagem focada no Design Connected existe, mas fica escondida até ser afinada (o Google costuma devolver
# cópias do modelo em outros sites, e o título das páginas do Design Connected traz "3d model by Design Connected").
MOSTRAR_DESIGN_CONNECTED = False

# "8765287.69ff9ae40ba89" (número da imagem + sufixo), como aparece no fim do endereço da imagem
CODE_RE = re.compile(r"(\d{3,}\.[0-9a-f]{6,})", re.I)
IMG_RE = re.compile(r"/(\d{3,}\.[0-9a-f]{6,})\.(?:jpe?g|png|webp|gif)(?:[?#]|$)", re.I)
SLUG_RE = re.compile(r"/3dmodels/show/([^/?#\s]+)", re.I)
SHOW_HREF_RE = re.compile(r'href\s*=\s*["\'](?:https?://(?:www\.)?3dsky\.org)?/(?:[a-z]{2}/)?3dmodels/show/'
                          r'([^"\'/?#\s]+)', re.I)


class SemResultado(OSError):
    """A busca funcionou, mas não achou o modelo."""


# --------------------------------------------------------------------------- reconhecer o que foi colado

def fonte_de(url: str) -> str:
    """'3dsky', 'designconnected' ou 'outro' (vazio se não for um endereço)."""
    try:
        host = (urlparse((url or "").strip()).hostname or "").lower()
    except ValueError:
        return ""
    if host == "3dsky.org" or host.endswith(".3dsky.org"):
        return "3dsky"
    if host == "designconnected.com" or host.endswith(".designconnected.com"):
        return "designconnected"
    return "outro" if host else ""


def codigo_do_nome(nome: str) -> str:
    """O nome de um download do 3DSKY é só o código (9332998.6af59838593cc); devolve o código ou ''."""
    t = strip_key((nome or "").strip())
    m = re.fullmatch(r"(\d{3,}\.[0-9a-f]{6,})", t, re.I)
    return m.group(1).lower() if m else ""


def codigo_guardado(w, a: Asset) -> str:
    """Código do 3DSKY deste bloco: o nome original que a Entrada guardou (ou o próprio nome, se for o código)."""
    for nome in (w.db.original_name_of(a.key), a.name):
        c = codigo_do_nome(nome or "")
        if c:
            return c
    return ""


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
    m = IMG_RE.search(u.path + "?")
    if m:
        return {"tipo": "imagem", "codigo": m.group(1)}
    return None


def canonical_url(slug: str) -> str:
    return f"https://3dsky.org/3dmodels/show/{slug}"


def slug_of(url: str) -> str:
    m = SLUG_RE.search(url or "")
    return m.group(1) if m else ""


# --------------------------------------------------------------------------- leitura de páginas (segundo plano)

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


def _sem_site(t: str, site: str) -> str:
    """Tira o nome do site do começo ou do fim do título ('Poltrona X | Design Connected' → 'Poltrona X')."""
    t = html.unescape(t or "").strip()
    if site:
        s = re.escape(site.strip())
        t = re.sub(rf"\s*[|\-–—:·]\s*{s}\s*$", "", t, flags=re.I)
        t = re.sub(rf"^\s*{s}\s*[|\-–—:·]\s*", "", t, flags=re.I)
    return t.strip()


def parse_page(doc: str) -> dict:
    """3DSKY: nome, código da primeira imagem e autor, tirados do HTML da página do modelo."""
    nome = clean_title(_meta(doc, "og:title") or _meta(doc, "twitter:title"))
    if not nome:
        m = re.search(r"<title[^>]*>(.*?)</title>", doc, re.I | re.S)
        nome = clean_title(m.group(1)) if m else ""
    codigo, imagem = "", ""
    for img in (_meta(doc, "og:image"), _meta(doc, "twitter:image")):
        m = IMG_RE.search(img or "")
        if m:
            codigo, imagem = m.group(1), img
            break
    if not codigo:
        m = re.search(r"model_images/[0-9/]+/(\d{3,}\.[0-9a-f]{6,})\.(?:jpe?g|png|webp)", doc, re.I)
        codigo = m.group(1) if m else ""
    autor = _meta(doc, "author")
    if not autor:
        m = re.search(r'href\s*=\s*["\'](?:https?://3dsky\.org)?/users/([A-Za-z0-9_.\-]+)["\']', doc)
        autor = m.group(1) if m else ""
    return {"nome_original": nome, "codigo_imagem": codigo, "autor": autor, "imagem_url": imagem}


def parse_generico(doc: str) -> dict:
    """Outros sites (ex.: Design Connected): nome e imagem pelas marcas og: da página (sem código)."""
    site = _meta(doc, "og:site_name")
    titulo = _meta(doc, "og:title") or _meta(doc, "twitter:title")
    if not titulo:
        m = re.search(r"<title[^>]*>(.*?)</title>", doc, re.I | re.S)
        titulo = html.unescape(re.sub(r"\s+", " ", m.group(1))).strip() if m else ""
    return {"nome_original": _sem_site(titulo, site),
            "imagem_url": _meta(doc, "og:image") or _meta(doc, "twitter:image"),
            "codigo_imagem": "", "autor": _meta(doc, "author")}


def _baixar(url: str, limite: int, aceita: str) -> tuple[bytes, str]:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": aceita,
                                               "Accept-Language": "en-US,en;q=0.8"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read(limite), resp.headers.get_content_charset() or "utf-8"
    except urllib.error.HTTPError as e:
        raise OSError(f"o site respondeu {e.code}") from e
    except urllib.error.URLError as e:
        raise OSError(f"sem conexão com o site ({e.reason})") from e


def _texto(url: str) -> str:
    raw, charset = _baixar(url, MAX_PAGE, "text/html,*/*;q=0.8")
    try:
        return raw.decode(charset, "replace")
    except LookupError:
        return raw.decode("utf-8", "replace")


def _baixar_imagem(url: str) -> bytes | None:
    """Imagem principal da página (para a pessoa conferir). Falhar aqui não atrapalha nada."""
    if not url:
        return None
    if url.startswith("//"):
        url = "https:" + url
    if not url.lower().startswith("http"):
        return None
    try:
        return _baixar(url, MAX_IMG, "image/*,*/*;q=0.8")[0] or None
    except OSError:
        return None


def fetch_page(url: str) -> dict:
    """Baixa a página do modelo (3DSKY) e lê os dados. Levanta OSError se falhar."""
    info = parse_page(_texto(url))
    if not (info["nome_original"] or info["codigo_imagem"]):
        raise OSError("a página não trouxe os dados esperados (pode ter pedido uma verificação do navegador)")
    return info


def carregar_pagina(url: str) -> dict:
    """Lê a página de qualquer site aceito e devolve a ficha provisória: fonte, url, nome_original, codigo_imagem,
    autor e imagem (bytes da imagem principal, se deu para baixar). Roda num ajudante."""
    fonte = fonte_de(url) or "outro"
    if fonte == "3dsky" and slug_of(url):
        url = canonical_url(slug_of(url))
        info = fetch_page(url)
    else:
        info = parse_generico(_texto(url))
        if not (info["nome_original"] or info["imagem_url"]):
            raise OSError("a página não trouxe nome nem imagem")
    info["fonte"], info["url"] = fonte, url
    info["imagem"] = _baixar_imagem(info.get("imagem_url", ""))
    return info


def buscar_por_codigo(codigo: str) -> dict:
    """3DSKY pelo código do arquivo: busca no site, abre os resultados e confere se o código aparece na página.
    Devolve {"fonte", "url", "slug", "nome_original", "codigo_imagem", "autor", "validado", "imagem"}.
    SemResultado se o site não achou nada; OSError nas falhas de rede. Roda num ajudante."""
    codigo = (codigo or "").strip().lower()
    if not CODE_RE.fullmatch(codigo):
        raise SemResultado("código inválido")
    busca = _texto(SEARCH_URL + quote(codigo))
    slugs: list[str] = []
    for m in SHOW_HREF_RE.finditer(busca):
        if m.group(1) not in slugs:
            slugs.append(m.group(1))
    if not slugs:
        raise SemResultado("o 3DSKY não achou nenhum modelo com esse código")
    achado = None
    for slug in slugs[:4]:
        url = canonical_url(slug)
        doc = _texto(url)
        if codigo in doc.lower():
            achado = (url, slug, doc, True)
            break
        if achado is None and len(slugs) == 1:        # um só resultado, mas a página não cita o código
            achado = (url, slug, doc, False)
    if achado is None:
        raise SemResultado("o site mostrou modelos, mas nenhum com esse código na página")
    url, slug, doc, ok = achado
    info = parse_page(doc)
    info.update(fonte="3dsky", url=url, slug=slug, codigo_imagem=codigo, validado=ok)
    info["imagem"] = _baixar_imagem(info.get("imagem_url", ""))
    return info


def paginas_por_imagem(key: str, preview: str, dominio: str | None) -> list[dict]:
    """Google (Cloud Vision): páginas que contêm a prévia. Com `dominio` (ex.: designconnected.com) só as desse
    site; sem ele, todas, com 3DSKY e Design Connected primeiro. Roda num ajudante."""
    from . import busca_web
    paginas = busca_web.web_pages(key, busca_web._encode_preview(preview))
    if dominio:
        paginas = [p for p in paginas
                   if (urlparse(p["url"]).hostname or "").lower().endswith(dominio)]
    else:
        paginas.sort(key=lambda p: (0 if fonte_de(p["url"]) in ("3dsky", "designconnected") else 1,
                                    0 if p["completa"] else 1))
    return paginas[:15]


# --------------------------------------------------------------------------- ficha e busca

def make_ficha(old: dict | None, url: str, nome: str, codigo: str, autor: str, fonte: str | None = None) -> dict:
    url = (url or "").strip()
    fonte = fonte_de(url) or fonte or (old or {}).get("fonte") or SITE
    slug = slug_of(url) if fonte == "3dsky" else ""
    return {
        "fonte": fonte,
        "nome_original": (nome or "").strip(),
        "url": canonical_url(slug) if slug else url,
        "slug": slug,
        "codigo_imagem": (codigo or "").strip(),
        "autor": (autor or "").strip(),
        "registrado_em": (old or {}).get("registrado_em") or time.strftime("%Y-%m-%d"),
    }


def search_text(o: dict | None) -> str:
    """Texto que entra na busca do item (já normalizado): nome original, slug, link, código, número, autor, site."""
    if not o:
        return ""
    cod = o.get("codigo_imagem", "")
    partes = [o.get("fonte", ""), FONTES.get(o.get("fonte", ""), ""), o.get("nome_original", ""),
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
        self._fonte = (self._old or {}).get("fonte", "")
        self._codigo = codigo_guardado(w, a)
        self.setWindowTitle(f"Propriedades · {a.name}")
        self.setMinimumWidth(780)
        self.resize(800, 720)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 12)
        sa = QScrollArea()                          # o conteúdo rola; os botões ficam sempre à vista embaixo
        sa.setWidgetResizable(True)
        sa.setFrameShape(QFrame.NoFrame)
        sa.setStyleSheet("QScrollArea{background:transparent;} QScrollArea > QWidget > QWidget{background:transparent;}")
        content = QWidget()
        sa.setWidget(content)
        outer.addWidget(sa, 1)
        root = QVBoxLayout(content)
        root.setContentsMargins(12, 12, 12, 0)
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

        root.addWidget(ui.heading("Origem", 11.5))
        if self.can_edit:
            busca = QHBoxLayout()
            self.btn_cod = QPushButton("Buscar pelo código")
            ui.primary(self.btn_cod)
            self.btn_cod.setToolTip("O arquivo baixado do 3DSKY tem o código como nome. O Archiva procura esse código "
                                    "no site e confere se a página tem o mesmo código.")
            self.btn_cod.clicked.connect(self._buscar_codigo)
            self.btn_cod.setVisible(bool(self._codigo))
            busca.addWidget(self.btn_cod)
            self.btn_img = QPushButton("Buscar por imagem no Google")
            self.btn_img.setToolTip("Procura no Google a página que tem a prévia deste bloco (usa a chave da Google "
                                    "Cloud Vision; cada busca conta na cota).")
            if MOSTRAR_DESIGN_CONNECTED:
                self.btn_img.setText("Buscar por imagem  ▾")
                menu = QMenu(self.btn_img)
                menu.addAction("Google · Design Connected", lambda: self._buscar_imagem("designconnected.com"))
                menu.addAction("Google · geral", lambda: self._buscar_imagem(None))
                self.btn_img.setMenu(menu)
            else:
                self.btn_img.clicked.connect(lambda: self._buscar_imagem(None))
            self.btn_img.setEnabled(bool(a.preview))
            busca.addWidget(self.btn_img)
            busca.addStretch(1)
            root.addLayout(busca)
            carga = QHBoxLayout()
            self.link_in = QLineEdit()
            self.link_in.setPlaceholderText("Ou cole o link da página do modelo (3DSKY ou outro site) ou da imagem do 3DSKY")
            self.link_in.returnPressed.connect(self._carregar)
            carga.addWidget(self.link_in, 1)
            self.btn_load = QPushButton("Carregar")
            self.btn_load.clicked.connect(self._carregar)
            carga.addWidget(self.btn_load)
            root.addLayout(carga)
        self.status = QLabel("")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{theme.MUTED.name()};")
        root.addWidget(self.status)

        # candidatos da busca por imagem
        self.box_cands = QWidget()
        cl = QVBoxLayout(self.box_cands)
        cl.setContentsMargins(0, 0, 0, 0)
        self.cands = QListWidget()
        self.cands.setMaximumHeight(150)
        self.cands.itemDoubleClicked.connect(lambda *_: self._usar_candidato())
        cl.addWidget(self.cands)
        usar = QPushButton("Usar a página selecionada")
        usar.clicked.connect(self._usar_candidato)
        cl.addWidget(usar, 0, Qt.AlignLeft)
        self.box_cands.setVisible(False)
        root.addWidget(self.box_cands)

        orow = QHBoxLayout()
        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)
        form.setHorizontalSpacing(14)
        o = self._old or {}
        self.f_nome = QLineEdit(o.get("nome_original", ""))
        self.f_url = QLineEdit(o.get("url", ""))
        self.f_cod = QLineEdit(o.get("codigo_imagem", ""))
        self.f_autor = QLineEdit(o.get("autor", ""))
        self.f_cod.setPlaceholderText("3DSKY: ex.: 8765287.69ff9ae40ba89 (o código do arquivo baixado)")
        self.f_url.setPlaceholderText("ex.: https://3dsky.org/3dmodels/show/nome-do-modelo-1")
        self.lb_fonte = QLabel(FONTES.get(self._fonte, "—"))
        for cap, f in (("Site", self.lb_fonte), ("Nome original", self.f_nome), ("Link da página", self.f_url),
                       ("Código", self.f_cod), ("Autor", self.f_autor)):
            lb = QLabel(cap)
            lb.setStyleSheet(f"color:{theme.MUTED.name()};")
            if isinstance(f, QLineEdit):
                f.setReadOnly(not self.can_edit)
            form.addRow(lb, f)
        orow.addLayout(form, 1)
        self.pic_pg = QLabel()
        self.pic_pg.setAlignment(Qt.AlignCenter)
        self.pic_pg.setFixedSize(170, 170)
        self.pic_pg.setStyleSheet("border:1px solid rgba(240,226,201,0.10); border-radius:12px;")
        self.pic_pg.setToolTip("Imagem principal da página encontrada: confira se é o mesmo bloco")
        self.pic_pg.setVisible(False)
        orow.addWidget(self.pic_pg, 0, Qt.AlignTop)
        root.addLayout(orow)
        if o.get("registrado_em"):
            r = QLabel(f"Origem registrada em {o['registrado_em']}")
            r.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:8.5pt;")
            root.addWidget(r)
        if not self.can_edit:
            self.status.setText("Só o administrador registra a origem; você pode consultar.")
        elif self._codigo and not self._old:
            self._dizer(f"Este bloco veio com o código {self._codigo}. Clique em Buscar pelo código.")

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
        b.setContentsMargins(12, 0, 12, 0)
        outer.addLayout(b)

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

    def _ocupado(self, sim: bool):
        if self.can_edit:
            for b in (self.btn_cod, self.btn_img, self.btn_load):
                b.setEnabled(not sim and (b is not self.btn_img or bool(self.a.preview)))

    def _preencher(self, info: dict):
        """Põe nos campos o que veio da página (você confere e salva)."""
        if info.get("nome_original"):
            self.f_nome.setText(info["nome_original"])
        if info.get("url"):
            self.f_url.setText(info["url"])
        if info.get("codigo_imagem"):
            self.f_cod.setText(info["codigo_imagem"])
        if info.get("autor"):
            self.f_autor.setText(info["autor"])
        self._fonte = info.get("fonte") or self._fonte
        self.lb_fonte.setText(FONTES.get(self._fonte, "—"))
        img = info.get("imagem")
        if img:
            qi = QImage.fromData(img)
            if not qi.isNull():
                self.pic_pg.setPixmap(QPixmap.fromImage(qi).scaled(166, 166, Qt.KeepAspectRatio,
                                                                  Qt.SmoothTransformation))
                self.pic_pg.setVisible(True)
                return
        self.pic_pg.setVisible(False)

    def _buscar_codigo(self):
        cod = self._codigo
        if not cod:
            return
        self._ocupado(True)
        self._dizer(f"Procurando o código {cod} no 3DSKY…")
        segundo_plano.run_async(lambda: buscar_por_codigo(cod), self._achou_codigo, self._falhou)

    def _achou_codigo(self, info: dict):
        if not self._open:
            return
        self._ocupado(False)
        self._preencher(info)
        if info.get("validado"):
            self._dizer(f"Achei: {info.get('nome_original') or info['url']}. O código confere com a página. "
                        "Clique em Salvar.", theme.OK)
        else:
            self._dizer("Achei um modelo, mas a página não cita esse código: confira a imagem ao lado antes de "
                        "salvar.", theme.WARN)

    def _buscar_imagem(self, dominio: str | None):
        from . import busca_web
        if not self.a.preview:
            return
        key = busca_web.get_key(self.w)
        if not key:
            self._dizer("A busca por imagem precisa da chave da Google Cloud Vision (Configurações › Biblioteca).",
                        theme.WARN)
            return
        self._ocupado(True)
        self.box_cands.setVisible(False)
        self._dizer("Procurando no Google" + (" · só Design Connected" if dominio else "") + "…")
        prev = self.a.preview
        segundo_plano.run_async(lambda: paginas_por_imagem(key, prev, dominio),
                                lambda r: self._candidatos(r, dominio), self._falhou)

    def _candidatos(self, paginas: list, dominio: str | None):
        if not self._open:
            return
        self._ocupado(False)
        if not paginas:
            self._dizer("O Google não achou " + (f"páginas do {dominio} " if dominio else "páginas ")
                        + "com essa imagem. Tente a outra busca ou cole o link.", theme.WARN)
            return
        self.cands.clear()
        for p in paginas:
            host = (urlparse(p["url"]).hostname or "").removeprefix("www.")
            it = QListWidgetItem(f"{p['titulo'] or p['url']}\n{host}" + ("  ·  imagem igual" if p["completa"] else ""))
            it.setData(Qt.UserRole, p["url"])
            self.cands.addItem(it)
        self.cands.setCurrentRow(0)
        self.box_cands.setVisible(True)
        self._dizer(f"{len(paginas)} página(s) encontrada(s). Escolha a certa e clique em Usar: a imagem dela "
                    "aparece ao lado para você conferir.")

    def _usar_candidato(self):
        it = self.cands.currentItem()
        if it is not None:
            self._carregar_url(it.data(Qt.UserRole))

    def _carregar(self):
        txt = self.link_in.text().strip()
        r = parse_input(txt)
        if r and r["tipo"] == "imagem":
            self.f_cod.setText(r["codigo"])
            self._fonte = "3dsky"
            self.lb_fonte.setText(FONTES["3dsky"])
            self._dizer("Código da imagem preenchido. Para trazer o nome, cole também o link da página.", theme.OK)
            return
        if r and r["tipo"] == "pagina":
            self._carregar_url(r["url"])
        elif txt.lower().startswith(("http://", "https://")):
            self._carregar_url(txt)
        else:
            self._dizer("Não reconheci esse link. Use o endereço da página do modelo (3DSKY, Design Connected…) ou o "
                        "da imagem do 3dsky.org.", theme.WARN)

    def _carregar_url(self, url: str):
        self.f_url.setText(url)
        self._ocupado(True)
        self._dizer("Lendo a página…")
        segundo_plano.run_async(lambda: carregar_pagina(url), self._lido, self._falhou)

    def _lido(self, info: dict):
        if not self._open:
            return
        self._ocupado(False)
        self._preencher(info)
        faltou = [n for n, k in (("o nome", "nome_original"),) if not info.get(k)]
        if info["fonte"] == "3dsky" and not info.get("codigo_imagem"):
            faltou.append("o código da imagem")
        if faltou:
            self._dizer("Li a página, mas não achei " + " e ".join(faltou) + ". Complete à mão e salve.", theme.WARN)
        else:
            self._dizer("Pronto: confira os dados (e a imagem ao lado) e clique em Salvar.", theme.OK)

    def _falhou(self, e: Exception):
        if not self._open:
            return
        self._ocupado(False)
        self._dizer(f"Não consegui: {e}. Você pode colar o link da página ou preencher à mão e salvar.", theme.WARN)

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
            self._dizer("Preencha pelo menos o link, o nome ou o código.", theme.WARN)
            return
        if url and not url.lower().startswith(("http://", "https://")):
            self._dizer("O link da página deve começar com https://", theme.WARN)
            return
        if url and fonte_de(url) == "3dsky" and not slug_of(url):
            self._dizer("O link do 3DSKY deve ser o da página do modelo (…/3dmodels/show/…).", theme.WARN)
            return
        if cod and not CODE_RE.fullmatch(cod):
            self._dizer("O código tem o formato 8765287.69ff9ae40ba89 (número, ponto e letras/números).", theme.WARN)
            return
        self.w.db.set_origin(self.a.key, make_ficha(self._old, url, nome, cod, autor, self._fonte or None))
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


# --------------------------------------------------------------------------- em lote (pelo código guardado)

class LoteThread(QThread):
    linha = Signal(int, str, object)       # posição, estado (buscando/ok/conferir/nao/erro), dados ou mensagem
    fim = Signal(str)

    def __init__(self, itens: list[tuple[str, str, str]]):
        super().__init__()
        self.itens = itens                  # (chave, nome, código)
        self.cancel = False

    def run(self):
        for i, (_key, _nome, cod) in enumerate(self.itens):
            if self.cancel:
                break
            self.linha.emit(i, "buscando", None)
            try:
                info = buscar_por_codigo(cod)
            except SemResultado as e:
                self.linha.emit(i, "nao", str(e))
            except OSError as e:
                msg = str(e)
                self.linha.emit(i, "erro", msg)
                if "429" in msg or "403" in msg:
                    self.fim.emit("O 3DSKY recusou os pedidos; parei para não insistir. Tente de novo mais tarde.")
                    return
            else:
                self.linha.emit(i, "ok" if info.get("validado") else "conferir", info)
            for _ in range(int(LOTE_PAUSA * 10)):
                if self.cancel:
                    break
                time.sleep(0.1)
        self.fim.emit("")


class LoteDialog(QDialog):
    ESTADOS = {"buscando": "buscando…", "ok": "achado e conferido", "conferir": "conferir à mão",
               "nao": "não achado", "erro": "erro"}

    def __init__(self, w, assets: list[Asset]):
        super().__init__(w)
        self.w = w
        self.itens = [(a, codigo_guardado(w, a)) for a in assets]
        self.res: dict[int, dict] = {}
        self.setWindowTitle("Preencher origem pelo código guardado")
        self.resize(860, 520)
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        lay.addWidget(ui.heading("Origem pelo código do 3DSKY", 13))
        self.status = QLabel(f"{len(self.itens)} bloco(s) com código guardado. O Archiva procura cada um no 3DSKY "
                             "(um por vez, devagar) e só marca como conferido quando o código aparece na página. "
                             "Nada é gravado até você clicar em Gravar.")
        self.status.setWordWrap(True)
        self.status.setStyleSheet(f"color:{theme.MUTED.name()};")
        lay.addWidget(self.status)
        self.tab = QTableWidget(len(self.itens), 4)
        self.tab.setHorizontalHeaderLabels(["Bloco", "Código", "Modelo no 3DSKY", "Situação"])
        self.tab.verticalHeader().setVisible(False)
        self.tab.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectRows)
        h = self.tab.horizontalHeader()
        h.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(1, QHeaderView.ResizeToContents)
        h.setSectionResizeMode(2, QHeaderView.Stretch)
        h.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        for i, (a, cod) in enumerate(self.itens):
            for c, t in enumerate((a.name, cod, "", "na fila")):
                self.tab.setItem(i, c, QTableWidgetItem(t))
        lay.addWidget(self.tab, 1)
        b = QHBoxLayout()
        close = QPushButton("Fechar")
        close.clicked.connect(self.reject)
        b.addWidget(close)
        b.addStretch(1)
        self.btn = QPushButton("Gravar os conferidos")
        ui.primary(self.btn)
        self.btn.setEnabled(False)
        self.btn.clicked.connect(self._gravar)
        b.addWidget(self.btn)
        lay.addLayout(b)
        self.th = LoteThread([(a.key, a.name, cod) for a, cod in self.itens])
        self.th.linha.connect(self._linha)
        self.th.fim.connect(self._fim)
        self.finished.connect(self._limpar)
        self.th.start()

    def _linha(self, i: int, estado: str, dado):
        self.tab.item(i, 3).setText(self.ESTADOS.get(estado, estado))
        if estado in ("ok", "conferir"):
            self.res[i] = dado
            self.res[i]["_ok"] = estado == "ok"
            self.tab.item(i, 2).setText(dado.get("nome_original") or dado.get("url", ""))
        elif estado in ("nao", "erro"):
            self.tab.item(i, 2).setText(str(dado))
        n = sum(1 for d in self.res.values() if d.get("_ok"))
        self.btn.setEnabled(n > 0)
        self.btn.setText(f"Gravar os conferidos ({n})")

    def _fim(self, msg: str):
        n = sum(1 for d in self.res.values() if d.get("_ok"))
        self.status.setText((msg + " ") if msg else "")
        self.status.setText(self.status.text() + f"Pronto: {n} conferido(s). Os marcados como \"conferir à mão\" "
                            "não são gravados aqui: abra Propriedades do bloco para ver a página.")

    def _gravar(self):
        gravados = []
        for i, d in self.res.items():
            if not d.get("_ok"):
                continue
            a = self.itens[i][0]
            if self.w.db.origin(a.key):
                continue
            self.w.db.set_origin(a.key, make_ficha(None, d["url"], d.get("nome_original", ""),
                                                   d["codigo_imagem"], d.get("autor", ""), "3dsky"))
            gravados.append(a)
        if gravados:
            self.w._rebuild_search_text(gravados)
        QMessageBox.information(self, "Origem", f"{len(gravados)} bloco(s) com a origem gravada.")
        self.accept()

    def _limpar(self, *_):
        self.th.cancel = True
        self.th.wait(30000)


def preencher_em_lote(w, assets: list[Asset]) -> None:
    LoteDialog(w, assets).exec()
