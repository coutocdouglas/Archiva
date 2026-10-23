"""Liga o Archiva à pasta compartilhada da biblioteca: tags de todos, travas, histórico e desfazer."""
from __future__ import annotations

import os
import shutil
import time

from PySide6.QtCore import QObject, QTimer, Signal

from . import rede, segundo_plano
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
    "absorver": "Absorveu categoria:",
    "comparar": "Pasta × compactado:",
    "separar": "Separou o compactado repetido:",
    "excluir": "Excluiu",
    "previa": "Trocou a",
    "repetido": "Tirou o repetido",
    "desfazer": "Desfez:",
}


class Compartilhado(QObject):
    tags_changed = Signal()           # chegaram tags/novidades de outras pessoas
    items_changed = Signal(list)      # outras pessoas mexeram nestas categorias (chave da categoria de cima)
    locks_changed = Signal()
    ready = Signal()                  # tags da biblioteca montadas (depois de bind)

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
        self._lock_timer.timeout.connect(lambda: self.poll_locks(wait=False))
        self._beat_timer = QTimer(self, interval=30_000)
        self._beat_timer.timeout.connect(self._heartbeat)
        self.error = ""
        self._syncing = False
        self._polling = False
        self._rebuilding = False

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
        self.db.sink = self._sink
        if self.db.meta_get("lib_id") != lib.id:
            # 1ª vez neste computador: monta as tags num ajudante (a janela abre e as tags aparecem em seguida)
            self._rebuild_async(lib, first=True)
        else:
            self.sync(wait=True)
            QTimer.singleShot(0, lambda: self.lib is lib and self.ready.emit())
        try:
            from . import perfil
            lib.publish_profile(profile, perfil.avatar_png_bytes(profile))
        except OSError:
            pass
        self.poll_locks(wait=True)
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

    def sync(self, wait: bool = False) -> None:
        """Lê os registros novos da equipe. A leitura dos arquivos roda num ajudante; o banco é atualizado
        na janela quando ela termina (wait=True: tudo agora, usado ao abrir a biblioteca)."""
        if not self.lib or self._syncing:
            return
        lib = self.lib
        snap = dict(self.db.meta_get("offsets", {}) or {})

        def work():
            info = rede._read_json(os.path.join(lib.root, "biblioteca.json"))
            offsets = dict(snap)
            new = lib.read_new(offsets)
            return info, offsets, new, None

        def done(res):
            self._syncing = False
            if self.lib is lib:
                self._apply_sync(lib, snap, *res)

        def failed(_e):
            self._syncing = False

        if wait:
            try:
                done(work())
            except OSError:
                pass
            return
        self._syncing = True
        segundo_plano.run_async(work, done, failed)

    def _rebuild_async(self, lib, first: bool = False) -> None:
        """Remonta as tags do zero num arquivo separado (num ajudante) e troca na janela quando termina.

        O que chegar, ou o que eu gravar, enquanto monta é lido pelo sync() logo depois da troca."""
        if self._rebuilding:
            return
        import uuid
        from .database import TagDB
        self._rebuilding = True
        self._syncing = True
        tmp = data_dir() / "bibliotecas" / f"{lib.id}.montando-{uuid.uuid4().hex[:6]}.db"

        def cleanup():
            for suf in ("", "-wal", "-shm", "-journal"):
                try:
                    os.remove(str(tmp) + suf)
                except OSError:
                    pass

        def work():
            offsets: dict[str, int] = {}
            events = lib.all_events(offsets)
            TagDB.build_file(tmp, events)
            last = list(ev_key(events[-1])) if events else [0, "", 0]
            return offsets, last, any(e.get("k") == "db" for e in events)

        def done(res):
            self._rebuilding = False
            self._syncing = False
            try:
                if self.lib is not lib:
                    return
                offsets, last, has_db = res
                self.db.replace_shared(tmp)
                self.db.meta_set("offsets", offsets)
                self.db.meta_set("last_key", last)
                if first:
                    self.db.meta_set("lib_id", lib.id)
                    old = data_dir() / "biblioteca.db"
                    if old.exists() and _old_has_data(old):
                        if not has_db:
                            self.db.seed_from(old)          # biblioteca nova: leva as tags que já existiam
                        else:
                            self.offer_old_tags = True      # já tem tags de outras pessoas: pergunta antes
                self.tags_changed.emit()
                if first:
                    self.ready.emit()
            finally:
                cleanup()
            self.sync()

        def failed(_e):
            self._rebuilding = False
            self._syncing = False
            cleanup()
            if self.lib is lib:                  # sem ajudante: monta aqui mesmo (como antes)
                offsets: dict[str, int] = {}
                try:
                    events = lib.all_events(offsets)
                except OSError:
                    return
                self.db.rebuild(events)
                self.db.meta_set("offsets", offsets)
                self.db.meta_set("last_key", list(ev_key(events[-1])) if events else [0, "", 0])
                if first:
                    self.db.meta_set("lib_id", lib.id)
                    self.ready.emit()
                self.tags_changed.emit()

        segundo_plano.run_async(work, done, failed)

    def _apply_sync(self, lib, snap: dict, info, offsets: dict, new: list, everything) -> None:
        if isinstance(info, dict) and info.get("id") == lib.id:
            lib.info = info
        cur = self.db.meta_get("offsets", {}) or {}
        own = os.path.basename(lib.own_file)
        if cur.get(own, 0) != snap.get(own, 0):
            # gravei eventos enquanto o ajudante lia: os meus já estão no banco
            new = [e for e in new if e.get("u") != lib.uid]
            offsets[own] = cur.get(own, 0)
        if not new:
            if offsets != cur:
                self.db.meta_set("offsets", offsets)
            return
        self.db.meta_set("offsets", offsets)
        dbev = sorted((e for e in new if e.get("k") == "db"), key=ev_key)
        if dbev:
            last = tuple(self.db.meta_get("last_key") or (0, "", 0))
            if ev_key(dbev[0]) < last:
                # evento mais antigo que o último aplicado: remonta tudo na ordem certa (num ajudante)
                self._rebuild_async(lib)
                cats = sorted({e.get("cat", "").split("/")[0] for e in new
                               if e.get("k") in ("op", "undo") and e.get("u") != lib.uid and e.get("cat")})
                if cats:
                    self.items_changed.emit(cats)
                return
            else:
                self.db.apply_events(dbev)
            self.db.meta_set("last_key", list(max(last, ev_key(dbev[-1]))))
            self.tags_changed.emit()
        cats = sorted({e.get("cat", "").split("/")[0] for e in new
                       if e.get("k") in ("op", "undo") and e.get("u") != lib.uid and e.get("cat")})
        if cats:
            self.items_changed.emit(cats)

    def _heartbeat(self) -> None:
        if self.lib:
            lib, paths = self.lib, self.lib.held_files()
            segundo_plano.run_async(lambda: lib.heartbeat(paths))

    # ------------------------------------------------------------------ travas
    def poll_locks(self, wait: bool = True) -> None:
        """Confere as travas dos outros. Pelo relógio (wait=False) roda num ajudante."""
        if not self.lib:
            return
        lib, held = self.lib, self.lib.held_files()
        if wait:
            self._apply_locks(lib, lib.locks(held))
            return
        if self._polling:
            return
        self._polling = True

        def done(cur):
            self._polling = False
            if self.lib is lib:
                self._apply_locks(lib, cur)

        def failed(_e):
            self._polling = False

        segundo_plano.run_async(lambda: lib.locks(held), done, failed)

    def _apply_locks(self, lib, cur: dict) -> None:
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
        state: dict[str, bool] = {}     # simula o desfazer passo a passo (um mesmo caminho pode aparecer duas vezes)

        def there(p):
            k = os.path.normcase(p)
            return state[k] if k in state else os.path.exists(p)
        for a, b in reversed(ev.get("moves", [])):
            pa, pb = absolute(root, a), absolute(root, b)
            if not there(pb):
                return False, "os arquivos já foram mexidos depois (ou o backup já foi apagado)"
            if there(pa):
                return False, f"já existe '{os.path.basename(a)}' no lugar original"
            state[os.path.normcase(pb)] = False
            state[os.path.normcase(pa)] = True
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
