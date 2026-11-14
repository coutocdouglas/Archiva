"""Lado de quem acessa uma biblioteca da Nuvem: convite, conversa com o servidor e cópias locais dos modelos.

Nada aqui depende da janela: a janela da Nuvem chama estas funções em ajudantes (segundo_plano), nunca na thread
da janela, porque tudo passa pela internet.

Onde ficam as coisas (no PC de quem acessa, nunca na biblioteca de ninguém):
  %LOCALAPPDATA%\\GerenciadorAssets3D\\nuvem\\<id da biblioteca>\\
      catalogo.json      último catálogo recebido (abre na hora, mesmo com o servidor desligado)
      previas\\          miniaturas já vistas
      modelos\\<categoria>\\<item>\\   modelos baixados e extraídos (prontos para arrastar para o Max)
"""
from __future__ import annotations

import base64
import gzip
import hashlib
import json
import os
import shutil
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import quote, unquote

PREFIXO = "ARCHIVA2-"


# --------------------------------------------------------------------------- convite

def criar_convite(host: str, chave: str, nome: str, authkey: str = "", local: str = "") -> str:
    """Texto que o dono da biblioteca manda para a pessoa (WhatsApp, e-mail…). Uma linha só."""
    d = {"h": host, "k": chave, "n": nome}
    if authkey:
        d["a"] = authkey
    if local:
        d["l"] = local
    raw = json.dumps(d, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return PREFIXO + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def ler_convite(texto: str) -> dict:
    t = "".join((texto or "").split())
    i = t.find(PREFIXO)
    if i < 0:
        raise ValueError("Isso não parece um convite do Archiva (começa com ARCHIVA2-).")
    corpo = t[i + len(PREFIXO):]
    corpo += "=" * (-len(corpo) % 4)
    try:
        d = json.loads(base64.urlsafe_b64decode(corpo.encode("ascii")).decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise ValueError("O convite está incompleto. Copie de novo a linha inteira.") from e
    if not d.get("h") or not d.get("k"):
        raise ValueError("O convite está incompleto. Copie de novo a linha inteira.")
    return d


def id_biblioteca(host: str, chave: str) -> str:
    return hashlib.sha1(f"{host}|{chave}".encode("utf-8")).hexdigest()[:12]


def pasta_nuvem() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return Path(base) / "GerenciadorAssets3D" / "nuvem"


# --------------------------------------------------------------------------- catálogo

@dataclass
class ItemRemoto:
    key: str
    name: str
    category: str
    tipo: str                 # archive | folder | max
    fmt: str = ""
    tem_previa: bool = False
    previa_mtime: float = 0.0
    added_time: float = 0.0
    variacoes: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    search_text: str = ""


@dataclass
class CategoriaRemota:
    key: str
    name: str
    quantidade: int
    children: list["CategoriaRemota"] = field(default_factory=list)


@dataclass
class Catalogo:
    nome: str
    versao: str
    categorias: list[CategoriaRemota]
    itens: list[ItemRemoto]
    recebido: float = 0.0
    do_cache: bool = False

    def por_chave(self) -> dict[str, ItemRemoto]:
        return {i.key: i for i in self.itens}


def _cat(d: dict) -> CategoriaRemota:
    return CategoriaRemota(d["k"], d["n"], int(d.get("q", 0)), [_cat(s) for s in d.get("sub", [])])


def catalogo_de(dados: dict, recebido: float = 0.0, do_cache: bool = False) -> Catalogo:
    from .scanner import normalize
    itens = []
    for d in dados.get("itens", []):
        it = ItemRemoto(d["k"], d["n"], d["c"], d.get("tipo", "archive"), d.get("fmt", ""), bool(d.get("prev")),
                        float(d.get("pm", 0)), float(d.get("t", 0)), list(d.get("var", [])), list(d.get("tags", [])))
        it.search_text = normalize(" ".join([it.name, it.category, *it.tags]))
        itens.append(it)
    return Catalogo(dados.get("nome", ""), dados.get("versao", ""), [_cat(c) for c in dados.get("categorias", [])],
                    itens, recebido, do_cache)


# --------------------------------------------------------------------------- conexão

class SemAcesso(Exception):
    """Convite revogado ou inválido (o servidor respondeu 403)."""


class Desligada(Exception):
    """O computador da biblioteca não respondeu (desligado, sem internet ou o Archiva fechado lá)."""


class Remota:
    """Uma biblioteca da Nuvem. `base` é o endereço que leva ao servidor (o motor de rede ou um endereço local)."""

    def __init__(self, ident: str, base: str, chave: str, nome: str = ""):
        self.ident, self.base, self.chave, self.nome = ident, base.rstrip("/"), chave, nome
        self.pasta = pasta_nuvem() / ident
        self.pasta.mkdir(parents=True, exist_ok=True)

    # ---------------------------------------------------------------- HTTP
    def _pedir(self, caminho: str, cab: dict | None = None, tempo: float = 20.0):
        h = {"X-Archiva-Chave": self.chave, "Accept-Encoding": "gzip"}
        h.update(cab or {})
        req = urllib.request.Request(self.base + caminho, headers=h)
        # o motor de rede é local: nunca passar por proxy do sistema
        abridor = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            return abridor.open(req, timeout=tempo)
        except urllib.error.HTTPError as e:
            if e.code == 304:
                return e
            if e.code == 403:
                raise SemAcesso("Este convite não vale mais. Peça um novo ao dono da biblioteca.") from e
            if e.code in (502, 503, 504):
                try:
                    corpo = e.read(300).decode("utf-8", "replace")
                except Exception:  # noqa: BLE001
                    corpo = ""
                raise Desligada(f"O computador da biblioteca não respondeu (HTTP {e.code}). {corpo}".strip()) from e
            raise
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
            raise Desligada(f"O computador da biblioteca não respondeu ({type(e).__name__}: {e}).") from e

    def info(self) -> dict:
        with self._pedir("/api/info", tempo=10) as r:
            d = json.loads(r.read().decode("utf-8"))
        if d.get("app") != "archiva":
            raise Desligada("O endereço não é uma biblioteca do Archiva.")
        if d.get("nome"):
            self.nome = d["nome"]
        return d

    # ---------------------------------------------------------------- catálogo (com cópia local)
    def catalogo_salvo(self) -> Catalogo | None:
        f = self.pasta / "catalogo.json"
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            return catalogo_de(d["dados"], d.get("recebido", 0.0), do_cache=True)
        except (OSError, ValueError, KeyError):
            return None

    def catalogo(self) -> Catalogo:
        f = self.pasta / "catalogo.json"
        salvo = None
        try:
            salvo = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
        cab = {"If-None-Match": salvo["etag"]} if salvo and salvo.get("etag") else {}
        r = self._pedir("/api/catalogo", cab, tempo=60)
        with r:
            if getattr(r, "code", 200) == 304 and salvo:
                salvo["recebido"] = time.time()
                _gravar_json(f, salvo)
                return catalogo_de(salvo["dados"], salvo["recebido"])
            bruto = r.read()
            if r.headers.get("Content-Encoding") == "gzip":
                bruto = gzip.decompress(bruto)
            dados = json.loads(bruto.decode("utf-8"))
            etag = r.headers.get("ETag", "")
        agora = time.time()
        _gravar_json(f, {"etag": etag, "recebido": agora, "dados": dados})
        if dados.get("nome"):
            self.nome = dados["nome"]
        return catalogo_de(dados, agora)

    # ---------------------------------------------------------------- prévias
    def previa(self, it: ItemRemoto, largura: int = 340, so_disco: bool = False) -> bytes | None:
        nome = hashlib.sha1(f"{it.key}|{it.previa_mtime}|{largura}".encode("utf-8")).hexdigest() + ".jpg"
        arq = self.pasta / "previas" / nome[:2] / nome
        if arq.exists():
            try:
                return arq.read_bytes()
            except OSError:
                pass
        if not it.tem_previa or so_disco:
            return None
        try:
            with self._pedir(f"/api/previa?k={quote(it.key)}&w={largura}", tempo=30) as r:
                dados = r.read()
        except urllib.error.HTTPError:
            return None
        try:
            arq.parent.mkdir(parents=True, exist_ok=True)
            arq.write_bytes(dados)
        except OSError:
            pass
        return dados

    # ---------------------------------------------------------------- modelos baixados
    def pasta_item(self, it: ItemRemoto) -> Path:
        partes = [_seguro(p) for p in it.key.split("/") if p]
        return self.pasta.joinpath("modelos", *partes)

    def baixado(self, it: ItemRemoto) -> Path | None:
        p = self.pasta_item(it)
        return p if (p / ".pronto").exists() else None

    def baixar(self, it: ItemRemoto, progresso=None, cancelado=None) -> Path:
        """Baixa (continuando de onde parou, se a conexão cair) e deixa a pasta pronta para arrastar.

        progresso(baixados, total); cancelado() -> True para parar. Devolve a pasta do item.
        """
        destino = self.pasta_item(it)
        temp = self.pasta / "baixando"
        temp.mkdir(parents=True, exist_ok=True)
        parcial = temp / (hashlib.sha1(it.key.encode("utf-8")).hexdigest() + ".parte")
        tentativas = 0
        while True:
            ja = parcial.stat().st_size if parcial.exists() else 0
            cab = {"Range": f"bytes={ja}-"} if ja and it.tipo != "folder" else {}
            if it.tipo == "folder" and ja:
                parcial.unlink(missing_ok=True)   # pasta vem montada na hora: não dá para continuar no meio
                ja = 0
            try:
                r = self._pedir(f"/api/arquivo?k={quote(it.key)}", cab, tempo=60)
                with r:
                    total = int(r.headers.get("X-Archiva-Tamanho") or 0)
                    tipo = r.headers.get("X-Archiva-Tipo", it.fmt or "")
                    nome = unquote(r.headers.get("X-Archiva-Nome", "") or it.name)
                    if getattr(r, "status", 200) != 206:
                        ja = 0
                    with open(parcial, "ab" if ja else "wb") as f:
                        feito = ja
                        while True:
                            if cancelado and cancelado():
                                raise InterruptedError("cancelado")
                            bloco = r.read(1024 * 256)
                            if not bloco:
                                break
                            f.write(bloco)
                            feito += len(bloco)
                            if progresso:
                                progresso(feito, total)
                break
            except Desligada:
                tentativas += 1
                if tentativas > 4:
                    raise
                time.sleep(2 * tentativas)
        return self._preparar(it, parcial, tipo, nome, destino)

    def _preparar(self, it: ItemRemoto, arquivo: Path, tipo: str, nome: str, destino: Path) -> Path:
        from . import extractor
        if destino.exists():
            shutil.rmtree(destino, ignore_errors=True)
        destino.mkdir(parents=True, exist_ok=True)
        if tipo == "max":
            shutil.move(str(arquivo), str(destino / (nome if nome.lower().endswith(".max") else it.name + ".max")))
        else:
            kind = "zip" if tipo in ("zip", "pasta-zip") else (tipo or None)
            if kind not in ("zip", "rar", "7z"):
                kind = extractor._archive_kind(str(arquivo))
            from .config import Config
            cfg = Config()
            ferramentas = extractor.find_tool(cfg["unrar_path"] or "")
            extrair = destino.parent / (destino.name + ".extraindo")
            shutil.rmtree(extrair, ignore_errors=True)
            extractor.raw_extract_with_passwords(str(arquivo), kind, str(extrair), ferramentas, cfg["passwords"] or [])
            shutil.rmtree(destino, ignore_errors=True)
            # se tudo veio dentro de uma pasta só, sobe um nível (fica <item>\*.max)
            dentro = [p for p in extrair.iterdir()]
            if len(dentro) == 1 and dentro[0].is_dir():
                shutil.move(str(dentro[0]), str(destino))
                shutil.rmtree(extrair, ignore_errors=True)
            else:
                extrair.rename(destino)
            arquivo.unlink(missing_ok=True)
        (destino / ".pronto").write_text(json.dumps({"key": it.key, "quando": time.time()}), encoding="utf-8")
        return destino

    def apagar_copia(self, it: ItemRemoto) -> None:
        shutil.rmtree(self.pasta_item(it), ignore_errors=True)

    def espaco_usado(self) -> int:
        total = 0
        for raiz, _d, nomes in os.walk(self.pasta / "modelos"):
            for n in nomes:
                try:
                    total += os.path.getsize(os.path.join(raiz, n))
                except OSError:
                    pass
        return total


def max_do_item(pasta: Path) -> tuple[str | None, list[str], list[str]]:
    """(.max principal, todos os .max, pastas de textura) de um modelo baixado — para arrastar para o Max."""
    from .scanner import pick_primary, walk_item
    maxes, _arqs, _lixo = walk_item(str(pasta))
    dirs = [str(pasta)]
    for raiz, subs, _n in os.walk(pasta):
        if raiz[len(str(pasta)):].count(os.sep) >= 5:
            subs[:] = []
        dirs.extend(os.path.join(raiz, s) for s in subs)
    return pick_primary(maxes), maxes, dirs


def _seguro(s: str) -> str:
    s = "".join("_" if c in '<>:"\\|?*' or ord(c) < 32 else c for c in s).strip(" .")
    return s or "_"


def _gravar_json(f: Path, obj) -> None:
    tmp = f.with_suffix(".tmp")
    try:
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, f)
    except OSError:
        pass
