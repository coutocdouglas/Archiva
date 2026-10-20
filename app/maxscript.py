"""Gera um pequeno MaxScript que faz o MERGE do modelo e já liga as texturas à pasta do item na biblioteca.

Arrastar um arquivo .ms para a viewport do 3ds Max executa o script.

Por que religar: o .max guarda o caminho das texturas no PC de quem criou o modelo (ex.: C:\\Users\\fulano\\maps).
Antes, o script só acrescentava a pasta MAPS como caminho de busca da SESSÃO do Max — funcionava até fechar o Max;
ao reabrir a cena, as texturas apareciam faltando e era preciso fazer o relink. Agora, logo depois do merge, cada
bitmap (Bitmap, CoronaBitmap, VRayBitmap) e cada proxy (CoronaProxy, VRayProxy) dos objetos que entraram é
procurado pelo NOME do arquivo nas pastas do item e passa a apontar para o caminho completo da biblioteca.
O caminho fica salvo na cena. O resultado aparece no MAXScript Listener (F11)."""
from __future__ import annotations

from pathlib import Path
from string import Template

from .extractor import safe_name

TEMPLATE = Template(r"""-- Gerado pelo Archiva
-- Item: $name
(
	local f = @"$maxfile"
	local dirs = #($dirs)
	if doesFileExist f then
	(
		for d in dirs do sessionPaths.add #map d

		-- índice dos arquivos do item: nome (minúsculo) -> caminho completo
		local names = #()
		local paths = #()
		for d in dirs do for p in (getFiles (d + "\\*")) do
		(
			local n = toLower (filenameFromPath p)
			if findItem names n == 0 do (append names n; append paths p)
		)

		mergeMaxFile f #select #promptDups #promptMtlDups #promptReparent
		local novos = selection as array

		local religadas = 0
		local faltando = #()
		local classes = #()
		for c in #(BitmapTexture, CoronaBitmap, VRayBitmap, VRayHDRI) where c != undefined do appendIfUnique classes c

		-- bitmaps dos materiais e modificadores dos objetos que entraram
		local texs = #()
		for o in novos do for c in classes do
		(
			local found = try (getClassInstances c target:o) catch (#())
			for t in found do appendIfUnique texs t
		)
		local alvos = #()   -- pares (objeto, propriedade com o caminho)
		for t in texs do
		(
			if hasProperty t #filename then append alvos #(t, #filename)
			else if hasProperty t #HDRIMapName do append alvos #(t, #HDRIMapName)
		)
		-- proxies (Corona / V-Ray) também apontam para arquivos
		for o in novos do
		(
			if hasProperty o #filename and (matchPattern ((classOf o) as string) pattern:"*Proxy*") do append alvos #(o, #filename)
		)

		for par in alvos do
		(
			local cur = try (getProperty par[1] par[2]) catch (undefined)
			if classOf cur == String and cur != "" do
			(
				local i = findItem names (toLower (filenameFromPath cur))
				if i > 0 then
				(
					if toLower cur != toLower paths[i] do
					(
						try (setProperty par[1] par[2] paths[i]; religadas += 1) catch ()
					)
				)
				else if not (doesFileExist cur) do appendIfUnique faltando (filenameFromPath cur)
			)
		)
		try (ATSOps.Refresh()) catch ()
		completeRedraw()

		format "\n-- Archiva: $name\n"
		format "   % arquivo(s) religado(s) para a pasta da biblioteca.\n" religadas
		if faltando.count > 0 do
		(
			format "   % não encontrado(s) na pasta do item:\n" faltando.count
			for n in faltando do format "     - %\n" n
		)
	)
	else messageBox ("Arquivo não encontrado:\n" + f) title:"Archiva"
)
""")


def write_merge_script(name: str, item_key: str, max_file: str, dirs: list[str], cache_root: Path) -> Path:
    clean = name.replace('"', "'")
    dir_list = ", ".join(f'@"{d}"' for d in dirs[:200] if '"' not in d)
    text = TEMPLATE.substitute(name=clean, maxfile=max_file, dirs=dir_list)
    out = Path(cache_root, "scripts", safe_name(item_key.replace("/", " - ")) + ".ms")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8-sig")
    return out
