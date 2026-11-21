"""Receber coleções novas (2.0.20): o que foi baixado na pasta de entrada (ex.: F:\\COLECOES\\_ENTRADAS) vai, por
escolha da pessoa, para a pasta da coleção certa (Maxtree, Globe Plants), ainda compactado. Daí segue o fluxo de
sempre na aba Vegetação: Extrair volume › Organizar volume.

Regras:
  * Agrupa por VOLUME, não por arquivo: "Maxtree - Plant Models Vol.130.part1.rar", ".part2.rar" e
    "MT_PM_V130.pdf" são um pacote só (Vol 130). Sem número no nome, cada compactado (com as partes) é um pacote.
  * Sugere a coleção pelo nome (Maxtree / MT_PM → Maxtree; Globe / GP_B → Globe Plants) e o nome da pasta no
    padrão das coleções ("Maxtree - Plant Models Vol 130", "Globe Plants – Bundle 65"). A pessoa confere e pode
    trocar os dois antes de mover. Nada é renomeado sem ela ver.
  * Se a pasta do volume já existe na coleção, os arquivos entram nela (completar um volume, como a parte que
    faltava), desde que nenhum arquivo tenha o mesmo nome. Pasta baixada já extraída só entra se não existir.
  * Nunca apaga: no mesmo disco, move (renomeia); entre discos, copia, confere o tamanho e só então tira da
    entrada. Download em andamento (.crdownload, .part, mexido há menos de 1 minuto) fica esperando.

Este módulo não usa Qt.
"""
from __future__ import annotations

import collections
import json
import os
import re
import shutil
import time
from dataclasses import dataclass, field

from . import leitor

CONFIG_FILE = "vegetacao_entrada.json"     # em %APPDATA%\GerenciadorAssets3D: {"pasta": "F:\\COLECOES\\_ENTRADAS"}
PASTA_PADRAO = "_ENTRADAS"                  # sugerida ao lado das coleções (F:\COLECOES\_ENTRADAS)
BAIXANDO_EXT = {".crdownload", ".part", ".partial", ".download", ".tmp", ".!ut", ".opdownload"}
RECENTE_S = 60
IGNORAR = leitor.IGNORED_FILES | {"archiva_entrada.json"}

_NUM = [
    ("maxtree", re.compile(r"\bMT_PM_V0*(\d{1,4})(?!\d)", re.I)),
    ("globe", re.compile(r"\bGP_B0*(\d{1,4})(?!\d)", re.I)),
    ("", re.compile(r"\bvol(?:ume)?[ ._-]*0*(\d{1,4})(?!\d)", re.I)),
    ("", re.compile(r"\bbundle[ ._-]*0*(\d{1,4})(?!\d)", re.I)),
]
_PART = re.compile(r"^(.*?)(?:\.part\d+)?\.(rar|zip|7z)$", re.I)


# ----------------------------------------------------------------------------- configuração

def load_pasta(cfg_dir: str) -> str | None:
    try:
        with open(os.path.join(cfg_dir, CONFIG_FILE), encoding="utf-8") as f:
            p = json.load(f).get("pasta")
        return p if isinstance(p, str) and p else None
    except (OSError, ValueError, AttributeError):
        return None


def save_pasta(cfg_dir: str, pasta: str) -> None:
    try:
        with open(os.path.join(cfg_dir, CONFIG_FILE), "w", encoding="utf-8") as f:
            json.dump({"pasta": pasta}, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


def sugerir_pasta(colecoes: list[str]) -> str | None:
    """_ENTRADAS ao lado das coleções (F:\\COLECOES\\_ENTRADAS), se existir."""
    for c in colecoes:
        p = os.path.join(os.path.dirname(os.path.normpath(c)), PASTA_PADRAO)
        if os.path.isdir(p):
            return p
    return None


# ----------------------------------------------------------------------------- nomes

def tipo_colecao(nome: str) -> str:
    """'maxtree' | 'globe' | '' pelo nome do arquivo/pasta."""
    low = nome.casefold()
    if "maxtree" in low or re.search(r"\bmt_pm", low):
        return "maxtree"
    if "globe" in low or re.search(r"\bgp_b\d", low):
        return "globe"
    return ""


def numero(nome: str) -> int | None:
    for _, rx in _NUM:
        m = rx.search(nome)
        if m:
            return int(m.group(1))
    return None


def nome_pasta(tipo: str, n: int | None, original: str) -> str:
    """Nome da pasta do volume no padrão que as coleções já usam."""
    if n is not None and tipo == "maxtree":
        return f"Maxtree - Plant Models Vol {n:03d}"
    if n is not None and tipo == "globe":
        return f"Globe Plants – Bundle {n}"
    return original


def colecao_do_tipo(cols, tipo: str):
    """A coleção configurada que corresponde ao tipo (pela chave: veg:maxtree, veg:globe-plants)."""
    if not tipo:
        return None
    return next((c for c in cols if tipo in c.key), None)


# ----------------------------------------------------------------------------- listar

@dataclass
class Pacote:
    chave: str                       # agrupamento ("maxtree:130", "arq:nome-base", "pasta:nome")
    nome: str                        # o que aparece na tela
    itens: list[str] = field(default_factory=list)      # caminhos na entrada (arquivos ou uma pasta)
    tamanho: int = 0
    tipo: str = ""                   # maxtree | globe | ""
    numero: int | None = None
    pasta: bool = False              # True = pasta baixada já extraída
    baixando: bool = False
    avisos: list[str] = field(default_factory=list)

    @property
    def sugestao(self) -> str:
        return nome_pasta(self.tipo, self.numero, self.nome)


def _size(p: str) -> int:
    try:
        if os.path.isdir(p):
            return sum(os.path.getsize(os.path.join(dp, f)) for dp, _, fns in os.walk(p) for f in fns)
        return os.path.getsize(p)
    except OSError:
        return 0


def _mtime(p: str) -> float:
    try:
        if os.path.isdir(p):
            return max([os.path.getmtime(os.path.join(dp, f)) for dp, _, fns in os.walk(p) for f in fns]
                       or [os.path.getmtime(p)])
        return os.path.getmtime(p)
    except OSError:
        return 0.0


def listar(pasta: str, agora: float | None = None) -> list[Pacote]:
    """Pacotes na pasta de entrada (só o primeiro nível; não mexe em nada)."""
    agora = time.time() if agora is None else agora
    try:
        entries = sorted(os.scandir(pasta), key=lambda e: leitor.natural_key(e.name))
    except OSError:
        return []
    grupos: dict[str, Pacote] = collections.OrderedDict()
    baixando_bases: set[str] = set()
    for e in entries:
        name = e.name
        if name.casefold() in IGNORAR or name.startswith(("~", ".")):
            continue
        stem, ext = os.path.splitext(name)
        if not e.is_dir() and ext.lower() in BAIXANDO_EXT:      # "x.part3.rar.crdownload"
            baixando_bases.add(_base(stem).casefold())
            n = numero(stem)
            if n is not None:
                baixando_bases.add(f"{tipo_colecao(stem)}:{n}")
            continue
        tipo, n = tipo_colecao(name), numero(name)
        if e.is_dir():
            key = f"{tipo}:{n}" if n is not None and tipo else f"pasta:{name.casefold()}"
            label = name
        elif ext.lower() in leitor.ARCHIVE_EXT or ext.lower() == ".pdf" or ext.lower() in leitor.IMAGE_EXT:
            if n is not None and tipo:
                key = f"{tipo}:{n}"
            elif ext.lower() in leitor.ARCHIVE_EXT:
                key = f"arq:{_base(name).casefold()}"
            else:
                continue                      # PDF/imagem solta sem volume: fica na entrada
            label = _base(name)
        else:
            continue                          # outros arquivos ficam onde estão
        p = grupos.get(key)
        if p is None:
            p = grupos[key] = Pacote(key, label, tipo=tipo, numero=n)
        if e.is_dir():
            p.pasta = True
        p.itens.append(e.path)
    out = []
    for p in grupos.values():
        p.tamanho = sum(_size(i) for i in p.itens)
        if any(agora - _mtime(i) < RECENTE_S for i in p.itens) or \
                any(_base(os.path.basename(i)).casefold() in baixando_bases for i in p.itens) or \
                p.chave in baixando_bases:
            p.baixando = True
            p.avisos.append("ainda baixando")
        arqs = [(i, _size(i)) for i in p.itens if os.path.splitext(i)[1].lower() in leitor.ARCHIVE_EXT]
        falta = leitor._archive_problem(arqs)
        if falta:
            p.avisos.append(falta)
        if p.pasta and len(p.itens) > 1:
            p.avisos.append("pasta e arquivos soltos do mesmo volume")
        if p.numero is None:
            p.avisos.append("sem número de volume no nome")
        if not p.tipo:
            p.avisos.append("coleção não reconhecida pelo nome")
        out.append(p)
    return out


def _base(name: str) -> str:
    m = _PART.match(name)
    return m.group(1) if m else os.path.splitext(name)[0]


# ----------------------------------------------------------------------------- conferir / mover

def destino(pacote: Pacote, col_path: str, pasta_nome: str) -> str:
    return os.path.join(os.path.normpath(col_path), pasta_nome.strip())


def conferir(pacote: Pacote, col_path: str, pasta_nome: str) -> str:
    """Motivo para não mover ("" = pode). Só lê."""
    nome = pasta_nome.strip()
    if not nome or nome != os.path.basename(nome) or nome in (".", "..") or re.search(r'[<>:"/\\|?*]', nome):
        return "nome de pasta inválido"
    if nome.startswith("_"):
        return "o nome não pode começar com _ (a Vegetação ignora essas pastas)"
    if pacote.baixando:
        return "ainda baixando"
    if not os.path.isdir(col_path):
        return "a pasta da coleção não foi encontrada"
    dest = destino(pacote, col_path, nome)
    entrada = os.path.dirname(pacote.itens[0])
    if os.path.normcase(os.path.normpath(dest)).startswith(os.path.normcase(os.path.normpath(entrada)) + os.sep):
        return "o destino fica dentro da pasta de entrada"
    if pacote.pasta and len(pacote.itens) > 1:
        return "pasta e arquivos soltos do mesmo volume: junte numa pasta só antes"
    if pacote.pasta:
        return "já existe uma pasta com esse nome na coleção" if os.path.exists(dest) else ""
    if os.path.exists(dest) and not os.path.isdir(dest):
        return "já existe um arquivo com esse nome na coleção"
    for i in pacote.itens:
        if os.path.exists(os.path.join(dest, os.path.basename(i))):
            return f"{os.path.basename(i)} já existe na pasta do volume"
    return ""


def _mesmo_disco(a: str, b: str) -> bool:
    return os.path.splitdrive(os.path.abspath(a))[0].casefold() == os.path.splitdrive(os.path.abspath(b))[0].casefold()


def _copiar_e_tirar(src: str, dst: str, report=None) -> None:
    """Entre discos: copia, confere o tamanho de cada arquivo e só então tira da entrada."""
    if os.path.isdir(src):
        shutil.copytree(src, dst)
        for dp, _, fns in os.walk(src):
            for f in fns:
                a = os.path.join(dp, f)
                b = os.path.join(dst, os.path.relpath(a, src))
                if not os.path.isfile(b) or os.path.getsize(a) != os.path.getsize(b):
                    raise OSError(f"cópia diferente do original: {b}")
        shutil.rmtree(src)
    else:
        shutil.copy2(src, dst)
        if os.path.getsize(src) != os.path.getsize(dst):
            raise OSError(f"cópia diferente do original: {dst}")
        os.remove(src)


def mover(pacote: Pacote, col_path: str, pasta_nome: str, report=None) -> str:
    """Leva o pacote para a coleção. Devolve a pasta do volume. Levanta erro sem ter apagado nada."""
    motivo = conferir(pacote, col_path, pasta_nome)
    if motivo:
        raise ValueError(motivo)
    dest = destino(pacote, col_path, pasta_nome)
    same = _mesmo_disco(pacote.itens[0], dest)
    if pacote.pasta:
        if report:
            report(0, 1, os.path.basename(pacote.itens[0]))
        os.replace(pacote.itens[0], dest) if same else _copiar_e_tirar(pacote.itens[0], dest)
        return dest
    os.makedirs(dest, exist_ok=True)
    for k, i in enumerate(pacote.itens):
        if report:
            report(k, len(pacote.itens), os.path.basename(i))
        alvo = os.path.join(dest, os.path.basename(i))
        if os.path.exists(alvo):
            raise FileExistsError(f"Já existe: {alvo}")
        os.replace(i, alvo) if same else _copiar_e_tirar(i, alvo)
    return dest
