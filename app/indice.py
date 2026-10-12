"""Índice da biblioteca guardado no computador (abertura rápida, principalmente com a biblioteca na rede).

Ao abrir, o Archiva mostra a biblioteca a partir do índice salvo e, em segundo plano, confere cada
categoria com uma única listagem de pasta (nomes + datas). Só as categorias que mudaram são lidas de
novo por inteiro. "Atualizar" (F5) continua fazendo a leitura completa.
"""
from __future__ import annotations

import hashlib
import os
import pickle
from pathlib import Path

from PySide6.QtCore import QThread, Signal

from .scanner import Category, list_categories, scan_category

VERSION = 1


def cache_file(cache_dir: Path, root: str) -> Path:
    h = hashlib.sha1(os.path.normcase(os.path.normpath(root)).encode("utf-8")).hexdigest()[:16]
    d = Path(cache_dir) / "indice"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{h}.pkl"


def _listing(path: str) -> list:
    out = []
    try:
        with os.scandir(path) as it:
            for e in it:
                try:
                    st = e.stat()
                    out.append((e.name, e.is_dir(), int(st.st_mtime), 0 if e.is_dir() else st.st_size))
                except OSError:
                    out.append((e.name, None, 0, 0))
    except OSError:
        return [("<erro>",)]
    out.sort()
    return out


def signature(cat: Category | None, path: str) -> str:
    """Impressão digital da categoria: listagem dela + das subcategorias (ex.: LUMINARIAS › PENDENTE)."""
    parts = [_listing(path)]
    stack = list(cat.children) if cat else []
    while stack:
        c = stack.pop()
        parts.append((c.path, _listing(c.path)))
        stack.extend(c.children)
    return hashlib.sha1(repr(parts).encode("utf-8", "replace")).hexdigest()


def load(path: Path, root: str):
    try:
        with open(path, "rb") as f:
            d = pickle.load(f)
        if d.get("v") == VERSION and d.get("root") == root:
            return d["cats"], d["sigs"]
    except Exception:  # noqa: BLE001 — índice velho ou corrompido: lê tudo de novo
        pass
    return None


def save(path: Path, root: str, cats: list, sigs: dict) -> None:
    try:
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            pickle.dump({"v": VERSION, "root": root, "cats": cats, "sigs": sigs}, f, protocol=pickle.HIGHEST_PROTOCOL)
        os.replace(tmp, path)
    except Exception:  # noqa: BLE001
        pass


def all_signatures(root: str, cats: list) -> dict:
    return {c.key: signature(c, c.path) for c in cats}


class VerifyThread(QThread):
    """Confere o índice salvo com o disco; relê só o que mudou."""
    changed = Signal(object, str)        # Category nova, assinatura
    removed = Signal(str)                # chave da categoria que sumiu
    finished_ok = Signal(int)            # quantas categorias mudaram

    def __init__(self, root: str, cats: list, sigs: dict):
        super().__init__()
        self.root, self.cats, self.sigs = root, {c.key: c for c in cats}, dict(sigs)

    def run(self):
        n = 0
        try:
            current = list_categories(self.root)
        except Exception:  # noqa: BLE001
            self.finished_ok.emit(0)
            return
        names = {name for name, _ in current}
        for key in list(self.cats):
            if key not in names:
                self.removed.emit(key)
                n += 1
        for name, path in current:
            if self.isInterruptionRequested():
                return
            old = self.cats.get(name)
            sig = signature(old, path)
            if old is not None and self.sigs.get(name) == sig:
                continue
            try:
                new = scan_category(path, name, name)
            except Exception:  # noqa: BLE001
                continue
            self.changed.emit(new, signature(new, path))
            n += 1
        self.finished_ok.emit(n)
