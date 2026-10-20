"""Pasta e compactado com o mesmo nome: comparar o conteúdo dos dois e decidir o que fica.

Nada é apagado: o que sai vai para _BACKUP_COMPACTADOS\\_DESCARTADOS e tudo entra no histórico (desfazer).
  * Manter a pasta       -> o compactado vai para _DESCARTADOS
  * Manter o compactado  -> a pasta vai para _DESCARTADOS (o item volta a ser "compactado, precisa extrair")
  * Ficar com os dois    -> o compactado vira um item novo, com o próximo número da categoria e uma cópia da prévia
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
import zipfile
from dataclasses import dataclass, field

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMessageBox, QPushButton,
                               QVBoxLayout)

from . import intake, theme, ui
from .extractor import JUNK_DIRS, JUNK_FILES, NO_WINDOW
from .scanner import Asset

KEEP_FOLDER, KEEP_ARCHIVE, KEEP_BOTH = "pasta", "compactado", "os dois"


# ------------------------------------------------------------------ listar conteúdo
def _skip(rel: str) -> bool:
    parts = [p.casefold() for p in re.split(r"[\\/]+", rel) if p]
    return not parts or parts[-1] in JUNK_FILES or any(p in JUNK_DIRS for p in parts)


def list_folder(folder: str) -> dict[str, int]:
    """Caminho relativo -> tamanho, de todos os arquivos da pasta do item."""
    out = {}
    for r, _d, fs in os.walk(folder):
        for f in fs:
            p = os.path.join(r, f)
            rel = os.path.relpath(p, folder)
            if _skip(rel):
                continue
            try:
                out[rel] = os.path.getsize(p)
            except OSError:
                pass
    return out


def _run_list(cmd: list[str]) -> str | None:
    try:
        r = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL, creationflags=NO_WINDOW, timeout=120)
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode not in (0, 1):
        return None
    return (r.stdout or b"").decode("utf-8", "replace")


def _parse_7z(text: str) -> dict[str, int]:
    out, cur = {}, {}
    for line in text.splitlines() + [""]:
        line = line.strip()
        if not line:
            if cur.get("Path") and cur.get("Folder") != "+" and "D" not in cur.get("Attributes", "")[:1]:
                try:
                    out[cur["Path"]] = int(cur.get("Size") or 0)
                except ValueError:
                    out[cur["Path"]] = 0
            cur = {}
            continue
        k, sep, v = line.partition(" = ")
        if sep:
            cur[k] = v
    return out


def _parse_unrar(text: str) -> dict[str, int]:
    out, cur = {}, {}
    for line in text.splitlines() + [""]:
        line = line.strip()
        if not line:
            if cur.get("Name") and cur.get("Type", "File").lower().startswith("file"):
                try:
                    out[cur["Name"]] = int(cur.get("Size") or 0)
                except ValueError:
                    out[cur["Name"]] = 0
            cur = {}
            continue
        k, sep, v = line.partition(":")
        if sep and k in ("Name", "Type", "Size"):
            cur[k] = v.strip()
    return out


def list_archive(archive: str, kind: str | None, tools: dict[str, str], passwords: list[str]) -> dict[str, int] | None:
    """Caminho relativo -> tamanho, sem extrair. None = não deu para ler (sem programa ou nomes protegidos)."""
    out = None
    if kind == "zip":
        try:
            with zipfile.ZipFile(archive) as z:
                out = {i.filename: i.file_size for i in z.infolist() if not i.is_dir()}
        except (OSError, zipfile.BadZipFile, RuntimeError):
            out = None
    if out is None:
        for pwd in [None, *[p for p in passwords if p]]:
            if "7z" in tools:
                text = _run_list([tools["7z"], "l", "-slt", "-ba", f"-p{pwd or ''}", archive])
                parsed = _parse_7z(text) if text else {}
            elif "unrar" in tools and kind == "rar":
                text = _run_list([tools["unrar"], "lt", f"-p{pwd}" if pwd else "-p-", archive])
                parsed = _parse_unrar(text) if text else {}
            else:
                return None
            if parsed:
                out = parsed
                break
    if out is None:
        return None
    return {k: v for k, v in out.items() if not _skip(k)}


# ------------------------------------------------------------------ comparar
@dataclass
class Comparison:
    same: list[str] = field(default_factory=list)           # mesmo nome e tamanho
    differ: list[tuple[str, int, int]] = field(default_factory=list)   # nome, tamanho na pasta, no compactado
    only_folder: list[str] = field(default_factory=list)
    only_archive: list[str] = field(default_factory=list)
    folder_size: int = 0
    archive_size: int = 0       # descompactado
    readable: bool = True


def compare(folder_files: dict[str, int], archive_files: dict[str, int] | None) -> Comparison:
    """Compara pelo NOME do arquivo (a pasta já organizada não tem as mesmas subpastas do compactado)."""
    c = Comparison(folder_size=sum(folder_files.values()))
    if archive_files is None:
        c.readable = False
        return c
    c.archive_size = sum(archive_files.values())

    def by_name(files):
        d: dict[str, list[int]] = {}
        for rel, size in files.items():
            d.setdefault(os.path.basename(rel.replace("\\", "/")).casefold(), []).append(size)
        return d

    fo, ar = by_name(folder_files), by_name(archive_files)
    display = {os.path.basename(r.replace("\\", "/")).casefold(): os.path.basename(r.replace("\\", "/"))
               for r in list(archive_files) + list(folder_files)}
    # cópias da prévia criadas pelo Archiva ao organizar (<nome do .max>.jpg) não contam como diferença
    max_stems = {os.path.splitext(n)[0] for n in fo if n.endswith(".max")}
    for n in sorted(set(fo) | set(ar)):
        if n in fo and n in ar:
            if set(fo[n]) & set(ar[n]):
                c.same.append(display[n])
            else:
                c.differ.append((display[n], fo[n][0], ar[n][0]))
        elif n in fo:
            stem, ext = os.path.splitext(n)
            if not (ext in (".jpg", ".jpeg", ".png") and stem in max_stems):
                c.only_folder.append(display[n])
        else:
            c.only_archive.append(display[n])
    return c


def _mb(n: int) -> str:
    return f"{n / 1024 ** 2:.1f} MB" if n < 1024 ** 3 else f"{n / 1024 ** 3:.2f} GB"


# ------------------------------------------------------------------ tela
class CompareDialog(QDialog):
    def __init__(self, parent, a: Asset, cmp: Comparison):
        super().__init__(parent)
        self.choice = ""
        self.setWindowTitle(f"Comparar pasta e compactado · {a.name}")
        self.resize(760, 620)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(ui.heading(f"{a.name}: pasta × compactado", 14))
        intro = QLabel("O mesmo item existe como pasta extraída e como arquivo compactado. Compare o conteúdo e "
                       "escolha o que fica. O que sair vai para _DESCARTADOS e dá para desfazer pelo histórico.")
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{theme.MUTED.name()};")
        lay.addWidget(intro)

        row = QHBoxLayout()
        row.setSpacing(14)
        for title, path, size, n in (
                ("PASTA", a.folder, cmp.folder_size, len(cmp.same) + len(cmp.differ) + len(cmp.only_folder)),
                ("COMPACTADO", a.dup_archive, cmp.archive_size,
                 len(cmp.same) + len(cmp.differ) + len(cmp.only_archive))):
            g = ui.Glass(14)
            gl = QVBoxLayout(g)
            gl.setContentsMargins(16, 12, 16, 12)
            t = QLabel(title)
            t.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:8.5pt; letter-spacing:1px;")
            gl.addWidget(t)
            nm = QLabel(os.path.basename(path or ""))
            nm.setWordWrap(True)
            gl.addWidget(nm)
            if title == "COMPACTADO" and not cmp.readable:
                try:
                    disk = os.path.getsize(path)
                except OSError:
                    disk = 0
                info = f"{_mb(disk)} compactado · conteúdo não pôde ser lido"
            else:
                info = f"{n} arquivos · {_mb(size)}" + (" (descompactado)" if title == "COMPACTADO" else "")
            i = QLabel(info)
            i.setStyleSheet(f"color:{theme.MUTED.name()};")
            gl.addWidget(i)
            row.addWidget(g, 1)
        lay.addLayout(row)

        verdict = QLabel(self._verdict(cmp))
        verdict.setWordWrap(True)
        verdict.setStyleSheet(f"color:{theme.HILITE.name()};")
        lay.addWidget(verdict)

        lst = QListWidget()
        lst.setStyleSheet("QListWidget::item{padding:3px 4px;}")

        def add(text, color):
            it = QListWidgetItem(text)
            it.setForeground(color)
            lst.addItem(it)
        for n, fs, as_ in cmp.differ:
            add(f"≠  {n}   (pasta {_mb(fs)} · compactado {_mb(as_)})", theme.WARN)
        for n in cmp.only_archive:
            add(f"só no compactado   {n}", theme.BAD)
        for n in cmp.only_folder:
            add(f"só na pasta   {n}", theme.ORG)
        for n in cmp.same:
            add(f"✓  {n}", theme.MUTED)
        if not cmp.readable:
            add("Não deu para listar o compactado (programa não encontrado ou nomes protegidos por senha).",
                theme.MUTED)
        lay.addWidget(lst, 1)

        b = QHBoxLayout()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        b.addWidget(cancel)
        b.addStretch(1)
        for label, key, tip in (
                ("Ficar com os dois", KEEP_BOTH, "O compactado vira um item novo, com o próximo número da categoria."),
                ("Manter o compactado", KEEP_ARCHIVE, "A pasta vai para _DESCARTADOS; o item volta a ser compactado."),
                ("Manter a pasta", KEEP_FOLDER, "O compactado vai para _DESCARTADOS.")):
            btn = QPushButton(label)
            btn.setToolTip(tip)
            btn.setMinimumHeight(38)
            btn.clicked.connect(lambda _=False, k=key: self._pick(k))
            if key == self._suggest(cmp):
                ui.primary(btn)
            b.addWidget(btn)
        lay.addLayout(b)

    @staticmethod
    def _suggest(c: Comparison) -> str:
        if not c.readable:
            return ""
        if not c.only_archive and not c.differ:
            return KEEP_FOLDER
        return ""

    @staticmethod
    def _verdict(c: Comparison) -> str:
        if not c.readable:
            return "Só dá para comparar os tamanhos. Se estiver em dúvida, escolha \"Ficar com os dois\"."
        if not c.only_archive and not c.differ:
            return "A pasta já tem tudo o que está no compactado. Manter a pasta é seguro."
        parts = []
        if c.only_archive:
            parts.append(f"{len(c.only_archive)} arquivo(s) só no compactado")
        if c.differ:
            parts.append(f"{len(c.differ)} com tamanho diferente")
        if c.only_folder:
            parts.append(f"{len(c.only_folder)} só na pasta")
        return "Há diferenças: " + ", ".join(parts) + ". Confira antes de escolher."

    def _pick(self, key: str):
        msg = {KEEP_FOLDER: "O compactado vai para _DESCARTADOS.",
               KEEP_ARCHIVE: "A pasta extraída vai para _DESCARTADOS e o item volta a ser compactado.",
               KEEP_BOTH: "O compactado vira um item novo, com o próximo número da categoria."}[key]
        if QMessageBox.question(self, "Confirmar", f"{msg}\n\nDá para desfazer pelo histórico. Continuar?") \
                != QMessageBox.Yes:
            return
        self.choice = key
        self.accept()


# ------------------------------------------------------------------ aplicar
def _discard_one(root: str, path: str, label: str, rec: list) -> None:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    base = os.path.join(root, intake.DISCARD_DIR, f"{stamp}__{label}")
    dest, i = base, 2
    while os.path.exists(dest):
        dest, i = f"{base} ({i})", i + 1
    os.makedirs(dest)
    target = os.path.join(dest, os.path.basename(path))
    try:
        os.rename(path, target)
    except OSError:
        shutil.move(path, target)
    rec.append((path, target))


def resolve(w, a: Asset) -> None:
    """Abre a comparação e aplica a escolha (chamado pelo painel de detalhes)."""
    if not (a.folder and a.dup_archive and os.path.exists(a.dup_archive)):
        QMessageBox.information(w, "Comparar", "Não há mais pasta e compactado com o mesmo nome neste item.")
        return
    from PySide6.QtWidgets import QApplication
    QApplication.setOverrideCursor(Qt.WaitCursor)
    try:
        cmp = compare(list_folder(a.folder), list_archive(a.dup_archive, a.dup_archive_type, w.tools, w.passwords))
    finally:
        QApplication.restoreOverrideCursor()
    dlg = CompareDialog(w, a, cmp)
    if dlg.exec() != QDialog.Accepted or not dlg.choice:
        return
    got, busy = w.try_lock([a.key], "comparando pasta e compactado")
    if busy:
        QMessageBox.information(w, "Em uso", "\n".join(busy) + "\n\nTente de novo quando a pessoa terminar.")
        return
    root = w.cfg["library_root"]
    try:
        rec, created = [], []
        if dlg.choice == KEEP_FOLDER:
            _discard_one(root, a.dup_archive, a.name, rec)
            w.log_op("comparar", a.category, a.key, f"{a.name}: compactado repetido (ficou a pasta)", rec)
        elif dlg.choice == KEEP_ARCHIVE:
            _discard_one(root, a.folder, a.name, rec)
            w.log_op("comparar", a.category, a.key, f"{a.name}: pasta extraída (ficou o compactado)", rec)
        else:
            from .organizar import top_of
            cat = w.cat_by_key.get(a.category)
            if cat is None:
                raise OSError("categoria não encontrada")
            new = intake.next_names(cat, 1, w.db.prefixes().get(cat.key), top_of(cat, w.categories).all_assets())[0]
            ext = os.path.splitext(a.dup_archive)[1] or ("." + (a.dup_archive_type or "rar"))
            dst = os.path.join(cat.path, new + ext)
            if os.path.exists(dst):
                raise OSError(f"já existe {os.path.basename(dst)}")
            os.rename(a.dup_archive, dst)
            rec.append((a.dup_archive, dst))
            if a.preview and os.path.exists(a.preview):
                pv = os.path.join(cat.path, new + os.path.splitext(a.preview)[1].lower())
                if not os.path.exists(pv):
                    shutil.copy2(a.preview, pv)
                    created.append(pv)
            w.log_op("separar", a.category, f"{a.category}/{new}", f"{a.name}: compactado virou {new}",
                     rec, created)
    except OSError as e:
        QMessageBox.warning(w, "Comparar", f"Não foi possível concluir ({e}). Nada mais foi alterado.")
    finally:
        for k in got:
            w.shared.release(k)
    w.refresh_category(a.category.split("/")[0])
