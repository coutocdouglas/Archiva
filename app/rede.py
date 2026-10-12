"""Dados compartilhados da biblioteca (pasta oculta _ARCHIVA dentro dela).

Funciona igual com a biblioteca no próprio disco ou num servidor:

    _ARCHIVA\\biblioteca.json        identificação da biblioteca e quem é administrador
    _ARCHIVA\\usuarios\\<id>.json     perfil de cada pessoa (nome, cor, computador) + <id>.png (foto)
    _ARCHIVA\\eventos\\<id>.jsonl     registro de cada pessoa: tags e operações, uma linha por evento
    _ARCHIVA\\travas\\*.lock          item ou categoria sendo alterado agora

Cada pessoa só escreve no PRÓPRIO arquivo de registro. Assim duas pessoas nunca gravam no mesmo
arquivo ao mesmo tempo, o que numa pasta de rede do Windows é o que corrompe dados.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import uuid

DIR = "_ARCHIVA"
LOCK_STALE = 150          # s sem batimento -> trava abandonada (programa fechou no meio)


def _hide(path: str) -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.kernel32.SetFileAttributesW(str(path), 0x2)     # FILE_ATTRIBUTE_HIDDEN
        except Exception:  # noqa: BLE001
            pass


def _read_json(path: str, default=None):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return default


def _write_json(path: str, data) -> None:
    tmp = f"{path}.{uuid.uuid4().hex[:6]}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def ev_key(e: dict) -> tuple:
    """Ordem global dos eventos (hora, pessoa, sequência)."""
    return (float(e.get("t", 0)), str(e.get("u", "")), int(e.get("s", 0)))


def rel(library_root: str, path: str) -> str:
    """Caminho relativo à biblioteca, com '/' (igual em qualquer computador / letra de disco)."""
    return os.path.relpath(path, library_root).replace("\\", "/")


def absolute(library_root: str, relpath: str) -> str:
    return os.path.normpath(os.path.join(library_root, relpath.replace("/", os.sep)))


class Biblioteca:
    def __init__(self, library_root: str, profile: dict):
        self.library_root = library_root
        self.profile = profile
        self.uid = profile["id"]
        self.root = os.path.join(library_root, DIR)
        new = not os.path.isdir(self.root)
        for d in ("eventos", "usuarios", "travas"):
            os.makedirs(os.path.join(self.root, d), exist_ok=True)
        if new:
            _hide(self.root)
        info_path = os.path.join(self.root, "biblioteca.json")
        self.info = _read_json(info_path)
        if not isinstance(self.info, dict) or not self.info.get("id"):
            self.info = {"id": uuid.uuid4().hex, "criada_em": time.time(), "admins": [self.uid]}
            _write_json(info_path, self.info)
        if not self.info.get("admins"):
            self.info["admins"] = [self.uid]
            _write_json(info_path, self.info)
        self.id = self.info["id"]
        self.skew = self.measure_skew()        # relógio do servidor - relógio deste computador (s)
        self.own_file = os.path.join(self.root, "eventos", f"{self.uid}.jsonl")
        self._seq = self._last_seq()
        self._held: dict[str, str] = {}          # chave -> arquivo da trava que eu tenho
        self._users_cache: dict[str, tuple[float, dict]] = {}

    # ------------------------------------------------------------------ relógio
    def measure_skew(self) -> float:
        """Diferença entre o relógio do servidor (data gravada no arquivo) e o deste computador.

        Travas e a ordem das tags usam a hora; com o relógio de um computador errado, uma trava poderia
        "vencer" antes da hora. Por isso o Archiva usa sempre a hora do servidor (now()).
        """
        probe = os.path.join(self.root, f"relogio_{self.uid}.tmp")
        try:
            t0 = time.time()
            with open(probe, "w") as f:
                f.write("x")
            t1 = time.time()
            mt = os.path.getmtime(probe)
            os.remove(probe)
        except OSError:
            return 0.0
        d = mt - (t0 + t1) / 2
        return 0.0 if abs(d) < 2 else d

    def now(self) -> float:
        return time.time() + self.skew

    # ------------------------------------------------------------------ opções da biblioteca
    def option(self, key: str, default=None):
        return self.info.get(key, default)

    def set_option(self, key: str, value) -> None:
        self.reload_info()
        self.info[key] = value
        _write_json(os.path.join(self.root, "biblioteca.json"), self.info)

    # ------------------------------------------------------------------ administradores
    def reload_info(self) -> None:
        d = _read_json(os.path.join(self.root, "biblioteca.json"))
        if isinstance(d, dict) and d.get("id") == self.id:
            self.info = d

    def is_admin(self, uid: str | None = None) -> bool:
        return (uid or self.uid) in (self.info.get("admins") or [])

    def set_admin(self, uid: str, on: bool) -> None:
        self.reload_info()
        admins = [a for a in (self.info.get("admins") or []) if a != uid]
        if on:
            admins.append(uid)
        if not admins:           # sempre fica ao menos um administrador
            return
        self.info["admins"] = admins
        _write_json(os.path.join(self.root, "biblioteca.json"), self.info)

    # ------------------------------------------------------------------ pessoas
    def publish_profile(self, profile: dict, avatar_png: bytes | None) -> None:
        self.profile = profile
        d = {k: profile.get(k) for k in ("id", "nome", "cor", "pc", "foto")}
        d["visto_em"] = time.time()
        _write_json(os.path.join(self.root, "usuarios", f"{self.uid}.json"), d)
        png = os.path.join(self.root, "usuarios", f"{self.uid}.png")
        try:
            if avatar_png:
                with open(png, "wb") as f:
                    f.write(avatar_png)
            elif os.path.exists(png):
                os.remove(png)
        except OSError:
            pass

    def users(self) -> dict[str, dict]:
        out = {}
        folder = os.path.join(self.root, "usuarios")
        try:
            entries = list(os.scandir(folder))
        except OSError:
            return out
        for e in entries:
            if not e.name.endswith(".json"):
                continue
            uid = e.name[:-5]
            try:
                mt = e.stat().st_mtime
            except OSError:
                continue
            c = self._users_cache.get(uid)
            if not c or c[0] != mt:
                d = _read_json(e.path, {})
                if isinstance(d, dict):
                    self._users_cache[uid] = (mt, d)
            if uid in self._users_cache:
                out[uid] = dict(self._users_cache[uid][1])
                png = os.path.join(folder, f"{uid}.png")
                out[uid]["foto_arquivo"] = png if os.path.exists(png) else None
                out[uid]["admin"] = self.is_admin(uid)
        return out

    # ------------------------------------------------------------------ registros
    def _last_seq(self) -> int:
        n = 0
        try:
            with open(self.own_file, "rb") as f:
                for line in f:
                    if line.strip():
                        try:
                            n = max(n, int(json.loads(line).get("s", 0)))
                        except ValueError:
                            pass
        except OSError:
            pass
        return n

    def append(self, ev: dict) -> dict:
        self._seq += 1
        ev = dict(ev)
        ev.setdefault("t", self.now())
        ev.update(u=self.uid, s=self._seq, pc=self.profile.get("pc", ""), id=f"{self.uid}.{self._seq}")
        line = json.dumps(ev, ensure_ascii=False, separators=(",", ":")) + "\n"
        with open(self.own_file, "a", encoding="utf-8", newline="\n") as f:
            f.write(line)
            f.flush()
        return ev

    def event_files(self) -> list[str]:
        folder = os.path.join(self.root, "eventos")
        try:
            return sorted(e.path for e in os.scandir(folder) if e.name.endswith(".jsonl"))
        except OSError:
            return []

    @staticmethod
    def _read_from(path: str, pos: int) -> tuple[list[dict], int]:
        """Eventos completos (até a última quebra de linha) a partir de 'pos'."""
        try:
            with open(path, "rb") as f:
                f.seek(pos)
                data = f.read()
        except OSError:
            return [], pos
        end = data.rfind(b"\n")
        if end < 0:
            return [], pos
        out = []
        for line in data[:end].splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line.decode("utf-8")))
                except (ValueError, UnicodeDecodeError):
                    pass
        return out, pos + end + 1

    def read_new(self, offsets: dict[str, int]) -> list[dict]:
        """Eventos novos de todos os arquivos; atualiza 'offsets' (nome do arquivo -> posição)."""
        out = []
        for p in self.event_files():
            name = os.path.basename(p)
            evs, offsets[name] = self._read_from(p, offsets.get(name, 0))
            out.extend(evs)
        return out

    def all_events(self, offsets: dict[str, int] | None = None) -> list[dict]:
        out = []
        for p in self.event_files():
            evs, pos = self._read_from(p, 0)
            out.extend(evs)
            if offsets is not None:
                offsets[os.path.basename(p)] = pos
        out.sort(key=ev_key)
        return out

    def own_offset(self) -> int:
        try:
            return os.path.getsize(self.own_file)
        except OSError:
            return 0

    # ------------------------------------------------------------------ travas
    def _lock_path(self, key: str) -> str:
        h = hashlib.sha1(key.casefold().encode("utf-8")).hexdigest()[:20]
        return os.path.join(self.root, "travas", f"{h}.lock")

    def acquire(self, key: str, op: str) -> tuple[bool, dict | None]:
        """Tenta travar 'key'. Devolve (True, None) ou (False, dados de quem está usando)."""
        path = self._lock_path(key)
        info = {"key": key, "u": self.uid, "nome": self.profile.get("nome", ""), "pc": self.profile.get("pc", ""),
                "op": op, "t": self.now()}
        for _ in range(2):
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                cur = _read_json(path, {}) or {}
                stale = self._stale(path)
                if cur.get("u") == self.uid and cur.get("pc") == info["pc"] and key not in self._held:
                    stale = True                       # sobrou de uma sessão minha que fechou no meio
                if cur.get("u") == self.uid and key in self._held:
                    return True, None
                if stale:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    continue
                return False, cur
            except OSError:
                return False, {"nome": "?", "op": "erro ao acessar a pasta compartilhada"}
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(info, f, ensure_ascii=False)
            self._held[key] = path
            return True, None
        return False, _read_json(path, {}) or {}

    def release(self, key: str) -> None:
        path = self._held.pop(key, None)
        if path:
            try:
                os.remove(path)
            except OSError:
                pass

    def release_all(self) -> None:
        for k in list(self._held):
            self.release(k)

    def heartbeat(self) -> None:
        for path in self._held.values():
            try:
                os.utime(path, None)
            except OSError:
                pass

    def _stale(self, path: str) -> bool:
        try:
            return self.now() - os.path.getmtime(path) > LOCK_STALE
        except OSError:
            return True

    def locks(self) -> dict[str, dict]:
        """Travas ativas de OUTRAS pessoas/sessões: chave -> dados."""
        out = {}
        folder = os.path.join(self.root, "travas")
        try:
            entries = [e for e in os.scandir(folder) if e.name.endswith(".lock")]
        except OSError:
            return out
        for e in entries:
            if e.path in self._held.values() or self._stale(e.path):
                continue
            d = _read_json(e.path, {}) or {}
            if d.get("key"):
                out[d["key"]] = d
        return out
