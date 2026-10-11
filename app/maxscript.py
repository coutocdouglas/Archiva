"""Gera um pequeno MaxScript que faz o MERGE do modelo já apontando as pastas de
texturas (MAPS) para o 3ds Max — evita texturas faltando no Corona.

Arrastar um arquivo .ms para a viewport do 3ds Max executa o script."""
from __future__ import annotations

from pathlib import Path

from .extractor import safe_name

TEMPLATE = """-- Gerado pelo Gerenciador de Assets 3D
-- Item: {name}
(
\tlocal f = @"{maxfile}"
\tif doesFileExist f then
\t(
{paths}
\t\tmergeMaxFile f #select #promptDups #promptMtlDups #promptReparent
\t\tcompleteRedraw()
\t)
\telse messageBox ("Arquivo não encontrado:\\n" + f) title:"Gerenciador de Assets 3D"
)
"""


def write_merge_script(name: str, item_key: str, max_file: str, dirs: list[str], cache_root: Path) -> Path:
    paths = "\n".join(f'\t\tsessionPaths.add #map @"{d}"' for d in dirs[:200])
    text = TEMPLATE.format(name=name, maxfile=max_file, paths=paths)
    out = Path(cache_root, "scripts", safe_name(item_key.replace("/", " - ")) + ".ms")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8-sig")
    return out
