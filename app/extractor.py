"""Extração de modelos compactados PARA DENTRO da biblioteca, no padrão:

    CATEGORIA\\
        ADORNO 01.jpg            <- prévia (fica onde está)
        ADORNO 01\\               <- pasta com o nome do compactado
            modelo_corona.max    <- todos os .max juntos, na raiz
            modelo_corona.jpg    <- imagem com o mesmo nome de um .max fica ao lado dele
            MAPS\\                <- todo o resto (sem subpastas)

Segurança:
  * extrai numa pasta temporária no mesmo disco (F:\\MODELOS\\_TEMP_EXTRACAO);
  * só move para a categoria depois de conferir que veio pelo menos um .max;
  * nunca sobrescreve pasta existente;
  * o compactado original vai para F:\\MODELOS\\_BACKUP_COMPACTADOS (limpo depois do prazo configurado);
  * se der qualquer erro antes do fim, a biblioteca fica exatamente como estava.
"""
from __future__ import annotations

import filecmp
import os
import re
import shutil
import subprocess
import time
import zipfile
import zlib
from dataclasses import dataclass, field

from . import layout
from .scanner import Asset, IMAGE_EXT, MAPS_NAMES, find_max_files, pick_primary

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
TEMP_DIR = "_TEMP_EXTRACAO"
BACKUP_DIR = "_BACKUP_COMPACTADOS"
ARCHIVE_EXT = {".zip", ".rar", ".7z"}
JUNK_FILES = {"thumbs.db", "desktop.ini", ".ds_store"}
JUNK_DIRS = {"__macosx"}
DEFAULT_UNWANTED = [".fbx", ".obj", ".mtl"]


def safe_name(s: str) -> str:
    s = re.sub(r'[<>:"|?*\x00-\x1f]', "_", s).strip(" .")
    return s or "_"


# --------------------------------------------------------------------------- ferramentas

def find_tool(custom: str = "") -> dict[str, str]:
    """Localiza UnRAR.exe / WinRAR.exe / 7z.exe."""
    tools: dict[str, str] = {}
    pf = [os.environ.get("ProgramFiles", r"C:\Program Files"),
          os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
          os.environ.get("ProgramW6432", r"C:\Program Files")]
    if custom and os.path.isfile(custom):
        low = os.path.basename(custom).lower()
        tools["7z" if low.startswith("7z") else ("winrar" if low.startswith("winrar") else "unrar")] = custom
    for base in pf:
        for name, rel in (("unrar", r"WinRAR\UnRAR.exe"), ("winrar", r"WinRAR\WinRAR.exe"), ("7z", r"7-Zip\7z.exe")):
            p = os.path.join(base, rel)
            if name not in tools and os.path.isfile(p):
                tools[name] = p
    for name, exe in (("unrar", "unrar"), ("7z", "7z")):
        if name not in tools:
            w = shutil.which(exe)
            if w:
                tools[name] = w
    return tools


def _zip_member_name(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp850")  # zips criados no Windows em PT-BR
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


class PasswordError(Exception):
    """Arquivo protegido por senha (sem senha ou senha errada)."""


PWD_WORDS = ("password", "senha", "encrypted", "incorrect", "wrong pass")


def _zip_is_encrypted(archive: str) -> bool:
    try:
        with zipfile.ZipFile(archive) as zf:
            return any(i.flag_bits & 0x1 for i in zf.infolist())
    except (zipfile.BadZipFile, OSError):
        return False


def _extract_zip(archive: str, dest: str, password: str | None = None) -> None:
    with zipfile.ZipFile(archive) as zf:
        if password is not None:
            zf.setpassword(password.encode("utf-8"))
        for info in zf.infolist():
            name = _zip_member_name(info).replace("\\", "/")
            parts = [p for p in name.split("/") if p not in ("", ".", "..")]
            if not parts or ":" in parts[0]:
                continue
            target = os.path.join(dest, *[safe_name(p) for p in parts])
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            try:
                with zf.open(info) as src, open(target, "wb") as out:
                    shutil.copyfileobj(src, out, 1024 * 1024)
            except RuntimeError as e:  # "File is encrypted" / "Bad password"
                if "password" in str(e).lower() or "encrypted" in str(e).lower():
                    raise PasswordError(str(e)) from e
                raise
            except (zipfile.BadZipFile, zlib.error) as e:
                if info.flag_bits & 0x1:  # senha errada que passou na checagem rápida
                    raise PasswordError(str(e)) from e
                raise


def _run(cmd: list[str]) -> None:
    # stdin fechado: se o programa pedir senha, ele falha em vez de travar esperando
    r = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW)
    out = ((r.stdout or b"") + b"\n" + (r.stderr or b"")).decode("utf-8", "replace")
    low = out.lower()
    if r.returncode == 11 or (r.returncode not in (0, 1) and any(w in low for w in PWD_WORDS)):
        raise PasswordError(out.strip()[:300])
    if r.returncode not in (0, 1):  # 1 = avisos não fatais no UnRAR/7z
        raise RuntimeError(f"Falha ao descompactar (código {r.returncode}). {out.strip()[:300]}")
    if any(w in low for w in ("incorrect password", "wrong password", "senha incorreta")):
        raise PasswordError(out.strip()[:300])


def raw_extract(archive: str, kind: str | None, dest: str, tools: dict[str, str],
                password: str | None = None) -> None:
    os.makedirs(dest, exist_ok=True)
    rarpwd = f"-p{password}" if password is not None else "-p-"   # -p- = nunca perguntar senha
    zpwd = [f"-p{password}"] if password is not None else ["-p"]   # 7z sem senha: falha (stdin fechado)
    if kind == "zip":
        if _zip_is_encrypted(archive):
            if password is None:
                raise PasswordError("Arquivo protegido por senha.")
            if "winrar" in tools:  # WinRAR abre zip com qualquer criptografia (inclusive AES)
                _run([tools["winrar"], "x", "-ibck", "-inul", "-y", "-o+", rarpwd, archive, dest + os.sep])
            elif "7z" in tools:
                _run([tools["7z"], "x", "-y", *zpwd, f"-o{dest}", archive])
            else:
                try:
                    _extract_zip(archive, dest, password)
                except NotImplementedError as e:
                    raise RuntimeError("Zip com criptografia AES: instale o WinRAR ou 7-Zip.") from e
        else:
            _extract_zip(archive, dest)
    elif kind == "rar":
        if "unrar" in tools:
            _run([tools["unrar"], "x", "-y", "-o+", rarpwd, archive, dest + os.sep])
        elif "winrar" in tools:
            _run([tools["winrar"], "x", "-ibck", "-inul", "-y", "-o+", rarpwd, archive, dest + os.sep])
        elif "7z" in tools:
            _run([tools["7z"], "x", "-y", *zpwd, f"-o{dest}", archive])
        else:
            raise RuntimeError("WinRAR ou 7-Zip não encontrado para abrir arquivos RAR.")
    elif kind == "7z":
        if "7z" in tools:
            _run([tools["7z"], "x", "-y", *zpwd, f"-o{dest}", archive])
        elif "winrar" in tools:
            _run([tools["winrar"], "x", "-ibck", "-inul", "-y", "-o+", rarpwd, archive, dest + os.sep])
        else:
            raise RuntimeError("7-Zip ou WinRAR não encontrado para abrir arquivos 7z.")
    else:
        raise RuntimeError("Formato de arquivo compactado desconhecido.")


def raw_extract_with_passwords(archive: str, kind: str | None, dest: str, tools: dict[str, str],
                               passwords: list[str]) -> str | None:
    """Tenta sem senha e depois cada senha salva. Retorna a senha que funcionou (None = sem senha)."""
    for pwd in [None, *[p for p in passwords if p]]:
        shutil.rmtree(dest, ignore_errors=True)
        try:
            raw_extract(archive, kind, dest, tools, pwd)
            return pwd
        except PasswordError:
            continue
    shutil.rmtree(dest, ignore_errors=True)
    raise PasswordError("Arquivo protegido por senha.")


def _archive_kind(path: str) -> str | None:
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return None
    if head.startswith(b"Rar!"):
        return "rar"
    if head.startswith(b"PK"):
        return "zip"
    if head.startswith(b"7z\xbc\xaf\x27\x1c"):
        return "7z"
    return None


# --------------------------------------------------------------------------- renderizador pelo nome

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


# --------------------------------------------------------------------------- extração principal

@dataclass
class ExtractResult:
    key: str
    name: str
    category: str
    ok: bool = False
    message: str = ""
    dest: str | None = None
    max_files: list[str] = field(default_factory=list)
    vray_to_suggest: list[str] = field(default_factory=list)
    unwanted: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    backup: str | None = None
    needs_password: bool = False
    used_password: str | None = None
    moves: list = field(default_factory=list)       # (origem, destino) — para o histórico / desfazer
    created: list = field(default_factory=list)     # pastas criadas


def _unique(path: str) -> str:
    if not os.path.exists(path):
        return path
    stem, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{stem} ({i}){ext}"):
        i += 1
    return f"{stem} ({i}){ext}"


def _same_file(a: str, b: str) -> bool:
    try:
        return filecmp.cmp(a, b, shallow=False)
    except OSError:
        return False


def _common_dir(dirs: list[str]) -> str:
    try:
        return os.path.commonpath(dirs) if dirs else ""
    except ValueError:
        return os.path.dirname(dirs[0])


def _walk_files(root: str):
    for dirpath, dirnames, files in os.walk(root):
        dirnames[:] = [d for d in dirnames if d.casefold() not in JUNK_DIRS]
        for f in files:
            if f.casefold() in JUNK_FILES:
                continue
            yield os.path.join(dirpath, f)


def _uncompressed_estimate(archive: str, kind: str | None) -> int:
    size = os.path.getsize(archive)
    if kind == "zip":
        try:
            with zipfile.ZipFile(archive) as zf:
                return sum(i.file_size for i in zf.infolist())
        except (zipfile.BadZipFile, OSError):
            pass
    return size * 4


def extract_to_library(asset: Asset, library_root: str, tools: dict[str, str],
                       unwanted_ext: list[str], passwords: list[str] | None = None,
                       keep_backup: bool = True) -> ExtractResult:
    res = ExtractResult(key=asset.key, name=asset.name, category=asset.category)
    if asset.kind != "archive" or not asset.archive:
        res.message = "Este item não é um arquivo compactado."
        return res

    archive = asset.archive
    category_dir = os.path.dirname(archive)
    kind = _archive_kind(archive) or asset.archive_type

    # Arquivo baixado sem extensão (ex.: "ADORNO 141"): dá a extensão certa (.rar/.zip/.7z).
    # Sem isso ele teria o mesmo nome da pasta que vamos criar.
    if kind and os.path.splitext(archive)[1].lower() not in ARCHIVE_EXT:
        new_path = archive + "." + kind
        if os.path.exists(new_path):
            res.message = f"Existe '{os.path.basename(archive)}' sem extensão e também '{os.path.basename(new_path)}'. Nada foi alterado."
            return res
        try:
            os.rename(archive, new_path)
        except OSError as e:
            res.message = f"Não consegui adicionar a extensão .{kind} ao arquivo ({e}). Nada foi alterado."
            return res
        archive = asset.archive = new_path
        asset.archive_type = kind
        res.warnings.append(f"O arquivo estava sem extensão: renomeado para '{os.path.basename(new_path)}'.")

    final_dest = os.path.join(category_dir, safe_name(asset.name))
    if os.path.exists(final_dest):
        res.message = f"Já existe uma pasta '{os.path.basename(final_dest)}' na categoria. Nada foi alterado."
        return res
    try:
        need = _uncompressed_estimate(archive, kind) + 300 * 1024 ** 2
        free = shutil.disk_usage(category_dir).free
        if free < need:
            res.message = (f"Pouco espaço no disco: precisa de ~{need / 1024 ** 3:.1f} GB livres, "
                           f"há {free / 1024 ** 3:.1f} GB. Nada foi alterado.")
            return res
    except OSError:
        pass

    work = os.path.join(library_root, TEMP_DIR, f"{safe_name(asset.name)}_{int(time.time() * 1000)}")
    raw = os.path.join(work, "raw")
    final = os.path.join(work, "final")
    try:
        try:
            res.used_password = raw_extract_with_passwords(archive, kind, raw, tools, passwords or [])
        except PasswordError:
            res.needs_password = True
            raise RuntimeError("Arquivo protegido por senha.")

        # compactado dentro do compactado (um nível)
        if not find_max_files(raw, max_depth=8):
            for f in list(_walk_files(raw)):
                k = _archive_kind(f) if os.path.splitext(f)[1].lower() in ARCHIVE_EXT else None
                if k:
                    try:
                        raw_extract_with_passwords(f, k, os.path.splitext(f)[0] + "_conteudo", tools,
                                                   [p for p in [res.used_password, *(passwords or [])] if p])
                    except PasswordError:
                        raise RuntimeError("Compactado interno protegido por senha desconhecida.")
                    os.remove(f)

        files = list(_walk_files(raw))
        max_files = [f for f in files if f.lower().endswith(".max")]
        if not max_files:
            raise RuntimeError("Nenhum arquivo .max dentro do compactado. Nada foi alterado.")

        plan = layout.plan_layout(files)
        res.warnings.extend(plan.warnings)
        os.makedirs(final)
        for src, rel in plan.moves:
            dst = os.path.join(final, rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.move(src, dst)

        # coloca na biblioteca (mesmo disco = instantâneo)
        if os.path.exists(final_dest):
            raise RuntimeError("Uma pasta com esse nome apareceu durante a extração. Nada foi alterado.")
        try:
            os.rename(final, final_dest)
        except OSError:
            shutil.move(final, final_dest)
    except Exception as e:  # noqa: BLE001
        shutil.rmtree(work, ignore_errors=True)
        try:
            os.rmdir(os.path.dirname(work))
        except OSError:
            pass
        res.message = str(e)
        return res

    shutil.rmtree(work, ignore_errors=True)
    try:
        os.rmdir(os.path.dirname(work))  # remove _TEMP_EXTRACAO se ficou vazia
    except OSError:
        pass
    res.ok = True
    res.dest = final_dest
    res.created.append(final_dest)
    res.max_files = find_max_files(final_dest, max_depth=0)

    # copia a prévia (que fica ao lado do compactado) para dentro da pasta, com o nome de cada .max
    res.warnings.extend(layout.copy_preview(final_dest, [os.path.basename(m) for m in res.max_files], asset.preview))

    # compactado original -> backup
    if keep_backup:
        try:
            rel_cat = os.path.relpath(category_dir, library_root)
            bdir = os.path.join(library_root, BACKUP_DIR, rel_cat)
            os.makedirs(bdir, exist_ok=True)
            target = _unique(os.path.join(bdir, os.path.basename(archive)))
            os.replace(archive, target)
            os.utime(target, None)  # marca a hora em que entrou no backup
            res.backup = target
            res.moves.append((archive, target))
        except OSError as e:
            res.warnings.append(f"Não consegui mover o compactado original para o backup ({e}). Ele continua no lugar.")

    # sugestões de limpeza
    res.vray_to_suggest, res.unwanted = layout.cleanup_suggestions(
        final_dest, [os.path.basename(m) for m in res.max_files], _norm_exts(unwanted_ext))
    return res


def _norm_exts(exts) -> set[str]:
    return {e.lower() if e.startswith(".") else "." + e.lower() for e in exts or []}


def organize_folder(asset: Asset, library_root: str, unwanted_ext: list[str]) -> ExtractResult:
    """Coloca uma pasta já extraída (fora do programa) no padrão, dentro dela mesma."""
    res = ExtractResult(key=asset.key, name=asset.name, category=asset.category)
    folder = asset.folder
    if asset.kind != "folder" or not folder or not os.path.isdir(folder):
        res.message = "Este item não é uma pasta extraída."
        return res
    try:
        files, junk = layout.walk_files(folder, skip_dirs={layout.STAGING})
        if not any(f.lower().endswith(".max") for f in files):
            raise RuntimeError("Nenhum arquivo .max na pasta. Nada foi alterado.")
        plan = layout.plan_layout(files, folder)
        res.warnings.extend(plan.warnings)
        res.warnings.extend(layout.apply_in_place(folder, plan, junk, res.moves))
    except Exception as e:  # noqa: BLE001
        res.message = f"{e} Nada foi alterado."
        if "Nada foi alterado" in str(e):
            res.message = str(e)
        return res
    res.ok = True
    res.dest = folder
    max_rel = plan.max_rel
    res.max_files = [os.path.join(folder, r) for r in max_rel]
    res.warnings.extend(layout.copy_preview(folder, max_rel, asset.preview))
    res.vray_to_suggest, res.unwanted = layout.cleanup_suggestions(folder, max_rel, _norm_exts(unwanted_ext))
    return res


# --------------------------------------------------------------------------- manutenção

def clean_backup(library_root: str, max_age_minutes: int) -> int:
    """Apaga do backup os compactados mais velhos que o prazo. Retorna quantos apagou."""
    if max_age_minutes <= 0:
        return 0
    root = os.path.join(library_root, BACKUP_DIR)
    if not os.path.isdir(root):
        return 0
    limit = time.time() - max_age_minutes * 60
    n = 0
    # _DESCARTADOS tem o próprio relógio (data no nome de cada pasta, ver intake.clean_discarded): pela data dos
    # arquivos, um descarte recém-feito (arquivo antigo movido, que guarda a data original) sumiria na hora
    disc = os.path.normcase(os.path.join(root, "_DESCARTADOS"))
    for dirpath, _, files in os.walk(root, topdown=False):
        if os.path.normcase(dirpath) == disc or os.path.normcase(dirpath).startswith(disc + os.sep):
            continue
        for f in files:
            p = os.path.join(dirpath, f)
            try:
                if os.path.getmtime(p) < limit:
                    os.remove(p)
                    n += 1
            except OSError:
                pass
        if dirpath != root:
            try:
                os.rmdir(dirpath)  # só remove se ficou vazia
            except OSError:
                pass
    return n


def clean_temp(library_root: str) -> None:
    """Remove sobras de extrações interrompidas (só dentro de _TEMP_EXTRACAO)."""
    root = os.path.join(library_root, TEMP_DIR)
    if os.path.isdir(root):
        limit = time.time() - 12 * 3600     # na rede, outra pessoa pode estar extraindo agora: só sobras antigas
        for e in os.scandir(root):
            try:
                if e.is_dir() and e.stat().st_mtime < limit:
                    shutil.rmtree(e.path, ignore_errors=True)
            except OSError:
                pass
        try:
            os.rmdir(root)
        except OSError:
            pass


def backup_size(library_root: str) -> tuple[int, int]:
    root = os.path.join(library_root, BACKUP_DIR)
    n = total = 0
    for dirpath, _, files in os.walk(root):
        for f in files:
            n += 1
            try:
                total += os.path.getsize(os.path.join(dirpath, f))
            except OSError:
                pass
    return n, total


# --------------------------------------------------------------------------- para o arrastar

def item_root(asset: Asset) -> str | None:
    if asset.kind == "folder":
        return asset.folder
    if asset.kind == "max" and asset.loose_max:
        return os.path.dirname(asset.loose_max)
    return None


def map_dirs(asset: Asset) -> list[str]:
    """Pastas onde o 3ds Max deve procurar as texturas deste item."""
    root = item_root(asset)
    if not root:
        return []
    out = [root]
    if asset.kind == "max":
        try:
            out += [e.path for e in os.scandir(root) if e.is_dir() and e.name.casefold() in MAPS_NAMES]
        except OSError:
            pass
        return out
    for dirpath, dirnames, _ in os.walk(root):
        if dirpath[len(root):].count(os.sep) >= 5:
            dirnames[:] = []
        for d in dirnames:
            out.append(os.path.join(dirpath, d))
    return out


def primary_max(asset: Asset) -> str | None:
    return pick_primary(asset.max_files) if asset.kind in ("folder", "max") else None
