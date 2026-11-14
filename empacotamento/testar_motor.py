"""Teste do motor de rede pelo lado do Python (roda no GitHub, em testar-motor.yml).

Confere que app/nuvem_motor.py sobe o archiva-rede de verdade nos dois modos, lê os endereços, consulta o
estado (pedido de login do Tailscale) e que o motor termina sozinho quando o Archiva solta a entrada padrão.
Uso: ARCHIVA_MOTOR=motor/archiva-rede python empacotamento/testar_motor.py
"""
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["APPDATA"] = tempfile.mkdtemp()
from app import nuvem_motor  # noqa: E402


def esperar_login(m):
    for _ in range(40):
        e = m.estado()
        if e.get("estado") == "NeedsLogin" and (e.get("url_login") or "").startswith("https://login.tailscale.com/"):
            return e
        time.sleep(1)
    raise SystemExit(f"{m.modo}: não chegou ao pedido de login: {m.estado()}")


falhas = 0
for modo, extra in (("servir", {"destino": "127.0.0.1:9"}), ("ligar", {"alvo": "archiva-qualquer"})):
    m = nuvem_motor.Motor(modo, Path(tempfile.mkdtemp()), "archiva-teste-" + modo, **extra)
    assert m.iniciar(30), m.erro
    print(modo, "controle", m.controle, "local", m.local or "-")
    e = esperar_login(m)
    print(modo, "estado", e["estado"], nuvem_motor.texto_estado(e, modo))
    if modo == "ligar":
        try:
            urllib.request.build_opener(urllib.request.ProxyHandler({})).open(f"http://{m.local}/api/info", timeout=20)
            print("ERRO: ligar respondeu sem estar na rede"); falhas += 1
        except urllib.error.HTTPError as err:
            print("ligar sem rede ->", err.code, "(esperado 502)")
            falhas += err.code != 502
    p = m.proc
    m.parar()
    time.sleep(1)
    print(modo, "terminou ao soltar a entrada:", p.poll() is not None)
    falhas += p.poll() is None
print("FALHAS", falhas)
sys.exit(1 if falhas else 0)
