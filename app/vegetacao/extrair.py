"""Extrair um volume de vegetação que ainda está compactado (decisão da etapa 0, item 4).

  * Extrai numa pasta temporária DENTRO do volume (mesma unidade: depois só renomeia) e move o conteúdo para o volume.
  * Os compactados ficam onde estão. "Organizar" manda para _DESCARTADOS os que já foram extraídos por completo.
  * Se der erro (parte faltando, arquivo corrompido, senha): apaga só a extração parcial que o próprio Archiva criou
    e marca o volume como "corrompido ou fora do padrão" (archiva_extracao.json), sem mexer em mais nada.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import time

from .. import extractor
from . import leitor

MARK = "archiva_extracao.json"
TEMP_PREFIX = "_EXTRAINDO"
_PART = re.compile(r"^(.*?)\.part(\d+)\.rar$", re.I)


def archives_to_extract(vol_path: str) -> list[str]:
    """Um compactado por conjunto: de um .rar em partes, só a parte 1 (o programa lê as outras sozinho)."""
    out, groups = [], {}
    for dp, dns, fns in os.walk(vol_path):
        dns[:] = [d for d in dns if not d.startswith((TEMP_PREFIX, "_"))]
        for fn in sorted(fns, key=leitor.natural_key):
            if os.path.splitext(fn)[1].lower() not in leitor.ARCHIVE_EXT:
                continue
            full = os.path.join(dp, fn)
            m = _PART.match(fn)
            if m:
                key = os.path.join(dp, m.group(1)).casefold()
                if key not in groups or int(m.group(2)) < groups[key][0]:
                    groups[key] = (int(m.group(2)), full)
            else:
                out.append(full)
    out += [p for _, p in groups.values()]
    return sorted(out, key=leitor.natural_key)


def estimate(archives: list[str]) -> int:
    total = 0
    for a in archives:
        kind = extractor._archive_kind(a)
        if _PART.match(os.path.basename(a)):     # tamanho de todas as partes
            base = _PART.match(os.path.basename(a)).group(1)
            d = os.path.dirname(a)
            total += 2 * sum(os.path.getsize(os.path.join(d, f)) for f in os.listdir(d)
                             if f.lower().startswith(base.lower() + ".part") and f.lower().endswith(".rar"))
        else:
            total += extractor._uncompressed_estimate(a, kind) if kind == "zip" else 2 * os.path.getsize(a)
    return total


def free_space(path: str) -> int:
    try:
        return shutil.disk_usage(path).free
    except OSError:
        return 0


def marked_error(vol_path: str) -> str:
    try:
        with open(os.path.join(vol_path, MARK), encoding="utf-8") as f:
            return json.load(f).get("erro", "")
    except (OSError, ValueError):
        return ""


def extrair(vol_path: str, tools: dict[str, str], report=None) -> dict:
    """Extrai tudo. Devolve {"ok": bool, "erro": str, "extraidos": [compactados], "movidos": [itens]}."""
    archives = archives_to_extract(vol_path)
    if not archives:
        return {"ok": False, "erro": "nenhum compactado neste volume", "extraidos": [], "movidos": []}
    tmp = os.path.join(vol_path, TEMP_PREFIX.rstrip("_"))      # nome curto: caminhos longos estouram 260 caracteres
    shutil.rmtree(tmp, ignore_errors=True)     # sobra de uma extração interrompida (pasta criada pelo Archiva)
    done, moved = [], []
    try:
        for i, a in enumerate(archives):
            if report:
                report(i, len(archives), f"Extraindo {os.path.basename(a)} ({i + 1} de {len(archives)})…")
            kind = extractor._archive_kind(a)
            if not kind:
                raise RuntimeError(f"{os.path.basename(a)} não é um compactado reconhecido")
            extractor.raw_extract(a, kind, os.path.join(tmp, str(i)), tools)
            done.append(a)
        # tudo extraiu: move o conteúdo para o volume (nunca sobrescreve)
        for i in range(len(archives)):
            src_root = os.path.join(tmp, str(i))
            for name in sorted(os.listdir(src_root)):
                dest = os.path.join(vol_path, name)
                if os.path.exists(dest):
                    if os.path.isdir(dest) and os.path.isdir(os.path.join(src_root, name)):
                        _merge(os.path.join(src_root, name), dest, moved)
                        continue
                    raise FileExistsError(f"{name} já existe no volume")
                shutil.move(os.path.join(src_root, name), dest)
                moved.append(dest)
        shutil.rmtree(tmp, ignore_errors=True)
        with open(os.path.join(vol_path, MARK), "w", encoding="utf-8") as f:     # extraído por completo
            json.dump({"ok": True, "quando": time.time(), "compactados": [os.path.basename(a) for a in archives]},
                      f, ensure_ascii=False, indent=1)
        return {"ok": True, "erro": "", "extraidos": done, "movidos": moved}
    except Exception as e:  # noqa: BLE001 — qualquer falha: corrompido ou fora do padrão
        shutil.rmtree(tmp, ignore_errors=True)          # só a extração parcial que o Archiva criou
        if moved:       # falhou depois de começar a mover: não desmonta nada, só avisa
            msg = f"extração incompleta ({e}); confira a pasta do volume"
        else:
            msg = _friendly(e)
        with open(os.path.join(vol_path, MARK), "w", encoding="utf-8") as f:
            json.dump({"erro": msg, "quando": time.time(), "compactados": [os.path.basename(a) for a in archives]},
                      f, ensure_ascii=False, indent=1)
        return {"ok": False, "erro": msg, "extraidos": done, "movidos": moved}


def _merge(src: str, dest: str, moved: list[str]) -> None:
    for name in os.listdir(src):
        s, d = os.path.join(src, name), os.path.join(dest, name)
        if os.path.exists(d):
            if os.path.isdir(s) and os.path.isdir(d):
                _merge(s, d, moved)
                continue
            raise FileExistsError(f"{d} já existe")
        shutil.move(s, d)
        moved.append(d)


def _friendly(e: Exception) -> str:
    if isinstance(e, extractor.PasswordError):
        return "compactado protegido por senha"
    t = str(e)
    low = t.lower()
    m = re.search(r"código (\d+)", low)
    code = int(m.group(1)) if m else None
    # códigos de saída do UnRAR/WinRAR: 3 = erro de verificação (CRC), 2 = erro fatal, 9 = não criou arquivos,
    # 10 = nada para extrair, 11 = senha
    if code == 3:
        return "compactado corrompido (erro de verificação)"
    if code == 9:
        return "o Windows não conseguiu criar alguns arquivos (caminho longo demais ou sem permissão na pasta)"
    if code == 11:
        return "compactado protegido por senha"
    if "volume" in low and ("previous" in low or "anterior" in low or "missing" in low or "next" in low):
        return "falta uma parte do compactado"
    if "código 9" in low or "cannot create" in low or "não foi possível criar" in low or "nao foi possivel criar" in low:
        return "o Windows não conseguiu criar alguns arquivos (caminho longo demais ou sem permissão na pasta)"
    if "crc" in low or "checksum" in low or "verifica" in low or "corrupt" in low:
        return "compactado corrompido (erro de verificação)"
    return f"não foi possível extrair ({t[:160]})"
