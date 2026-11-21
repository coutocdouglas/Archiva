"""Arrastar da aba Vegetação para o 3ds Max (etapa 3).

O cartão do nível 4 é arrastado como .max puro, igual à Biblioteca: o Max mostra o menu Merge/XRef e o
script do Archiva (archiva_texturas.ms, instalado ao abrir o programa) liga, depois do Merge, as texturas que
estão faltando na cena às pastas que o Archiva avisou em ultimo_arrasto.txt.

Na Vegetação o aviso leva as pastas de textura DO VOLUME, não só a pasta do .max: os modelos Maxtree e Globe
Plants guardam cada textura só pelo nome (ex.: MT_PM_V71_Alpinia_purpurata_01_Leaf_01_albedo.jpg) e as imagens
ficam na pasta Maps do volume (- Maps no padrão de pastas; MT_PM_V71_Maps ou Maps nos volumes não organizados).

Versão a importar: Mesh (o .max original) ou Proxy (o .max pequeno da pasta "- Proxy", que aponta para o
.cproxy). O Proxy é a preferência padrão; enquanto o proxy de um arquivo não existe, o arrasto leva a malha e o
painel avisa (a criação automática do proxy é a etapa 4).

Este módulo não usa Qt: só decide o que arrastar e grava o aviso.
"""
from __future__ import annotations

import os

from . import leitor

MESH = "mesh"
PROXY = "proxy"
MAX_DIRS = 200          # o aviso do Max lê no máximo 200 pastas (max_startup.write_handoff)


def is_proxy_dir(name: str) -> bool:
    """Pasta de proxies: "MT_PM_V071 - Proxy" (padrão de pastas) ou só "Proxy"."""
    n = name.casefold().strip()
    return n == "proxy" or n == "proxies" or n.endswith(" - proxy")


def proxy_max(arq) -> str | None:
    """O .max do proxy deste arquivo, se já existe (o .cproxy sozinho não dá para arrastar para o Max)."""
    p = getattr(arq, "proxy", None)
    if p and p.lower().endswith(".max") and os.path.isfile(p):
        return p
    return None


def versao_efetiva(arq, preferida: str) -> str:
    """O que vai de fato para o Max: Proxy só quando o proxy do arquivo já existe."""
    return PROXY if preferida == PROXY and proxy_max(arq) else MESH


def arquivo_para_arrastar(arq, preferida: str) -> str:
    return proxy_max(arq) if versao_efetiva(arq, preferida) == PROXY else arq.path


def _in_maps(parts: list[str]) -> bool:
    return any("maps" in p for p in parts)      # mesmo critério do leitor (MT_PM_V71_Maps, Maps, "- Maps")


def pastas_texturas(vol_path: str, max_path: str | None = None) -> list[str]:
    """Pastas onde o Max deve procurar as texturas: a do .max, a do proxy e as pastas Maps do volume (com as
    subpastas). Se o volume não tem pasta Maps, todas as pastas dele (texturas soltas ao lado das malhas).
    Pula _DESCARTADOS, "- Outros" e extrações em andamento, como o leitor."""
    vol_path = os.path.normpath(vol_path)
    maps: list[str] = []
    others: list[str] = []
    for dp, dns, _ in os.walk(vol_path):
        dns[:] = sorted((d for d in dns if not leitor._skip_dir(d)), key=leitor.natural_key)
        parts = leitor._parts(dp, vol_path)
        (maps if _in_maps(parts) else others).append(dp)
    # as Maps mais perto da raiz primeiro (a pasta principal antes das subpastas)
    maps.sort(key=lambda d: (d.count(os.sep), leitor.natural_key(d)))
    out: list[str] = []
    if max_path:
        out.append(os.path.dirname(os.path.normpath(max_path)))
    out += maps or others
    seen, uniq = set(), []
    for d in out:
        k = os.path.normcase(d)
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq[:MAX_DIRS]


def nome_do_aviso(esp, arq, versao: str) -> str:
    """Primeira linha do aviso: aparece no MAXScript Listener depois do Merge."""
    return f"{esp.nome} · {arq.rotulo} ({'Proxy' if versao == PROXY else 'Mesh'})"


def preparar(vol, esp, arq, preferida: str) -> tuple[str | None, str]:
    """Decide o arquivo e grava o aviso para o script do Max. Devolve (caminho do .max, mensagem)."""
    versao = versao_efetiva(arq, preferida)
    path = arquivo_para_arrastar(arq, preferida)
    if not path or not os.path.isfile(path):
        return None, f"{esp.nome}: o arquivo não foi encontrado (use Atualizar)."
    dirs = pastas_texturas(vol.path, path)
    if versao == PROXY and os.path.normcase(os.path.dirname(arq.path)) not in {os.path.normcase(d) for d in dirs}:
        dirs.insert(1, os.path.dirname(arq.path))
    from .. import max_startup
    max_startup.write_handoff(nome_do_aviso(esp, arq, versao), path, dirs[:MAX_DIRS])
    msg = f"{esp.nome} · {arq.rotulo}: solte na viewport do 3ds Max e escolha Merge."
    if preferida == PROXY and versao == MESH:
        msg += " Ainda não há proxy deste arquivo: vai a malha (Mesh)."
    return path, msg
