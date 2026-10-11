"""Banco de tags (SQLite). Itens são identificados por 'CATEGORIA/ITEM', o que permite,
no futuro, compartilhar o mesmo banco entre vários PCs que leem a mesma biblioteca."""
from __future__ import annotations

import json
import sqlite3
import time
from collections import defaultdict
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS tags (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS item_tags (
    item_key TEXT NOT NULL,
    tag_id   INTEGER NOT NULL REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (item_key, tag_id)
);
CREATE INDEX IF NOT EXISTS idx_item_tags_tag ON item_tags(tag_id);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
CREATE TABLE IF NOT EXISTS additions (
    item_key      TEXT PRIMARY KEY,
    added_at      REAL NOT NULL,
    original_name TEXT
);
CREATE TABLE IF NOT EXISTS usage (
    item_key  TEXT PRIMARY KEY,
    last_used REAL NOT NULL,
    uses      INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS tag_groups_list (
    name TEXT PRIMARY KEY COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS tag_group_of (
    tag TEXT PRIMARY KEY COLLATE NOCASE,
    grp TEXT NOT NULL COLLATE NOCASE
);
CREATE TABLE IF NOT EXISTS tag_covers (
    tag      TEXT NOT NULL COLLATE NOCASE,
    item_key TEXT NOT NULL,
    pos      REAL NOT NULL,
    PRIMARY KEY (tag, item_key)
);
CREATE TABLE IF NOT EXISTS item_flags (
    item_key TEXT NOT NULL,
    flag     TEXT NOT NULL,
    PRIMARY KEY (item_key, flag)
);
"""


def clean_tag(t: str) -> str:
    return " ".join(t.strip().lower().split())


class TagDB:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.executescript(SCHEMA)
        self.conn.execute("INSERT OR IGNORE INTO meta(k, v) VALUES('schema_version', '1')")
        self.conn.commit()
        self._by_item: dict[str, set[str]] = defaultdict(set)
        self._flags: set[tuple[str, str]] = set()
        self.reload()

    def reload(self) -> None:
        self._flags = {(k, f) for k, f in self.conn.execute("SELECT item_key, flag FROM item_flags")}
        self._by_item.clear()
        for key, name in self.conn.execute(
            "SELECT it.item_key, t.name FROM item_tags it JOIN tags t ON t.id = it.tag_id"
        ):
            self._by_item[key].add(name)

    # marcações por item ----------------------------------------------------
    def has_flag(self, item_key: str, flag: str) -> bool:
        return (item_key, flag) in self._flags

    def set_flag(self, item_key: str | None, flag: str) -> None:
        if not item_key:
            return
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO item_flags(item_key, flag) VALUES(?, ?)", (item_key, flag))
        self._flags.add((item_key, flag))

    # novidades (itens que entraram pela aba Entrada) ---------------------
    def add_addition(self, item_key: str, original_name: str) -> None:
        with self.conn:
            self.conn.execute("INSERT OR REPLACE INTO additions(item_key, added_at, original_name) VALUES(?, ?, ?)",
                              (item_key, time.time(), original_name))

    def recent_additions(self, limit: int = 30) -> list[tuple[str, float, str]]:
        return self.conn.execute("SELECT item_key, added_at, original_name FROM additions "
                                 "ORDER BY added_at DESC LIMIT ?", (limit,)).fetchall()

    # uso (arrastado para o 3ds Max) ---------------------------------------
    def record_use(self, item_key: str) -> None:
        with self.conn:
            self.conn.execute("INSERT INTO usage(item_key, last_used, uses) VALUES(?, ?, 1) "
                              "ON CONFLICT(item_key) DO UPDATE SET last_used = excluded.last_used, uses = uses + 1",
                              (item_key, time.time()))

    def recent_uses(self, limit: int = 30) -> list[tuple[str, float, int]]:
        return self.conn.execute("SELECT item_key, last_used, uses FROM usage ORDER BY last_used DESC LIMIT ?",
                                 (limit,)).fetchall()

    def move_item_data(self, old_key: str, new_key: str) -> None:
        """Leva tags e marcações de um item para outro nome (ex.: ao substituir um duplicado)."""
        with self.conn:
            self.conn.execute("UPDATE OR IGNORE item_tags SET item_key = ? WHERE item_key = ?", (new_key, old_key))
            self.conn.execute("UPDATE OR IGNORE item_flags SET item_key = ? WHERE item_key = ?", (new_key, old_key))
            self.conn.execute("UPDATE OR IGNORE tag_covers SET item_key = ? WHERE item_key = ?", (new_key, old_key))
        self.reload()

    # leitura ---------------------------------------------------------------
    def tags_of(self, item_key: str) -> set[str]:
        return self._by_item.get(item_key, set())

    def all_tags(self) -> list[tuple[str, int]]:
        rows = self.conn.execute(
            "SELECT t.name, COUNT(it.item_key) FROM tags t LEFT JOIN item_tags it ON it.tag_id = t.id "
            "GROUP BY t.id HAVING COUNT(it.item_key) > 0 ORDER BY t.name"
        ).fetchall()
        return [(r[0], r[1]) for r in rows]

    # escrita ---------------------------------------------------------------
    def _tag_id(self, name: str) -> int:
        self.conn.execute("INSERT OR IGNORE INTO tags(name) VALUES(?)", (name,))
        return self.conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()[0]

    def add_tags(self, item_keys: list[str], tags: list[str]) -> None:
        tags = [clean_tag(t) for t in tags if clean_tag(t)]
        with self.conn:
            for t in tags:
                tid = self._tag_id(t)
                for k in item_keys:
                    self.conn.execute("INSERT OR IGNORE INTO item_tags(item_key, tag_id) VALUES(?, ?)", (k, tid))
                    self._by_item[k].add(t)

    def remove_tag(self, item_keys: list[str], tag: str) -> None:
        tag = clean_tag(tag)
        row = self.conn.execute("SELECT id FROM tags WHERE name = ?", (tag,)).fetchone()
        if not row:
            return
        with self.conn:
            for k in item_keys:
                self.conn.execute("DELETE FROM item_tags WHERE item_key = ? AND tag_id = ?", (k, row[0]))
                self._by_item.get(k, set()).discard(tag)
            self.conn.execute("DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM item_tags)")

    # gestão de tags (aba Tags) ------------------------------------------------
    def items_with(self, tag: str) -> list[str]:
        tag = clean_tag(tag)
        return [k for k, ts in self._by_item.items() if tag in ts]

    def rename_tag(self, old: str, new: str) -> None:
        """Renomeia; se já existir uma tag com o novo nome, junta as duas."""
        old, new = clean_tag(old), clean_tag(new)
        if not new or old == new:
            return
        if self.conn.execute("SELECT 1 FROM tags WHERE name = ?", (new,)).fetchone() and old.lower() != new.lower():
            self.merge_tags(old, new)
            return
        with self.conn:
            self.conn.execute("UPDATE tags SET name = ? WHERE name = ?", (new, old))
            self.conn.execute("UPDATE OR REPLACE tag_group_of SET tag = ? WHERE tag = ?", (new, old))
            self.conn.execute("UPDATE OR IGNORE tag_covers SET tag = ? WHERE tag = ?", (new, old))
            self.conn.execute("DELETE FROM tag_covers WHERE tag = ?", (old,))
        self.reload()

    def merge_tags(self, src: str, dst: str) -> None:
        """Todos os itens de 'src' passam a ter 'dst'; 'src' deixa de existir."""
        src, dst = clean_tag(src), clean_tag(dst)
        if not src or not dst or src == dst:
            return
        keys = self.items_with(src)
        self.add_tags(keys, [dst])
        with self.conn:
            if not self.conn.execute("SELECT 1 FROM tag_group_of WHERE tag = ?", (dst,)).fetchone():
                self.conn.execute("UPDATE OR IGNORE tag_group_of SET tag = ? WHERE tag = ?", (dst, src))
            self.conn.execute("DELETE FROM tag_group_of WHERE tag = ?", (src,))
            self.conn.execute("DELETE FROM tag_covers WHERE tag = ?", (src,))
        self.delete_tag(src)

    def delete_tag(self, tag: str) -> None:
        tag = clean_tag(tag)
        with self.conn:
            self.conn.execute("DELETE FROM tags WHERE name = ?", (tag,))
            self.conn.execute("DELETE FROM item_tags WHERE tag_id NOT IN (SELECT id FROM tags)")
            self.conn.execute("DELETE FROM tag_group_of WHERE tag = ?", (tag,))
            self.conn.execute("DELETE FROM tag_covers WHERE tag = ?", (tag,))
        self.reload()

    # grupos (pastas que juntam tags; um nível só)
    def groups(self) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT name FROM tag_groups_list ORDER BY name COLLATE NOCASE")]

    def group_map(self) -> dict[str, str]:
        return {t: g for t, g in self.conn.execute("SELECT tag, grp FROM tag_group_of")}

    def create_group(self, name: str) -> str:
        name = " ".join(name.split())
        if name:
            with self.conn:
                self.conn.execute("INSERT OR IGNORE INTO tag_groups_list(name) VALUES(?)", (name,))
        return name

    def rename_group(self, old: str, new: str) -> None:
        new = " ".join(new.split())
        if not new or new == old:
            return
        with self.conn:
            self.conn.execute("INSERT OR IGNORE INTO tag_groups_list(name) VALUES(?)", (new,))
            self.conn.execute("UPDATE tag_group_of SET grp = ? WHERE grp = ?", (new, old))
            if old.lower() != new.lower():
                self.conn.execute("DELETE FROM tag_groups_list WHERE name = ?", (old,))
            else:
                self.conn.execute("UPDATE tag_groups_list SET name = ? WHERE name = ?", (new, old))

    def delete_group(self, name: str) -> None:
        """Desfaz o grupo; as tags voltam para o nível principal (nenhuma tag é apagada)."""
        with self.conn:
            self.conn.execute("DELETE FROM tag_group_of WHERE grp = ?", (name,))
            self.conn.execute("DELETE FROM tag_groups_list WHERE name = ?", (name,))

    def set_group(self, tags: list[str], group: str | None) -> None:
        with self.conn:
            for t in tags:
                t = clean_tag(t)
                if group:
                    self.conn.execute("INSERT OR IGNORE INTO tag_groups_list(name) VALUES(?)", (group,))
                    self.conn.execute("INSERT OR REPLACE INTO tag_group_of(tag, grp) VALUES(?, ?)", (t, group))
                else:
                    self.conn.execute("DELETE FROM tag_group_of WHERE tag = ?", (t,))

    # capas escolhidas (até 4 por tag; sem escolha = automático)
    def covers(self, tag: str) -> list[str]:
        return [r[0] for r in self.conn.execute("SELECT item_key FROM tag_covers WHERE tag = ? ORDER BY pos",
                                                (clean_tag(tag),))]

    def add_cover(self, tag: str, item_key: str) -> None:
        tag = clean_tag(tag)
        cur = self.covers(tag)
        if item_key in cur:
            return
        with self.conn:
            if len(cur) >= 4:
                self.conn.execute("DELETE FROM tag_covers WHERE tag = ? AND item_key = ?", (tag, cur[0]))
            self.conn.execute("INSERT INTO tag_covers(tag, item_key, pos) VALUES(?, ?, ?)", (tag, item_key, time.time()))

    def remove_cover(self, tag: str, item_key: str | None = None) -> None:
        with self.conn:
            if item_key is None:
                self.conn.execute("DELETE FROM tag_covers WHERE tag = ?", (clean_tag(tag),))
            else:
                self.conn.execute("DELETE FROM tag_covers WHERE tag = ? AND item_key = ?", (clean_tag(tag), item_key))

    # backup ----------------------------------------------------------------
    def export_json(self, path: Path) -> int:
        data = {k: sorted(v) for k, v in sorted(self._by_item.items()) if v}
        capas: dict[str, list[str]] = {}
        for t, k in self.conn.execute("SELECT tag, item_key FROM tag_covers ORDER BY pos"):
            capas.setdefault(t, []).append(k)
        out = {"versao": 2, "tags": data, "grupos": self.groups(), "grupo_da_tag": self.group_map(), "capas": capas}
        Path(path).write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
        return len(data)

    def import_json(self, path: Path) -> int:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        items = data.get("tags", data)
        n = 0
        for key, tags in items.items():
            if isinstance(tags, list) and tags:
                self.add_tags([key], tags)
                n += 1
        if isinstance(data, dict):
            for g in data.get("grupos", []) or []:
                self.create_group(g)
            for t, g in (data.get("grupo_da_tag") or {}).items():
                self.set_group([t], g)
            for t, keys in (data.get("capas") or {}).items():
                for k in keys:
                    self.add_cover(t, k)
        return n
