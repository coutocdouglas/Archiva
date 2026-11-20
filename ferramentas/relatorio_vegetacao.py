"""Etapa 0 da aba Vegetação: relatório de leitura (somente leitura, sem interface).

Varre as coleções de vegetação (por padrão Maxtree e Globe Plants em F:\\COLECOES),
aplica o "padrão de leitura" de docs/plano-vegetacao.md e escreve um relatório em
Markdown com o que foi achado, o que foi ignorado e os órfãos.

NUNCA altera, move ou apaga nada nas pastas lidas. Não importa nada de app/ — é um
script isolado, só com a biblioteca padrão do Python.

Uso:
    py ferramentas/relatorio_vegetacao.py [--raiz F:\\COLECOES] [--colecao Maxtree ...]
                                          [--saida docs/relatorio-leitura-vegetacao.md]
                                          [--json caminho.json]
"""
from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sys
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from datetime import datetime

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
ARCHIVE_EXT = {".rar", ".zip", ".7z"}
IGNORED_FILES = {"thumbs.db", "desktop.ini", ".ds_store"}
DISCARD_DIR = "_descartados"
MAPS_HINT = ("maps",)            # pastas de textura: imagens aqui não são prévias
THUMB_HINT = ("thumb", "preview", "prv")


# ----------------------------------------------------------------------------- utilidades

def natural_key(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.casefold())]


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def species_norm(s: str) -> str:
    """'Acer buergerianum', 'Acer-buergerianum' e 'Acer_buergerianum' viram a mesma chave."""
    return slug(s)


def human_size(n: int) -> str:
    for u in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024 or u == "TB":
            return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
        n /= 1024
    return str(n)


def rel(path: str, base: str) -> str:
    return os.path.relpath(path, base).replace("\\", "/")


def is_under(path_parts: list[str], hints) -> bool:
    return any(any(h in p.casefold() for h in hints) for p in path_parts)


# ----------------------------------------------------------------------------- nomes

MT_PREFIX = re.compile(r"^MT_PM_(?:V(\d+)_)?(.+)$", re.I)
GP_SUFFIX = re.compile(r"[_ ]+(MESH|GFX|GROWFX)[_ ]+(CRN|CORONA|VRY|VRAY|VR)$", re.I)
GP_NUM = re.compile(r"^(.*?)(\d{2,4})$")


@dataclass
class NameInfo:
    species: str | None          # nome legível ("Alpinia purpurata")
    variation: str | None = None
    size: str | None = None
    detail: str | None = None    # H / L (Vol 3)
    pattern: str = "?"           # assinatura do padrão, para o relatório


def parse_maxtree(stem: str) -> NameInfo:
    m = MT_PREFIX.match(stem)
    if not m:
        return NameInfo(None, pattern="fora do padrão")
    tokens = m.group(2).split("_")
    detail = None
    if tokens and tokens[-1].upper() in {"H", "L"}:
        detail = tokens.pop().upper()
    nums = []
    while tokens and re.fullmatch(r"\d{1,3}", tokens[-1]) and len(nums) < 2:
        nums.insert(0, tokens.pop())
    if not tokens:
        if nums:   # Vol 5: MT_PM_V5_18_03 — espécie só numerada (nome só no PDF)
            return NameInfo(f"Modelo {nums[0]}", nums[0], nums[1] if len(nums) > 1 else None, detail,
                            "{modelo}_{tam} (sem nome de espécie)")
        return NameInfo(None, pattern="sem espécie")
    species = " ".join(tokens).replace("  ", " ").strip()
    variation = size = None
    if len(nums) == 2:
        variation, size = nums
        pat = "{esp}_{var}_{tam}"
    elif len(nums) == 1:
        variation = nums[0]
        pat = "{esp}_{nº}"
    else:
        pat = "{esp}"
    if detail:
        pat += "_{H|L}"
    if " " in m.group(2):
        pat += " (com espaço)"
    if not m.group(1):
        pat = "MT_PM_ (sem V{vol}) " + pat
    return NameInfo(species, variation, size, detail, pat)


def parse_globe(stem: str) -> NameInfo:
    s = stem
    kind = None
    m = GP_SUFFIX.search(s)
    if m:
        kind = f"{m.group(1).upper()}_{m.group(2).upper()}"
        s = s[: m.start()]
    m = GP_NUM.match(s)
    variation = None
    if m and m.group(1).strip():
        s, variation = m.group(1), m.group(2)
    species = s.strip(" _-")
    pat = "{esp}" + ("{nnn}" if variation else "") + (f"_{kind}" if kind else "")
    return NameInfo(species or None, variation, None, None, pat)


# ----------------------------------------------------------------------------- modelo

@dataclass
class MaxFile:
    path: str
    size: int
    tipo: str            # mesh | growfx | cena | greenwall
    render: str          # corona | vray | ?
    in_fp_library: bool  # está numa pasta com index.xml (biblioteca Forest Pack)
    species: str | None
    variation: str | None
    tam: str | None
    detail: str | None
    pattern: str
    preview: str | None = None
    preview_via: str | None = None   # index.xml | mesmo nome | thumbnails | espécie


@dataclass
class Archive:
    path: str
    size: int
    group: str
    part: int | None


@dataclass
class Volume:
    name: str
    path: str
    key: str
    cover: str | None = None
    cover_kind: str | None = None             # jpg | pdf | pdf (dentro) | None
    maxes: list[MaxFile] = field(default_factory=list)
    archives: list[Archive] = field(default_factory=list)
    indexes: list[dict] = field(default_factory=list)
    ext_count: dict = field(default_factory=dict)
    total_bytes: int = 0
    thumbs_db: int = 0
    ignored: list[str] = field(default_factory=list)
    orphan_images: list[str] = field(default_factory=list)
    proxies: list[str] = field(default_factory=list)
    empty_libraries: list[str] = field(default_factory=list)   # .ms sem nenhum .max
    nested_double: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    species_cover: dict = field(default_factory=dict)          # chave espécie -> (via, caminho)


# ----------------------------------------------------------------------------- leitura

def _loose_stem(stem: str) -> str:
    return re.sub(r"^mt_pm_v\d+_", "mt_pm_", stem.casefold().rstrip(". "))


def classify(parts: list[str], stem: str) -> tuple[str, str]:
    low = " ".join(parts + [stem]).casefold()
    if "growfx" in low or "_gfx" in low:
        tipo = "growfx"
    elif "greenwall" in low or "grennwall" in low:
        tipo = "greenwall"
    elif re.search(r"scene", low):
        tipo = "cena"
    else:
        tipo = "mesh"
    if re.search(r"vray|_vry\b|vry", low):
        render = "vray"
    elif re.search(r"corona|_crn\b|crn", low):
        render = "corona"
    else:
        render = "?"
    return tipo, render


def parse_index(path: str) -> dict:
    info = {"path": path, "items": [], "erro": None}
    try:
        tree = ET.parse(path)
        for it in tree.getroot().iter("item"):
            if (it.get("class") or "").lower() != "maxobject":
                continue
            g = lambda t: (it.findtext(t) or "").strip()
            info["items"].append({"name": g("name"), "bitmap": g("bitmap"), "maxfile": g("maxfile"),
                                  "object": g("object"), "matlib": g("matlib"), "material": g("material")})
    except (ET.ParseError, OSError) as e:
        info["erro"] = str(e)
    return info


def resolve_rel(base_dir: str, p: str) -> str:
    p = p.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    return os.path.normpath(os.path.join(base_dir, p))


ARCH_PART = re.compile(r"^(.*?)(?:\.part(\d+))?\.(rar|zip|7z)$", re.I)


def scan_volume(vol: Volume, collection: str, parse_name) -> None:
    images_by_stem: dict[str, list[str]] = collections.defaultdict(list)
    images_loose: dict[str, list[str]] = collections.defaultdict(list)
    images_all: list[str] = []
    ms_dirs: list[str] = []
    ext_count = collections.Counter()

    for dp, dns, fns in os.walk(vol.path):
        dns[:] = sorted([d for d in dns if d.casefold() != DISCARD_DIR], key=natural_key)
        if any(d.casefold() == DISCARD_DIR for d in os.listdir(dp) if os.path.isdir(os.path.join(dp, d))):
            vol.ignored.append(rel(os.path.join(dp, "_DESCARTADOS"), vol.path) + "/ (pasta de descarte)")
        parts = rel(dp, vol.path).split("/") if dp != vol.path else []
        # pasta aninhada em dobro (X/X)
        if parts and len(parts) >= 2 and parts[-1].casefold() == parts[-2].casefold():
            vol.nested_double.append("/".join(parts))
        has_max = False
        for fn in sorted(fns, key=natural_key):
            full = os.path.join(dp, fn)
            stem, ext = os.path.splitext(fn)
            ext = ext.lower()
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            vol.total_bytes += size
            ext_count[ext or "(sem)"] += 1
            if fn.casefold() in IGNORED_FILES:
                if fn.casefold() == "thumbs.db":
                    vol.thumbs_db += 1
                continue
            if ext == ".max":
                has_max = True
                tipo, render = classify(parts, stem)
                ni = parse_name(stem)
                if tipo in ("cena", "greenwall"):
                    ni = NameInfo(None, pattern=f"{tipo} (fora da contagem de espécies)")
                vol.maxes.append(MaxFile(full, size, tipo, render, False, ni.species, ni.variation,
                                         ni.size, ni.detail, ni.pattern))
            elif ext in IMAGE_EXT:
                images_all.append(full)
                images_by_stem[stem.casefold()].append(full)
                images_loose[_loose_stem(stem)].append(full)
            elif ext in ARCHIVE_EXT:
                m = ARCH_PART.match(fn)
                vol.archives.append(Archive(full, size, m.group(1) if m else stem,
                                            int(m.group(2)) if m and m.group(2) else None))
            elif ext in {".cproxy", ".cgeo", ".vrmesh"}:
                vol.proxies.append(full)
            elif ext == ".ms":
                ms_dirs.append(dp)
            elif fn.casefold() == "index.xml":
                vol.indexes.append(parse_index(full))
    vol.ext_count = dict(sorted(ext_count.items(), key=lambda kv: -kv[1]))

    # bibliotecas (.ms) cuja árvore não tem nenhum .max
    for d in ms_dirs:
        if not any(m.path.startswith(d + os.sep) or os.path.dirname(m.path) == d for m in vol.maxes):
            vol.empty_libraries.append(rel(d, vol.path))

    # --- 1) index.xml (fonte principal)
    by_path = {os.path.normcase(m.path): m for m in vol.maxes}
    for idx in vol.indexes:
        base = os.path.dirname(idx["path"])
        idx["faltando_max"], idx["faltando_bitmap"] = [], []
        listed = set()
        for it in idx["items"]:
            mp = resolve_rel(base, it["maxfile"]) if it["maxfile"] else None
            if not mp or os.path.normcase(mp) not in by_path:
                idx["faltando_max"].append(it["maxfile"] or it["name"])
                continue
            listed.add(os.path.normcase(mp))
            mf = by_path[os.path.normcase(mp)]
            mf.in_fp_library = True
            if it["bitmap"]:
                cands = [resolve_rel(base, it["bitmap"]),
                         os.path.join(base, "thumbnails", os.path.basename(it["bitmap"]))]
                hit = next((c for c in cands if os.path.isfile(c)), None)
                if hit:
                    mf.preview, mf.preview_via = hit, "index.xml"
                else:
                    idx["faltando_bitmap"].append(it["bitmap"])
        for mf in by_path.values():
            if mf.in_fp_library and mf.render == "?":
                mf.render = "FP (render pelo .mat)"
        # .max na mesma pasta do index mas não listados
        idx["nao_listados"] = [rel(m.path, vol.path) for m in vol.maxes
                               if os.path.dirname(m.path) == base and os.path.normcase(m.path) not in listed]
        idx["vazio"] = not idx["items"]
        idx["path"] = rel(idx["path"], vol.path)

    # --- 2/3) plano B: mesmo nome (mesma pasta, depois qualquer pasta de thumbnails/preview)
    for m in vol.maxes:
        if m.preview:
            continue
        stem = os.path.splitext(os.path.basename(m.path))[0].casefold()
        cands = images_by_stem.get(stem, [])
        cands = [c for c in cands if not is_under(rel(c, vol.path).split("/")[:-1], MAPS_HINT)]
        same = [c for c in cands if os.path.dirname(c) == os.path.dirname(m.path)]
        if same:
            m.preview, m.preview_via = same[0], "mesmo nome"
        elif cands:
            m.preview, m.preview_via = cands[0], "thumbnails"
        else:   # nome quase igual: sem 'V{vol}_' ou com ponto sobrando ("..jpg")
            loose = [c for c in images_loose.get(_loose_stem(stem), [])
                     if not is_under(rel(c, vol.path).split("/")[:-1], MAPS_HINT)]
            if loose:
                m.preview, m.preview_via = loose[0], "nome quase igual"
            else:   # cenas do Vol 001: scene01.max ↔ scene01_1.jpg
                numbered = [c for c in images_by_stem.get(stem + "_1", [])
                            if os.path.dirname(c) == os.path.dirname(m.path)]
                if numbered:
                    m.preview, m.preview_via = numbered[0], "nome_1"

    # --- espécie: capa e plano C (prévia pela espécie, ex. Globe Plants Mesh/GrowFX)
    preview_imgs = [p for p in images_all
                    if not is_under(rel(p, vol.path).split("/")[:-1], MAPS_HINT)]
    for m in vol.maxes:
        if not m.species:
            continue
        sk = species_norm(m.species)
        if sk in vol.species_cover:
            continue
        sp_pat = re.escape(sk)
        comp = [p for p in preview_imgs if "------" in os.path.basename(p)
                and re.search(rf"(^|-){sp_pat}-", slug(os.path.basename(p)))]
        comp01 = [p for p in comp if re.search(r"_01------0?3", os.path.basename(p))]
        prv_name = lambda p: slug(os.path.splitext(os.path.basename(p))[0])
        by_base = lambda ps: sorted(ps, key=lambda p: natural_key(os.path.basename(p)))
        prv = [p for p in preview_imgs if re.match(rf"^{sp_pat}-prv\d", prv_name(p))]
        # Globe: prévia com o nome encurtado ("Acer-platanoides" para "Acer platanoides Crimson King")
        prv_short = [p for p in preview_imgs
                     if (mm := re.match(r"^(.+)-prv\d+$", prv_name(p))) and sk.startswith(mm.group(1) + "-")]
        if comp01:
            vol.species_cover[sk] = ("composição _01------03", comp01[0])
        elif comp:
            vol.species_cover[sk] = ("composição (outra)", comp[0])
        elif prv:
            vol.species_cover[sk] = ("_PRV1 (Globe)", by_base(prv)[0])
        elif prv_short:
            vol.species_cover[sk] = ("_PRV1 nome encurtado (Globe)", by_base(prv_short)[0])
        else:
            t03 = [x for x in vol.maxes if x.species and species_norm(x.species) == sk and x.tam == "03" and x.preview]
            anyp = [x for x in vol.maxes if x.species and species_norm(x.species) == sk and x.preview]
            if t03:
                vol.species_cover[sk] = ("miniatura tamanho 03", t03[0].preview)
            elif anyp:
                vol.species_cover[sk] = ("miniatura de outro arquivo", anyp[0].preview)
            else:
                vol.species_cover[sk] = ("sem capa", None)
    for m in vol.maxes:
        if m.preview or not m.species:
            continue
        via, p = vol.species_cover.get(species_norm(m.species), (None, None))
        if p:
            m.preview, m.preview_via = p, "espécie"

    # --- órfãos: imagens em pastas de miniatura/objeto que não casam com nenhum .max
    max_stems = {os.path.splitext(os.path.basename(m.path))[0].casefold() for m in vol.maxes}
    loose_max = {_loose_stem(os.path.splitext(os.path.basename(m.path))[0]) for m in vol.maxes}
    used = {os.path.normcase(m.preview) for m in vol.maxes if m.preview}
    used |= {os.path.normcase(p) for _, p in vol.species_cover.values() if p}
    for p in preview_imgs:
        d = os.path.dirname(p)
        stem = os.path.splitext(os.path.basename(p))[0].casefold()
        in_thumb_dir = is_under(rel(d, vol.path).split("/"), ("thumb",))
        beside_max = any(os.path.dirname(m.path) == d for m in vol.maxes)
        if (in_thumb_dir or beside_max) and stem not in max_stems and os.path.normcase(p) not in used                 and _loose_stem(stem) not in loose_max:
            vol.orphan_images.append(rel(p, vol.path))


def volume_cover(coll_dir: str, vol: Volume) -> None:
    for ext in (".jpg", ".jpeg", ".png"):
        p = os.path.join(coll_dir, vol.name + ext)
        if os.path.isfile(p):
            vol.cover, vol.cover_kind = p, "jpg ao lado"
            return
    p = os.path.join(coll_dir, vol.name + ".pdf")
    if os.path.isfile(p):
        vol.cover, vol.cover_kind = p, "pdf ao lado"
        return
    for dp, _, fns in os.walk(vol.path):
        for fn in sorted(fns):
            if fn.lower().endswith(".pdf"):
                vol.cover, vol.cover_kind = os.path.join(dp, fn), "pdf dentro"
                return


def volume_key(collection: str, name: str) -> str:
    m = re.search(r"vol\.?\s*(\d+)", name, re.I) or re.search(r"bundle\s*(\d+)", name, re.I)
    return f"veg:{slug(collection)}/{int(m.group(1)):03d}" if m else f"veg:{slug(collection)}/{slug(name)}"


def check_archives(vol: Volume) -> None:
    groups = collections.defaultdict(list)
    for a in vol.archives:
        groups[(os.path.dirname(a.path), a.group)].append(a)
    for (_, g), arcs in groups.items():
        parts = sorted(a.part for a in arcs if a.part is not None)
        if not parts:
            continue
        expected = list(range(1, max(parts) + 1))
        missing = [p for p in expected if p not in parts]
        if missing:
            vol.notes.append(f"Compactado em partes '{g}': falta(m) a(s) parte(s) {missing} — não dá para extrair.")
        sizes = {a.part: a.size for a in arcs}
        if sizes and len(parts) > 1:
            first = sizes.get(1) or max(sizes.values())
            short = [p for p in parts[:-1] if sizes[p] != first]
            if short:
                vol.notes.append(f"Compactado '{g}': parte(s) {short} com tamanho diferente da parte 1 "
                                 f"(as do meio deveriam ser iguais) — possível download incompleto.")


def scan_collection(root: str, collection: str) -> dict:
    coll_dir = os.path.join(root, collection)
    parse_name = parse_maxtree if "maxtree" in collection.casefold() else parse_globe
    vols, ignored, loose = [], [], []
    for e in sorted(os.scandir(coll_dir), key=lambda e: natural_key(e.name)):
        if e.is_dir():
            if e.name.casefold() == DISCARD_DIR or e.name.startswith("_"):
                ignored.append(f"{e.name}/ (pasta de descarte/oculta)")
                continue
            v = Volume(e.name, e.path, volume_key(collection, e.name))
            scan_volume(v, collection, parse_name)
            if not v.maxes and not v.archives:
                if v.indexes and all(i["vazio"] for i in v.indexes):
                    ignored.append(f"{e.name}/ (índice de biblioteca vazio)")
                else:
                    ignored.append(f"{e.name}/ (sem .max nem compactado)")
                continue
            volume_cover(coll_dir, v)
            check_archives(v)
            m_vol = re.search(r"(\d+)$", v.key)
            if m_vol and "maxtree" in collection.casefold():
                wrong = collections.Counter(
                    int(mm.group(1)) for x in v.maxes
                    if (mm := re.match(r"^MT_PM_V(\d+)_", os.path.basename(x.path), re.I))
                    and int(mm.group(1)) != int(m_vol.group(1)))
                for n, k in wrong.items():
                    v.notes.append(f"{k} arquivos com 'V{n}' no nome, mas a pasta é do Vol {int(m_vol.group(1))} "
                                   "— a chave usa o número da pasta.")
            vols.append(v)
        else:
            stem = os.path.splitext(e.name)[0]
            if e.name.casefold() in IGNORED_FILES:
                ignored.append(e.name)
            elif not os.path.isdir(os.path.join(coll_dir, stem)):
                loose.append(e.name)
    return {"nome": collection, "dir": coll_dir, "volumes": vols, "ignorados": ignored, "soltos": loose}


# ----------------------------------------------------------------------------- relatório

def md_report(root: str, colls: list[dict]) -> str:
    L: list[str] = []
    w = L.append
    w("# Relatório de leitura — Vegetação (etapa 0)")
    w("")
    w(f"Gerado em {datetime.now():%Y-%m-%d %H:%M} por `ferramentas/relatorio_vegetacao.py`, lendo `{root}`. "
      "Somente leitura: nada foi alterado nas pastas.")
    w("")

    # ---- resumo
    w("## Resumo")
    w("")
    w("| Coleção | Volumes | .max | Espécies | Com prévia | Sem prévia | Tamanho |")
    w("|---|---:|---:|---:|---:|---:|---:|")
    for c in colls:
        mx = [m for v in c["volumes"] for m in v.maxes]
        sp = {(v.key, species_norm(m.species)) for v in c["volumes"] for m in v.maxes if m.species}
        tb = sum(v.total_bytes for v in c["volumes"])
        w(f"| {c['nome']} | {len(c['volumes'])} | {len(mx)} | {len(sp)} | "
          f"{sum(1 for m in mx if m.preview)} | {sum(1 for m in mx if not m.preview)} | {human_size(tb)} |")
    w("")

    for c in colls:
        vols: list[Volume] = c["volumes"]
        w(f"## {c['nome']}")
        w("")
        # tabela de volumes
        w("| Volume | Chave | .max | Espécies | Tipos (render) | index.xml | Prévia via | Capa do volume | Obs. |")
        w("|---|---|---:|---:|---|---|---|---|---|")
        for v in vols:
            tipos = collections.Counter(f"{m.tipo} {m.render}" for m in v.maxes)
            tipos_s = ", ".join(f"{k}: {n}" for k, n in tipos.most_common()) or "—"
            via = collections.Counter(m.preview_via or "nenhuma" for m in v.maxes)
            via_s = ", ".join(f"{k}: {n}" for k, n in via.most_common()) or "—"
            nidx = [i for i in v.indexes if not i["vazio"]]
            idx_s = (f"{len(nidx)} ({sum(len(i['items']) for i in nidx)} itens)" if nidx else "não tem")
            sp = {species_norm(m.species) for m in v.maxes if m.species}
            obs = []
            if not v.maxes and v.archives:
                obs.append("só compactado")
            elif v.archives:
                obs.append("compactado ao lado da pasta extraída")
            if v.empty_libraries:
                obs.append("biblioteca .ms sem .max")
            if v.notes:
                obs.append("⚠ ver detalhes")
            w(f"| {v.name} | `{v.key}` | {len(v.maxes)} | {len(sp)} | {tipos_s} | {idx_s} | {via_s} | "
              f"{v.cover_kind or '**falta**'} | {'; '.join(obs)} |")
        w("")

        # padrões de nome
        w(f"### Padrões de nome ({c['nome']})")
        w("")
        w("| Volume | Padrão | Arquivos | Exemplo |")
        w("|---|---|---:|---|")
        for v in vols:
            pats = collections.defaultdict(list)
            for m in v.maxes:
                pats[m.pattern].append(m)
            for p, ms in sorted(pats.items(), key=lambda kv: -len(kv[1])):
                w(f"| {v.name} | `{p}` | {len(ms)} | `{os.path.basename(ms[0].path)}` |")
        w("")

        # capas de espécie
        w(f"### Capa das espécies ({c['nome']})")
        w("")
        w("| Volume | " + " | ".join(["composição _01------03", "composição (outra)", "_PRV1 (Globe)", "_PRV1 nome encurtado (Globe)",
                                         "miniatura tamanho 03", "miniatura de outro arquivo", "sem capa"]) + " |")
        w("|---|" + "---:|" * 7)
        for v in vols:
            cnt = collections.Counter(via for via, _ in v.species_cover.values())
            if not v.species_cover:
                continue
            w(f"| {v.name} | " + " | ".join(str(cnt.get(k, 0) or "") for k in
                                              ["composição _01------03", "composição (outra)", "_PRV1 (Globe)", "_PRV1 nome encurtado (Globe)",
                                               "miniatura tamanho 03", "miniatura de outro arquivo", "sem capa"]) + " |")
        w("")

        # duplicados dentro do volume (mesmo nome de .max em mais de um lugar)
        dup_lines = []
        for v in vols:
            byname = collections.defaultdict(list)
            for m in v.maxes:
                byname[os.path.basename(m.path).casefold()].append(m)
            dups = {k: ms for k, ms in byname.items() if len(ms) > 1}
            if dups:
                same = sum(1 for ms in dups.values() if len({m.size for m in ms}) == 1)
                dirs = collections.Counter(" + ".join(sorted({rel(os.path.dirname(m.path), v.path) for m in ms}))
                                           for ms in dups.values())
                dup_lines.append(f"- **{v.name}**: {len(dups)} nomes repetidos ({same} com tamanho idêntico). "
                                 + "; ".join(f"`{d}` ({n})" for d, n in dirs.most_common(3)))
        w(f"### Mesmo .max em mais de uma pasta ({c['nome']})")
        w("")
        w("\n".join(dup_lines) if dup_lines else "Nenhum.")
        w("")

        # detalhes por volume
        w(f"### Detalhes e avisos ({c['nome']})")
        w("")
        for v in vols:
            items = []
            for n in v.notes:
                items.append(f"⚠ {n}")
            for a in v.archives:
                items.append(f"Compactado: `{rel(a.path, v.path)}` ({human_size(a.size)})"
                             + (" — **há conteúdo extraído ao lado: só avisar, nunca apagar sozinho**" if v.maxes else ""))
            for d in v.empty_libraries:
                items.append(f"Pasta `{d}` tem o script da biblioteca (.ms) mas nenhum .max.")
            for d in v.nested_double:
                items.append(f"Pasta aninhada em dobro: `{d}`")
            for i in v.indexes:
                if i["vazio"]:
                    items.append(f"index.xml vazio (ignorado): `{i['path']}`")
                    continue
                if i["erro"]:
                    items.append(f"index.xml ilegível: `{i['path']}` ({i['erro']})")
                if i["faltando_max"]:
                    items.append(f"`{i['path']}`: {len(i['faltando_max'])} itens apontam para .max que não existe "
                                 f"(ex.: `{i['faltando_max'][0]}`)")
                if i["faltando_bitmap"]:
                    items.append(f"`{i['path']}`: {len(i['faltando_bitmap'])} itens com prévia (bitmap) inexistente "
                                 f"(ex.: `{i['faltando_bitmap'][0]}`)")
                if i["nao_listados"]:
                    items.append(f"`{i['path']}`: {len(i['nao_listados'])} .max na pasta que o índice não lista "
                                 f"(ex.: `{i['nao_listados'][0]}`)")
            nop = [m for m in v.maxes if not m.preview]
            if nop:
                ex = ", ".join(f"`{rel(m.path, v.path)}`" for m in nop[:5])
                items.append(f"{len(nop)} .max sem prévia: {ex}" + (" …" if len(nop) > 5 else ""))
            nosp = [m for m in v.maxes if not m.species]
            if nosp:
                ex = ", ".join(f"`{os.path.basename(m.path)}`" for m in nosp[:5])
                items.append(f"{len(nosp)} .max sem espécie reconhecida pelo nome: {ex}" + (" …" if len(nosp) > 5 else ""))
            if v.orphan_images:
                ex = ", ".join(f"`{p}`" for p in v.orphan_images[:5])
                items.append(f"{len(v.orphan_images)} imagens órfãs (em pasta de miniaturas/objetos, sem .max): {ex}"
                             + (" …" if len(v.orphan_images) > 5 else ""))
            if v.proxies:
                pc = collections.Counter(os.path.splitext(p)[1].lower() for p in v.proxies)
                items.append("Proxies já existentes: " + ", ".join(f"{k} {n}" for k, n in pc.items())
                             + f" (ex.: `{rel(v.proxies[0], v.path)}`)")
            if v.thumbs_db:
                items.append(f"Thumbs.db ignorados: {v.thumbs_db} (não apagados)")
            for ig in v.ignored:
                items.append(f"Ignorado: `{ig}`")
            if items:
                w(f"**{v.name}** ({human_size(v.total_bytes)})")
                w("")
                for it in items:
                    w(f"- {it}")
                w("")

        if c["ignorados"] or c["soltos"]:
            w(f"### Ignorados na raiz da coleção ({c['nome']})")
            w("")
            for ig in c["ignorados"]:
                w(f"- `{ig}`")
            for s in c["soltos"]:
                w(f"- Arquivo solto sem pasta de mesmo nome: `{s}`")
            w("")

    # ---- simulação das decisões (nada é feito; só mostra o que a etapa 2 faria)
    w("## Simulação das regras da etapa 2 (nada foi movido)")
    w("")
    w("Aplica as decisões registradas em `docs/plano-vegetacao.md`. \"Descartar\" = mover para `_DESCARTADOS` "
      "dentro do volume, com conferência e desfazer.")
    w("")
    w("| Coleção / volume | Regra | O que | Tamanho |")
    w("|---|---|---|---:|")
    total = 0
    for c in colls:
        for v in c["volumes"]:
            for regra, alvo, size, _ in simulate(v):
                total += size
                w(f"| {c['nome']} / {v.name} | {regra} | `{alvo}` | {human_size(size) if size else '—'} |")
    w("")
    w(f"Total que sairia das coleções: **{human_size(total)}**.")
    w("")
    return "\n".join(L) + "\n"


def _tree_size(path: str) -> int:
    if os.path.isfile(path):
        return os.path.getsize(path)
    n = 0
    for dp, _, fns in os.walk(path):
        for fn in fns:
            try:
                n += os.path.getsize(os.path.join(dp, fn))
            except OSError:
                pass
    return n


def _top(v: Volume, path: str) -> str:
    """Primeira pasta abaixo do volume (a de fora, quando há pasta aninhada em dobro)."""
    return rel(path, v.path).split("/")[0]


def simulate(v: Volume) -> list[tuple[str, str, int, str | None]]:
    """(regra, alvo relativo, bytes, caminho absoluto que sairia — ou None se nada sai)."""
    out: list[tuple[str, str, int, str | None]] = []
    meshes = [m for m in v.maxes if m.tipo == "mesh"]
    # regra 1: mesmo .max em duas pastas → fica o da pasta Corona
    byname = collections.defaultdict(list)
    for m in meshes:
        byname[os.path.basename(m.path).casefold()].append(m)
    losers = collections.Counter()
    for ms in byname.values():
        if len(ms) < 2:
            continue
        corona = [m for m in ms if "corona" in rel(m.path, v.path).casefold()]
        keep = corona[0] if corona else ms[0]
        for m in ms:
            if m is not keep:
                losers[_top(v, m.path)] += 1
    for top, n in losers.items():
        allin = sum(1 for m in v.maxes if _top(v, m.path) == top)
        what = top if n == allin else f"{top} ({n} de {allin} .max)"
        out.append(("1: versão repetida (fica a Corona)", what + "/", _tree_size(os.path.join(v.path, top)),
                    os.path.join(v.path, top)))
    # regra 2: volume com malhas e com pasta de cena → descarta a pasta de cena
    if meshes:
        for top in sorted({_top(v, m.path) for m in v.maxes if m.tipo == "cena"}):
            out.append(("2: cena num volume que tem malhas", top + "/", _tree_size(os.path.join(v.path, top)),
                        os.path.join(v.path, top)))
    # regra do plano: V-Ray sai só se existir a mesma coisa em Corona
    for tipo in ("mesh", "growfx", "greenwall"):
        vr = [m for m in v.maxes if m.tipo == tipo and m.render == "vray"]
        co = [m for m in v.maxes if m.tipo == tipo and m.render == "corona"]
        if vr and co:
            for d in sorted({os.path.dirname(m.path) for m in vr}):
                if any(os.path.dirname(m.path) == d for m in co):   # V-Ray e Corona na mesma pasta: só os arquivos
                    for m in vr:
                        if os.path.dirname(m.path) == d:
                            out.append((f"plano: {tipo} V-Ray com versão Corona", rel(m.path, v.path), m.size, m.path))
                else:
                    out.append((f"plano: {tipo} V-Ray com versão Corona", rel(d, v.path) + "/", _tree_size(d), d))
    # regra 4: compactados
    has_maps = any("maps" in p.casefold() for p in os.listdir(v.path)) or any(
        "maps" in d.casefold() for dp, dns, _ in os.walk(v.path) for d in dns)
    # extração completa? cada espécie precisa ter ao menos uma textura no Maps.
    # Só serve para volumes cujas texturas levam o nome da espécie (Maxtree recentes, ex. Vol 130);
    # nos antigos (003–023) as texturas não têm o nome da espécie e o teste daria falso alarme.
    map_names = " ".join(slug(f) for dp, _, fns in os.walk(v.path)
                         if any("maps" in p.casefold() for p in rel(dp, v.path).split("/")) for f in fns)
    sem_textura = sorted({m.species for m in meshes if m.species and species_norm(m.species) not in map_names})
    for a in v.archives:
        r = rel(a.path, v.path)
        if v.maxes and has_maps and sem_textura and "maxtree" in v.key:
            out.append((f"4: extração **incompleta** (sem texturas: {', '.join(sem_textura)}) → "
                        "\"corrompido ou fora do padrão\", não descartar", r, 0, None))
        elif v.maxes and has_maps:
            out.append(("4: compactado já extraído (Maps e malhas presentes)", r, a.size, a.path))
        else:
            out.append(("4: não extraído → tentar extrair; se falhar, \"corrompido ou fora do padrão\"", r, 0, None))
    return out


# ----------------------------------------------------------------------------- padrão de pastas (simulação)

def volume_prefix(v: Volume) -> str:
    num = int(re.search(r"(\d+)$", v.key).group(1)) if re.search(r"(\d+)$", v.key) else 0
    return f"GP_B{num:03d}" if "globe" in v.key else f"MT_PM_V{num:03d}"


def layout(v: Volume) -> dict:
    """Para onde cada arquivo iria no padrão de pastas (docs/plano-vegetacao.md). Não move nada."""
    pre = volume_prefix(v)
    sim = simulate(v)
    res = {"prefixo": pre, "status": "organizar", "linhas": collections.Counter(), "bytes": collections.Counter(),
           "copias": 0, "colisoes": [], "descartados": sum(1 for *_, a in sim if a)}
    if any("incompleta" in r for r, *_ in sim) or any("falta" in n for n in v.notes):
        res["status"] = "não organizar: corrompido ou fora do padrão"
        return res
    if not v.maxes:
        res["status"] = "extrair antes de organizar"
        return res
    gone = [os.path.normcase(a) for *_, a in sim if a]
    is_gone = lambda p: any(os.path.normcase(p) == g or os.path.normcase(p).startswith(g + os.sep) for g in gone)

    kept = [m for m in v.maxes if not is_gone(m.path)]
    has_mesh = any(m.tipo in ("mesh", "greenwall") for m in kept)
    to_mesh = [m for m in kept if m.tipo in ("mesh", "greenwall") or (m.tipo == "cena" and not has_mesh)]
    mesh_paths = {os.path.normcase(m.path) for m in to_mesh}
    mesh_stems = {(os.path.normcase(os.path.dirname(m.path)), os.path.splitext(os.path.basename(m.path))[0].casefold())
                  for m in to_mesh}
    mesh_dirs = {os.path.normcase(os.path.dirname(m.path)) for m in to_mesh}
    # prévia fora da pasta do .max → cópia com o nome do .max
    for m in to_mesh:
        if m.preview and (os.path.dirname(m.preview) != os.path.dirname(m.path) or
                          os.path.splitext(os.path.basename(m.preview))[0].casefold()
                          != os.path.splitext(os.path.basename(m.path))[0].casefold()):
            res["copias"] += 1
    # biblioteca Forest Pack (index.xml, matlib, .ms) acompanha as malhas
    lib_dirs = {os.path.normcase(os.path.join(v.path, i["path"].replace("/", os.sep))).rsplit(os.sep, 1)[0]
                for i in v.indexes if not i["vazio"]}
    lib_dirs = {d for d in lib_dirs if any(md == d or md.startswith(d + os.sep) for md in mesh_dirs)}

    covers = {os.path.normcase(p) for _, p in v.species_cover.values() if p}
    dest_names = collections.defaultdict(list)
    for dp, dns, fns in os.walk(v.path):
        dns[:] = [d for d in dns if d.casefold() != DISCARD_DIR]
        ndp = os.path.normcase(dp)
        for fn in fns:
            full = os.path.join(dp, fn)
            if is_gone(full):
                continue
            ext = os.path.splitext(fn)[1].lower()
            stem = os.path.splitext(fn)[0].casefold()
            parts = [x.casefold() for x in rel(dp, v.path).split("/")] if dp != v.path else []
            if fn.casefold() in IGNORED_FILES:
                res["ignorados"] = res.get("ignorados", 0) + 1
                continue
            if ext == ".max":
                dest = "Mesh" if os.path.normcase(full) in mesh_paths else "Outros"
            elif ext in IMAGE_EXT and (ndp, stem) in mesh_stems:
                dest = "Mesh"
            elif ext in {".cproxy", ".cgeo", ".vrmesh"}:
                dest = "Mesh/Proxy"
            elif ext == ".pdf" or (ext in IMAGE_EXT and "------" in fn):
                dest = "PDF"
            elif os.path.normcase(full) in covers and not any("thumb" in x for x in parts):
                dest = "PDF"   # capa da espécie (ex.: Globe _PRV1)
            elif any(ndp == d or ndp.startswith(d + os.sep) for d in lib_dirs) and (
                    fn.casefold() == "index.xml" or ext == ".mat") and not any("thumb" in x for x in parts):
                dest = "Mesh"
            elif ext == ".ms" and any(d == ndp or d.startswith(ndp + os.sep) for d in lib_dirs):
                dest = "Mesh"
            elif any("maps" in x for x in parts) and ext in IMAGE_EXT | {".exr", ".hdr", ".tga", ".tx"}:
                dest = "Maps"
            else:
                dest = "Outros"
            src = rel(dp, v.path) if dp != v.path else "(raiz do volume)"
            res["linhas"][(src, dest)] += 1
            try:
                res["bytes"][(src, dest)] += os.path.getsize(full)
            except OSError:
                pass
            if dest in ("Mesh", "Maps", "Mesh/Proxy"):
                dest_names[(dest, fn.casefold())].append(src)
    res["colisoes"] = [(d, n, srcs) for (d, n), srcs in dest_names.items() if len(srcs) > 1]
    return res


def md_layout(colls: list[dict]) -> str:
    L: list[str] = []
    w = L.append
    w("## Simulação do padrão de pastas (nada foi movido)")
    w("")
    w("Para onde cada pasta iria ao organizar no padrão de `docs/plano-vegetacao.md`. Os descartes da seção "
      "anterior não aparecem aqui. **Outros** é o que o usuário revisa na tela de organizar (padrão: manter).")
    w("")
    resumo = collections.Counter()
    for c in colls:
        for v in c["volumes"]:
            r = layout(v)
            w(f"### {v.name} → `{r['prefixo']} - …`")
            w("")
            if r["status"] != "organizar":
                w(f"**{r['status']}**.")
                w("")
                continue
            w("| Origem | Destino | Arquivos | Tamanho |")
            w("|---|---|---:|---:|")
            for (src, dest), n in sorted(r["linhas"].items(), key=lambda kv: (kv[0][1], natural_key(kv[0][0]))):
                b = r["bytes"][(src, dest)]
                resumo[dest] += b
                shown = f"`{r['prefixo']} - {dest.replace('Mesh/Proxy', 'Mesh/' + r['prefixo'] + ' - Proxy')}`"
                w(f"| `{src}` | {shown} | {n} | {human_size(b)} |")
            w("")
            extra = []
            if r.get("ignorados"):
                extra.append(f"{r['ignorados']} Thumbs.db/desktop.ini ignorados")
            if r["copias"]:
                extra.append(f"{r['copias']} prévias copiadas para o lado do .max, com o nome dele")
            if r["colisoes"]:
                ex = r["colisoes"][0]
                extra.append(f"⚠ {len(r['colisoes'])} nomes repetidos no mesmo destino "
                             f"(ex.: `{ex[1]}` em {ex[0]}, vindo de {', '.join('`'+s+'`' for s in ex[2][:3])}) — "
                             "decidir antes de mover")
            for e in extra:
                w(f"- {e}")
            if extra:
                w("")
    w("### Total por destino")
    w("")
    w("| Destino | Tamanho |")
    w("|---|---:|")
    for d, b in sorted(resumo.items(), key=lambda kv: -kv[1]):
        w(f"| {d} | {human_size(b)} |")
    w("")
    return "\n".join(L) + "\n"


def to_json(colls: list[dict]) -> dict:
    out = []
    for c in colls:
        vs = []
        for v in c["volumes"]:
            d = asdict(v)
            d["species_cover"] = {k: {"via": via, "path": p} for k, (via, p) in v.species_cover.items()}
            vs.append(d)
        out.append({"nome": c["nome"], "dir": c["dir"], "ignorados": c["ignorados"], "soltos": c["soltos"], "volumes": vs})
    return {"gerado": datetime.now().isoformat(timespec="seconds"), "colecoes": out}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", default=r"F:\COLECOES")
    ap.add_argument("--colecao", action="append", help="pode repetir; padrão: Maxtree e Globe Plants")
    ap.add_argument("--saida", default=os.path.join(os.path.dirname(__file__), "..", "docs",
                                                    "relatorio-leitura-vegetacao.md"))
    ap.add_argument("--json", help="também grava os detalhes em JSON neste caminho")
    a = ap.parse_args(argv)
    names = a.colecao or ["Maxtree", "Globe Plants"]
    colls = []
    for n in names:
        if not os.path.isdir(os.path.join(a.raiz, n)):
            print(f"Coleção não encontrada: {os.path.join(a.raiz, n)}", file=sys.stderr)
            continue
        colls.append(scan_collection(a.raiz, n))
    text = md_report(a.raiz, colls) + "\n" + md_layout(colls)
    os.makedirs(os.path.dirname(os.path.abspath(a.saida)), exist_ok=True)
    with open(a.saida, "w", encoding="utf-8") as f:
        f.write(text)
    if a.json:
        with open(a.json, "w", encoding="utf-8") as f:
            json.dump(to_json(colls), f, ensure_ascii=False, indent=1)
    print(f"Relatório: {os.path.abspath(a.saida)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
