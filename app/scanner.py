"""Leitura da biblioteca (somente leitura — nunca altera nada nas pastas).

Regras, baseadas na organização real de F:\\MODELOS:
  * Cada pasta na raiz é uma CATEGORIA (pastas que começam com "_" são ignoradas).
  * Dentro da categoria, arquivos/pastas com o MESMO NOME formam um item:
        ADORNO 01.jpg + ADORNO 01.rar      -> item compactado
        ADORNO 08.jpg + ADORNO 08\\ (pasta) -> item em pasta (.max + MAPS)
        ADORNO 141.jpg + ADORNO 141         -> arquivo sem extensão (detecta RAR/ZIP)
  * A imagem com o mesmo nome é a prévia. A pasta MAPS nunca aparece.
  * Uma pasta sem .max dentro, mas com conteúdo, vira SUBCATEGORIA.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
ARCHIVE_EXT = {".rar", ".zip", ".7z"}
MAX_EXT = ".max"
STRIP_EXT = IMAGE_EXT | ARCHIVE_EXT | {MAX_EXT}
IGNORED_FILES = {"thumbs.db", "desktop.ini", ".ds_store"}
PARTIAL_EXT = {".crdownload", ".part", ".partial", ".download", ".tmp", ".opdownload"}  # download em andamento
MAPS_NAMES = {"maps", "map", "textures", "texture", "texturas", "textura", "tex", "__macosx"}
SKIP_ROOT = {"$recycle.bin", "system volume information"}
UNWANTED_EXT: set[str] = {".fbx", ".obj", ".mtl"}   # atualizado pelas configurações
CHECK_LAYOUT = True


# --------------------------------------------------------------------------- utilidades

def natural_key(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.casefold())]


def normalize(s: str) -> str:
    """Minúsculas e sem acento (para busca: 'vegetacao' encontra 'VEGETAÇAO')."""
    s = unicodedata.normalize("NFKD", s)
    return "".join(c for c in s if not unicodedata.combining(c)).casefold()


def strip_key(filename: str) -> str:
    base = filename
    stem, ext = os.path.splitext(base)
    while ext and ext.lower() in STRIP_EXT:
        base = stem
        stem, ext = os.path.splitext(base)
    return base.strip()


def detect_archive_type(path: str) -> str | None:
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


def find_max_files(folder: str, max_depth: int = 4) -> list[str]:
    """Procura .max dentro de uma pasta (ignora MAPS). Retorna do mais raso ao mais fundo."""
    found: list[str] = []

    def walk(d: str, depth: int):
        try:
            entries = sorted(os.scandir(d), key=lambda e: natural_key(e.name))
        except OSError:
            return
        subdirs = []
        for e in entries:
            try:
                if e.is_file() and e.name.lower().endswith(MAX_EXT):
                    found.append(e.path)
                elif e.is_dir() and e.name.casefold() not in MAPS_NAMES:
                    subdirs.append(e.path)
            except OSError:
                continue
        if depth < max_depth:
            for s in subdirs:
                walk(s, depth + 1)

    walk(folder, 0)
    return found


def pick_primary(max_files: list[str]) -> str | None:
    """Escolhe o .max principal: prefere nomes com 'corona', depois o mais raso."""
    if not max_files:
        return None
    for f in max_files:
        if "corona" in os.path.basename(f).casefold():
            return f
    return max_files[0]


def first_image_in(folder: str) -> str | None:
    try:
        for e in sorted(os.scandir(folder), key=lambda e: natural_key(e.name)):
            if e.is_file() and os.path.splitext(e.name)[1].lower() in IMAGE_EXT:
                return e.path
    except OSError:
        pass
    return None


# --------------------------------------------------------------------------- modelo de dados

@dataclass
class Asset:
    key: str                    # identificador estável: "ADORNOS/ADORNO 08"
    name: str                   # "ADORNO 08"
    category: str               # "ADORNOS" ou "ADORNOS/Studios"
    preview: str | None = None
    folder: str | None = None   # pasta já extraída na biblioteca
    archive: str | None = None  # .rar/.zip/.7z ou arquivo sem extensão
    archive_type: str | None = None
    loose_max: str | None = None
    max_files: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    layout_issues: list[str] = field(default_factory=list)   # pasta fora do padrão (botão Organizar)
    members: list[str] = field(default_factory=list)         # todos os arquivos/pastas do grupo (usado na Entrada)
    search_text: str = ""
    added_time: float = 0.0     # data da prévia/pasta (lida junto com a listagem; usada no Início)

    @property
    def kind(self) -> str:
        if self.folder and self.max_files:
            return "folder"
        if self.archive:
            return "archive"
        if self.loose_max:
            return "max"
        return "missing"


@dataclass
class Category:
    key: str        # "ADORNOS" ou "ADORNOS/Studios"
    name: str
    path: str
    assets: list[Asset] = field(default_factory=list)
    children: list["Category"] = field(default_factory=list)

    def all_assets(self) -> list[Asset]:
        out = list(self.assets)
        for c in self.children:
            out.extend(c.all_assets())
        return out


# --------------------------------------------------------------------------- leitura

def list_categories(root: str) -> list[tuple[str, str]]:
    out = []
    try:
        for e in os.scandir(root):
            if e.is_dir() and not e.name.startswith(("_", ".", "$")) and e.name.casefold() not in SKIP_ROOT:
                out.append((e.name, e.path))
    except OSError:
        pass
    out.sort(key=lambda t: natural_key(t[0]))
    return out


def looks_like_category(folder: str) -> bool:
    """Pasta que agrupa itens (ex.: LUMINARIAS\\LUMINARIA PENDENTE) e não um modelo.

    É subcategoria quando NÃO tem .max na raiz e tem pelo menos um par 'prévia + arquivo/pasta'
    com o mesmo nome (ex.: LUMINARIA 05.jpg + LUMINARIA 05.rar).
    """
    img_stems, other_stems = set(), set()
    try:
        for e in os.scandir(folder):
            n = e.name
            if e.is_dir():
                if n.casefold() not in MAPS_NAMES:
                    other_stems.add(n.strip().casefold())
                continue
            ext = os.path.splitext(n)[1].lower()
            if ext == MAX_EXT:
                return False
            k = strip_key(n).casefold()
            if ext in IMAGE_EXT:
                img_stems.add(k)
            elif ext in ARCHIVE_EXT or ext == "" or not ext[1:].isalpha():
                other_stems.add(k)
    except OSError:
        return False
    return bool(img_stems & other_stems)


def scan_category(path: str, key: str, name: str, depth: int = 0, check_layout: bool = True) -> Category:
    cat = Category(key=key, name=name, path=path)
    groups: dict[str, dict] = {}

    try:
        entries = list(os.scandir(path))
    except OSError:
        return cat

    mtimes: dict[str, float] = {}
    for e in entries:
        lname = e.name.casefold()
        if lname in IGNORED_FILES or os.path.splitext(lname)[1] in PARTIAL_EXT:
            continue
        try:
            is_dir = e.is_dir()
        except OSError:
            continue
        if is_dir:
            if lname in MAPS_NAMES:
                continue
            k = e.name.strip()
        else:
            k = strip_key(e.name)
        g = groups.setdefault(k.casefold(), {"name": k, "images": [], "dirs": [], "archives": [], "max": [], "other": []})
        try:
            mtimes[e.path] = e.stat().st_mtime      # no Windows vem junto com a listagem (sem custo extra)
        except OSError:
            pass
        if is_dir:
            g["dirs"].append(e.path)
            continue
        ext = os.path.splitext(e.name)[1].lower()
        if ext in IMAGE_EXT:
            g["images"].append(e.path)
        elif ext in ARCHIVE_EXT:
            g["archives"].append((e.path, ext[1:]))
        elif ext == MAX_EXT:
            g["max"].append(e.path)
        elif ext == "" or not ext[1:].isalpha() or len(ext) > 5:
            t = detect_archive_type(e.path)
            if t:
                g["archives"].append((e.path, t))
            else:
                g["other"].append(e.path)
        else:
            g["other"].append(e.path)

    for g in groups.values():
        nm = g["name"]
        folder_max: list[str] = []
        folder = None
        alone = not g["images"] and not g["archives"] and not g["max"]
        sub_dirs = [d for d in g["dirs"] if alone and depth < 3 and looks_like_category(d)]
        for d in g["dirs"]:
            if d in sub_dirs:
                continue
            mf = find_max_files(d)
            if mf:
                folder, folder_max = d, mf
                break
        if sub_dirs and not folder:
            for d in sub_dirs:
                sub = scan_category(d, f"{key}/{nm}", nm, depth + 1, check_layout)
                if sub.assets or sub.children:
                    cat.children.append(sub)
            continue

        # Pasta sem .max e sem arquivo irmão -> subcategoria (ou pasta vazia, ignorada)
        if g["dirs"] and not folder and not g["images"] and not g["archives"] and not g["max"]:
            for d in g["dirs"]:
                if depth < 3:
                    sub = scan_category(d, f"{key}/{nm}", nm, depth + 1, check_layout)
                    if sub.assets or sub.children:
                        cat.children.append(sub)
            continue

        if not (g["images"] or g["dirs"] or g["archives"] or g["max"]):
            continue

        a = Asset(key=f"{key}/{nm}", name=nm, category=key)
        a.members = g["images"] + g["dirs"] + [p for p, _ in g["archives"]] + g["max"] + g["other"]
        a.added_time = max((mtimes.get(m, 0.0) for m in a.members), default=0.0)
        a.preview = sorted(g["images"], key=lambda p: (os.path.splitext(p)[1].lower() not in (".jpg", ".jpeg", ".png"), p))[0] if g["images"] else None

        if folder:
            a.folder, a.max_files = folder, folder_max
            if not a.preview:
                prim = pick_primary(folder_max)
                stem_img = None
                if prim:
                    stem = os.path.splitext(prim)[0]
                    for ext in (".jpg", ".jpeg", ".png", ".JPG", ".PNG"):
                        if os.path.exists(stem + ext):
                            stem_img = stem + ext
                            break
                a.preview = stem_img or first_image_in(folder)
            if g["archives"]:
                a.issues.append("Existe pasta e arquivo compactado com o mesmo nome (usando a pasta)")
        elif g["archives"]:
            a.archive, a.archive_type = g["archives"][0]
            if len(g["archives"]) > 1:
                a.issues.append("Mais de um arquivo compactado com o mesmo nome")
        elif g["max"]:
            a.loose_max = g["max"][0]
            a.max_files = list(g["max"])
        elif g["dirs"]:
            a.folder = g["dirs"][0]
            a.issues.append("Pasta sem arquivo .max dentro")

        if a.kind == "folder" and CHECK_LAYOUT and check_layout:
            from .layout import check_layout  # import tardio (evita import circular)
            outer = a.preview if a.preview and os.path.dirname(a.preview) == path else None
            a.layout_issues = check_layout(a.folder, outer, UNWANTED_EXT)
        if a.kind == "missing" and not a.issues:
            a.issues.append("Só a imagem — arquivo do modelo não encontrado")
        if not a.preview:
            a.issues.append("Sem imagem de prévia")
        cat.assets.append(a)

    cat.assets.sort(key=lambda a: natural_key(a.name))
    cat.children.sort(key=lambda c: natural_key(c.name))
    return cat


def scan_library(root: str, progress=None) -> list[Category]:
    cats = []
    items = list_categories(root)
    for i, (name, path) in enumerate(items):
        c = scan_category(path, name, name)
        cats.append(c)
        if progress:
            progress(i + 1, len(items), c)
    return cats
