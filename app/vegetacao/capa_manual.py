"""Capa escolhida à mão (botão direito › "Escolher capa…"), para uma coleção ou um volume.

A pessoa aponta um PDF (vale a 1ª página) ou uma imagem (jpg, png…). A capa é gravada como jpg onde o leitor já
procura:
  * volume:   <coleção>\\<nome da pasta do volume>.jpg   (o mesmo lugar da capa automática)
  * coleção:  <coleção>\\_capa.jpg                       (antes: a capa do primeiro volume que tem uma)

A capa que já existia não é apagada: vai para <coleção>\\_DESCARTADOS\\<volume ou _capa da coleção>\\, com a data
no nome. Outras capas do mesmo volume com outra extensão (.jpeg/.png, que o leitor também lê) vão junto, para a
nova valer. Sem Qt, exceto para converter imagens que não são jpg (QImage)."""
from __future__ import annotations

import os
import shutil
import time

from . import organizar

CAPA_COLECAO = "_capa.jpg"
EXT_ACEITAS = (".pdf", ".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tif", ".tiff")
_EXT_LIDAS = (".jpg", ".jpeg", ".png")          # as que o leitor procura ao lado da pasta do volume


def destino_volume(col_path: str, vol_nome: str) -> str:
    return os.path.join(col_path, vol_nome + ".jpg")


def destino_colecao(col_path: str) -> str:
    return os.path.join(col_path, CAPA_COLECAO)


def _jpg_de(origem: str) -> bytes:
    """Os bytes da capa em jpg: 1ª página do PDF, o próprio jpg, ou a imagem convertida."""
    ext = os.path.splitext(origem)[1].lower()
    if ext == ".pdf":
        jpg = organizar.capa_pdf(origem)
        if not jpg:
            raise ValueError("não foi possível tirar uma imagem da 1ª página deste PDF")
        return jpg
    if ext in (".jpg", ".jpeg"):
        with open(origem, "rb") as f:
            data = f.read()
        if data[:2] != b"\xff\xd8":
            raise ValueError("o arquivo não é uma imagem jpg")
        return data
    if ext not in EXT_ACEITAS:
        raise ValueError("escolha um PDF ou uma imagem (jpg, png…)")
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QImage
    img = QImage(origem)
    if img.isNull():
        raise ValueError("não foi possível abrir esta imagem")
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.WriteOnly)
    img.save(buf, "JPG", 92)
    buf.close()
    return bytes(ba.data())


def _descartar_antiga(path: str, col_path: str, pasta: str) -> str | None:
    if not os.path.isfile(path):
        return None
    stem, ext = os.path.splitext(os.path.basename(path))
    dest_dir = os.path.join(col_path, organizar.DESCARTE, pasta)
    os.makedirs(dest_dir, exist_ok=True)
    dest = os.path.join(dest_dir, f"{stem} (capa anterior {time.strftime('%Y-%m-%d %H%M%S')}){ext}")
    n = 2
    while os.path.exists(dest):
        dest = os.path.join(dest_dir, f"{stem} (capa anterior {time.strftime('%Y-%m-%d %H%M%S')} {n}){ext}")
        n += 1
    shutil.move(path, dest)
    return dest


def aplicar(origem: str, col_path: str, vol_nome: str | None = None) -> tuple[str, list[str]]:
    """Grava a capa (volume quando vol_nome, senão a da coleção). Devolve (capa gravada, capas antigas
    descartadas). Lança ValueError com o motivo se a origem não serve."""
    if not os.path.isfile(origem):
        raise ValueError("arquivo não encontrado")
    jpg = _jpg_de(origem)
    if vol_nome:
        dest = destino_volume(col_path, vol_nome)
        antigas = [os.path.join(col_path, vol_nome + e) for e in _EXT_LIDAS]
        pasta = vol_nome
    else:
        dest = destino_colecao(col_path)
        antigas = [dest]
        pasta = "_capa da coleção"
    if any(os.path.normcase(os.path.abspath(origem)) == os.path.normcase(os.path.abspath(a)) for a in antigas):
        # escolheu a própria capa atual: nada a descartar, só garante que é ela que vale
        return dest if os.path.isfile(dest) else origem, []
    tmp = dest + ".tmp"
    with open(tmp, "wb") as f:
        f.write(jpg)
    descartadas = [d for d in (_descartar_antiga(a, col_path, pasta) for a in antigas) if d]
    os.replace(tmp, dest)
    return dest, descartadas


def capa_colecao(col_path: str) -> str | None:
    p = destino_colecao(col_path)
    return p if os.path.isfile(p) else None


def sugestao_pasta(col, vol=None) -> str:
    """Onde o seletor de arquivo abre: a pasta do PDF do volume, senão a pasta do volume/coleção."""
    if vol is not None:
        if vol.pdf:
            return os.path.dirname(vol.pdf)
        return vol.path
    return col.path

