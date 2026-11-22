"""Arrastar da aba Vegetação para o 3ds Max (etapa 3; na 2.0.22, Merge automático).

O cartão do nível 4 não vai como .max (que abre o menu Merge/XRef do Max): vai um pequeno script gerado na hora
(proxy.gravar_soltar), que o Max executa ao soltar. Ele faz o Merge sozinho no ponto onde o mouse soltou, liga as
texturas que faltam às pastas do volume e, quando pedido, cria o proxy. A Biblioteca continua como era.

As pastas levadas são as de textura DO VOLUME, não só a pasta do .max: os modelos Maxtree e Globe Plants guardam
cada textura só pelo nome (ex.: MT_PM_V71_Alpinia_purpurata_01_Leaf_01_albedo.jpg) e as imagens ficam na pasta
Maps do volume (- Maps no padrão de pastas; MT_PM_V71_Maps ou Maps nos volumes não organizados).

Versão a importar: Mesh (o .max original) ou Proxy (o .max pequeno da pasta "- Proxy", que aponta para o
.cproxy). O Proxy é a preferência padrão; enquanto o proxy de um arquivo não existe, vai a malha e o próprio
script do arrasto cria o proxy depois do Merge (etapa 4, proxy.py).

Este módulo não usa Qt: só decide o que arrastar e grava o script.
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


def preparar(vol, esp, arq, preferida: str, espalhar_modo: str = "nada") -> tuple[str | None, str]:
    """Decide o arquivo e grava o script que vai no arrasto (proxy.py): o Max faz o Merge sozinho, sem menu,
    religa as texturas às pastas do volume e, se foi pedido Proxy e ele ainda não existe, cria o proxy.
    Devolve (caminho do script .ms, mensagem)."""
    versao = versao_efetiva(arq, preferida)
    path = arquivo_para_arrastar(arq, preferida)
    if not path or not os.path.isfile(path):
        return None, f"{esp.nome}: o arquivo não foi encontrado (use Atualizar)."
    dirs = pastas_texturas(vol.path, path)
    if versao == PROXY and os.path.normcase(os.path.dirname(arq.path)) not in {os.path.normcase(d) for d in dirs}:
        dirs.insert(1, os.path.dirname(arq.path))
    from . import proxy
    criar = arq.path if preferida == PROXY and versao == MESH and proxy.pode_criar(arq) else None
    proxy.instalar()          # desliga o script de inicialização da 2.0.21, se ele existir
    # o aviso da Biblioteca (archiva_texturas.ms) não vale para este arrasto: o script do arrasto religa sozinho
    from .. import max_startup
    for h in max_startup.handoff_paths():
        try:
            if os.path.isfile(h):
                os.remove(h)
        except OSError:
            pass
    from . import espalhar
    espalhar_modo = espalhar.valido(espalhar_modo)
    ms = proxy.gravar_soltar(path, dirs[:MAX_DIRS], nome_do_aviso(esp, arq, PROXY if criar else versao), criar,
                             espalhar_modo, f"{esp.nome} {arq.rotulo}")
    if not ms:
        return None, f"{esp.nome}: não foi possível preparar o arrasto (pasta do Archiva sem acesso)."
    msg = f"{esp.nome} · {arq.rotulo}: solte na viewport do 3ds Max (entra sozinho, sem o menu Merge)."
    if criar:
        msg += " Ainda não há proxy: vai a malha e o 3ds Max cria o proxy na pasta \"- Proxy\" (precisa do Corona)."
    elif preferida == PROXY and versao == MESH:
        msg += " Este arquivo não tem proxy: vai a malha (Mesh)."
    if espalhar_modo != espalhar.NADA:
        msg += f" Também cria um {espalhar.ROTULO[espalhar_modo]} vazio com a planta."
    return ms, msg
