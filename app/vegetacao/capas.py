"""Capa dos volumes: quando o volume não tem imagem própria, grava a 1ª página do PDF como jpg na pasta da
coleção, com o mesmo nome da pasta do volume (F:\\COLECOES\\Maxtree\\Maxtree - Plant Models Vol 032.jpg).

O leitor procura sempre a capa nesse lugar, então depois de gravada o programa a encontra sozinho. Nunca
sobrescreve uma imagem que já existe; só cria arquivo novo na pasta da coleção (nada dentro dos volumes).

Desde a 2.0.24 a capa é só a foto da página (recorte.py). As capas antigas que o próprio Archiva gravou com a
página inteira são trocadas uma vez pela foto recortada (a antiga vai para _DESCARTADOS)."""
from __future__ import annotations

import os

from . import organizar


def garantir(cols) -> list[str]:
    """Para cada volume sem capa e com PDF, grava a capa (jpg) e preenche volume.capa. Devolve os jpg criados."""
    criadas: list[str] = []
    for c in cols:
        for v in c.volumes:
            if v.capa or not v.pdf:
                continue
            dest = os.path.join(c.path, v.nome + ".jpg")
            if os.path.exists(dest):          # já existe (imagem própria ou criada antes): nunca sobrescreve
                v.capa = dest
                continue
            try:
                jpg = organizar.capa_pdf(v.pdf)
                if not jpg:
                    continue
                tmp = dest + ".tmp"
                with open(tmp, "wb") as f:
                    f.write(jpg)
                os.replace(tmp, dest)
            except OSError:
                continue
            v.capa = dest
            criadas.append(dest)
    try:
        recortar_antigas(cols)
    except Exception:  # noqa: BLE001 — a capa antiga continua valendo
        pass
    return criadas


# --------------------------------------------------------------------- capas antigas com a página inteira (até 2.0.23)

CONFERIDAS = "vegetacao_capas_conferidas.json"     # em %APPDATA%\GerenciadorAssets3D: capas já olhadas


def _pagina_inteira(jpg: str, pdf: str) -> bool:
    """A capa é a 1ª página inteira do PDF gravada pelo Archiva antes do recorte: 1600 px de largura e a mesma
    proporção da página."""
    from PySide6.QtGui import QImageReader
    sz = QImageReader(jpg).size()
    if sz.width() != 1600:
        return False
    from PySide6.QtPdf import QPdfDocument
    doc = QPdfDocument()
    try:
        if doc.load(pdf) != QPdfDocument.Error.None_ or doc.pageCount() < 1:
            return False
        ps = doc.pagePointSize(0)
        return abs(sz.height() - int(1600 * ps.height() / max(1.0, ps.width()))) <= 1
    finally:
        doc.close()


def recortar_antigas(cols) -> list[str]:
    """Troca as capas que o Archiva tirou do PDF com a página inteira (título, logotipo, margem) pela foto
    recortada. A antiga vai para _DESCARTADOS da coleção. Cada capa é conferida uma vez só."""
    import json
    from ..config import data_dir
    from . import capa_manual
    reg = data_dir() / CONFERIDAS
    try:
        vistas = set(json.loads(reg.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        vistas = set()
    trocadas: list[str] = []
    mudou = False
    for c in cols:
        for v in c.volumes:
            if not v.capa or not v.pdf or not v.capa.lower().endswith(".jpg"):
                continue
            try:
                st = os.stat(v.capa)
            except OSError:
                continue
            chave = f"{os.path.normcase(v.capa)}|{st.st_size}|{int(st.st_mtime)}"
            if chave in vistas:
                continue
            vistas.add(chave)
            mudou = True
            if not _pagina_inteira(v.capa, v.pdf):
                continue
            jpg = organizar.capa_pdf(v.pdf)
            from PySide6.QtGui import QImage
            novo = QImage.fromData(jpg) if jpg else None
            if novo is None or novo.isNull() or novo.width() == 1600:     # nada a recortar (a página já é foto)
                continue
            tmp = v.capa + ".tmp"
            with open(tmp, "wb") as f:
                f.write(jpg)
            capa_manual._descartar_antiga(v.capa, c.path, v.nome)
            os.replace(tmp, v.capa)
            st = os.stat(v.capa)
            vistas.add(f"{os.path.normcase(v.capa)}|{st.st_size}|{int(st.st_mtime)}")
            trocadas.append(v.capa)
    if mudou:
        try:
            reg.write_text(json.dumps(sorted(vistas)), encoding="utf-8")
        except OSError:
            pass
    return trocadas
