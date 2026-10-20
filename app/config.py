"""Configurações e caminhos do programa.

Nada aqui escreve dentro da biblioteca de modelos: configuração, banco de tags,
miniaturas e modelos extraídos ficam nas pastas do usuário do Windows
(%APPDATA% e %LOCALAPPDATA%).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

APP_NAME = "Archiva"
APP_ID = "GerenciadorAssets3D"


def app_dir() -> Path:
    """Pasta dos arquivos do programa (no instalado: a pasta interna do Archiva)."""
    return Path(__file__).resolve().parent.parent


def is_installed() -> bool:
    """True quando roda a versão instalada (Archiva.exe), False quando roda pelos .bat."""
    return bool(getattr(sys, "frozen", False))


def version() -> str:
    try:
        return (app_dir() / "VERSION").read_text(encoding="utf-8").strip()
    except OSError:
        return "?"


def data_dir() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home() / ".config")
    p = Path(base) / APP_ID
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / ".cache")
    return Path(base) / APP_ID / "cache"


DEFAULTS = {
    "library_root": "",
    "cache_dir": "",
    "thumb_size": 170,
    "drag_mode": "max",          # "max" = .max puro (Merge/XRef do Max + relink pelo script de inicialização) | "script" = merge direto no 0,0,0
    "backup_minutes": 60,         # compactados originais ficam no backup por este tempo (0 = nunca apagar)
    "unwanted_ext": [".fbx", ".obj", ".mtl"],
    "passwords": [],              # senhas de compactados já usadas (testadas automaticamente)
    "unrar_path": "",
    "show_filter": "all",
    "prefixes": {},               # nome dos itens em categorias vazias (Entrada)
    "last_entry_category": "",
    "expand_subfolders": [],      # na Entrada, estas categorias mostram as subpastas imediatas (ex.: LUMINARIAS)
    "titlebar": "archiva",        # "archiva" = barra integrada | "windows" = barra padrão do Windows
    "check_updates": True,        # procura versão nova no GitHub ao abrir
    "github_token": "",           # só se o repositório for privado (token só de leitura)
    "skip_version": "",           # versão que o usuário mandou ignorar
    "pastas_ocultas": {},         # por biblioteca: categorias que esta pessoa escondeu
    "tutorial_off": False,        # boas-vindas ao abrir desligadas
    "tutoriais_vistos": [],
    "versao_vista": "",           # última versão aberta (para mostrar as novidades)
    "window_geometry": "",
    "splitter_state": "",
}


class Config:
    def __init__(self) -> None:
        self.path = data_dir() / "config.json"
        self.values = dict(DEFAULTS)
        try:
            self.values.update(json.loads(self.path.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            pass
        self.first_run = not self.path.exists()
        # versão aberta pelo .bat dentro da biblioteca (F:\\MODELOS\\_GERENCIADOR): já sabe onde está a biblioteca.
        # Na versão instalada nada vem pronto: cada pessoa escolhe a sua pasta no primeiro uso.
        if not self.values.get("library_root") and not is_installed():
            guess = app_dir().parent
            if _looks_like_library(guess):
                self.values["library_root"] = str(guess)

    def __getitem__(self, key):
        return self.values.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        self.values[key] = value
        self.save()

    def save(self) -> None:
        try:
            self.path.write_text(json.dumps(self.values, indent=2, ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass

    @property
    def cache_dir(self) -> Path:
        p = Path(self["cache_dir"]) if self["cache_dir"] else default_cache_dir()
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def db_path(self) -> Path:
        return data_dir() / "biblioteca.db"


def _looks_like_library(p: Path) -> bool:
    try:
        dirs = [d for d in p.iterdir() if d.is_dir() and not d.name.startswith(("_", ".", "$"))]
    except OSError:
        return False
    return len(dirs) >= 3
