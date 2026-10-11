"""Aviso de atualização pelo GitHub.

Ao abrir, consulta (em segundo plano) a última versão publicada em
https://github.com/coutocdouglas/Archiva/releases. Se for mais nova que a instalada, o programa
mostra um aviso discreto. "Atualizar" baixa o instalador e o executa sem perguntas; o instalador
fecha o Archiva, troca os arquivos e abre a versão nova. Configurações, tags e a biblioteca não
são tocadas.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import tempfile
import urllib.request

from PySide6.QtCore import QThread, Signal

REPO = "coutocdouglas/Archiva"
API = f"https://api.github.com/repos/{REPO}/releases/latest"
PAGE = f"https://github.com/{REPO}/releases/latest"
UA = {"User-Agent": "Archiva-atualizador", "Accept": "application/vnd.github+json"}


def parse_version(v: str) -> tuple:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:4]) or (0,)


def is_newer(remote: str, local: str) -> bool:
    return parse_version(remote) > parse_version(local)


def _open(url: str, headers: dict, timeout: float = 15):
    req = urllib.request.Request(url, headers=headers)
    ctx = ssl.create_default_context()
    return urllib.request.urlopen(req, timeout=timeout, context=ctx)


class CheckThread(QThread):
    """Emite found(versão, url_do_instalador, notas) quando há versão nova."""
    found = Signal(str, str, str)
    uptodate = Signal(str)
    failed = Signal(str)

    def __init__(self, current: str, token: str = ""):
        super().__init__()
        self.current, self.token = current, token

    def run(self):
        try:
            h = dict(UA)
            if self.token:
                h["Authorization"] = f"Bearer {self.token}"
            with _open(API, h) as r:
                data = json.loads(r.read().decode("utf-8"))
            tag = data.get("tag_name", "")
            exe = next((a for a in data.get("assets", []) if a.get("name", "").lower().endswith(".exe")), None)
            if not is_newer(tag, self.current) or not exe:
                self.uptodate.emit(tag.lstrip("vV"))
                return
            url = exe.get("url") if self.token else exe.get("browser_download_url")
            notes = (data.get("body") or "").strip()
            self.found.emit(tag.lstrip("vV"), url or "", notes[:800])
        except Exception as e:  # noqa: BLE001 — sem internet, GitHub fora etc.: só não avisa
            self.failed.emit(str(e))


class DownloadThread(QThread):
    progress = Signal(int, int)
    done = Signal(str)
    failed = Signal(str)

    def __init__(self, url: str, version: str, token: str = ""):
        super().__init__()
        self.url, self.version, self.token = url, version, token

    def run(self):
        try:
            h = {"User-Agent": UA["User-Agent"], "Accept": "application/octet-stream"}
            if self.token:
                h["Authorization"] = f"Bearer {self.token}"
            dest = os.path.join(tempfile.gettempdir(), f"Archiva-Setup-{self.version}.exe")
            with _open(self.url, h, timeout=60) as r, open(dest + ".part", "wb") as f:
                total = int(r.headers.get("Content-Length") or 0)
                got = 0
                while True:
                    chunk = r.read(256 * 1024)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    self.progress.emit(got, total)
            os.replace(dest + ".part", dest)
            self.done.emit(dest)
        except Exception as e:  # noqa: BLE001
            self.failed.emit(str(e))


def run_installer(path: str) -> bool:
    """Executa o instalador em modo silencioso; ele fecha o Archiva e reabre a versão nova."""
    if sys.platform != "win32":
        return False
    import subprocess
    flags = 0x00000008 | 0x00000200          # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    subprocess.Popen([path, "/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS",
                      "/RESTARTAPPLICATIONS"], creationflags=flags, close_fds=True)
    return True
