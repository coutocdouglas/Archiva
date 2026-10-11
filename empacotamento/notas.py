"""Imprime as novidades de uma versão (seção '## x.y.z' do NOVIDADES.md) para a página da versão no GitHub."""
import pathlib
import sys

v = sys.argv[1]
text = (pathlib.Path(__file__).resolve().parent.parent / "NOVIDADES.md").read_text(encoding="utf-8")
out, on = [], False
for line in text.splitlines():
    if line.startswith("## "):
        if on:
            break
        on = line[3:].split()[0].strip() == v
        continue
    if on:
        out.append(line)
sys.stdout.reconfigure(encoding="utf-8")
print("\n".join(out).strip() or f"Archiva {v}")
