"""Archiva Servidor: entrega a biblioteca deste computador para quem tem convite (modo Nuvem, 2.0).

Só leitura nesta etapa. Quem decide o que cada pessoa pode fazer é o servidor, nunca o programa de quem acessa:
  * GET /api/info       nome da biblioteca, versão e (com chave válida) o papel da pessoa
  * GET /api/catalogo   categorias + itens (+ tags) de uma vez só, em JSON comprimido
  * GET /api/previa     prévia do item (?k=chave&w=largura; w=0 = original)
  * GET /api/arquivo    o arquivo do item: o compactado como está, a pasta como .zip (sem recompressão) ou o .max

Os caminhos nunca vêm de quem acessa: a chave do item é procurada no catálogo montado aqui, e só os arquivos
listados nele são entregues. A chave de acesso de cada convidado fica só como hash, na configuração deste PC.

O servidor escuta só em 127.0.0.1; quem leva até a internet é o motor de rede (archiva-rede.exe).
O banco de tags é lido só na thread da janela: ela entrega ao servidor um "retrato" pronto (`publicar`).
"""
from __future__ import annotations

import gzip
import hashlib
import hmac
import io
import json
import os
import secrets
import threading
import time
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

from .scanner import Asset, Category

PAPEIS = ("leitor", "colaborador", "admin")
CHUNK = 1024 * 1024


# --------------------------------------------------------------------------- chaves e convidados

def nova_chave() -> str:
    return secrets.token_urlsafe(24)


def hash_chave(chave: str) -> str:
    return hashlib.sha256(chave.encode("utf-8")).hexdigest()


def achar_convidado(convidados: list[dict], chave: str | None) -> dict | None:
    if not chave:
        return None
    h = hash_chave(chave)
    for c in convidados:
        if not c.get("revogado") and hmac.compare_digest(c.get("hash", ""), h):
            return c
    return None


# --------------------------------------------------------------------------- retrato da biblioteca

class Retrato:
    """Tudo o que o servidor entrega, montado de uma vez (na thread da janela) e trocado inteiro."""

    def __init__(self, nome: str, versao: str, cats: list[Category], tags_of=None, rev: int = 0):
        self.nome, self.versao, self.rev = nome, versao, rev
        self.itens: dict[str, Asset] = {}
        arvore = [self._cat(c) for c in cats]
        lista = []
        for c in cats:
            for a in c.all_assets():
                if a.kind == "missing":
                    continue
                self.itens[a.key] = a
                lista.append({
                    "k": a.key, "n": a.name, "c": a.category, "tipo": a.kind,
                    "fmt": (a.archive_type or "") if a.kind == "archive" else "",
                    "prev": bool(a.preview), "pm": round(a.preview_mtime, 3), "t": round(a.added_time, 3),
                    "var": [os.path.basename(m) for m in (a.max_files or [])],
                    "tags": sorted(tags_of(a.key)) if tags_of else [],
                })
        corpo = {"nome": nome, "versao": versao, "rev": rev, "categorias": arvore, "itens": lista}
        self.json_gz = gzip.compress(json.dumps(corpo, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), 6)
        self.etag = '"%s"' % hashlib.sha1(self.json_gz).hexdigest()[:16]
        self.total = len(lista)

    def _cat(self, c: Category) -> dict:
        return {"k": c.key, "n": c.name, "q": len([a for a in c.all_assets() if a.kind != "missing"]),
                "sub": [self._cat(s) for s in c.children]}


# --------------------------------------------------------------------------- servidor

class Servidor:
    """Liga/desliga o servidor HTTP local. `convidados` é lido a cada pedido (pode mudar com o servidor ligado)."""

    def __init__(self, convidados_fn, cache_dir: str | None = None, registrar=None):
        self._convidados_fn = convidados_fn
        self._retrato: Retrato | None = None
        self.cache_dir = cache_dir
        self.registrar = registrar or (lambda *a: None)
        self._http: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self.porta = 0
        self._miniaturas: dict[str, bytes] = {}
        self._mini_lock = threading.Lock()
        self.acessos: dict[str, float] = {}     # convidado -> último acesso (para a tela "quem está usando")

    # chamado pela janela (thread da janela)
    def publicar(self, retrato: Retrato) -> None:
        self._retrato = retrato

    @property
    def ligado(self) -> bool:
        return self._http is not None

    def iniciar(self, porta: int = 0) -> int:
        if self._http:
            return self.porta
        srv = self

        class H(_Handler):
            servidor = srv
        self._http = ThreadingHTTPServer(("127.0.0.1", porta), H)
        self._http.daemon_threads = True
        self.porta = self._http.server_address[1]
        self._thread = threading.Thread(target=self._http.serve_forever, name="archiva-servidor", daemon=True)
        self._thread.start()
        return self.porta

    def parar(self) -> None:
        h, self._http = self._http, None
        if h:
            h.shutdown()
            h.server_close()

    # ---------------------------------------------------------------- miniaturas
    def miniatura(self, caminho: str, largura: int) -> bytes | None:
        try:
            st = os.stat(caminho)
        except OSError:
            return None
        chave = hashlib.sha1(f"{caminho}|{st.st_mtime}|{st.st_size}|{largura}".encode("utf-8", "replace")).hexdigest()
        with self._mini_lock:
            if chave in self._miniaturas:
                return self._miniaturas[chave]
        arq = os.path.join(self.cache_dir, chave[:2], chave + ".jpg") if self.cache_dir else None
        dados = None
        if arq and os.path.exists(arq):
            try:
                with open(arq, "rb") as f:
                    dados = f.read()
            except OSError:
                dados = None
        if dados is None:
            dados = _reduzir(caminho, largura)
            if dados and arq:
                try:
                    os.makedirs(os.path.dirname(arq), exist_ok=True)
                    with open(arq, "wb") as f:
                        f.write(dados)
                except OSError:
                    pass
        if dados:
            with self._mini_lock:
                if len(self._miniaturas) > 800:
                    self._miniaturas.clear()
                self._miniaturas[chave] = dados
        return dados


def _reduzir(caminho: str, largura: int) -> bytes | None:
    """Miniatura em JPEG (QImage é reentrante: pode rodar fora da thread da janela)."""
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice, Qt
        from PySide6.QtGui import QImage
    except ImportError:
        return None
    img = QImage(caminho)
    if img.isNull():
        return None
    if img.width() > largura:
        img = img.scaledToWidth(largura, Qt.SmoothTransformation)
    if img.hasAlphaChannel():
        fundo = QImage(img.size(), QImage.Format_RGB32)
        fundo.fill(0xFFFFFFFF)
        from PySide6.QtGui import QPainter
        p = QPainter(fundo)
        p.drawImage(0, 0, img)
        p.end()
        img = fundo
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "JPG", 86)
    buf.close()
    return bytes(ba)


class _Handler(BaseHTTPRequestHandler):
    servidor: Servidor
    protocol_version = "HTTP/1.1"
    server_version = "Archiva"

    def log_message(self, fmt, *args):   # sem barulho no console
        pass

    # ---------------------------------------------------------------- respostas
    def _json(self, codigo: int, obj, extra: dict | None = None):
        corpo = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def _erro(self, codigo: int, msg: str):
        self._json(codigo, {"erro": msg})

    def _convidado(self) -> dict | None:
        try:
            convidados = self.servidor._convidados_fn() or []
        except Exception:  # noqa: BLE001
            convidados = []
        c = achar_convidado(convidados, self.headers.get("X-Archiva-Chave"))
        if c:
            self.servidor.acessos[c.get("id", "")] = time.time()
        return c

    # ---------------------------------------------------------------- rotas
    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        r = self.servidor._retrato
        try:
            if u.path == "/api/info":
                c = self._convidado()
                return self._json(200, {"app": "archiva", "nome": r.nome if r else "", "versao": r.versao if r else "",
                                        "itens": r.total if r else 0, "pronto": r is not None,
                                        "papel": c.get("papel") if c else None,
                                        "pessoa": c.get("nome") if c else None})
            c = self._convidado()
            if not c:
                return self._erro(403, "convite inválido ou revogado")
            if r is None:
                return self._erro(503, "a biblioteca ainda está sendo lida")
            if u.path == "/api/catalogo":
                return self._catalogo(r)
            if u.path == "/api/previa":
                return self._previa(r, q)
            if u.path == "/api/arquivo":
                return self._arquivo(r, q, c)
            return self._erro(404, "não encontrado")
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return None

    def do_POST(self):   # nada se altera nesta etapa (só leitura)
        self._erro(403, "esta biblioteca é só de leitura")

    do_PUT = do_DELETE = do_PATCH = do_POST

    def _catalogo(self, r: Retrato):
        if self.headers.get("If-None-Match") == r.etag:
            self.send_response(304)
            self.send_header("ETag", r.etag)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Encoding", "gzip")
        self.send_header("ETag", r.etag)
        self.send_header("Content-Length", str(len(r.json_gz)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(r.json_gz)

    def _previa(self, r: Retrato, q: dict):
        a = r.itens.get(q.get("k", ""))
        if not a or not a.preview:
            return self._erro(404, "sem prévia")
        try:
            w = max(0, min(int(q.get("w", "0") or 0), 2400))
        except ValueError:
            w = 0
        if w:
            dados = self.servidor.miniatura(a.preview, w)
            if dados is None:
                return self._erro(404, "prévia ilegível")
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(dados)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(dados)
            return
        ext = os.path.splitext(a.preview)[1].lower().lstrip(".")
        tipo = {"jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png", "webp": "image/webp",
                "bmp": "image/bmp"}.get(ext, "application/octet-stream")
        self._enviar_arquivo(a.preview, tipo, os.path.basename(a.preview))

    def _arquivo(self, r: Retrato, q: dict, c: dict):
        a = r.itens.get(q.get("k", ""))
        if not a:
            return self._erro(404, "item não encontrado")
        self.servidor.registrar("baixar", c.get("nome", "?"), a.key)
        if a.kind == "archive" and a.archive:
            fmt = a.archive_type or os.path.splitext(a.archive)[1].lstrip(".").lower() or "rar"
            return self._enviar_arquivo(a.archive, "application/octet-stream", f"{a.name}.{fmt}",
                                        {"X-Archiva-Tipo": fmt})
        if a.kind == "max" and a.loose_max:
            return self._enviar_arquivo(a.loose_max, "application/octet-stream", os.path.basename(a.loose_max),
                                        {"X-Archiva-Tipo": "max"})
        if a.kind == "folder" and a.folder:
            return self._enviar_pasta(a)
        return self._erro(404, "arquivo do modelo não encontrado")

    # ---------------------------------------------------------------- envio
    def _enviar_arquivo(self, caminho: str, tipo: str, nome: str, extra: dict | None = None):
        try:
            tam = os.path.getsize(caminho)
            f = open(caminho, "rb")
        except OSError:
            return self._erro(404, "arquivo indisponível")
        with f:
            ini, fim = 0, tam - 1
            faixa = self.headers.get("Range", "")
            parcial = False
            if faixa.startswith("bytes="):
                try:
                    a_, b_ = faixa[6:].split(",")[0].split("-")
                    ini = int(a_) if a_ else max(0, tam - int(b_))
                    fim = int(b_) if (a_ and b_) else tam - 1
                    fim = min(fim, tam - 1)
                    parcial = ini <= fim
                except ValueError:
                    parcial = False
                if not parcial:
                    ini, fim = 0, tam - 1
            self.send_response(206 if parcial else 200)
            self.send_header("Content-Type", tipo)
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(fim - ini + 1))
            if parcial:
                self.send_header("Content-Range", f"bytes {ini}-{fim}/{tam}")
            self.send_header("X-Archiva-Nome", _ascii(nome))
            self.send_header("X-Archiva-Tamanho", str(tam))
            for k, v in (extra or {}).items():
                self.send_header(k, v)
            self.end_headers()
            if self.command == "HEAD":
                return
            f.seek(ini)
            falta = fim - ini + 1
            while falta > 0:
                bloco = f.read(min(CHUNK, falta))
                if not bloco:
                    break
                self.wfile.write(bloco)
                falta -= len(bloco)

    def _enviar_pasta(self, a: Asset):
        """Pasta do item como .zip sem recompressão (texturas e .max já não ganham quase nada comprimindo)."""
        base = a.folder
        arquivos = []
        for raiz, _dirs, nomes in os.walk(base):
            for n in nomes:
                if n.casefold() in ("thumbs.db", "desktop.ini", ".ds_store"):
                    continue
                arquivos.append(os.path.join(raiz, n))
        total = 0
        for p in arquivos:
            try:
                total += os.path.getsize(p)
            except OSError:
                pass
        self.send_response(200)
        self.send_header("Content-Type", "application/zip")
        self.send_header("Transfer-Encoding", "chunked")
        self.send_header("X-Archiva-Nome", _ascii(f"{a.name}.zip"))
        self.send_header("X-Archiva-Tipo", "pasta-zip")
        self.send_header("X-Archiva-Tamanho", str(total))
        self.end_headers()
        if self.command == "HEAD":
            self.wfile.write(b"0\r\n\r\n")
            return
        saida = _Chunked(self.wfile)
        with zipfile.ZipFile(saida, "w", zipfile.ZIP_STORED, allowZip64=True) as z:
            for p in arquivos:
                rel = os.path.relpath(p, os.path.dirname(base))
                try:
                    z.write(p, rel)
                except OSError:
                    continue
        saida.fechar()


class _Chunked(io.RawIOBase):
    """Saída 'chunked' do HTTP/1.1 que o zipfile consegue usar sem saber o tamanho final (não precisa de seek)."""

    def __init__(self, w):
        self.w, self.pos = w, 0

    def writable(self):
        return True

    def write(self, b):
        b = bytes(b)
        if b:
            self.w.write(b"%x\r\n" % len(b) + b + b"\r\n")
            self.pos += len(b)
        return len(b)

    def tell(self):
        return self.pos

    def flush(self):
        try:
            self.w.flush()
        except OSError:
            pass

    def fechar(self):
        self.w.write(b"0\r\n\r\n")
        self.flush()


def _ascii(s: str) -> str:
    """Cabeçalho HTTP só aceita latin-1: o nome vai codificado (o cliente decodifica)."""
    from urllib.parse import quote
    return quote(s, safe=" ._-()")
