"""Aba Entrada: classificar downloads novos para dentro da biblioteca.

Fluxo:  F:\\MODELOS\\_ENTRADA\\Cadeira_X.rar + Cadeira_X.jpg
        -> escolho a categoria CADEIRAS
        -> vira CADEIRAS\\CADEIRA 87.rar + CADEIRA 87.jpg   (próximo número, nunca preenche buracos)

Duplicados: compara a prévia nova só com as prévias da categoria escolhida (dHash 64 bits).
Descartes (o novo ou o antigo) vão para _BACKUP_COMPACTADOS\\_DESCARTADOS\\<data>__<nome> e são
apagados depois do mesmo prazo do backup.
"""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import time
from collections import Counter
from dataclasses import dataclass, field

from .scanner import Asset, Category, IMAGE_EXT, ARCHIVE_EXT, detect_archive_type, natural_key, scan_category

ENTRY_DIR = "_ENTRADA"
DISCARD_DIR = os.path.join("_BACKUP_COMPACTADOS", "_DESCARTADOS")
NAME_RE = re.compile(r"^(.*?)[\s_\-]*(\d+)$")


# --------------------------------------------------------------------------- entrada

def entry_path(library_root: str) -> str:
    p = os.path.join(library_root, ENTRY_DIR)
    os.makedirs(p, exist_ok=True)
    return p


def scan_entry(library_root: str) -> list[Asset]:
    """Itens na pasta de entrada (inclui subpastas de pacotes)."""
    root = entry_path(library_root)
    cat = scan_category(root, ENTRY_DIR, "Entrada", check_layout=False)
    out = list(cat.assets)

    def walk(c: Category):
        for ch in c.children:
            out.extend(ch.assets)
            walk(ch)

    walk(cat)
    out.sort(key=lambda a: natural_key(a.name))
    return out


# --------------------------------------------------------------------------- numeração

def _mtime(a: Asset) -> float:
    if getattr(a, "added_time", 0.0):          # já lida junto com a listagem (sem ir ao servidor)
        return a.added_time
    for p in (a.members or []) + ([a.preview] if a.preview else []):
        try:
            return os.path.getmtime(p)
        except OSError:
            continue
    return 0.0


def _parse(items: list[Asset]):
    out = []
    for a in items:
        m = NAME_RE.match(a.name.strip())
        if m and m.group(1).strip():
            out.append((m.group(1).strip(), int(m.group(2)), len(m.group(2)), a))
    return out


def name_pattern(cat: Category, scope: list[Asset] | None = None) -> tuple[str | None, int, int]:
    """(prefixo, maior número, largura).

    Prefixo = o mais recente da pasta de destino, medido pelo 2º item mais novo de cada nome (prefixos com 2+ itens).
    Ex.: LUMINARIAS › LUMINARIA PENDENTE tem LUMINARIA 05…278 (antigos) e PENDENTE 01…19 (recentes) -> PENDENTE.
    O maior número é procurado em `scope` (a categoria inteira, com todas as subpastas), para nunca repetir
    um nome que já exista em outra subpasta.
    """
    parsed = _parse(cat.assets)
    if not parsed:
        return None, 0, 2
    counts: Counter = Counter(p.casefold() for p, *_ in parsed)
    spelled: dict[str, Counter] = {}
    newest: dict[str, float] = {}
    for p, n, w, a in parsed:
        k = p.casefold()
        spelled.setdefault(k, Counter())[p] += 1
        newest[k] = max(newest.get(k, 0.0), _mtime(a))
    cands = [k for k in counts if counts[k] >= 2] or list(counts)
    # vence o nome cujo SEGUNDO item mais recente é o mais novo: um único item antigo que foi
    # mexido recentemente (extraído, prévia trocada) não decide sozinho
    times: dict[str, list[float]] = {}
    for p, n, w, a in parsed:
        times.setdefault(p.casefold(), []).append(_mtime(a))
    def score(k):
        t = sorted(times[k], reverse=True)
        return (t[1] if len(t) > 1 else t[0], counts[k])
    key = max(cands, key=score)
    prefix = spelled[key].most_common(1)[0][0]
    pool = _parse(scope) if scope else parsed
    top = max((n for p, n, w, a in pool if p.casefold() == key), default=0)
    widths = Counter(w for p, n, w, a in parsed if p.casefold() == key)
    width = max(2, widths.most_common(1)[0][0]) if widths else 2
    return prefix, top, width


def guess_prefix(category_name: str) -> str:
    n = category_name.strip()
    if len(n) > 3 and n.upper().endswith("S") and " " not in n:
        return n[:-1]
    return n


def _name_taken(folder: str, name: str) -> bool:
    low = name.casefold()
    try:
        for e in os.scandir(folder):
            stem = e.name.casefold()
            if stem == low:
                return True
            if e.is_file():
                base = stem
                while True:
                    b, ext = os.path.splitext(base)
                    if not ext or (ext not in IMAGE_EXT and ext not in ARCHIVE_EXT and ext != ".max"):
                        break
                    base = b
                if base == low:
                    return True
    except OSError:
        pass
    return False


def next_names(cat: Category, count: int, prefix_override: str | None = None,
               scope: list[Asset] | None = None) -> list[str]:
    prefix, top, width = name_pattern(cat, scope)
    if prefix_override and (not prefix or prefix_override.casefold() != prefix.casefold()):
        prefix = prefix_override
        pool = [x for x in _parse(scope or cat.assets) if x[0].casefold() == prefix.casefold()]
        top = max((n for p, n, w, a in pool), default=0)
        ws = Counter(w for p, n, w, a in pool)
        width = max(2, ws.most_common(1)[0][0]) if ws else 2   # nome novo começa em 01
    prefix = prefix or guess_prefix(cat.name)
    used = {a.name.casefold() for a in (scope or cat.assets)}
    out, n = [], top
    while len(out) < count:
        n += 1
        nm = f"{prefix} {n:0{width}d}"
        if nm.casefold() in used or _name_taken(cat.path, nm) or nm.casefold() in {o.casefold() for o in out}:
            continue
        out.append(nm)
    return out


# --------------------------------------------------------------------------- mover / descartar

@dataclass
class MoveResult:
    ok: bool = False
    new_name: str = ""
    message: str = ""
    moved: list[str] = field(default_factory=list)
    pairs: list = field(default_factory=list)       # (origem, destino) — para o histórico / desfazer
    left_behind: list[str] = field(default_factory=list)


def _plan_targets(asset: Asset, dest_dir: str, new_name: str) -> tuple[list[tuple[str, str]], list[str]]:
    """(origem, destino) para cada arquivo do item. Imagens extras ficam na Entrada."""
    moves, left = [], []
    main_img = asset.preview if asset.preview in asset.members else None
    for m in asset.members:
        base = os.path.basename(m)
        if os.path.isdir(m):
            moves.append((m, os.path.join(dest_dir, new_name)))
            continue
        ext = os.path.splitext(base)[1].lower()
        if ext in IMAGE_EXT:
            if m == main_img:
                moves.append((m, os.path.join(dest_dir, new_name + ext)))
            else:
                left.append(m)
            continue
        if m == asset.archive and ext not in ARCHIVE_EXT:
            kind = detect_archive_type(m)
            ext = "." + kind if kind else ext
        moves.append((m, os.path.join(dest_dir, new_name + ext)))
    return moves, left


def move_into(asset: Asset, dest_dir: str, new_name: str) -> MoveResult:
    """Move os arquivos do item para a categoria com o novo nome. Desfaz tudo se algo falhar."""
    res = MoveResult(new_name=new_name)
    moves, res.left_behind = _plan_targets(asset, dest_dir, new_name)
    if not moves:
        res.message = "Nada para mover."
        return res
    for _, dst in moves:
        if os.path.exists(dst):
            res.message = f"Já existe '{os.path.basename(dst)}' na categoria. Nada foi alterado."
            return res
    done = []
    try:
        for src, dst in moves:
            try:
                os.rename(src, dst)          # mesmo disco: instantâneo
            except OSError:
                shutil.move(src, dst)        # outro disco
            done.append((src, dst))
    except Exception as e:  # noqa: BLE001
        for src, dst in reversed(done):
            try:
                shutil.move(dst, src)
            except OSError:
                pass
        res.message = f"Erro ao mover ({e}). Nada foi alterado."
        return res
    res.ok = True
    res.moved = [d for _, d in done]
    res.pairs = list(done)
    return res


def discard(asset: Asset, library_root: str, record: list | None = None) -> str:
    """Move todos os arquivos do item para _DESCARTADOS (apagado depois do prazo do backup)."""
    stamp = time.strftime("%Y%m%d-%H%M%S")
    dest = os.path.join(library_root, DISCARD_DIR, f"{stamp}__{asset.name}")
    i = 2
    while os.path.exists(dest):
        dest = os.path.join(library_root, DISCARD_DIR, f"{stamp}__{asset.name} ({i})")
        i += 1
    os.makedirs(dest)
    for m in asset.members:
        target = os.path.join(dest, os.path.basename(m))
        try:
            os.rename(m, target)
        except OSError:
            shutil.move(m, target)
        if record is not None:
            record.append((m, target))
    return dest


def restore(trash_dir: str, dest_dir: str) -> None:
    """Desfaz um descarte (volta os arquivos para a pasta de origem)."""
    for e in os.scandir(trash_dir):
        target = os.path.join(dest_dir, e.name)
        if not os.path.exists(target):
            shutil.move(e.path, target)
    try:
        os.rmdir(trash_dir)
    except OSError:
        pass


def clean_discarded(library_root: str, max_age_minutes: int) -> int:
    if max_age_minutes <= 0:
        return 0
    root = os.path.join(library_root, DISCARD_DIR)
    if not os.path.isdir(root):
        return 0
    limit = time.time() - max_age_minutes * 60
    n = 0
    for e in os.scandir(root):
        try:
            t = time.mktime(time.strptime(e.name.split("__")[0], "%Y%m%d-%H%M%S"))
        except (ValueError, OverflowError):
            continue
        if t < limit:
            shutil.rmtree(e.path, ignore_errors=True) if e.is_dir() else os.remove(e.path)
            n += 1
    return n


# --------------------------------------------------------------------------- semelhança de imagens
#
# Assinatura de cada prévia (calculada uma vez e guardada em cache):
#   * dHash 16x16 (256 bits) -> forma/estrutura da imagem;
#   * miniatura colorida 24x24 -> cor e detalhe.
# Só é "possível duplicado" quando as DUAS medidas batem. Assim, renders diferentes de produtos
# parecidos (objeto centralizado em fundo branco) não são confundidos.

SIG_VERSION = 2


def signature(path: str) -> tuple[int, bytes] | None:
    from PySide6.QtCore import QSize, Qt
    from PySide6.QtGui import QImage, QImageReader
    r = QImageReader(path)
    r.setAutoTransform(True)
    sz = r.size()
    if sz.isValid() and max(sz.width(), sz.height()) > 320:
        r.setScaledSize(sz.scaled(320, 320, Qt.KeepAspectRatio))  # leitura rápida de JPEG grande
    img = r.read()
    if img.isNull():
        return None
    g = img.convertToFormat(QImage.Format_Grayscale8).scaled(QSize(17, 16), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    h = 0
    for y in range(16):
        line = g.constScanLine(y).tobytes()
        for x in range(16):
            h = (h << 1) | (1 if line[x] > line[x + 1] else 0)
    c = img.convertToFormat(QImage.Format_RGB888).scaled(QSize(24, 24), Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    thumb = b"".join(c.constScanLine(y).tobytes()[:24 * 3] for y in range(24))
    return h, thumb


def compare(a: tuple[int, bytes], b: tuple[int, bytes]) -> float:
    """0..1 — 1 = imagens praticamente iguais."""
    shape = 1.0 - bin(a[0] ^ b[0]).count("1") / 256.0
    diff = sum(abs(x - y) for x, y in zip(a[1], b[1])) / (len(a[1]) * 255.0)
    color = 1.0 - min(1.0, diff * 4.0)   # 25% de diferença média já zera
    return min(shape, color)


class HashCache:
    """Cache em disco das assinaturas (arquivo próprio, pode ser aberto em qualquer thread)."""

    def __init__(self, path: str):
        self.path = path
        with sqlite3.connect(path) as c:
            c.execute("CREATE TABLE IF NOT EXISTS sig (path TEXT PRIMARY KEY, mtime REAL, size INTEGER, "
                      "ver INTEGER, h TEXT, thumb BLOB)")

    def get_many(self, paths: list[str], known: dict | None = None) -> dict[str, tuple[int, bytes]]:
        """Assinaturas destas imagens. `known` = {caminho: (data, tamanho)} já lidos na listagem da pasta (sem
        perguntar ao servidor de novo); o que não estiver lá é conferido com os.stat."""
        out: dict[str, tuple[int, bytes]] = {}
        known = known or {}
        with sqlite3.connect(self.path) as c:
            for p in paths:
                kn = known.get(p)
                if kn and kn[0] and kn[1]:
                    st = os.stat_result((0, 0, 0, 0, 0, 0, kn[1], 0, kn[0], 0))
                else:
                    try:
                        st = os.stat(p)
                    except OSError:
                        continue
                row = c.execute("SELECT mtime, size, ver, h, thumb FROM sig WHERE path = ?", (p,)).fetchone()
                if row and abs(row[0] - st.st_mtime) < 1 and row[1] == st.st_size and row[2] == SIG_VERSION:
                    out[p] = (int(row[3], 16), bytes(row[4]))
                    continue
                sg = signature(p)
                if sg is not None:
                    c.execute("INSERT OR REPLACE INTO sig VALUES (?, ?, ?, ?, ?, ?)",
                              (p, st.st_mtime, st.st_size, SIG_VERSION, f"{sg[0]:064x}", sg[1]))
                    out[p] = sg
        return out


def known_of(assets) -> dict:
    """{prévia: (data, tamanho)} dos itens que já trazem isso da listagem da pasta."""
    return {a.preview: (a.preview_mtime, a.preview_size) for a in assets
            if a.preview and getattr(a, "preview_mtime", 0.0) and getattr(a, "preview_size", 0)}


def find_similar(new_preview: str, candidates: list[Asset], cache: HashCache,
                 threshold: float = 0.88) -> list[tuple[Asset, float]]:
    paths = [a.preview for a in candidates if a.preview]
    sigs = cache.get_many([new_preview] + paths, known_of(candidates))
    sn = sigs.get(new_preview)
    if sn is None:
        return []
    out = []
    for a in candidates:
        sg = sigs.get(a.preview) if a.preview else None
        if sg is not None and a.preview != new_preview:
            s = compare(sn, sg)
            if s >= threshold:
                out.append((a, s))
    out.sort(key=lambda t: -t[1])
    return out[:6]
