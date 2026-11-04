"""Registro de falhas do Archiva.

Quando o programa fecha sozinho, quase sempre foi uma falha interna do Qt (crash nativo): o Python não consegue
mostrar mensagem nenhuma. Este módulo deixa um arquivo de texto (``registro.log``, em %APPDATA%\\GerenciadorAssets3D)
com o que for possível saber depois:

* **falha nativa** (``faulthandler``): o Windows derruba o programa, mas antes a lista do que o Python estava
  fazendo em cada thread é escrita no arquivo;
* **erros do Python** (também os das threads) e **avisos/erros do Qt**;
* **última ação** (``marca``): por exemplo, qual modelo foi clicado. No início da sessão seguinte, se a anterior
  não terminou normalmente, o registro diz isso e qual foi a última ação;
* cabeçalho de cada sessão: versão, Windows, Python, PySide6/Qt e nome do computador.

O botão "Salvar registro…" em Configurações › Diagnóstico copia o arquivo para onde a pessoa quiser.
Nada daqui mexe na biblioteca de modelos.
"""
from __future__ import annotations

import faulthandler
import json
import os
import platform
import sys
import threading
import time
import traceback
from datetime import datetime
from pathlib import Path

from .config import data_dir, is_installed, version

MAX_BYTES = 1_000_000        # acima disto, o início do arquivo é cortado ao abrir o programa
KEEP_BYTES = 400_000         # o que fica depois do corte
MAX_AVISOS_QT = 150          # avisos do Qt por sessão (evita encher o arquivo)

_lock = threading.RLock()
_fh = None                   # arquivo aberto durante toda a sessão (o faulthandler escreve direto nele)
_ultima = ""                 # última ação marcada
_avisos = 0
_ultimo_aviso = ""
_inicio = 0.0


def caminho() -> Path:
    return data_dir() / "registro.log"


def _estado_path() -> Path:
    return data_dir() / "sessao.json"


def _agora() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def escrever(texto: str) -> None:
    """Acrescenta uma linha (ou bloco) com data e hora. Nunca levanta erro."""
    with _lock:
        try:
            if _fh is None:
                with open(caminho(), "a", encoding="utf-8") as f:
                    f.write(f"[{_agora()}] {texto}\n")
            else:
                _fh.write(f"[{_agora()}] {texto}\n")
                _fh.flush()
        except (OSError, ValueError):
            pass


def _gravar_estado(limpa: bool) -> None:
    try:
        dados = {"limpa": limpa, "versao": version(), "inicio": _inicio, "ultima": _ultima,
                 "ultima_t": _agora()}
        tmp = _estado_path().with_suffix(".tmp")
        tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, _estado_path())
    except OSError:
        pass


def marca(texto: str) -> None:
    """Anota a última ação (ex.: "selecionou POLTRONAS/POLTRONA 12"). Se o programa cair, ela aparece no registro."""
    global _ultima
    _ultima = texto
    _gravar_estado(False)


def _cortar_se_grande() -> None:
    p = caminho()
    try:
        if p.stat().st_size <= MAX_BYTES:
            return
        with open(p, "rb") as f:
            f.seek(-KEEP_BYTES, os.SEEK_END)
            resto = f.read()
        nl = resto.find(b"\n")
        if nl >= 0:
            resto = resto[nl + 1:]
        p.write_bytes(b"[... trecho antigo removido ...]\n" + resto)
    except OSError:
        pass


def _versoes_qt() -> str:
    try:
        import PySide6
        from PySide6.QtCore import qVersion
        return f"PySide6 {PySide6.__version__} / Qt {qVersion()}"
    except Exception:  # noqa: BLE001
        return "PySide6 ?"


def _qt_handler(modo, contexto, mensagem) -> None:
    global _avisos, _ultimo_aviso
    try:
        from PySide6.QtCore import QtMsgType
        if modo == QtMsgType.QtFatalMsg:
            nivel = "FATAL"
        elif modo == QtMsgType.QtCriticalMsg:
            nivel = "ERRO-QT"
        elif modo == QtMsgType.QtWarningMsg:
            nivel = "AVISO-QT"
        else:
            return
        if nivel == "AVISO-QT":
            if _avisos >= MAX_AVISOS_QT or mensagem == _ultimo_aviso:
                return
            _avisos += 1
        _ultimo_aviso = mensagem
        onde = ""
        try:
            if contexto.file:
                onde = f"  ({os.path.basename(contexto.file)}:{contexto.line})"
        except Exception:  # noqa: BLE001
            pass
        escrever(f"{nivel}: {mensagem}{onde}")
    except Exception:  # noqa: BLE001
        pass


def erro(texto: str) -> None:
    """Para quem trata a exceção por conta própria (gerenciador.pyw)."""
    escrever("ERRO DO PYTHON:\n" + texto.rstrip())


def _thread_hook(args) -> None:
    if args.exc_type is SystemExit:
        return
    texto = "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback))
    nome = args.thread.name if args.thread else "?"
    escrever(f"ERRO DO PYTHON numa thread ({nome}):\n{texto.rstrip()}")


def iniciar() -> None:
    """Liga o registro. Chamar o quanto antes em ``main()``."""
    global _fh, _inicio, _ultima
    if _fh is not None:
        return
    _inicio = time.time()
    _cortar_se_grande()
    anterior = None
    try:
        anterior = json.loads(_estado_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        _fh = open(caminho(), "a", encoding="utf-8")
    except OSError:
        _fh = None
        return
    escrever("=" * 72)
    escrever(f"Archiva {version()} iniciado ({'instalado' if is_installed() else 'pelo .bat'})")
    escrever(f"Sistema: {platform.platform()} | Python {platform.python_version()} | {_versoes_qt()} | "
             f"PC: {platform.node()}")
    if anterior and not anterior.get("limpa", True):
        ini = datetime.fromtimestamp(anterior.get("inicio", 0)).strftime("%Y-%m-%d %H:%M:%S") if anterior.get("inicio") else "?"
        escrever(f"QUEDA DETECTADA: a sessão anterior (versão {anterior.get('versao', '?')}, aberta em {ini}) "
                 f"terminou sem fechar normalmente (falha, programa encerrado à força ou PC desligado). "
                 f"Última ação anotada às {anterior.get('ultima_t', '?')}: {anterior.get('ultima') or '(nenhuma)'}")
    _ultima = ""
    _gravar_estado(False)
    try:
        faulthandler.enable(file=_fh, all_threads=True)     # falha nativa: escreve o que cada thread fazia
    except (RuntimeError, ValueError, OSError):
        pass
    threading.excepthook = _thread_hook
    try:
        from PySide6.QtCore import qInstallMessageHandler
        qInstallMessageHandler(_qt_handler)
    except Exception:  # noqa: BLE001
        pass


def fim_normal() -> None:
    """Chamado quando o programa fecha normalmente (``aboutToQuit``)."""
    escrever("Fechado normalmente.")
    _gravar_estado(True)


# ----------------------------------------------------------------------------------------------- Configurações
def quedas() -> int:
    try:
        return caminho().read_text(encoding="utf-8", errors="replace").count("QUEDA DETECTADA")
    except OSError:
        return 0


def tamanho() -> int:
    try:
        return caminho().stat().st_size
    except OSError:
        return 0


def exportar(destino: str) -> bool:
    """Copia o registro para ``destino`` (com um aviso no topo). True se deu certo."""
    with _lock:
        try:
            if _fh is not None:
                _fh.flush()
            texto = caminho().read_text(encoding="utf-8", errors="replace")
            topo = (f"Registro do Archiva {version()} salvo em {_agora()} (PC: {platform.node()})\n"
                    f"Procure por 'QUEDA DETECTADA' e por 'Windows fatal exception' / 'Fatal Python error'.\n"
                    + "-" * 72 + "\n")
            Path(destino).write_text(topo + texto, encoding="utf-8")
            return True
        except OSError:
            return False


def limpar() -> None:
    with _lock:
        try:
            if _fh is not None:
                _fh.seek(0)
                _fh.truncate()
            else:
                caminho().write_text("", encoding="utf-8")
        except (OSError, ValueError):
            pass
    escrever(f"Registro limpo. Archiva {version()}.")
