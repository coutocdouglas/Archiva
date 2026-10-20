"""Relink automático das texturas quando o item é arrastado como .max puro (janela Merge/XRef do próprio Max).

Como funciona:
  1. O Archiva instala `archiva_texturas.ms` na pasta scripts\\startup de cada 3ds Max do computador
     (%LOCALAPPDATA%\\Autodesk\\3dsMax\\<versão>\\<idioma>\\scripts\\startup). O Max carrega o script ao abrir.
  2. Ao começar a arrastar um item, o Archiva grava em %TEMP%\\Archiva\\ultimo_arrasto.txt o nome do item e as
     pastas dele na biblioteca.
  3. Depois de um Merge, o script lê esse arquivo (e o apaga) e liga as texturas que estão FALTANDO na cena às
     pastas do item, pelo nome do arquivo. Texturas que já existem não são tocadas.
O posicionamento pelo mouse e a escolha Merge/XRef continuam sendo do próprio Max."""
from __future__ import annotations

import glob
import os
import sys
import tempfile

SCRIPT_NAME = "archiva_texturas.ms"
HANDOFF_DIR = "Archiva"
HANDOFF_FILE = "ultimo_arrasto.txt"

STARTUP_SCRIPT = r"""-- Archiva: religa as texturas do item arrastado depois do Merge.
-- Instalado automaticamente pelo Archiva (gerenciador da biblioteca 3D). Pode apagar se nao usar mais o Archiva.
global ArchivaRelink
fn ArchivaRelink =
(
	local tmp = systemTools.getEnvVariable "TEMP"
	if tmp == undefined do return ok
	local f = tmp + "\\Archiva\\ultimo_arrasto.txt"
	if not doesFileExist f do return ok
	local fs = openFile f
	if fs == undefined do return ok
	local nome = ""
	local dirs = #()
	local first = true
	while not eof fs do
	(
		local l = readLine fs
		if first then (nome = l; first = false) else if l != "" do append dirs l
	)
	close fs
	try (deleteFile f) catch ()
	if dirs.count == 0 do return ok

	local names = #()
	local paths = #()
	for d in dirs do for p in (getFiles (d + "\\*")) do
	(
		local n = toLower (filenameFromPath p)
		if findItem names n == 0 do (append names n; append paths p)
	)

	local classes = #()
	for c in #(BitmapTexture, CoronaBitmap, VRayBitmap, VRayHDRI) where c != undefined do appendIfUnique classes c
	local alvos = #()
	for c in classes do for t in (getClassInstances c) do
	(
		if hasProperty t #filename then append alvos #(t, #filename)
		else if hasProperty t #HDRIMapName do append alvos #(t, #HDRIMapName)
	)
	for o in objects where (matchPattern ((classOf o) as string) pattern:"*Proxy*") and (hasProperty o #filename) do
		append alvos #(o, #filename)

	local religadas = 0
	local faltando = #()
	for par in alvos do
	(
		local cur = try (getProperty par[1] par[2]) catch (undefined)
		if classOf cur == String and cur != "" and not (doesFileExist cur) do
		(
			local i = findItem names (toLower (filenameFromPath cur))
			if i > 0 then (try (setProperty par[1] par[2] paths[i]; religadas += 1) catch ())
			else appendIfUnique faltando (filenameFromPath cur)
		)
	)
	try (ATSOps.Refresh()) catch ()
	format "\n-- Archiva: %\n" nome
	format "   % arquivo(s) religado(s) para a pasta da biblioteca.\n" religadas
	if faltando.count > 0 do
	(
		format "   % ainda faltando na cena (nao estao na pasta do item):\n" faltando.count
		for n in faltando do format "     - %\n" n
	)
	ok
)
callbacks.removeScripts id:#archiva
callbacks.addScript #filePostMerge "ArchivaRelink()" id:#archiva
format "-- Archiva: relink de texturas ativo (depois de cada Merge).\n"
"""


def startup_dirs() -> list[str]:
    """Pastas scripts\\startup de cada 3ds Max instalado para este usuário (cria 'startup' se faltar)."""
    base = os.environ.get("LOCALAPPDATA")
    if sys.platform != "win32" or not base:
        return []
    out = []
    for lang in glob.glob(os.path.join(base, "Autodesk", "3dsMax", "*", "*")):
        name = os.path.basename(lang)
        if os.path.isdir(lang) and (os.path.isdir(os.path.join(lang, "scripts")) or (len(name) == 3 and name.isupper())):
            out.append(os.path.join(lang, "scripts", "startup"))
    return sorted(set(out))


def install() -> list[str]:
    """Instala/atualiza o script em cada Max. Devolve as versões do Max onde ele está (ex.: '2024 - 64bit')."""
    done = []
    for d in startup_dirs():
        target = os.path.join(d, SCRIPT_NAME)
        try:
            os.makedirs(d, exist_ok=True)
            cur = None
            if os.path.exists(target):
                with open(target, encoding="utf-8-sig", errors="replace") as fh:
                    cur = fh.read()
            if cur != STARTUP_SCRIPT:
                with open(target, "w", encoding="utf-8-sig") as fh:
                    fh.write(STARTUP_SCRIPT)
            done.append(os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(d)))))
        except OSError:
            continue
    return done


def write_handoff(name: str, dirs: list[str]) -> None:
    """Avisa o script do Max qual item está sendo arrastado (nome + pastas)."""
    folder = os.path.join(tempfile.gettempdir(), HANDOFF_DIR)
    try:
        os.makedirs(folder, exist_ok=True)
        # o MaxScript (openFile/readLine) lê no código de página do Windows; acentos do português cabem nele
        enc = "mbcs" if sys.platform == "win32" else "utf-8"
        with open(os.path.join(folder, HANDOFF_FILE), "w", encoding=enc, errors="replace") as fh:
            fh.write("\n".join([name, *[d for d in dirs[:200]]]) + "\n")
    except OSError:
        pass


INSTALLER = r"""-- Archiva: instala o relink de texturas neste 3ds Max (arraste este arquivo para a viewport uma vez)
(
	local src = @"$src"
	local dst = (getDir #userStartupScripts) + "\\archiva_texturas.ms"
	makeDir (getDir #userStartupScripts) all:true
	if doesFileExist dst do deleteFile dst
	if copyFile src dst then
	(
		fileIn dst
		messageBox ("Relink de texturas do Archiva instalado e ativo.\n\n" + dst) title:"Archiva"
	)
	else messageBox ("Nao foi possivel copiar para:\n" + dst) title:"Archiva"
)
"""


def write_installer(cache_root) -> str:
    """Gera o instalador .ms (e uma cópia do script) na pasta do cache. Devolve o caminho do instalador."""
    from string import Template
    folder = os.path.join(str(cache_root), "scripts")
    os.makedirs(folder, exist_ok=True)
    src = os.path.join(folder, SCRIPT_NAME)
    with open(src, "w", encoding="utf-8") as fh:
        fh.write(STARTUP_SCRIPT)
    inst = os.path.join(folder, "Instalar Archiva no 3ds Max.ms")
    with open(inst, "w", encoding="utf-8") as fh:
        fh.write(Template(INSTALLER).substitute(src=src))
    return inst
