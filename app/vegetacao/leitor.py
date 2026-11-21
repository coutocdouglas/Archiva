"""Leitura das coleções de vegetação (somente leitura: nunca altera nada nas pastas).

Padrão de leitura (docs/plano-vegetacao.md):
  * Cada pasta dentro da coleção é um VOLUME (Maxtree "Vol 071", Globe Plants "Bundle 65").
  * Acha todos os .max do volume, recursivamente, e liga cada um à prévia: o index.xml (biblioteca Forest Pack) é a
    fonte principal; depois o mesmo nome (na pasta ou em pastas de miniaturas); depois nome quase igual; depois a
    prévia da espécie.
  * Funciona por conteúdo, não por posição: serve tanto para os volumes como vieram quanto para os já organizados
    no padrão de pastas (- Mesh, - Maps, - PDF, - Outros).
  * Decisões da etapa 0: versão repetida (Forest Pack × Corona) aparece uma vez só, a da pasta Corona; cena só
    aparece quando é a única malha do volume; GrowFX e V-Ray com versão Corona não aparecem (vão para "Outros").
  * Ignora Thumbs.db, índices vazios e as pastas _DESCARTADOS / "- Outros".
"""
from __future__ import annotations

import collections
import json
import os
import re
import time
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field

INDEX_VERSION = 1

IMAGE_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff"}
ARCHIVE_EXT = {".rar", ".zip", ".7z"}
PROXY_EXT = {".cproxy", ".cgeo", ".vrmesh"}
IGNORED_FILES = {"thumbs.db", "desktop.ini", ".ds_store"}
SKIP_DIRS = {"_descartados"}


# ----------------------------------------------------------------------------- utilidades

def natural_key(s: str):
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", s.casefold())]


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c)).casefold()
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def _parts(path: str, base: str) -> list[str]:
    r = os.path.relpath(path, base)
    return [] if r == "." else [p.casefold() for p in r.replace("\\", "/").split("/")]


def _skip_dir(name: str) -> bool:
    n = name.casefold()
    return n in SKIP_DIRS or n.endswith(" - outros") or n.startswith("_extraindo")


# ----------------------------------------------------------------------------- nomes

MT_PREFIX = re.compile(r"^MT_PM_(?:V(\d+)_)?(.+)$", re.I)
GP_SUFFIX = re.compile(r"[_ ]+(MESH|GFX|GROWFX)[_ ]+(CRN|CORONA|VRY|VRAY|VR)$", re.I)
GP_NUM = re.compile(r"^(.*?)(\d{2,4})$")


def parse_maxtree(stem: str) -> dict:
    """MT_PM_V71_Phoenix_canariensis_01_04 → espécie, variação, tamanho (aceita as variações dos volumes antigos)."""
    m = MT_PREFIX.match(stem)
    if not m:
        return {}
    tokens = m.group(2).split("_")
    detail = tokens.pop().upper() if tokens and tokens[-1].upper() in {"H", "L"} else None
    nums: list[str] = []
    while tokens and re.fullmatch(r"\d{1,3}", tokens[-1]) and len(nums) < 2:
        nums.insert(0, tokens.pop())
    if not tokens:
        if nums:   # Vol 5: MT_PM_V5_18_03 — o nome da espécie não existe nem no PDF
            return {"especie": f"Modelo {nums[0]}", "variacao": nums[0],
                    "tamanho": nums[1] if len(nums) > 1 else None, "detalhe": detail}
        return {}
    especie = re.sub(r"\s+", " ", " ".join(tokens)).strip()
    especie = especie[:1].upper() + especie[1:]
    if len(nums) == 2:
        return {"especie": especie, "variacao": nums[0], "tamanho": nums[1], "detalhe": detail}
    return {"especie": especie, "variacao": nums[0] if nums else None, "tamanho": None, "detalhe": detail}


def parse_globe(stem: str) -> dict:
    s = stem
    m = GP_SUFFIX.search(s)
    if m:
        s = s[: m.start()]
    m = GP_NUM.match(s)
    variacao = None
    if m and m.group(1).strip():
        s, variacao = m.group(1), m.group(2)
    especie = s.strip(" _-")
    return {"especie": especie, "variacao": variacao, "tamanho": None, "detalhe": None} if especie else {}


def _classify(parts: list[str], stem: str) -> tuple[str, str]:
    low = " ".join(parts + [stem.casefold()])
    if "growfx" in low or "_gfx" in low:
        tipo = "growfx"
    elif "greenwall" in low or "grennwall" in low:
        tipo = "conjunto"
    elif "scene" in low:
        tipo = "cena"
    else:
        tipo = "mesh"
    if re.search(r"vray|vry", low):
        render = "V-Ray"
    elif re.search(r"corona|crn", low):
        render = "Corona"
    else:
        render = ""
    return tipo, render


def _loose(stem: str) -> str:
    """Nome 'quase igual': sem 'V{vol}_', sem ponto sobrando e sem o sufixo do renderizador (Greenwall_Corona)."""
    s = re.sub(r"^mt_pm_v\d+_", "mt_pm_", stem.casefold().rstrip(". "))
    return re.sub(r"[_ -](corona|vray)$", "", s)


# ----------------------------------------------------------------------------- modelo

@dataclass
class Arquivo:
    path: str
    nome: str               # nome do arquivo sem .max
    size: int
    tipo: str               # mesh | cena | conjunto
    render: str             # Corona | V-Ray | "" (Forest Pack: escolhido pelo .mat)
    variacao: str | None = None
    tamanho: str | None = None
    detalhe: str | None = None
    preview: str | None = None
    proxy: str | None = None
    forest_pack: bool = False

    @property
    def rotulo(self) -> str:
        """Texto do cartão: 'Tamanho 04', 'Variação 02 · H', 'Acer buergerianum 003', 'scene01'…"""
        if self.tipo != "mesh":
            return self.nome
        m = GP_SUFFIX.search(self.nome)        # Globe: "Acer buergerianum_MESH_CRN" → "Mesh · Corona"
        if m and not self.variacao:
            return f"{m.group(1).capitalize()} · {self.render or m.group(2)}"
        if self.tamanho:
            r = f"Tamanho {self.tamanho}"
            if self.variacao and self.variacao != "01":
                r = f"Variação {self.variacao} · {r}"
            return r
        if self.variacao:
            r = f"Variação {self.variacao}"
            return f"{r} · {'alta' if self.detalhe == 'H' else 'baixa'}" if self.detalhe else r
        return self.nome


@dataclass
class Especie:
    key: str                # slug da espécie (parte final da chave estável)
    nome: str
    arquivos: list[Arquivo] = field(default_factory=list)
    capa: str | None = None
    grupo: bool = False     # True = "Cenas" / "Conjuntos" (não é espécie de verdade)


@dataclass
class Volume:
    key: str                # veg:maxtree/071
    nome: str               # pasta: "Maxtree - Plant Models Vol 071"
    rotulo: str             # "Vol 071" / "Bundle 65"
    path: str
    capa: str | None = None
    pdf: str | None = None
    status: str = "ok"      # ok | compactado | corrompido
    aviso: str = ""
    organizado: bool = False
    especies: list[Especie] = field(default_factory=list)

    @property
    def n_arquivos(self) -> int:
        return sum(len(e.arquivos) for e in self.especies)

    @property
    def n_especies(self) -> int:
        return sum(1 for e in self.especies if not e.grupo)


@dataclass
class Colecao:
    key: str                # veg:maxtree
    nome: str
    path: str
    volumes: list[Volume] = field(default_factory=list)
    lida_em: float = 0.0

    @property
    def capa(self) -> str | None:
        return next((v.capa for v in self.volumes if v.capa), None)

    @property
    def n_especies(self) -> int:
        return len({e.key for v in self.volumes for e in v.especies if not e.grupo})


# ----------------------------------------------------------------------------- leitura de um volume

def _parse_index(path: str) -> list[dict]:
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError):
        return []
    out = []
    for it in root.iter("item"):
        if (it.get("class") or "").lower() == "maxobject":
            out.append({"bitmap": (it.findtext("bitmap") or "").strip(),
                        "maxfile": (it.findtext("maxfile") or "").strip()})
    return out


def _resolve(base: str, p: str) -> str:
    p = p.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    return os.path.normpath(os.path.join(base, p))


_ARCH_PART = re.compile(r"^(.*?)(?:\.part(\d+))?\.(rar|zip|7z)$", re.I)


def _archive_problem(archives: list[tuple[str, int]]) -> str:
    groups = collections.defaultdict(dict)
    for path, size in archives:
        m = _ARCH_PART.match(os.path.basename(path))
        if m and m.group(2):
            groups[(os.path.dirname(path), m.group(1))][int(m.group(2))] = size
    for (_, name), parts in groups.items():
        missing = [n for n in range(1, max(parts) + 1) if n not in parts]
        if missing:
            return f"falta a parte {', '.join(map(str, missing))} do compactado"
    return ""


def volume_key(col_key: str, name: str) -> tuple[str, str]:
    m = re.search(r"vol\.?\s*(\d+)", name, re.I)
    if m:
        n = int(m.group(1))
        return f"{col_key}/{n:03d}", f"Vol {n:03d}"
    m = re.search(r"bundle\s*(\d+)", name, re.I)
    if m:
        n = int(m.group(1))
        return f"{col_key}/{n:03d}", f"Bundle {n}"
    return f"{col_key}/{slug(name)}", name


def read_volume(col_key: str, path: str, name: str, cover_dir: str) -> Volume | None:
    key, rotulo = volume_key(col_key, name)
    vol = Volume(key, name, rotulo, path)
    vol.organizado = os.path.isfile(os.path.join(path, "archiva.json"))
    parse = parse_maxtree if "maxtree" in col_key else parse_globe
    # volume organizado: o nome da pasta original ("…_Mesh_Corona") se perdeu; tipo e renderizador vêm do diário
    itens: dict = {}
    if vol.organizado:
        try:
            with open(os.path.join(path, "archiva.json"), encoding="utf-8") as f:
                itens = {k.casefold(): v for k, v in (json.load(f).get("itens") or {}).items()}
        except (OSError, ValueError, AttributeError):
            itens = {}

    maxes: list[dict] = []
    images: dict[str, list[str]] = collections.defaultdict(list)       # nome (minúsculo) → caminhos
    images_loose: dict[str, list[str]] = collections.defaultdict(list)
    previews: list[str] = []                                            # imagens fora de pastas de textura
    proxies: dict[str, str] = {}
    proxy_maxes: dict[str, str] = {}                                    # .max da pasta "- Proxy"
    indexes: list[str] = []
    archives: list[tuple[str, int]] = []
    pdfs: list[str] = []

    for dp, dns, fns in os.walk(path):
        dns[:] = sorted((d for d in dns if not _skip_dir(d)), key=natural_key)
        parts = _parts(dp, path)
        in_maps = any("maps" in p for p in parts)
        # pasta "- Proxy" (etapa 4): o .max pequeno de lá é o proxy do .max de mesmo nome, não uma malha nova
        in_proxy = bool(parts) and any(p == "proxy" or p == "proxies" or p.endswith(" - proxy") for p in parts)
        for fn in fns:
            low = fn.casefold()
            if low in IGNORED_FILES:
                continue
            full = os.path.join(dp, fn)
            stem, ext = os.path.splitext(fn)
            ext = ext.lower()
            if in_proxy:
                if ext == ".max":
                    proxy_maxes[stem.casefold()] = full
                elif ext in PROXY_EXT:
                    proxies.setdefault(stem.casefold(), full)
                continue
            if ext == ".max":
                tipo, render = _classify(parts, stem)
                info = itens.get(fn.casefold())
                if info:
                    tipo, render = info.get("tipo", tipo), info.get("render", render)
                try:
                    size = os.path.getsize(full)
                except OSError:
                    size = 0
                maxes.append({"path": full, "stem": stem, "size": size, "tipo": tipo, "render": render,
                              "parts": parts, **parse(stem)})
            elif ext in IMAGE_EXT and not in_maps:
                images[stem.casefold()].append(full)
                images_loose[_loose(stem)].append(full)
                previews.append(full)
            elif ext in PROXY_EXT and not in_maps:
                proxies[stem.casefold()] = full
            elif low == "index.xml":
                indexes.append(full)
            elif ext in ARCHIVE_EXT:
                try:
                    archives.append((full, os.path.getsize(full)))
                except OSError:
                    archives.append((full, 0))
            elif ext == ".pdf":
                pdfs.append(full)

    # capa do volume: jpg ao lado da pasta; senão nada (o PDF vira capa na etapa 2)
    for ext in (".jpg", ".jpeg", ".png"):
        p = os.path.join(cover_dir, name + ext)
        if os.path.isfile(p):
            vol.capa = p
            break
    vol.pdf = pdfs[0] if pdfs else None

    if not maxes:
        if archives:
            vol.status = "compactado"
            vol.aviso = _archive_problem(archives) or "ainda não extraído"
            if "falta" in vol.aviso:
                vol.status = "corrompido"
            try:        # a extração já foi tentada e deu erro (archiva_extracao.json)
                with open(os.path.join(path, "archiva_extracao.json"), encoding="utf-8") as f:
                    err = json.load(f).get("erro", "")
                if err:
                    vol.status, vol.aviso = "corrompido", err
            except (OSError, ValueError):
                pass
            return vol
        return None

    # 1) index.xml
    by_path = {os.path.normcase(m["path"]): m for m in maxes}
    for idx in indexes:
        base = os.path.dirname(idx)
        for it in _parse_index(idx):
            mp = _resolve(base, it["maxfile"]) if it["maxfile"] else None
            m = by_path.get(os.path.normcase(mp)) if mp else None
            if not m:
                continue
            m["fp"] = True
            if it["bitmap"] and not m.get("preview"):
                for c in (_resolve(base, it["bitmap"]), os.path.join(base, "thumbnails", os.path.basename(it["bitmap"]))):
                    if os.path.isfile(c):
                        m["preview"] = c
                        break
    # 2) mesmo nome  3) nome quase igual  4) cena01 ↔ cena01_1
    for m in maxes:
        m["proxy"] = proxy_maxes.get(m["stem"].casefold()) or proxies.get(m["stem"].casefold())
        if m.get("preview"):
            continue
        st = m["stem"].casefold()
        cands = images.get(st, [])
        same = [c for c in cands if os.path.dirname(c) == os.path.dirname(m["path"])]
        m["preview"] = (same or cands or images_loose.get(_loose(st), []) or
                        [c for c in images.get(st + "_1", []) if os.path.dirname(c) == os.path.dirname(m["path"])]
                        or [None])[0]

    # decisões da etapa 0: o que aparece
    has_mesh = any(m["tipo"] in ("mesh", "conjunto") for m in maxes)
    shown = [m for m in maxes if m["tipo"] in ("mesh", "conjunto") or (m["tipo"] == "cena" and not has_mesh)]
    # V-Ray só fica se não existir Corona do mesmo tipo
    for tipo in ("mesh", "conjunto"):
        if any(m["tipo"] == tipo and m["render"] == "Corona" for m in shown):
            shown = [m for m in shown if not (m["tipo"] == tipo and m["render"] == "V-Ray")]
    # mesmo arquivo em duas pastas: fica o da pasta Corona
    by_name = collections.defaultdict(list)
    for m in shown:
        by_name[os.path.basename(m["path"]).casefold()].append(m)
    keep = []
    for ms in by_name.values():
        corona = [m for m in ms if any("corona" in p for p in m["parts"])]
        keep.append((corona or ms)[0])
    keep.sort(key=lambda m: natural_key(m["stem"]))

    # agrupa por espécie
    groups: dict[str, Especie] = {}
    for m in keep:
        if m["tipo"] == "cena":
            k, nome, grupo = "cenas", "Cenas", True
        elif m["tipo"] == "conjunto":
            k, nome, grupo = "conjuntos", "Conjuntos", True
        elif m.get("especie"):
            k, nome, grupo = slug(m["especie"]), m["especie"], False
        else:
            k, nome, grupo = "outros", "Sem espécie no nome", True
        e = groups.get(k)
        if e is None:
            e = groups[k] = Especie(k, nome, grupo=grupo)
        e.arquivos.append(Arquivo(m["path"], m["stem"], m["size"], m["tipo"], m["render"],
                                  m.get("variacao"), m.get("tamanho"), m.get("detalhe"),
                                  m.get("preview"), m.get("proxy"), bool(m.get("fp"))))

    # capa de cada espécie: composição "_01------03" › Globe _PRV1 (ou nome encurtado) › tamanho 03 › a primeira
    for e in groups.values():
        if e.grupo:
            e.capa = next((a.preview for a in e.arquivos if a.preview), None)
            continue
        comp = [p for p in previews if "------" in p and re.search(rf"(^|-){re.escape(e.key)}-", slug(os.path.basename(p)))]
        comp01 = [p for p in comp if re.search(r"_01------0?3", os.path.basename(p))]
        prv = []
        for p in previews:
            mm = re.match(r"^(.+)-prv(\d+)$", slug(os.path.splitext(os.path.basename(p))[0]))
            if mm and (e.key == mm.group(1) or e.key.startswith(mm.group(1) + "-")):
                prv.append((e.key != mm.group(1), int(mm.group(2)), p))
        # imagem de apresentação com o nome da espécie (Vol 004: "MT_PM_V4_Aglaonema spp.jpg")
        named = [p for p in previews
                 if slug(re.sub(r"^MT_PM_(V\d+_)?", "", os.path.splitext(os.path.basename(p))[0], flags=re.I)) == e.key]
        t03 = [a.preview for a in e.arquivos if a.tamanho == "03" and a.preview]
        first = [a.preview for a in e.arquivos if a.preview]
        e.capa = (comp01 or comp or named or [p for *_, p in sorted(prv)] or t03 or first or [None])[0]
        # prévia de quem não tem (Globe: Mesh/Corona e GrowFX só têm a prévia da espécie)
        for a in e.arquivos:
            if not a.preview:
                a.preview = e.capa

    vol.especies = sorted(groups.values(), key=lambda e: (e.grupo, natural_key(e.nome)))

    # extração incompleta (Vol 130): algumas espécies têm texturas com o nome delas e outras não, com o compactado
    # ao lado. Não vale quando o próprio Archiva extraiu e deu certo, nem quando nenhuma textura leva o nome da
    # espécie (volumes antigos, como o 004: aí o nome das texturas não diz nada).
    extracted_ok = False
    try:
        with open(os.path.join(path, "archiva_extracao.json"), encoding="utf-8") as f:
            extracted_ok = bool(json.load(f).get("ok"))
    except (OSError, ValueError):
        pass
    if archives and not extracted_ok:
        map_names = " ".join(slug(f) for dp, _, fns in os.walk(path) if any("maps" in p for p in _parts(dp, path))
                             for f in fns)
        reais = [e for e in vol.especies if not e.grupo]
        sem = [e.nome for e in reais if e.key not in map_names]
        if sem and len(sem) < len(reais) and "maxtree" in col_key:
            vol.status = "corrompido"
            vol.aviso = f"extração incompleta: {len(sem)} espécies sem texturas"
    return vol


# ----------------------------------------------------------------------------- coleção

def collection_key(path: str) -> str:
    return "veg:" + slug(os.path.basename(os.path.normpath(path)))


def read_collection(path: str) -> Colecao:
    path = os.path.normpath(path)
    col = Colecao(collection_key(path), os.path.basename(path), path, lida_em=time.time())
    try:
        entries = sorted(os.scandir(path), key=lambda e: natural_key(e.name))
    except OSError:
        return col
    for e in entries:
        if not e.is_dir() or e.name.startswith(("_", ".", "$")):
            continue
        v = read_volume(col.key, e.path, e.name, path)
        if v is not None:
            col.volumes.append(v)
    return col


# ----------------------------------------------------------------------------- índice em disco (abre na hora)

def _from_dict(d: dict) -> Colecao:
    vols = []
    for v in d.pop("volumes", []):
        esp = []
        for e in v.pop("especies", []):
            arqs = [Arquivo(**a) for a in e.pop("arquivos", [])]
            esp.append(Especie(**e, arquivos=arqs))
        vols.append(Volume(**v, especies=esp))
    return Colecao(**d, volumes=vols)


def save_index(path: str, cols: list[Colecao]) -> None:
    tmp = path + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"versao": INDEX_VERSION, "colecoes": [asdict(c) for c in cols]}, f, ensure_ascii=False)
        os.replace(tmp, path)
    except OSError:
        pass


def load_index(path: str) -> list[Colecao]:
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("versao") != INDEX_VERSION:
            return []
        return [_from_dict(c) for c in d.get("colecoes", [])]
    except (OSError, ValueError, TypeError):
        return []


# ----------------------------------------------------------------------------- busca

def search(cols: list[Colecao], text: str) -> list[tuple[Colecao, Volume, Especie]]:
    """Espécies cujo nome contém o texto (sem acento, sem maiúsculas; 'phoenix cana' acha 'Phoenix canariensis')."""
    words = [w for w in slug(text).split("-") if w]
    if not words:
        return []
    out = []
    for c in cols:
        for v in c.volumes:
            for e in v.especies:
                if e.grupo:
                    continue
                s = e.key
                if all(w in s for w in words):
                    out.append((c, v, e))
    first = "-".join(words)

    def rank(r):
        k = r[2].key
        # começa com o texto › alguma palavra começa com ele › só contém
        return (0 if k.startswith(first) else 1 if f"-{words[0]}" in f"-{k}" else 2,
                natural_key(r[2].nome), r[1].key)
    out.sort(key=rank)
    return out
