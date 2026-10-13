"""Liga o Archiva à pasta compartilhada da biblioteca: tags de todos, travas, histórico e desfazer."""
from __future__ import annotations

import os
import shutil
import time

from PySide6.QtCore import QObject, QTimer, Signal

from . import rede
from .config import data_dir
from .rede import Biblioteca, absolute, ev_key, rel

OP_NAMES = {
    "extrair": "Extraiu",
    "organizar": "Organizou",
    "classificar": "Classificou da Entrada",
    "substituir": "Substituiu pela versão nova",
    "descartar": "Descartou da Entrada",
    "limpar": "Removeu arquivos extras de",
    "mover": "Moveu",
    "renomear": "Renomeou",
    "juntar": "Juntou pastas:",
    "desfazer": "Desfez:",
}


class Compartilhado(QObject):
    tags_changed = Signal()           # chegaram tags/novidades de outras pessoas
    items_changed = Signal(list)      # outras pessoas mexeram nestas categorias (chave da categoria de cima)
    locks_changed = Signal()

    def __init__(self, db):
        super().__init__()
        self.db = db
        self.lib: Biblioteca | None = None
        self.profile: dict | None = None
        self.offer_old_tags = False
        self._locks: dict[str, dict] = {}
        self._sync_timer = QTimer(self, interval=15_000)
        self._sync_timer.timeout.connect(self.sync)
        self._lock_timer = QTimer(self, interval=8_000)
        self._lock_timer.timeout.connect(self.poll_locks)
        self._beat_timer = QTimer(self, interval=30_000)
        self._beat_timer.timeout.connect(lambda: self.lib and self.lib.heartbeat())
        self.error = ""

    # ------------------------------------------------------------------ ligar
    @property
    def active(self) -> bool:
        return self.lib is not None

    def bind(self, library_root: str, profile: dict) -> bool:
        """Abre a pasta _ARCHIVA da biblioteca e monta as tags. False = sem acesso (fica só local)."""
        self.unbind()
        self.profile = profile
        try:
            lib = Biblioteca(library_root, profile)
        except OSError as e:
            self.error = f"Sem permissão para gravar em {os.path.join(library_root, rede.DIR)} ({e})."
            self.db.open(None)
            return False
        self.lib = lib
        self.db.clock = lib.now
        folder = data_dir() / "bibliotecas"
        folder.mkdir(exist_ok=True)
        self.db.sink = None
        self.db.open(folder / f"{lib.id}.db")
        if self.db.meta_get("lib_id") != lib.id:
            offsets: dict[str, int] = {}
            events = lib.all_events(offsets)
            self.db.rebuild(events)
            self.db.meta_set("lib_id", lib.id)
            self.db.meta_set("offsets", offsets)
            self.db.meta_set("last_key", list(ev_key(events[-1])) if events else [0, "", 0])
            old = data_dir() / "biblioteca.db"
            self.db.sink = self._sink
            if old.exists() and _old_has_data(old):
                if not any(e.get("k") == "db" for e in events):
                    self.db.seed_from(old)              # biblioteca nova: leva as tags que já existiam
                else:
                    self.offer_old_tags = True          # já tem tags de outras pessoas: pergunta antes
        else:
            self.db.sink = self._sink
            self.sync()
        try:
            from . import perfil
            lib.publish_profile(profile, perfil.avatar_png_bytes(profile))
        except OSError:
            pass
        self.poll_locks()
        for t in (self._sync_timer, self._lock_timer, self._beat_timer):
            t.start()
        return True

    def unbind(self):
        for t in (self._sync_timer, self._lock_timer, self._beat_timer):
            t.stop()
        if self.lib:
            self.lib.release_all()
        self.lib = None
        self.db.sink = None
        import time as _t
        self.db.clock = _t.time
        self._locks = {}

    def import_old_tags(self) -> int:
        old = data_dir() / "biblioteca.db"
        self.offer_old_tags = False
        return self.db.seed_from(old) if old.exists() else 0

    # ------------------------------------------------------------------ registros
    def _sink(self, ev: dict) -> None:
        if not self.lib:
            return
        e = self.lib.append(ev)
        offsets = self.db.meta_get("offsets", {}) or {}
        offsets[os.path.basename(self.lib.own_file)] = self.lib.own_offset()
        self.db.meta_set("offsets", offsets)
        last = tuple(self.db.meta_get("last_key") or (0, "", 0))
        if e.get("k") == "db" and ev_key(e) > last:
            self.db.meta_set("last_key", list(ev_key(e)))

    def sync(self) -> None:
        if not self.lib:
            return
        self.lib.reload_info()
        offsets = self.db.meta_get("offsets", {}) or {}
        try:
            new = self.lib.read_new(offsets)
        except OSError:
            return
        if not new:
            return
        self.db.meta_set("offsets", offsets)
        dbev = sorted((e for e in new if e.get("k") == "db"), key=ev_key)
        if dbev:
            last = tuple(self.db.meta_get("last_key") or (0, "", 0))
            if ev_key(dbev[0]) < last:
                self.db.rebuild(self.lib.all_events())
            else:
                self.db.apply_events(dbev)
            self.db.meta_set("last_key", list(max(last, ev_key(dbev[-1]))))
            self.tags_changed.emit()
        cats = sorted({e.get("cat", "").split("/")[0] for e in new
                       if e.get("k") in ("op", "undo") and e.get("u") != self.lib.uid and e.get("cat")})
        if cats:
            self.items_changed.emit(cats)

    # ------------------------------------------------------------------ travas
    def poll_locks(self) -> None:
        if not self.lib:
            return
        cur = self.lib.locks()
        if cur != self._locks:
            self._locks = cur
            self.locks_changed.emit()

    def lock_of(self, key: str) -> dict | None:
        return self._locks.get(key)

    def acquire(self, key: str, op: str) -> tuple[bool, dict | None]:
        if not self.lib:
            return True, None
        ok, info = self.lib.acquire(key, op)
        if not ok:
            self.poll_locks()
        return ok, info

    def release(self, key: str) -> None:
        if self.lib:
            self.lib.release(key)

    # ------------------------------------------------------------------ operações
    def log_op(self, op: str, cat: str, item: str, desc: str = "", moves=(), created=(), extra: dict | None = None):
        """Registra uma alteração nos arquivos da biblioteca (com o que for preciso para desfazer)."""
        if not self.lib:
            return None
        root = self.lib.library_root
        ev = {"k": "op", "op": op, "cat": cat, "item": item, "desc": desc,
              "moves": [[rel(root, a), rel(root, b)] for a, b in moves],
              "created": [rel(root, c) for c in created]}
        if extra:
            ev.update(extra)
        try:
            return self.lib.append(ev)
        except OSError:
            return None

    def history(self, everyone: bool) -> list[dict]:
        """Operações (mais novas primeiro), já marcando as desfeitas."""
        if not self.lib:
            return []
        evs = self.lib.all_events()
        undone = {e.get("ref") for e in evs if e.get("k") == "undo"}
        ops = [dict(e, undone=e.get("id") in undone) for e in evs if e.get("k") in ("op", "undo")]
        if not everyone:
            ops = [e for e in ops if e.get("u") == self.lib.uid]
        ops.sort(key=ev_key, reverse=True)
        return ops

    def can_undo(self, ev: dict) -> tuple[bool, str]:
        if not self.lib or ev.get("k") != "op":
            return False, ""
        if ev.get("undone"):
            return False, "já desfeito"
        if ev.get("u") != self.lib.uid and not self.lib.is_admin():
            return False, "só quem fez ou o administrador"
        root = self.lib.library_root
        for a, b in ev.get("moves", []):
            if not os.path.exists(absolute(root, b)):
                return False, "os arquivos já foram mexidos depois (ou o backup já foi apagado)"
            if os.path.exists(absolute(root, a)):
                return False, f"já existe '{os.path.basename(a)}' no lugar original"
        if not ev.get("moves") and not ev.get("created"):
            return False, "nada a desfazer"
        return True, ""

    def undo(self, ev: dict) -> tuple[bool, str]:
        ok, why = self.can_undo(ev)
        if not ok:
            return False, why
        root = self.lib.library_root
        key = ev.get("item") or ev.get("cat") or ev["id"]
        got, info = self.acquire(key, "desfazendo")
        if not got:
            return False, f"em uso por {info.get('nome', '?')} agora"
        moved_back, discarded = [], []
        try:
            done = []
            try:
                for a, b in reversed(ev.get("moves", [])):
                    src, dst = absolute(root, b), absolute(root, a)
                    os.makedirs(os.path.dirname(dst), exist_ok=True)
                    _move(src, dst)
                    done.append((src, dst))
            except OSError as e:
                for src, dst in reversed(done):
                    try:
                        _move(dst, src)
                    except OSError:
                        pass
                return False, f"não consegui mover os arquivos de volta ({e}); nada foi alterado"
            moved_back = done
            # pastas criadas pela operação (ex.: a pasta da extração) vão para _DESCARTADOS
            for c in ev.get("created", []):
                p = absolute(root, c)
                if os.path.exists(p):
                    dest = _discard_path(root, os.path.basename(p))
                    os.makedirs(os.path.dirname(dest), exist_ok=True)
                    _move(p, dest)
                    discarded.append((p, dest))
            # pastas que ficaram vazias dentro do item (ex.: MAPS criada ao organizar)
            for old_key, new_key in ev.get("keys", []):     # tags e coleções voltam para o nome antigo
                try:
                    self.db.move_item_data(new_key, old_key)
                except Exception:  # noqa: BLE001
                    pass
            if ev.get("base"):
                base = absolute(root, ev["base"])
                for d in sorted({os.path.dirname(s) for s, _ in moved_back}, key=len, reverse=True):
                    _remove_empty_up(d, stop=base)
        finally:
            self.release(key)
        self.lib.append({"k": "undo", "ref": ev["id"], "op": "desfazer", "cat": ev.get("cat", ""),
                         "item": ev.get("item", ""), "desc": _lower1(f"{OP_NAMES.get(ev.get('op'), ev.get('op'))} "
                                                                    f"{ev.get('desc') or ev.get('item', '')}"),
                         "moves": [[rel(root, s), rel(root, d)] for s, d in moved_back + discarded]})
        return True, ""


def _lower1(t: str) -> str:
    return t[:1].lower() + t[1:]


def _old_has_data(path) -> bool:
    import sqlite3
    try:
        c = sqlite3.connect(str(path))
        try:
            return any(c.execute(f"SELECT 1 FROM {t} LIMIT 1").fetchone() for t in ("item_tags", "additions"))
        finally:
            c.close()
    except Exception:  # noqa: BLE001
        return False


def _move(src: str, dst: str) -> None:
    if os.path.exists(dst):
        raise OSError(f"já existe {dst}")
    try:
        os.rename(src, dst)
    except OSError:
        shutil.move(src, dst)


def _discard_path(root: str, name: str) -> str:
    from .extractor import BACKUP_DIR
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.join(root, BACKUP_DIR, "_DESCARTADOS", f"{stamp}__{name}")
    p, i = base, 2
    while os.path.exists(p):
        p, i = f"{base} ({i})", i + 1
    return p


def _remove_empty_up(d: str, stop: str) -> None:
    stop = os.path.normcase(os.path.normpath(stop))
    while d and os.path.normcase(os.path.normpath(d)).startswith(stop + os.sep) and os.path.isdir(d):
        try:
            os.rmdir(d)
        except OSError:
            return
        d = os.path.dirname(d)
