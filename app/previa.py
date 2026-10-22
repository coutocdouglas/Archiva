"""Atualizar a prévia de um item (botão direito › Atualizar prévia › Buscar no PC…).

Nada é sobrescrito:
  * a prévia antiga (e as cópias dela com o nome de cada .max, as miniaturas das Variações) vão para
    _BACKUP_COMPACTADOS\\_DESCARTADOS\\<data>__<item> (prévia) e são apagadas depois do prazo do backup;
  * a imagem nova é preparada primeiro nessa mesma pasta e só então entra no lugar da antiga;
  * tudo entra no histórico como uma sequência de movimentos, então o Desfazer devolve a prévia antiga.
Só as cópias IDÊNTICAS à prévia antiga são trocadas: uma miniatura própria de uma variação (ex.: um render
do WIRE) fica como está.
"""
from __future__ import annotations

import filecmp
import os
import shutil
import time

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QImage, QImageReader, QPixmap
from PySide6.QtWidgets import QDialog, QFileDialog, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout

from . import intake, theme, ui
from .scanner import Asset

IMG_FILTER = "Imagens (*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff)"
VAR_EXT = (".jpg", ".jpeg", ".png", ".JPG", ".JPEG", ".PNG", ".bmp", ".webp")


def image_size(path: str | None) -> QSize:
    if not path:
        return QSize()
    r = QImageReader(path)
    r.setAutoTransform(True)
    return r.size()


def _size_text(path: str | None) -> str:
    s = image_size(path)
    if not s.isValid():
        return "sem imagem"
    try:
        kb = os.path.getsize(path) / 1024
    except OSError:
        kb = 0
    tam = f"{kb / 1024:.1f} MB" if kb >= 1024 else f"{kb:.0f} KB"
    return f"{s.width()} × {s.height()} px  ·  {tam}"


def target_path(a: Asset) -> str:
    """Onde a prévia do item fica (a atual, ou <categoria>\\<nome>.jpg se o item ainda não tem)."""
    if a.preview:
        return a.preview
    base = os.path.dirname(a.members[0]) if a.members else ""
    return os.path.join(base, a.name + ".jpg")


def variation_copies(a: Asset) -> list[str]:
    """Miniaturas das Variações que são cópias exatas da prévia atual (essas acompanham a troca)."""
    if not a.preview or not os.path.isfile(a.preview) or a.kind not in ("folder", "max"):
        return []
    out = []
    for mx in a.max_files or []:
        stem = os.path.splitext(mx)[0]
        for e in VAR_EXT:
            p = stem + e
            if os.path.isfile(p) and os.path.normcase(p) != os.path.normcase(a.preview):
                try:
                    if filecmp.cmp(p, a.preview, shallow=False):
                        out.append(p)
                except OSError:
                    pass
                break
    return out


def prepare_image(src: str, dest: str) -> None:
    """Grava `src` em `dest` no formato da extensão de `dest` (cópia direta quando o formato já é o mesmo)."""
    s_ext = os.path.splitext(src)[1].lower().replace(".jpeg", ".jpg")
    d_ext = os.path.splitext(dest)[1].lower().replace(".jpeg", ".jpg")
    if s_ext == d_ext:
        shutil.copyfile(src, dest)
        return
    r = QImageReader(src)
    r.setAutoTransform(True)
    img = r.read()
    if img.isNull():
        raise OSError(f"não consegui ler a imagem ({r.errorString()})")
    if d_ext in (".jpg", ".bmp"):          # sem transparência: fundo branco no lugar do transparente
        flat = QImage(img.size(), QImage.Format_RGB32)
        flat.fill(Qt.white)
        from PySide6.QtGui import QPainter
        p = QPainter(flat)
        p.drawImage(0, 0, img)
        p.end()
        img = flat
    fmt = {".jpg": "JPG", ".png": "PNG", ".webp": "WEBP", ".bmp": "BMP", ".tif": "TIFF", ".tiff": "TIFF"}.get(d_ext, "JPG")
    if not img.save(dest, fmt, 95 if fmt == "JPG" else -1):
        raise OSError("não consegui gravar a imagem convertida")


class ConfirmDialog(QDialog):
    """Prévia atual × nova, lado a lado, com a resolução de cada uma."""

    def __init__(self, parent, a: Asset, new: str, n_var: int):
        super().__init__(parent)
        self.setWindowTitle(f"Atualizar prévia · {a.name}")
        self.resize(860, 560)
        lay = QVBoxLayout(self)
        lay.setSpacing(12)
        lay.addWidget(ui.heading(f"{a.name}: trocar a prévia", 14))
        txt = "A prévia atual vai para _DESCARTADOS (apagada depois do prazo do backup) e dá para desfazer pelo histórico."
        if n_var:
            txt += (" A miniatura da variação que é cópia da prévia também é trocada." if n_var == 1 else
                    f" As {n_var} miniaturas das Variações que são cópia da prévia também são trocadas.")
        intro = QLabel(txt)
        intro.setWordWrap(True)
        intro.setStyleSheet(f"color:{theme.MUTED.name()};")
        lay.addWidget(intro)
        row = QHBoxLayout()
        row.setSpacing(14)
        for title, path in (("ATUAL", a.preview), ("NOVA", new)):
            g = ui.Glass(14)
            gl = QVBoxLayout(g)
            gl.setContentsMargins(16, 12, 16, 14)
            t = QLabel(title)
            t.setStyleSheet(f"color:{theme.FAINT.name()}; font-size:8.5pt; letter-spacing:1px;")
            gl.addWidget(t)
            pic = QLabel()
            pic.setAlignment(Qt.AlignCenter)
            pic.setMinimumSize(360, 300)
            pm = QPixmap()
            if path:
                r = QImageReader(path)
                r.setAutoTransform(True)
                sz = r.size()
                if sz.isValid():
                    r.setScaledSize(sz.scaled(380, 320, Qt.KeepAspectRatio))
                pm = QPixmap.fromImage(r.read())
            if pm.isNull():
                pic.setText("sem prévia")
                pic.setStyleSheet(f"color:{theme.FAINT.name()};")
            else:
                pic.setPixmap(pm)
            gl.addWidget(pic, 1)
            info = QLabel(_size_text(path))
            info.setAlignment(Qt.AlignCenter)
            info.setStyleSheet(f"color:{theme.HILITE.name() if title == 'NOVA' else theme.MUTED.name()};")
            gl.addWidget(info)
            row.addWidget(g, 1)
        lay.addLayout(row, 1)
        b = QHBoxLayout()
        cancel = QPushButton("Cancelar")
        cancel.clicked.connect(self.reject)
        b.addWidget(cancel)
        b.addStretch(1)
        ok = QPushButton("Trocar prévia")
        ok.setMinimumHeight(38)
        ui.primary(ok)
        ok.clicked.connect(self.accept)
        b.addWidget(ok)
        lay.addLayout(b)


def apply(root: str, a: Asset, new_src: str) -> list[tuple[str, str]]:
    """Troca a prévia. Devolve os movimentos (para o histórico). Se algo falhar, desfaz o que já fez."""
    target = target_path(a)
    copies = variation_copies(a)
    folder = os.path.join(root, intake.DISCARD_DIR,
                          f"{time.strftime('%Y%m%d-%H%M%S')}__{a.name} (prévia)")
    base, i = folder, 2
    while os.path.exists(folder):
        folder, i = f"{base} ({i})", i + 1
    os.makedirs(folder)
    old_time = None
    if a.preview and os.path.isfile(a.preview):
        try:
            st = os.stat(a.preview)
            old_time = (st.st_atime, st.st_mtime)
        except OSError:
            pass
    # 1) prepara tudo dentro de _DESCARTADOS (nada da biblioteca muda ainda)
    staged = []
    new_main = os.path.join(folder, "nova__" + os.path.basename(target))
    prepare_image(new_src, new_main)
    if old_time:     # mantém a data de chegada do item (o Início não o mostra como novo); +1 s renova o cache
        os.utime(new_main, (old_time[0], old_time[1] + 1))
    staged.append((new_main, target))
    for c in copies:
        dst = os.path.join(folder, "nova__" + os.path.basename(c))
        n = 2
        while os.path.exists(dst):
            dst = os.path.join(folder, f"nova{n}__" + os.path.basename(c))
            n += 1
        if os.path.splitext(c)[1].lower() == os.path.splitext(target)[1].lower():
            shutil.copy2(new_main, dst)
        else:
            prepare_image(new_src, dst)
        staged.append((dst, c))
    # 2) antigas para _DESCARTADOS, novas no lugar (registro na ordem certa para o Desfazer)
    moves: list[tuple[str, str]] = []
    try:
        for staged_path, place in staged:
            if os.path.exists(place):
                old = os.path.join(folder, "anterior__" + os.path.basename(place))
                n = 2
                while os.path.exists(old):
                    old = os.path.join(folder, f"anterior{n}__" + os.path.basename(place))
                    n += 1
                shutil.move(place, old)
                moves.append((place, old))
            shutil.move(staged_path, place)
            moves.append((staged_path, place))
    except OSError:
        for src, dst in reversed(moves):       # devolve o que já tinha mudado
            try:
                shutil.move(dst, src)
            except OSError:
                pass
        raise
    return moves


def update_from_pc(w, a: Asset) -> None:
    """Fluxo completo: escolher a imagem, conferir, trocar com trava e histórico, atualizar a tela."""
    start = w.cfg.values.get("previa_last_dir") or os.path.join(os.path.expanduser("~"), "Downloads")
    path, _ = QFileDialog.getOpenFileName(w, f"Nova prévia para {a.name}", start, IMG_FILTER)
    if not path:
        return
    w.cfg.values["previa_last_dir"] = os.path.dirname(path)
    if not image_size(path).isValid():
        QMessageBox.warning(w, "Atualizar prévia", "Não consegui abrir essa imagem.")
        return
    if a.preview and os.path.normcase(os.path.abspath(path)) == os.path.normcase(os.path.abspath(a.preview)):
        QMessageBox.information(w, "Atualizar prévia", "Essa já é a prévia atual do item.")
        return
    copies = variation_copies(a)
    if ConfirmDialog(w, a, path, len(copies)).exec() != QDialog.Accepted:
        return
    root = w.cfg["library_root"]
    locked, busy = w.try_lock([a.key], "trocando a prévia")
    if not locked:
        QMessageBox.information(w, "Em uso", "\n".join(busy))
        return
    old_preview = a.preview
    try:
        moves = apply(root, a, path)
    except OSError as e:
        QMessageBox.warning(w, "Atualizar prévia", f"Não foi possível trocar a prévia: {e}\n\nNada foi alterado.")
        return
    finally:
        w.shared.release(a.key)
    w.log_op("previa", a.category, a.key, f"prévia de {a.name}", moves)
    for p in {old_preview, target_path(a), *copies} - {None}:
        w.forget_image(p)
    w.refresh_category(a.category.split("/")[0])
    w.statusBar().showMessage(f"{a.name}: prévia atualizada.", 6000)
