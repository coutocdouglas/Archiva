"""Gera empacotamento/versao_exe.txt (dados de versão que aparecem nas Propriedades do Archiva.exe)."""
import pathlib
import re

root = pathlib.Path(__file__).resolve().parent.parent
v = (root / "VERSION").read_text(encoding="utf-8").strip()
n = [int(x) for x in re.findall(r"\d+", v)][:4]
n += [0] * (4 - len(n))
t = tuple(n)
(root / "empacotamento" / "versao_exe.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={t}, prodvers={t}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0,
                    date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('041604B0', [
      StringStruct('CompanyName', 'TILD'),
      StringStruct('FileDescription', 'Archiva'),
      StringStruct('FileVersion', '{v}'),
      StringStruct('InternalName', 'Archiva'),
      StringStruct('OriginalFilename', 'Archiva.exe'),
      StringStruct('ProductName', 'Archiva'),
      StringStruct('ProductVersion', '{v}')])]),
    VarFileInfo([VarStruct('Translation', [1046, 1200])])
  ]
)
""", encoding="utf-8")
print(v)
