"""Liga o motor de rede (archiva-rede.exe, Go + Tailscale embutido) e conversa com ele.

O motor é um processo à parte que vive enquanto o Archiva estiver aberto: a entrada padrão dele fica ligada ao
Archiva; quando o Archiva fecha (ou cai), a entrada fecha e o motor termina sozinho.

Nada aqui roda na thread da janela por muito tempo: `iniciar` espera só a 1ª linha do motor (endereços locais) e
`estado` faz um pedido local rápido. Quem chama da janela usa segundo_plano.run_async.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from .config import app_dir, data_dir

NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


def caminho_motor() -> Path | None:
    nome = "archiva-rede.exe" if sys.platform == "win32" else "archiva-rede"
    for p in (app_dir() / "rede" / nome, app_dir().parent / "rede" / nome,
              app_dir() / "empacotamento" / "rede" / nome, app_dir() / "motor" / nome):
        if p.exists():
            return p
    env = os.environ.get("ARCHIVA_MOTOR")
    return Path(env) if env and Path(env).exists() else None


def disponivel() -> bool:
    return caminho_motor() is not None


def pasta_estado(nome: str) -> Path:
    """Identidade deste PC na rede (uma por papel: 'servidor' ou uma por biblioteca acessada)."""
    p = data_dir() / "rede" / nome
    p.mkdir(parents=True, exist_ok=True)
    return p


def nome_maquina(prefixo: str = "archiva") -> str:
    """Nome curto e válido na rede: archiva-<computador> (minúsculas, letras, números e hífen)."""
    import re
    import socket
    pc = os.environ.get("COMPUTERNAME") or socket.gethostname() or "pc"
    pc = re.sub(r"[^a-z0-9-]+", "-", pc.lower()).strip("-")[:40] or "pc"
    return f"{prefixo}-{pc}"


class Motor:
    def __init__(self, modo: str, estado_dir: Path, nome: str, destino: str = "", alvo: str = "",
                 authkey: str = ""):
        self.modo, self.estado_dir, self.nome = modo, estado_dir, nome
        self.destino, self.alvo, self.authkey = destino, alvo, authkey
        self.proc: subprocess.Popen | None = None
        self.controle = ""
        self.local = ""
        self.erro = ""

    @property
    def vivo(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def iniciar(self, espera: float = 20.0) -> bool:
        if self.vivo:
            return True
        exe = caminho_motor()
        if exe is None:
            self.erro = "O motor de rede não está instalado (reinstale o Archiva)."
            return False
        args = [str(exe), self.modo, "--dir", str(self.estado_dir), "--nome", self.nome]
        if self.modo == "servir":
            args += ["--destino", self.destino]
        else:
            args += ["--alvo", self.alvo]
        env = dict(os.environ)
        env.pop("ARCHIVA_AUTHKEY", None)
        if self.authkey:
            env["ARCHIVA_AUTHKEY"] = self.authkey
        try:
            self.proc = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE, env=env, creationflags=NO_WINDOW)
        except OSError as e:
            self.erro = f"Não consegui abrir o motor de rede: {e}"
            return False
        linha: list[str] = []

        def ler():
            try:
                linha.append(self.proc.stdout.readline().decode("utf-8", "replace"))
            except Exception:  # noqa: BLE001
                linha.append("")
        t = threading.Thread(target=ler, daemon=True)
        t.start()
        t.join(espera)
        try:
            d = json.loads(linha[0]) if linha and linha[0].strip() else {}
        except ValueError:
            d = {}
        if not d.get("controle"):
            err = b""
            if self.proc.poll() is not None:
                try:
                    err = self.proc.stderr.read() or b""
                except Exception:  # noqa: BLE001
                    pass
            self.erro = "O motor de rede não respondeu. " + err.decode("utf-8", "replace").strip()[-300:]
            self.parar()
            return False
        self.controle, self.local = d["controle"], d.get("local", "")
        # esvazia a saída de erros num ajudante (senão o buffer enche e o motor trava)
        threading.Thread(target=lambda: self.proc.stderr.read(), daemon=True).start()
        return True

    def estado(self) -> dict:
        if not self.vivo or not self.controle:
            return {"estado": "Parado", "erro": self.erro}
        try:
            op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with op.open(f"http://{self.controle}/estado", timeout=6) as r:
                return json.loads(r.read().decode("utf-8"))
        except (OSError, ValueError) as e:
            return {"estado": "Sem resposta", "erro": str(e)}

    def sair_da_conta(self) -> bool:
        if not self.vivo:
            return False
        try:
            op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            req = urllib.request.Request(f"http://{self.controle}/sair", data=b"", method="POST")
            with op.open(req, timeout=10):
                return True
        except OSError:
            return False

    def parar(self) -> None:
        p, self.proc = self.proc, None
        if p is None:
            return
        try:
            p.stdin.close()             # o motor termina sozinho quando a entrada fecha
            p.wait(5)
        except Exception:  # noqa: BLE001
            try:
                p.kill()
            except Exception:  # noqa: BLE001
                pass


def texto_estado(e: dict, modo: str = "servir") -> tuple[str, str]:
    """(texto para a pessoa, cor: ok | aviso | erro)."""
    s = e.get("estado", "")
    if s == "Running":
        if modo == "ligar" and e.get("alvo_ok") is False:
            return "Conectado à rede, mas o computador da biblioteca está desligado ou com o Archiva fechado.", "aviso"
        rede = e.get("rede") or ""
        return ("Conectado" + (f" · rede {rede}" if rede else "")), "ok"
    if s == "NeedsLogin":
        return "Falta entrar na conta (uma vez só neste computador).", "aviso"
    if s in ("Starting", "NoState", ""):
        return "Conectando…", "aviso"
    if s == "NeedsMachineAuth":
        return "Este computador precisa ser aprovado no painel do Tailscale.", "aviso"
    return (e.get("erro") or s or "Desligado"), "erro"
