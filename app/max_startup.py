"""Texturas automáticas no Merge: o item é arrastado como .max puro (janela Merge/XRef do próprio Max) e o
script do Archiva, carregado pelo Max ao abrir, liga as texturas que faltam à pasta do item.

Como funciona:
  1. Ao abrir, o Archiva instala o script de DOIS jeitos (os dois são idempotentes; carregar duas vezes não
     faz mal, o callback tem id fixo):
       - pacote do 3ds Max em %APPDATA%\\Autodesk\\ApplicationPlugins\\Archiva (mecanismo oficial: vale para
         qualquer versão do Max, inclusive as que forem instaladas depois, sem administrador);
       - cópia na pasta scripts\\startup de cada Max já usado neste computador.
  2. Ao começar a arrastar um item, o Archiva grava o aviso (nome do item + pastas) em
     %LOCALAPPDATA%\\Archiva\\ultimo_arrasto.txt (e uma cópia em %TEMP%\\Archiva, para scripts antigos).
  3. Depois de um Merge, o script lê o aviso (e o apaga) e liga as texturas e proxies que estão FALTANDO na
     cena às pastas do item, pelo nome do arquivo. O resumo aparece no MAXScript Listener (F11).
O posicionamento pelo mouse e a escolha Merge/XRef continuam sendo do próprio Max."""
from __future__ import annotations

import glob
import os
import sys
import tempfile

SCRIPT_NAME = "archiva_texturas.ms"
HANDOFF_DIR = "Archiva"
HANDOFF_FILE = "ultimo_arrasto.txt"
PACKAGE_NAME = "Archiva"

STARTUP_SCRIPT = r"""-- Archiva: texturas automaticas no Merge (liga as texturas do item arrastado a pasta dele na biblioteca).
-- Instalado automaticamente pelo Archiva (gerenciador da biblioteca 3D). Pode apagar se nao usar mais o Archiva.
global ArchivaAvisos = #(@"$aviso")
global ArchivaCarregado
global ArchivaRelink
fn ArchivaRelink =
(
	try
	(
		local cands = deepCopy ArchivaAvisos
		for v in #("LOCALAPPDATA", "TEMP", "TMP") do
		(
			local e = systemTools.getEnvVariable v
			if e != undefined and e != "" do appendIfUnique cands (e + "\\Archiva\\ultimo_arrasto.txt")
		)
		local f = undefined
		for c in cands do if f == undefined and (doesFileExist c) do f = c
		if f == undefined then
		(
			format "-- Archiva: Merge sem item do Archiva (nada religado).\n"
		)
		else
		(
			local nome = ""
			local dirs = #()
			local fs = openFile f
			if fs != undefined do
			(
				local first = true
				while not (eof fs) do
				(
					local l = readLine fs
					if first then (nome = l; first = false) else if l != "" do append dirs l
				)
				close fs
			)
			for c in cands where (doesFileExist c) do (try (deleteFile c) catch ())

			local nomes = #()
			local caminhos = #()
			for d in dirs do for p in (getFiles (d + "\\*")) do
			(
				local n = toLower (filenameFromPath p)
				if findItem nomes n == 0 do (append nomes n; append caminhos p)
			)

			local classes = #()
			for c in #(BitmapTexture, CoronaBitmap, VRayBitmap, VRayHDRI, CoronaProxy, VRayProxy) where c != undefined do appendIfUnique classes c
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
					local i = findItem nomes (toLower (filenameFromPath cur))
					if i > 0 then (try (setProperty par[1] par[2] caminhos[i]; religadas += 1) catch ())
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
		)
	)
	catch (format "-- Archiva: erro ao religar texturas: %\n" (getCurrentException()))
	ok
)
callbacks.removeScripts id:#archiva
callbacks.addScript #filePostMerge "ArchivaRelink()" id:#archiva
if ArchivaCarregado != true do
(
	ArchivaCarregado = true
	format "-- Archiva: texturas automaticas no Merge ativas.\n"
)
"""

PACKAGE_XML = """<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0" AutodeskProduct="3ds Max" ProductType="Application" Name="Archiva"
    Description="Archiva: texturas automaticas no Merge" Author="Douglas Couto" AppVersion="1.0.0"
    ProductCode="{6b2f4a3e-7c41-4f0e-9a52-3d1c8e5b7a10}" UpgradeCode="{0d9e6c2a-58b3-4e7f-8a14-b6f2c3d4e5a1}">
  <CompanyDetails Name="TILD" />
  <Components Description="post-start-up scripts parts">
    <RuntimeRequirements OS="Win64" Platform="3ds Max" SeriesMin="2018" SeriesMax="2035" />
    <ComponentEntry AppName="ArchivaTexturas" Version="1.0.0" ModuleName="./Contents/archiva_texturas.ms" />
  </Components>
</ApplicationPackage>
"""


def handoff_paths() -> list[str]:
    """Onde o aviso do item arrastado é gravado (a primeira é a principal)."""
    out = []
    base = os.environ.get("LOCALAPPDATA")
    if base:
        out.append(os.path.join(base, HANDOFF_DIR, HANDOFF_FILE))
    out.append(os.path.join(tempfile.gettempdir(), HANDOFF_DIR, HANDOFF_FILE))
    return list(dict.fromkeys(out))


def script_text() -> str:
    return STARTUP_SCRIPT.replace("$aviso", handoff_paths()[0])


def startup_dirs() -> list[str]:
    """Pastas scripts\\startup de cada 3ds Max já usado por este usuário (cria 'startup' se faltar)."""
    base = os.environ.get("LOCALAPPDATA")
    if sys.platform != "win32" or not base:
        return []
    out = []
    for lang in glob.glob(os.path.join(base, "Autodesk", "3dsMax", "*", "*")):
        name = os.path.basename(lang)
        if os.path.isdir(lang) and (os.path.isdir(os.path.join(lang, "scripts")) or (len(name) == 3 and name.isupper())):
            out.append(os.path.join(lang, "scripts", "startup"))
    return sorted(set(out))


def package_dir() -> str | None:
    base = os.environ.get("APPDATA")
    if sys.platform != "win32" or not base:
        return None
    return os.path.join(base, "Autodesk", "ApplicationPlugins", PACKAGE_NAME)


def _write_if_changed(path: str, text: str, encoding: str = "utf-8-sig") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    cur = None
    if os.path.exists(path):
        with open(path, encoding=encoding, errors="replace") as fh:
            cur = fh.read()
    if cur != text:
        with open(path, "w", encoding=encoding) as fh:
            fh.write(text)


def install() -> list[str]:
    """Instala/atualiza o script (pacote do Max + startup de cada versão). Devolve as versões do Max encontradas
    (ex.: '2024 - 64bit'); vazio se nenhum Max foi usado ainda neste computador (o pacote vale assim mesmo)."""
    text = script_text()
    pkg = package_dir()
    if pkg:
        try:
            _write_if_changed(os.path.join(pkg, "Contents", SCRIPT_NAME), text)
            _write_if_changed(os.path.join(pkg, "PackageContents.xml"), PACKAGE_XML, encoding="utf-8")
        except OSError:
            pass
    done = []
    for d in startup_dirs():
        try:
            _write_if_changed(os.path.join(d, SCRIPT_NAME), text)
            done.append(os.path.basename(os.path.dirname(os.path.dirname(os.path.dirname(d)))))
        except OSError:
            continue
    return sorted(set(done))


def write_handoff(name: str, max_file: str | None, dirs: list[str]) -> None:
    """Avisa o script do Max qual item está sendo arrastado (nome + pastas onde procurar as texturas)."""
    dirs = list(dirs)
    if max_file:
        mdir = os.path.dirname(max_file)
        if mdir and mdir not in dirs:
            dirs.insert(0, mdir)
    # o MaxScript (openFile/readLine) lê no código de página do Windows; acentos do português cabem nele
    enc = "mbcs" if sys.platform == "win32" else "utf-8"
    text = "\n".join([name, *dirs[:200]]) + "\n"
    for path in handoff_paths():
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding=enc, errors="replace") as fh:
                fh.write(text)
        except OSError:
            pass
