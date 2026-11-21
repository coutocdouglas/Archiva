"""Capa dos volumes: quando o volume não tem imagem própria, grava a 1ª página do PDF como jpg na pasta da
coleção, com o mesmo nome da pasta do volume (F:\\COLECOES\\Maxtree\\Maxtree - Plant Models Vol 032.jpg).

O leitor procura sempre a capa nesse lugar, então depois de gravada o programa a encontra sozinho. Nunca
sobrescreve uma imagem que já existe; só cria arquivo novo na pasta da coleção (nada dentro dos volumes)."""
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
    return criadas
