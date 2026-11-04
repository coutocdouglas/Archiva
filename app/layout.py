"""Padrão de pasta de um item — regra ÚNICA usada pela extração e pelo organizador.

    ITEM\\
        *.max                      todos os .max na raiz
        <nome do .max>.jpg         imagem com o nome de um .max, ao lado dele
        MAPS\\                      todo o resto, sem subpastas
                                   (exceção: texturas DIFERENTES com o mesmo nome -> mantém subpastas)

Texturas nunca são renomeadas. Arquivos idênticos repetidos viram um só.
"""
from __future__ import annotations

import filecmp
import os
import re
import shutil
import sys
import time
from dataclasses import dataclass, field

from .scanner import IMAGE_EXT, MAPS_NAMES

JUNK_FILES = {"thumbs.db", "desktop.ini", ".ds_store"}
JUNK_DIRS = {"__macosx"}
STAGING = "__organizando__"


def safe_name(s: str) -> str:
    s = re.sub(r'[<>:"|?*\x00-\x1f]', "_", s).strip(" .")
    return s or "_"


def same_file(a: str, b: str, deep: bool = True) -> bool:
    try:
        if os.path.getsize(a) != os.path.getsize(b):
            return False
        return filecmp.cmp(a, b, shallow=False) if deep else True
    except OSError:
        return False


def walk_files(root: str, skip_dirs: set[str] | None = None):
    """Todos os arquivos (sem lixo do sistema). Retorna (arquivos, lixo)."""
    files, junk = [], []
    skip = {d.casefold() for d in (skip_dirs or set())}
    for dirpath, dirnames, names in os.walk(root):
        keep = []
        for d in dirnames:
            if d.casefold() in JUNK_DIRS:
                junk.append(os.path.join(dirpath, d))
            elif d.casefold() not in skip:
                keep.append(d)
        dirnames[:] = keep
        for f in names:
            (junk if f.casefold() in JUNK_FILES else files).append(os.path.join(dirpath, f))
    return files, junk


def renderer_of(filename: str) -> str | None:
    """'corona' / 'vray' / None, pelo nome do arquivo (v-ray, v_ray, vray, VR, Corona 2020, CR...)."""
    n = os.path.splitext(os.path.basename(filename))[0].lower()
    compact = re.sub(r"[\s\-_.()\[\]]+", "", n)
    tokens = [t for t in re.split(r"[^a-z0-9]+", n) if t]
    if "corona" in compact or "cr" in tokens or "crn" in tokens:
        return "corona"
    if "vray" in compact or "vr" in tokens:
        return "vray"
    return None


@dataclass
class Plan:
    moves: list[tuple[str, str]] = field(default_factory=list)   # (origem absoluta, destino relativo)
    duplicates: list[str] = field(default_factory=list)           # cópias idênticas (podem ser apagadas)
    conflict: bool = False                                        # texturas diferentes com o mesmo nome
    warnings: list[str] = field(default_factory=list)
    max_rel: list[str] = field(default_factory=list)


def plan_layout(files: list[str], base: str | None = None, deep_compare: bool = True) -> Plan:
    """Calcula para onde vai cada arquivo. `base` = pasta atual (organizar) ou None (extração)."""
    plan = Plan()
    files = sorted(files, key=lambda f: (f.count(os.sep), f.casefold()))  # mais rasos primeiro
    max_files = [f for f in files if f.lower().endswith(".max")]
    max_stems = {os.path.splitext(os.path.basename(m))[0].casefold() for m in max_files}

    def beside_max(f: str) -> bool:
        stem, ext = os.path.splitext(os.path.basename(f))
        return ext.lower() == ".max" or (ext.lower() in IMAGE_EXT and stem.casefold() in max_stems)

    maps_files = [f for f in files if not beside_max(f)]
    groups: dict[str, list[str]] = {}
    for f in maps_files:
        groups.setdefault(os.path.basename(f).casefold(), []).append(f)
    plan.conflict = any(len(g) > 1 and any(not same_file(g[0], x, deep_compare) for x in g[1:])
                        for g in groups.values())
    common = None
    if plan.conflict:
        dirs = [os.path.dirname(f) for f in maps_files]
        try:
            common = os.path.commonpath(dirs)
        except ValueError:
            common = os.path.dirname(dirs[0])
        plan.warnings.append("Havia texturas diferentes com o mesmo nome em pastas diferentes. Para não quebrar o "
                             "vínculo com o .max, nenhum arquivo foi renomeado e a MAPS deste item manteve as "
                             "subpastas originais.")

    taken: dict[str, str] = {}  # destino (casefold) -> origem
    for f in files:
        name = os.path.basename(f)
        if beside_max(f):
            rel = name
            if rel.casefold() in taken:
                if same_file(taken[rel.casefold()], f, deep_compare):
                    plan.duplicates.append(f)
                    continue
                if name.lower().endswith(".max"):
                    stem, ext = os.path.splitext(name)
                    parent = safe_name(os.path.basename(os.path.dirname(f))) or "2"
                    rel = f"{stem} ({parent}){ext}"
                    i = 2
                    while rel.casefold() in taken:
                        rel = f"{stem} ({parent} {i}){ext}"
                        i += 1
                    plan.warnings.append(f"Dois .max diferentes com o mesmo nome: o segundo ficou como '{rel}'")
                else:
                    stem, ext = os.path.splitext(name)
                    i = 2
                    while f"{stem} ({i}){ext}".casefold() in taken:
                        i += 1
                    rel = f"{stem} ({i}){ext}"
        elif plan.conflict:
            parts = os.path.relpath(f, common).split(os.sep)
            if len(parts) > 1 and parts[0].casefold() in MAPS_NAMES:
                parts = parts[1:]
            rel = os.path.join("MAPS", *parts)
            if rel.casefold() in taken:
                plan.duplicates.append(f)
                continue
        else:
            rel = os.path.join("MAPS", name)
            if rel.casefold() in taken:  # só cai aqui se for idêntico (senão seria conflito)
                plan.duplicates.append(f)
                continue
        taken[rel.casefold()] = f
        plan.moves.append((f, rel))
        if rel.lower().endswith(".max"):
            plan.max_rel.append(rel)
    return plan


def _rel_is_same(src: str, base: str, rel: str) -> bool:
    return os.path.relpath(src, base).casefold() == rel.casefold()


# --------------------------------------------------------------------------- verificação (rápida, para a leitura)

def check_layout(folder: str, outer_preview: str | None, unwanted_ext: set[str],
                 walked: tuple[list[str], list[str]] | None = None) -> list[str]:
    """Motivos pelos quais a pasta está fora do padrão (lista vazia = organizada).

    `walked` = (arquivos, lixo) já lidos pela leitura (scanner.walk_item), para não percorrer a pasta de novo."""
    if walked is not None:
        files, junk = walked
    else:
        try:
            files, junk = walk_files(folder)
        except OSError:
            return []
    present = {os.path.normcase(f) for f in files}
    if not any(f.lower().endswith(".max") for f in files):
        return []
    plan = plan_layout(files, folder, deep_compare=False)
    reasons = []
    moving = [(s, r) for s, r in plan.moves if not _rel_is_same(s, folder, r)]
    if any(r.lower().endswith(".max") for _, r in moving):
        reasons.append("Arquivo .max dentro de subpasta")
    if any(not r.lower().endswith(".max") and os.sep not in os.path.relpath(s, folder) for s, r in moving):
        reasons.append("Arquivos soltos fora da MAPS")
    elif moving:
        reasons.append("Texturas fora da pasta MAPS ou em subpastas")
    if plan.duplicates:
        reasons.append(f"{len(plan.duplicates)} arquivo(s) repetido(s)")
    if outer_preview:
        for r in plan.max_rel:
            stem = os.path.splitext(os.path.join(folder, r))[0]
            if not any(os.path.normcase(stem + e) in present for e in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG")):
                reasons.append("Falta a cópia da prévia com o nome do .max")
                break
    maxes = [r for r in plan.max_rel]
    if any(renderer_of(m) == "corona" for m in maxes) and any(renderer_of(m) == "vray" for m in maxes):
        reasons.append("Versão V-Ray junto com versão Corona")
    if unwanted_ext and any(os.path.splitext(f)[1].lower() in unwanted_ext for f in files):
        reasons.append("Arquivos desnecessários (" + ", ".join(sorted(
            {os.path.splitext(f)[1].upper()[1:] for f in files if os.path.splitext(f)[1].lower() in unwanted_ext})) + ")")
    return reasons


# --------------------------------------------------------------------------- arquivo em uso (Windows)

EM_USO = {5, 32, 33}      # acesso negado, violação de compartilhamento, trecho do arquivo bloqueado


class ArquivoEmUso(RuntimeError):
    """O Windows recusou mexer num arquivo porque outro programa (ou outro computador) o mantém aberto."""


def _em_uso(e: OSError) -> bool:
    return getattr(e, "winerror", None) in EM_USO


def quem_usa(caminho: str) -> list[str]:
    """Nomes dos programas DESTE computador que mantêm o arquivo aberto (Gerenciador de Reinício do Windows).
    Só diagnóstico: qualquer falha devolve lista vazia. Não enxerga arquivos abertos por outros computadores."""
    if sys.platform != "win32":
        return []
    try:
        import ctypes
        from ctypes import wintypes

        class FILETIME(ctypes.Structure):
            _fields_ = [("dwLowDateTime", wintypes.DWORD), ("dwHighDateTime", wintypes.DWORD)]

        class RM_UNIQUE_PROCESS(ctypes.Structure):
            _fields_ = [("dwProcessId", wintypes.DWORD), ("ProcessStartTime", FILETIME)]

        class RM_PROCESS_INFO(ctypes.Structure):
            _fields_ = [("Process", RM_UNIQUE_PROCESS), ("strAppName", ctypes.c_wchar * 256),
                        ("strServiceShortName", ctypes.c_wchar * 64), ("ApplicationType", ctypes.c_int),
                        ("AppStatus", ctypes.c_ulong), ("TSSessionId", wintypes.DWORD),
                        ("bRestartable", wintypes.BOOL)]

        rm = ctypes.WinDLL("rstrtmgr")
        sessao = wintypes.DWORD(0)
        chave = ctypes.create_unicode_buffer(33)
        if rm.RmStartSession(ctypes.byref(sessao), 0, chave) != 0:
            return []
        try:
            arquivos = (ctypes.c_wchar_p * 1)(caminho)
            if rm.RmRegisterResources(sessao.value, 1, arquivos, 0, None, 0, None) != 0:
                return []
            precisa, tem, motivos = wintypes.UINT(0), wintypes.UINT(0), wintypes.DWORD(0)
            r = rm.RmGetList(sessao.value, ctypes.byref(precisa), ctypes.byref(tem), None, ctypes.byref(motivos))
            if r != 234 or precisa.value == 0:          # 234 = ERROR_MORE_DATA (há processos a listar)
                return []
            infos = (RM_PROCESS_INFO * precisa.value)()
            tem = wintypes.UINT(precisa.value)
            if rm.RmGetList(sessao.value, ctypes.byref(precisa), ctypes.byref(tem), infos, ctypes.byref(motivos)) != 0:
                return []
            nomes = []
            for i in range(tem.value):
                n = infos[i].strAppName.strip()
                if n and n not in nomes:
                    nomes.append(n)
            return nomes
        finally:
            rm.RmEndSession(sessao.value)
    except Exception:  # noqa: BLE001 — é só um palpite para a mensagem
        return []


def rename_retry(src: str, dst: str, base: str | None = None, tentativas: int = 10, espera: float = 0.5) -> None:
    """os.rename que insiste por alguns segundos quando o arquivo está momentaneamente em uso (antivírus,
    miniatura do Explorer…). Se continuar em uso, levanta ArquivoEmUso com uma mensagem que diz o que fazer."""
    for t in range(tentativas):
        try:
            os.rename(src, dst)
            return
        except OSError as e:
            if not _em_uso(e):
                raise
            if t < tentativas - 1:
                time.sleep(espera)
                continue
            nome = os.path.relpath(src, base) if base else os.path.basename(src)
            quem = quem_usa(src)
            onde = f" ({', '.join(quem)})" if quem else ""
            raise ArquivoEmUso(
                f"O arquivo '{nome}' está aberto em outro programa{onde} ou em outro computador da rede. "
                "Feche o que estiver usando este modelo (3ds Max, Explorer com a pasta aberta, Photoshop…) "
                "e tente de novo.") from e


# --------------------------------------------------------------------------- aplicar o plano dentro da própria pasta

def apply_in_place(folder: str, plan: Plan, junk: list[str], record: list | None = None) -> list[str]:
    """Move os arquivos para o padrão dentro da própria pasta, em duas fases (com volta em caso de erro)."""
    warnings: list[str] = []
    todo = [(s, r) for s, r in plan.moves if not _rel_is_same(s, folder, r)]
    staging = os.path.join(folder, STAGING)
    done: list[tuple[str, str]] = []   # (origem, onde está agora)
    try:
        if todo:
            os.makedirs(staging, exist_ok=False)
            # fase 1: tira do caminho (para nunca sobrescrever nada)
            for i, (src, rel) in enumerate(todo):
                tmp = os.path.join(staging, f"{i:05d}_{os.path.basename(src)}")
                rename_retry(src, tmp, folder)
                done.append((src, tmp))
            # fase 2: coloca no lugar certo
            for i, (src, rel) in enumerate(todo):
                tmp = done[i][1]
                dst = os.path.join(folder, rel)
                if os.path.exists(dst):
                    raise RuntimeError(f"Já existe '{rel}' na pasta (nada foi sobrescrito).")
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                rename_retry(tmp, dst, folder)
                done[i] = (src, dst)
    except Exception:
        for src, cur in reversed(done):  # desfaz
            try:
                os.makedirs(os.path.dirname(src), exist_ok=True)
                rename_retry(cur, src, folder, tentativas=6, espera=0.4)
            except (OSError, ArquivoEmUso):
                pass
        try:
            os.rmdir(staging)  # só se ficou vazia
        except OSError:
            pass
        raise

    if record is not None:
        record.extend(done)     # (de onde veio, onde ficou) — usado para desfazer
    for d in plan.duplicates:   # cópias idênticas (conferidas byte a byte)
        try:
            os.remove(d)
        except OSError:
            warnings.append(f"Não consegui apagar a cópia repetida '{os.path.relpath(d, folder)}'")
    for j in junk:
        try:
            shutil.rmtree(j) if os.path.isdir(j) else os.remove(j)
        except OSError:
            pass
    # remove pastas que ficaram vazias (de baixo para cima)
    for dirpath, dirnames, filenames in os.walk(folder, topdown=False):
        if dirpath == folder:
            continue
        try:
            os.rmdir(dirpath)
        except OSError:
            pass
    return warnings


def copy_preview(folder: str, max_rel: list[str], preview: str | None) -> list[str]:
    """Copia a prévia externa para dentro da pasta com o nome de cada .max (se ainda não houver)."""
    warnings = []
    if not preview or not os.path.isfile(preview):
        return warnings
    pext = os.path.splitext(preview)[1].lower()
    for r in max_rel:
        stem = os.path.splitext(os.path.join(folder, r))[0]
        if any(os.path.exists(stem + e) for e in (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG", ".bmp", ".webp")):
            continue
        try:
            shutil.copy2(preview, stem + pext)
        except OSError as e:
            warnings.append(f"Não consegui copiar a prévia para '{os.path.basename(stem + pext)}' ({e})")
    return warnings


def cleanup_suggestions(folder: str, max_rel: list[str], unwanted_ext: set[str]) -> tuple[list[str], list[str]]:
    """(versões V-Ray a sugerir apagar, arquivos desnecessários)."""
    maxes = [os.path.join(folder, r) for r in max_rel if os.path.exists(os.path.join(folder, r))]
    vray: list[str] = []
    if any(renderer_of(m) == "corona" for m in maxes):
        vray = [m for m in maxes if renderer_of(m) == "vray"]
    files, _ = walk_files(folder)
    unwanted = sorted(f for f in files if os.path.splitext(f)[1].lower() in unwanted_ext) if unwanted_ext else []
    return vray, unwanted
