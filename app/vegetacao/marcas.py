"""Favoritos e tags da Vegetação (etapa 5), sem Qt.

- Chaves estáveis (as do leitor), nunca o caminho: espécie `veg:maxtree/071/phoenix-canariensis`, volume
  `veg:maxtree/071`. Sobrevivem à organização (etapa 2), que só muda pastas.
- **Favoritos são pessoais**: `%APPDATA%\\GerenciadorAssets3D\\vegetacao_favoritos.json`, na ordem em que foram
  marcados (o mais recente primeiro na faixa).
- **Tags são compartilhadas como as da Biblioteca**: ficam no mesmo banco (`TagDB`), que já leva cada mudança
  para os registros da equipe. A chave começa com `#` (`#veg:maxtree/071/…`): o banco e a nuvem já deixam de
  fora das contagens, do filtro e das coleções da Biblioteca tudo o que começa com `#`, então a Biblioteca não muda.
"""
from __future__ import annotations

import json
import os

from ..config import data_dir

FAV_FILE = "vegetacao_favoritos.json"
PREFIX = "#"                   # chave da Vegetação dentro do banco de tags: "#" + chave estável


# =========================================================================== chaves

def chave_especie(vol, esp) -> str:
    return f"{vol.key}/{esp.key}"


def chave_volume(vol) -> str:
    return vol.key


def db_key(key: str) -> str:
    return PREFIX + key


def resolver(cols, key: str) -> tuple | None:
    """Da chave estável para o lugar na página: ("especie", c, v, e) ou ("volume", c, v)."""
    for c in cols:
        if not key.startswith(c.key + "/"):
            continue
        for v in c.volumes:
            if key == v.key:
                return ("volume", c, v)
            if key.startswith(v.key + "/"):
                slug = key[len(v.key) + 1:]
                for e in v.especies:
                    if e.key == slug:
                        return ("especie", c, v, e)
    return None


# =========================================================================== favoritos (pessoais)

class Favoritos:
    def __init__(self, path: str | None = None):
        self.path = path or str(data_dir() / FAV_FILE)
        self.keys: list[str] = []
        self.load()

    def load(self) -> None:
        try:
            d = json.loads(open(self.path, encoding="utf-8").read())
            self.keys = [k for k in d.get("favoritos", []) if isinstance(k, str)]
        except (OSError, ValueError, AttributeError):
            self.keys = []

    def save(self) -> None:
        try:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump({"versao": 1, "favoritos": self.keys}, f, ensure_ascii=False, indent=2)
            os.replace(tmp, self.path)
        except OSError:
            pass

    def __contains__(self, key: str) -> bool:
        return key in self.keys

    def toggle(self, key: str) -> bool:
        """Liga/desliga; devolve se ficou favorito."""
        if key in self.keys:
            self.keys.remove(key)
            on = False
        else:
            self.keys.insert(0, key)
            on = True
        self.save()
        return on


# =========================================================================== tags (compartilhadas, no TagDB)

def clean(t: str) -> str:
    return " ".join(t.strip().lower().split())


def split_tags(text: str) -> list[str]:
    out = []
    for t in text.replace(";", ",").split(","):
        t = clean(t)
        if t and t not in out:
            out.append(t)
    return out


def tags_de(db, key: str) -> list[str]:
    return sorted(db.tags_of(db_key(key)))


def adicionar(db, keys: list[str], tags: list[str]) -> None:
    tags = [clean(t) for t in tags if clean(t)]
    if keys and tags:
        db.add_tags([db_key(k) for k in keys], tags)


def remover(db, keys: list[str], tag: str) -> None:
    if keys:
        db.remove_tag([db_key(k) for k in keys], tag)


def definir(db, key: str, tags: list[str]) -> None:
    """Deixa o item exatamente com estas tags."""
    atuais = set(tags_de(db, key))
    novas = [clean(t) for t in tags if clean(t)]
    for t in atuais - set(novas):
        remover(db, [key], t)
    falta = [t for t in novas if t not in atuais]
    if falta:
        adicionar(db, [key], falta)


def todas(db) -> dict[str, list[str]]:
    """Tag → chaves estáveis da Vegetação que a usam (sem o '#')."""
    out: dict[str, list[str]] = {}
    for k, ts in db._by_item.items():
        if not k.startswith(PREFIX + "veg:"):
            continue
        for t in ts:
            out.setdefault(t, []).append(k[len(PREFIX):])
    for v in out.values():
        v.sort()
    return out


def renomear(db, old: str, new: str) -> None:
    """Só nos itens da Vegetação (a mesma tag na Biblioteca continua como está)."""
    old, new = clean(old), clean(new)
    if not new or old == new:
        return
    keys = todas(db).get(old, [])
    adicionar(db, keys, [new])
    remover(db, keys, old)


def excluir(db, tag: str) -> None:
    """Tira a tag de todos os itens da Vegetação (a Biblioteca não é tocada)."""
    remover(db, todas(db).get(clean(tag), []), tag)


def sugestoes(db) -> list[str]:
    """Para completar ao digitar: as tags da Vegetação e as da Biblioteca."""
    return sorted(set(todas(db)) | {t for t, _ in db.all_tags()})
