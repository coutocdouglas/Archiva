"""Organizar um volume de vegetação no padrão de pastas (docs/plano-vegetacao.md, "Padrão de pastas").

    <volume>/
      <prefixo> - Mesh/            .max com o nome original + prévia .jpg com o mesmo nome (+ index.xml, matlib, .ms)
        <prefixo> - Proxy/         proxies (.cproxy / .cgeo)
      <prefixo> - Maps/            texturas
      <prefixo> - PDF/             PDF do volume + capas das espécies
      <prefixo> - Outros/          tudo que não tem lugar no padrão (a pessoa escolhe manter ou descartar)
      _DESCARTADOS/                o que sai (versão repetida, cena com malhas, V-Ray com Corona, compactado extraído…)
      archiva.json                 marca de organizado + diário de tudo que foi feito (para desfazer)

Regras de segurança:
  * planejar() só lê. aplicar() nunca apaga nada: move (mesma unidade = renomear), copia prévias e escreve
    arquivos novos; tudo vai para o diário. desfazer() lê o diário e volta tudo, do último passo para o primeiro.
  * Nada é sobrescrito: se um destino já existe, o plano fica bloqueado e nada é feito.
  * Volume corrompido, compactado ou já organizado não é organizado.
"""
from __future__ import annotations

import collections
import json
import os
import re
import shutil
import stat
import time
from dataclasses import dataclass, field

from . import leitor

PADRAO = 1
JOURNAL = "archiva.json"
DESCARTE = "_DESCARTADOS"
TEXTURE_EXT = leitor.IMAGE_EXT | {".exr", ".hdr", ".tga", ".tx", ".dds"}

# grupos (ordem em que aparecem na tela de conferência)
MESH, PROXY, MAPS, PDF, OUTROS, DESC, CAPA = "Mesh", "Proxy", "Maps", "PDF", "Outros", "Descartar", "Capa"


@dataclass
class Passo:
    acao: str            # mover | copiar | escrever | descartar
    origem: str          # caminho absoluto (para "escrever": vazio)
    destino: str         # caminho absoluto
    grupo: str
    motivo: str = ""
    tamanho: int = 0
    conteudo: bytes | None = None      # só para "escrever" (capa tirada do PDF, index.xml reescrito)


@dataclass
class Plano:
    volume: str
    prefixo: str
    status: str = "ok"                 # ok | bloqueado
    motivo: str = ""
    passos: list[Passo] = field(default_factory=list)
    conflitos: list[str] = field(default_factory=list)
    itens: dict = field(default_factory=dict)        # nome.max → {tipo, render, forest_pack} (o nome da pasta se perde)

    def por_grupo(self) -> dict[str, list[Passo]]:
        g = collections.OrderedDict((k, []) for k in (MESH, PROXY, MAPS, PDF, CAPA, OUTROS, DESC))
        for p in self.passos:
            g[p.grupo].append(p)
        return g


# ----------------------------------------------------------------------------- utilidades

def _size(path: str) -> int:
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _writable(path: str) -> None:
    try:
        os.chmod(path, stat.S_IWRITE | stat.S_IREAD)
    except OSError:
        pass


def _tree_size(path: str) -> int:
    n = 0
    for dp, _, fns in os.walk(path):
        for f in fns:
            n += _size(os.path.join(dp, f))
    return n


def _rel(path: str, base: str) -> str:
    return os.path.relpath(path, base)


def _collapse_double(rel: str) -> str:
    """'X\\X\\a.jpg' → 'X\\a.jpg' (pastas aninhadas em dobro somem)."""
    parts = rel.split(os.sep)
    out = []
    for p in parts:
        if not out or p.casefold() != out[-1].casefold():
            out.append(p)
    return os.sep.join(out)


def prefix_for(col_key: str, vol_key: str) -> str:
    m = re.search(r"(\d+)$", vol_key)
    n = int(m.group(1)) if m else 0
    return f"GP_B{n:03d}" if "globe" in col_key else f"MT_PM_V{n:03d}"


def capa_pdf(path: str, largura: int = 1600) -> bytes | None:
    """Capa do volume: a primeira página do PDF, desenhada pelo QtPdf (abre também os PDFs protegidos da Maxtree).
    Se o QtPdf não estiver disponível, tenta a primeira imagem JPEG embutida."""
    try:
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QSize
        from PySide6.QtPdf import QPdfDocument
        doc = QPdfDocument()
        if doc.load(path) == QPdfDocument.Error.None_ and doc.pageCount() > 0:
            sz = doc.pagePointSize(0)
            img = doc.render(0, QSize(largura, int(largura * sz.height() / max(1.0, sz.width()))))
            if not img.isNull():
                buf = QByteArray()
                dev = QBuffer(buf)
                dev.open(QIODevice.WriteOnly)
                img.save(dev, "JPG", 88)
                dev.close()
                doc.close()
                return bytes(buf)
        doc.close()
    except Exception:  # noqa: BLE001 — sem QtPdf ou PDF estranho: tenta o outro jeito
        pass
    return pdf_first_jpeg(path)


def pdf_first_jpeg(path: str, limit: int = 60 * 1024 * 1024) -> bytes | None:
    """Primeira imagem JPEG embutida no PDF (nos PDFs da Maxtree é a capa). Não precisa de QtPdf."""
    try:
        with open(path, "rb") as f:
            data = f.read(limit)
    except OSError:
        return None
    for m in re.finditer(rb"/Filter\s*/DCTDecode", data):
        s = data.find(b"stream", m.end())
        if s < 0:
            continue
        s += 6
        s += 2 if data[s:s + 2] == b"\r\n" else 1
        e = data.find(b"endstream", s)
        if e > s and data[s:s + 2] == b"\xff\xd8":
            jpg = data[s:e].rstrip(b"\r\n")
            if len(jpg) > 20000:          # ignora ícones e logotipos pequenos
                return jpg
    return None


# ----------------------------------------------------------------------------- planejar (só lê)

def planejar(col_key: str, vol_path: str, cover_dir: str) -> Plano:
    vol_path = os.path.normpath(vol_path)
    name = os.path.basename(vol_path)
    vkey, _ = leitor.volume_key(col_key, name)
    pre = prefix_for(col_key, vkey)
    plano = Plano(vol_path, pre)
    D = {g: os.path.join(vol_path, f"{pre} - {g}") for g in (MESH, MAPS, PDF, OUTROS)}
    D[PROXY] = os.path.join(D[MESH], f"{pre} - Proxy")
    D[DESC] = os.path.join(vol_path, DESCARTE)

    if os.path.isfile(os.path.join(vol_path, JOURNAL)):
        plano.status, plano.motivo = "bloqueado", "Este volume já está organizado."
        return plano
    if os.path.isfile(os.path.join(vol_path, JOURNAL + ".parcial")):
        plano.status, plano.motivo = "bloqueado", ("A organização deste volume foi interrompida no meio. "
                                                    "Use \"Desfazer organização\" antes de organizar de novo.")
        return plano
    vol = leitor.read_volume(col_key, vol_path, name, cover_dir)
    if vol is None or vol.status == "compactado":
        plano.status, plano.motivo = "bloqueado", "Volume ainda compactado: extraia antes de organizar."
        return plano
    if vol.status == "corrompido":
        plano.status, plano.motivo = "bloqueado", f"Volume corrompido ou fora do padrão ({vol.aviso}). Não organizado."
        return plano

    parse = leitor.parse_maxtree if "maxtree" in col_key else leitor.parse_globe
    files: list[str] = []
    maxes: list[dict] = []
    indexes: list[str] = []
    for dp, dns, fns in os.walk(vol_path):
        dns[:] = sorted((d for d in dns if d.casefold() != DESCARTE.casefold()), key=leitor.natural_key)
        for fn in fns:
            full = os.path.join(dp, fn)
            if dp == vol_path and fn in (JOURNAL, "archiva_extracao.json"):
                continue
            files.append(full)
            stem, ext = os.path.splitext(fn)
            if ext.lower() == ".max":
                parts = leitor._parts(dp, vol_path)
                tipo, render = leitor._classify(parts, stem)
                maxes.append({"path": full, "stem": stem, "tipo": tipo, "render": render, "parts": parts,
                              **parse(stem)})
            elif fn.casefold() == "index.xml":
                indexes.append(full)

    top = lambda p: _rel(p, vol_path).split(os.sep)[0]
    gone: dict[str, str] = {}          # caminho (arquivo ou pasta) → motivo do descarte

    # --- decisões da etapa 0
    has_mesh = any(m["tipo"] in ("mesh", "conjunto") for m in maxes)
    if has_mesh:
        for t in sorted({top(m["path"]) for m in maxes if m["tipo"] == "cena"}):
            if not any(top(m["path"]) == t and m["tipo"] != "cena" for m in maxes):
                gone[os.path.join(vol_path, t)] = "cena num volume que já tem as malhas"
    for tipo in ("mesh", "conjunto", "growfx"):
        if any(m["tipo"] == tipo and m["render"] == "Corona" for m in maxes):
            for m in maxes:
                if m["tipo"] == tipo and m["render"] == "V-Ray":
                    d = os.path.dirname(m["path"])
                    if any(os.path.dirname(x["path"]) == d and x["render"] == "Corona" for x in maxes):
                        gone[m["path"]] = "versão V-Ray (existe a Corona)"
                    else:
                        gone[d] = "versão V-Ray (existe a Corona)"
    by_name = collections.defaultdict(list)
    for m in maxes:
        if m["tipo"] in ("mesh", "conjunto"):
            by_name[os.path.basename(m["path"]).casefold()].append(m)
    losers = collections.Counter()
    for ms in by_name.values():
        if len(ms) > 1:
            corona = [m for m in ms if any("corona" in p for p in m["parts"])]
            keep = (corona or ms)[0]
            for m in ms:
                if m is not keep:
                    losers[top(m["path"])] += 1
                    gone[m["path"]] = "versão repetida (fica a da pasta Corona)"
    for t, n in losers.items():
        if n == sum(1 for m in maxes if top(m["path"]) == t):     # a pasta inteira é a versão repetida
            for m in maxes:
                gone.pop(m["path"], None) if top(m["path"]) == t else None
            gone[os.path.join(vol_path, t)] = "versão repetida (fica a da pasta Corona)"
    for path, _ in [(f, 0) for f in files if os.path.splitext(f)[1].lower() in leitor.ARCHIVE_EXT]:
        gone[path] = "compactado já extraído"

    def gone_reason(p: str) -> str | None:
        n = os.path.normcase(p)
        for g, why in gone.items():
            gn = os.path.normcase(g)
            if n == gn or n.startswith(gn + os.sep):
                return why
        return None

    # --- o que vai para a Mesh
    kept = [m for m in maxes if not gone_reason(m["path"])]
    has_mesh = any(m["tipo"] in ("mesh", "conjunto") for m in kept)
    to_mesh = {os.path.normcase(m["path"]): m for m in kept
               if m["tipo"] in ("mesh", "conjunto") or (m["tipo"] == "cena" and not has_mesh)}
    mesh_stems = {(os.path.normcase(os.path.dirname(m["path"])), m["stem"].casefold()) for m in to_mesh.values()}
    mesh_dirs = {os.path.normcase(os.path.dirname(p)) for p in to_mesh}
    lib_dirs = set()
    for idx in indexes:
        d = os.path.normcase(os.path.dirname(idx))
        if any(md == d or md.startswith(d + os.sep) for md in mesh_dirs) and leitor._parse_index(idx):
            lib_dirs.add(d)
    # prévias e capas que o leitor ligou (index.xml, mesmo nome, nome quase igual, prévia da espécie)
    previews: dict[str, str] = {}
    covers: set[str] = set()
    for e in vol.especies:
        if e.capa:
            covers.add(os.path.normcase(e.capa))
        for a in e.arquivos:
            if a.preview:
                previews[os.path.normcase(a.path)] = a.preview
    for m in to_mesh.values():
        plano.itens[os.path.basename(m["path"])] = {"tipo": m["tipo"], "render": m["render"]}

    def add(acao, origem, destino, grupo, motivo="", tamanho=None, conteudo=None):
        plano.passos.append(Passo(acao, origem, destino, grupo, motivo,
                                  _size(origem) if tamanho is None and origem else (tamanho or 0), conteudo))

    # --- descartes de pastas/arquivos inteiros
    for g, why in sorted(gone.items()):
        dest = os.path.join(D[DESC], _collapse_double(_rel(g, vol_path)))
        add("descartar", g, dest, DESC, why, _tree_size(g) if os.path.isdir(g) else _size(g))

    # --- cada arquivo que sobra
    for f in files:
        if gone_reason(f):
            continue
        d, fn = os.path.split(f)
        nd = os.path.normcase(d)
        stem, ext = os.path.splitext(fn)
        ext = ext.lower()
        parts = leitor._parts(d, vol_path)
        rel = _collapse_double(_rel(f, vol_path))
        if fn.casefold() in leitor.IGNORED_FILES:
            add("descartar", f, os.path.join(D[DESC], rel), DESC, "arquivo de miniaturas do Windows")
        elif ext == ".max":
            if os.path.normcase(f) in to_mesh:
                add("mover", f, os.path.join(D[MESH], fn), MESH)
            else:
                why = "GrowFX (malha procedural)" if "growfx" in " ".join(parts) or "_gfx" in stem.casefold() \
                    else "fora do padrão"
                add("mover", f, os.path.join(D[OUTROS], rel), OUTROS, why)
        elif ext in leitor.IMAGE_EXT and (nd, stem.casefold()) in mesh_stems:
            add("mover", f, os.path.join(D[MESH], fn), MESH, "prévia")
        elif ext in leitor.PROXY_EXT:
            add("mover", f, os.path.join(D[PROXY], fn), PROXY)
        elif ext == ".pdf" or (ext in leitor.IMAGE_EXT and "------" in fn):
            add("mover", f, os.path.join(D[PDF], fn), PDF, "PDF" if ext == ".pdf" else "capa da espécie")
        elif os.path.normcase(f) in covers and not any("thumb" in p for p in parts) and ext in leitor.IMAGE_EXT:
            add("mover", f, os.path.join(D[PDF], fn), PDF, "capa da espécie")
        elif any(nd == ld or nd.startswith(ld + os.sep) for ld in lib_dirs) and not any("thumb" in p for p in parts) \
                and (fn.casefold() == "index.xml" or ext == ".mat"):
            sub = _rel(f, next(ld for ld in lib_dirs if nd == ld or nd.startswith(ld + os.sep)))
            if fn.casefold() == "index.xml":
                _index_steps(plano, f, os.path.join(D[MESH], sub), os.path.join(D[OUTROS], rel), add)
            else:
                add("mover", f, os.path.join(D[MESH], sub), MESH, "biblioteca de materiais do Forest Pack")
        elif ext == ".ms" and any(ld == nd or ld.startswith(nd + os.sep) for ld in lib_dirs):
            add("mover", f, os.path.join(D[MESH], fn), MESH, "script da biblioteca Forest Pack")
        elif any("maps" in p for p in parts) and ext in TEXTURE_EXT:
            add("mover", f, os.path.join(D[MAPS], fn), MAPS)
        else:
            add("mover", f, os.path.join(D[OUTROS], rel), OUTROS, _outros_motivo(parts, ext))

    # --- prévias que estão em outra pasta: cópia com o nome do .max, ao lado dele
    moved_to = {os.path.normcase(p.origem): p.destino for p in plano.passos if p.acao in ("mover", "descartar")}

    def where_after(path: str) -> str:
        """Onde o arquivo estará quando chegar a vez da cópia (pode ter ido junto com uma pasta inteira)."""
        n = os.path.normcase(path)
        if n in moved_to:
            return moved_to[n]
        for o, dst in moved_to.items():
            if n.startswith(o + os.sep):
                return os.path.join(dst, path[len(o) + 1:])
        return path

    for key, m in to_mesh.items():
        prev = previews.get(key)
        if not prev:
            continue
        own = (os.path.normcase(os.path.dirname(prev)), os.path.splitext(os.path.basename(prev))[0].casefold())
        if own in mesh_stems and own[1] == m["stem"].casefold():
            continue        # já é a prévia com o mesmo nome, vai junto
        dest = os.path.join(D[MESH], m["stem"] + os.path.splitext(prev)[1].lower())
        src = where_after(prev)
        add("copiar", src, dest, MESH, "prévia copiada com o nome do .max", _size(prev))

    # --- capa do volume (jpg ao lado da pasta): se não existe, tira a primeira imagem do PDF
    if not vol.capa and vol.pdf:
        jpg = capa_pdf(vol.pdf)
        if jpg:
            add("escrever", "", os.path.join(cover_dir, name + ".jpg"), CAPA, "capa do volume tirada do PDF",
                len(jpg), jpg)

    # --- conflitos: dois arquivos no mesmo destino, ou destino que já existe
    seen: dict[str, str] = {}
    for p in plano.passos:
        k = os.path.normcase(p.destino)
        if k in seen:
            plano.conflitos.append(f"{os.path.basename(p.destino)}: vem de {seen[k]} e de {p.origem or 'PDF'}")
        seen[k] = p.origem or "PDF"
        if os.path.exists(p.destino) and os.path.normcase(p.origem) != k:
            plano.conflitos.append(f"{p.destino} já existe")
    if plano.conflitos:
        plano.status = "bloqueado"
        plano.motivo = "Há arquivos que iriam para o mesmo lugar. Nada foi feito."
    return plano


def _outros_motivo(parts: list[str], ext: str) -> str:
    low = " ".join(parts)
    if ext == ".mat":
        return "biblioteca de materiais avulsa"
    if "thumb" in low:
        return "miniatura repetida (a prévia vai ao lado do .max)"
    if "preview" in low:
        return "imagem de apresentação"
    if ext in leitor.ARCHIVE_EXT:
        return "compactado"
    return "fora do padrão"


def _index_steps(plano: Plano, src: str, dest: str, outros_dest: str, add) -> None:
    """index.xml vai para a Mesh. Se aponta para subpastas (Globe: object/…, thumbnails/…), é reescrito com só o
    nome do arquivo (tudo fica lado a lado na Mesh) e o original vai para Outros."""
    try:
        text = open(src, encoding="utf-8").read()
    except (OSError, UnicodeDecodeError):
        add("mover", src, dest, MESH, "índice da biblioteca Forest Pack")
        return
    pat = re.compile(r"(<(maxfile|bitmap)>)([^<]*?)(</\2>)")
    changed = [False]

    def fix(m):
        val = m.group(3)
        base = re.split(r"[\\/]", val)[-1]
        new = (".\\" + base) if m.group(2) == "maxfile" else base
        if new != val:
            changed[0] = True
        return m.group(1) + new + m.group(4)

    new_text = pat.sub(fix, text)
    if not changed[0]:
        add("mover", src, dest, MESH, "índice da biblioteca Forest Pack")
        return
    add("mover", src, outros_dest, OUTROS, "índice original (antes de reescrever os caminhos)")
    data = new_text.encode("utf-8")
    add("escrever", "", dest, MESH, "índice com os caminhos da pasta Mesh", len(data), data)


# ----------------------------------------------------------------------------- aplicar / desfazer

def aplicar(plano: Plano, descartar_outros: set[str] | None = None, progress=None) -> dict:
    """Executa o plano. descartar_outros: origens (caminhos) dos itens de Outros que a pessoa marcou para descartar.
    Grava o diário a cada passo (archiva.json.parcial) e, no fim, archiva.json. Devolve o diário."""
    if plano.status != "ok":
        raise RuntimeError(plano.motivo or "plano bloqueado")
    descartar_outros = {os.path.normcase(p) for p in (descartar_outros or ())}
    vol = plano.volume
    journal = {"padrao": PADRAO, "prefixo": plano.prefixo, "inicio": time.time(), "itens": plano.itens,
               "passos": []}
    partial = os.path.join(vol, JOURNAL + ".parcial")

    def save(path):
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(journal, f, ensure_ascii=False, indent=1)
        os.replace(tmp, path)

    total = len(plano.passos)
    for i, p in enumerate(plano.passos):
        dest = p.destino
        acao = p.acao
        if p.grupo == OUTROS and os.path.normcase(p.origem) in descartar_outros:
            dest = os.path.join(vol, DESCARTE, os.path.relpath(p.destino, os.path.join(vol, f"{plano.prefixo} - Outros")))
            acao = "descartar"
        if os.path.exists(dest):
            raise FileExistsError(f"Já existe: {dest}")
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        if acao in ("mover", "descartar"):
            shutil.move(p.origem, dest)
        elif acao == "copiar":
            shutil.copy2(p.origem, dest)
            _writable(dest)          # a original pode ser somente leitura; a cópia é do Archiva
        elif acao == "escrever":
            with open(dest, "wb") as f:
                f.write(p.conteudo or b"")
        journal["passos"].append([acao, p.origem, dest])
        save(partial)
        if progress:
            progress(i + 1, total)
    removed = _remove_empty_dirs(vol, keep={DESCARTE.casefold()})
    journal["pastas_removidas"] = removed
    journal["fim"] = time.time()
    save(os.path.join(vol, JOURNAL))
    os.remove(partial)
    return journal


def _remove_empty_dirs(vol: str, keep: set[str]) -> list[str]:
    """Apaga as pastas que ficaram vazias (só pastas vazias, nunca arquivos)."""
    removed = []
    for dp, dns, fns in os.walk(vol, topdown=False):
        if dp == vol:
            continue
        rel_top = os.path.relpath(dp, vol).split(os.sep)[0].casefold()
        if rel_top in keep:
            continue
        try:
            if not os.listdir(dp):
                os.rmdir(dp)
                removed.append(dp)
        except OSError:
            pass
    return removed


def esta_organizado(vol_path: str) -> bool:
    return os.path.isfile(os.path.join(vol_path, JOURNAL))


def interrompido(vol_path: str) -> bool:
    return os.path.isfile(os.path.join(vol_path, JOURNAL + ".parcial"))


def desfazer(vol_path: str, progress=None) -> int:
    """Volta tudo o que aplicar() fez neste volume, do último passo para o primeiro. Devolve quantos passos."""
    path = os.path.join(vol_path, JOURNAL)
    if not os.path.isfile(path):
        path = os.path.join(vol_path, JOURNAL + ".parcial")      # organização interrompida no meio
    with open(path, encoding="utf-8") as f:
        journal = json.load(f)
    for d in journal.get("pastas_removidas", []):
        os.makedirs(d, exist_ok=True)
    steps = journal.get("passos", [])
    for i, (acao, origem, dest) in enumerate(reversed(steps)):
        if acao in ("mover", "descartar"):
            if os.path.exists(dest):
                os.makedirs(os.path.dirname(origem), exist_ok=True)
                if os.path.exists(origem):
                    raise FileExistsError(f"Não dá para voltar: {origem} já existe")
                shutil.move(dest, origem)
        elif acao in ("copiar", "escrever"):
            if os.path.isfile(dest):
                _writable(dest)
                os.remove(dest)          # só arquivos que o próprio Archiva criou
        if progress:
            progress(i + 1, len(steps))
    created_roots = {os.path.join(vol_path, f"{journal['prefixo']} - {g}") for g in (MESH, MAPS, PDF, OUTROS)}
    created_roots.add(os.path.join(vol_path, DESCARTE))
    for root in created_roots:
        for dp, _, _ in sorted(os.walk(root, topdown=False), key=lambda t: -len(t[0])):
            try:
                os.rmdir(dp)
            except OSError:
                pass
    os.remove(path)
    return len(steps)
