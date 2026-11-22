"""Arrasto da Vegetação para o 3ds Max: Merge automático e proxy automático (etapa 4, refeita na 2.0.22).

O Archiva não sabe gravar .cproxy sozinho (é formato do Corona): quem cria o proxy é o próprio 3ds Max. Por isso
o cartão não é arrastado como .max (que abre o menu Merge/XRef do Max), e sim como um pequeno script MAXScript
gerado na hora (%LOCALAPPDATA%\\Archiva\\arrastar_vegetacao.ms). O Max executa o script ao soltá-lo na viewport,
e o script:

  1. faz o Merge do .max sozinho, sem menu (nomes repetidos ganham outro nome; materiais repetidos também);
  2. põe o que entrou no ponto onde o mouse soltou (no chão, z = 0 da vista ativa) e deixa selecionado;
  3. religa as texturas que faltam às pastas Maps do volume, pelo nome do arquivo;
  4. se foi pedido proxy e ele ainda não existe: cada objeto de malha que entrou vira um Corona Proxy (.cproxy na
     pasta "- Proxy"), no lugar da malha (nome, posição, material, camada, pai); só os proxies são salvos num .max
     pequeno com o MESMO nome do .max da malha, e a malha sai da cena. Se der errado, a malha fica.

O resumo vai para o MAXScript Listener (F11) e o resultado do proxy para proxy_resultado.txt (o painel mostra).
Como o script vai junto com cada arrasto, não depende de nada instalado no Max nem de reabrir o Max.

Na 2.0.21 o proxy era feito por um script de inicialização (archiva_proxy.ms) que esperava o aviso de "Merge
vai começar" — que o Max não dá quando o arquivo é solto na viewport. instalar() agora troca aquele script por
uma versão vazia, que só desliga os avisos antigos.

Onde fica o proxy (o leitor e o arrasto já procuram aí):
  * volume no padrão de pastas:  <pre> - Mesh\\<pre> - Proxy\\<nome do .max>.max  (+ <nome>.cproxy)
  * volume não organizado:       <pasta do .max>\\Proxy\\<nome do .max>.max

Nada é sobrescrito: se o .max do proxy já existe, nada é feito; um .cproxy de mesmo nome que sobrou de uma
tentativa anterior faz o novo ganhar outro nome (_2, _3…).

Este módulo não usa Qt.
"""
from __future__ import annotations

import os
import sys

from .. import max_startup

SCRIPT_NAME = "archiva_proxy.ms"
PACKAGE_NAME = "ArchivaProxy"
PEDIDO = "proxy_pendente.txt"          # da 2.0.21; só é apagado se sobrou
RESULTADO = "proxy_resultado.txt"
SOLTAR = "arrastar_vegetacao.ms"


# ----------------------------------------------------------------------------- onde fica o proxy

def pasta_proxy(mesh_path: str) -> str:
    """A pasta "- Proxy" do .max da malha (dentro da pasta "- Mesh" no padrão; "Proxy" ao lado, fora dele)."""
    d = os.path.dirname(os.path.normpath(mesh_path))
    nome = os.path.basename(d)
    if nome.casefold().endswith(" - mesh"):
        return os.path.join(d, nome[:-len(" - mesh")] + " - Proxy")
    return os.path.join(d, "Proxy")


def destino(mesh_path: str) -> str:
    """O .max pequeno do proxy: mesmo nome do .max da malha, na pasta "- Proxy"."""
    return os.path.join(pasta_proxy(mesh_path), os.path.basename(mesh_path))


def pode_criar(arq) -> bool:
    """Só malhas (.max), sem proxy pronto. GrowFX e cenas ficam de fora."""
    return (getattr(arq, "tipo", "") in ("mesh", "conjunto") and arq.path.lower().endswith(".max")
            and not os.path.isfile(destino(arq.path)))


# ----------------------------------------------------------------------------- arquivos de conversa com o Max

def _dir() -> str | None:
    base = os.environ.get("LOCALAPPDATA")
    return os.path.join(base, "Archiva") if base else None


def _path(name: str) -> str | None:
    d = _dir()
    return os.path.join(d, name) if d else None


_ENC = "mbcs" if sys.platform == "win32" else "utf-8"    # o MaxScript grava no código de página do Windows


def resultado(mesh_path: str) -> tuple[str, str] | None:
    """O que o Max respondeu da última vez sobre esta malha: ("ok" | "erro", texto)."""
    p = _path(RESULTADO)
    try:
        with open(p, encoding=_ENC, errors="replace") as fh:
            lines = fh.read().splitlines()
    except (OSError, TypeError):
        return None
    if len(lines) >= 3 and os.path.normcase(os.path.normpath(lines[1])) == os.path.normcase(os.path.normpath(mesh_path)):
        return lines[0], "\n".join(lines[2:])
    return None


# ----------------------------------------------------------------------------- o script que é solto no Max

SOLTAR_SCRIPT = r"""-- Archiva: arrasto da Vegetacao. Gerado pelo Archiva a cada arrasto (pode apagar).
-- Merge automatico + texturas da pasta Maps do volume + proxy Corona quando pedido.
(
	local arquivo = @"$arquivo"
	local alvo = @"$alvo"
	local malha = @"$malha"
	local nome = "$nome"
	local resposta = @"$resposta"
	local pastas = #($pastas)

	fn responder resposta tipo malha texto =
	(
		try
		(
			local fs = createFile resposta
			format "%\n%\n%\n" tipo malha texto to:fs
			close fs
		)
		catch ()
		ok
	)

	fn ehProcedural o =
	(
		local c = (classOf o) as string
		(matchPattern c pattern:"*GrowFX*") or (matchPattern c pattern:"*Forest*")
	)

	-- texturas e proxies que faltam: procura o arquivo pelo nome nas pastas do volume
	fn religar novos pastas =
	(
		local classes = #()
		for c in #(BitmapTexture, CoronaBitmap, VRayBitmap, VRayHDRI, CProxy, CoronaProxy, VRayProxy) where c != undefined do appendIfUnique classes c
		local alvos = #()
		for c in classes do for t in (getClassInstances c) do
		(
			if hasProperty t #filename then append alvos #(t, #filename)
			else if hasProperty t #HDRIMapName do append alvos #(t, #HDRIMapName)
		)
		for o in novos where (matchPattern ((classOf o) as string) pattern:"*Proxy*") and (hasProperty o #filename) do
			append alvos #(o, #filename)
		local religadas = 0
		local faltando = #()
		for par in alvos do
		(
			local cur = try (getProperty par[1] par[2]) catch (undefined)
			if classOf cur == String and cur != "" and not (doesFileExist cur) do
			(
				local nomeArq = filenameFromPath cur
				local achou = undefined
				for d in pastas while achou == undefined do
				(
					local cand = d + "\\" + nomeArq
					if doesFileExist cand do achou = cand
				)
				if achou != undefined then (try (setProperty par[1] par[2] achou; religadas += 1) catch ())
				else appendIfUnique faltando nomeArq
			)
		)
		try (ATSOps.Refresh()) catch ()
		#(religadas, faltando)
	)

	-- devolve #(ok?, mensagem)
	fn criarProxy novos alvo =
	(
		local proc = for o in novos where (ehProcedural o) collect o
		local geo = for o in novos where (superClassOf o == GeometryClass) and not (isGroupHead o) and \
			not (ehProcedural o) and not (matchPattern ((classOf o) as string) pattern:"*Proxy*") and \
			(canConvertTo o Editable_Mesh) collect o
		if CProxy == undefined then #(false, "Corona nao encontrado neste 3ds Max: ficou a malha.")
		else if proc.count > 0 then #(false, "o arquivo tem GrowFX/Forest Pack (procedural): so malha vira proxy. Ficou a malha.")
		else if geo.count == 0 then #(false, "nenhum objeto de malha entrou: nada a converter.")
		else if doesFileExist alvo then #(false, "o proxy ja existe (" + alvo + "): nada foi feito.")
		else
		(
			local pasta = getFilenamePath alvo
			local stem = getFilenameFile alvo
			makeDir pasta all:true
			local feitos = #()       -- #(proxy, original)
			local arquivos = #()
			local erro = ""
			for i = 1 to geo.count while erro == "" do
			(
				local n = geo[i]
				local base = pasta + stem + (if geo.count > 1 then ("_" + (formattedPrint i format:"02d")) else "")
				local f = base + ".cproxy"
				local k = 2
				while doesFileExist f do (f = base + "_" + (k as string) + ".cproxy"; k += 1)
				local p = CProxy()
				local okp = false
				local e1 = ""
				-- Corona: <integer>fromScene <node>proxy <node>node <filename>filename (um objeto por vez)
				try (CProxy.ProxyFp.fromScene p n f; okp = true) catch (e1 = getCurrentException())
				if not okp do try (CProxy.ProxyFp.fromScene p #(n) f; okp = true) catch ()
				if okp and (doesFileExist f) then
				(
					append arquivos f
					try (p.filename = f) catch ()
					p.name = n.name
					p.wirecolor = n.wirecolor
					p.material = n.material
					try (n.layer.addNode p) catch ()
					classOf p      -- avalia o proxy (a caixa do .cproxy carregada antes de medir)
					-- posicao: o .cproxy pode guardar a malha no espaco do objeto ou no do mundo; fica a que bate
					local c0 = (n.min + n.max) / 2.0
					local tam = length (n.max - n.min)
					p.transform = n.transform
					if tam > 0 and (length (((p.min + p.max) / 2.0) - c0)) > (tam * 0.05) do
					(
						p.transform = matrix3 1
						if (length (((p.min + p.max) / 2.0) - c0)) > (tam * 0.05) do p.transform = n.transform
					)
					p.parent = n.parent
					if isGroupMember n do try (setGroupMember p true) catch ()
					append feitos #(p, n)
				)
				else
				(
					try (delete p) catch ()
					erro = "o Corona nao gravou o proxy de " + n.name + (if e1 != "" then (" (" + e1 + ")") else "")
				)
			)
			if erro != "" then
			(
				for par in feitos do try (delete par[1]) catch ()
				for f in arquivos do try (deleteFile f) catch ()
				format "-- Archiva: o que o Corona oferece para proxies (mande isto se o proxy nao for criado):\n"
				try (showInterfaces CProxy) catch ()
				#(false, erro + ". Ficou a malha.")
			)
			else
			(
				local originais = for par in feitos collect par[2]
				local proxies = for par in feitos collect par[1]
				delete originais
				local salvar = for o in novos where (isValidNode o) collect o
				join salvar proxies
				saveNodes salvar alvo quiet:true
				select salvar
				if doesFileExist alvo then
					#(true, "proxy criado: " + alvo + " (" + (proxies.count as string) + " objeto(s), " + (arquivos.count as string) + " .cproxy). Use Atualizar no Archiva.")
				else
					#(false, "o .max do proxy nao foi salvo em " + alvo + ". Os proxies ficaram na cena; a malha saiu.")
			)
		)
	)

	try
	(
		format "\n-- Archiva: %\n" nome
		if not (doesFileExist arquivo) then
		(
			format "   arquivo nao encontrado: %\n" arquivo
			if alvo != "" do responder resposta "erro" malha ("arquivo nao encontrado: " + arquivo)
		)
		else
		(
			-- ponto onde o mouse soltou, no chao (z = 0) da vista ativa
			local pt = undefined
			try
			(
				local r = mapScreenToWorldRay mouse.pos
				if (abs r.dir.z) > 0.0001 do
				(
					local t = -r.pos.z / r.dir.z
					if t > 0 and t < 1e7 do pt = r.pos + r.dir * t
				)
			)
			catch ()
			local h = 0
			for o in objects do (local x = o.inode.handle; if x > h do h = x)
			local okm = false
			try (mergeMAXFile arquivo #select #autoRenameDups #renameMtlDups #noRedraw quiet:true; okm = true) catch ()
			if not okm do try (mergeMAXFile arquivo #select #autoRenameDups quiet:true; okm = true) catch ()
			local novos = for o in objects where o.inode.handle > h collect o
			if novos.count == 0 then
			(
				format "   o Merge nao trouxe nenhum objeto.\n"
				if alvo != "" do responder resposta "erro" malha "o Merge nao trouxe nenhum objeto."
			)
			else
			(
				if pt != undefined do
				(
					local mn = novos[1].min
					local mx = novos[1].max
					for o in novos do
					(
						local a = o.min
						local b = o.max
						mn = [amin mn.x a.x, amin mn.y a.y, amin mn.z a.z]
						mx = [amax mx.x b.x, amax mx.y b.y, amax mx.z b.z]
					)
					local d = pt - [(mn.x + mx.x) / 2.0, (mn.y + mx.y) / 2.0, mn.z]
					for o in novos where o.parent == undefined or (findItem novos o.parent) == 0 do move o d
				)
				select novos
				local rl = religar novos pastas
				format "   % objeto(s) no Merge; % arquivo(s) religado(s) para a pasta do volume.\n" novos.count rl[1]
				if rl[2].count > 0 do
				(
					format "   % ainda faltando (nao estao nas pastas do volume):\n" rl[2].count
					for n in rl[2] do format "     - %\n" n
				)
				if alvo != "" do
				(
					local rp = criarProxy novos alvo
					format "   %\n" rp[2]
					responder resposta (if rp[1] then "ok" else "erro") malha rp[2]
				)
			)
		)
	)
	catch
	(
		local e = getCurrentException()
		format "-- Archiva: erro no arrasto: %\n" e
		if alvo != "" do responder resposta "erro" malha ("erro no 3ds Max: " + (e as string))
	)
	redrawViews()
	ok
)
"""


def _ms_verbatim(s: str) -> str:
    """Texto para @"..." do MaxScript (não aceita aspas dentro)."""
    return (s or "").replace('"', "'")


def _ms_string(s: str) -> str:
    return (s or "").replace("\\", "\\\\").replace('"', "'").replace("\n", " ")


def script_soltar(arquivo: str, pastas: list[str], nome: str, criar_proxy_de: str | None) -> str:
    """O texto do script que vai para o Max. criar_proxy_de: a malha cujo proxy deve ser criado (ou None)."""
    alvo = destino(criar_proxy_de) if criar_proxy_de else ""
    lista = ", ".join(f'@"{_ms_verbatim(d)}"' for d in pastas)
    rep = {
        "$arquivo": _ms_verbatim(os.path.normpath(arquivo)),
        "$alvo": _ms_verbatim(alvo),
        "$malha": _ms_verbatim(os.path.normpath(criar_proxy_de) if criar_proxy_de else ""),
        "$nome": _ms_string(nome),
        "$resposta": _ms_verbatim(_path(RESULTADO) or ""),
        "$pastas": lista,
    }
    text = SOLTAR_SCRIPT
    for k, v in rep.items():
        text = text.replace(k, v)
    return text


def gravar_soltar(arquivo: str, pastas: list[str], nome: str, criar_proxy_de: str | None) -> str | None:
    """Grava o script do arrasto e devolve o caminho dele (é ele que vai no arrasto para o Max)."""
    p = _path(SOLTAR)
    if not p:
        return None
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8-sig") as fh:     # o MaxScript lê UTF-8 com BOM (acentos nos caminhos)
            fh.write(script_soltar(arquivo, pastas, nome, criar_proxy_de))
        return p
    except OSError:
        return None


# ----------------------------------------------------------------------------- script da 2.0.21 (desligado)

STUB_SCRIPT = r"""-- Archiva: o proxy automatico da Vegetacao agora vai junto com cada arrasto (2.0.22).
-- Este arquivo so desliga os avisos da 2.0.21. Pode apagar se nao usar mais o Archiva.
callbacks.removeScripts id:#archivaProxy
"""


def instalar() -> bool:
    """Troca o script de inicialização da 2.0.21 por um que só desliga os avisos antigos (onde ele existir) e
    apaga um pedido de proxy que tenha sobrado. Idempotente."""
    ok = False
    base = os.environ.get("APPDATA")
    if sys.platform == "win32" and base:
        f = os.path.join(base, "Autodesk", "ApplicationPlugins", PACKAGE_NAME, "Contents", SCRIPT_NAME)
        if os.path.isfile(f):
            try:
                max_startup._write_if_changed(f, STUB_SCRIPT)
                ok = True
            except OSError:
                pass
    for d in max_startup.startup_dirs():
        f = os.path.join(d, SCRIPT_NAME)
        if os.path.isfile(f):
            try:
                max_startup._write_if_changed(f, STUB_SCRIPT)
                ok = True
            except OSError:
                continue
    p = _path(PEDIDO)
    if p and os.path.isfile(p):
        try:
            os.remove(p)
        except OSError:
            pass
    return ok


# ----------------------------------------------------------------------------- desfazer a organização

def guardar_no_desfazer(vol_path: str, journal: dict) -> list[tuple[str, str]]:
    """Chamado pelo desfazer da organização DEPOIS de voltar os passos do diário. Os proxies criados depois de
    organizar (na "<pre> - Mesh\\<pre> - Proxy", fora do diário) acompanham a malha: vão para a pasta "Proxy" ao
    lado de onde o .max da malha voltou. Nada é sobrescrito: o que daria conflito fica onde está.
    Devolve os movimentos feitos (origem, destino)."""
    import shutil
    pre = journal.get("prefixo") or ""
    pdir = os.path.join(vol_path, f"{pre} - Mesh", f"{pre} - Proxy")
    if not os.path.isdir(pdir):
        return []
    # onde cada .max da Mesh voltou (nome do arquivo → pasta de origem)
    voltou: dict[str, str] = {}
    for acao, origem, dest in journal.get("passos", []):
        if acao == "mover" and dest.lower().endswith(".max") and \
                os.path.normcase(os.path.dirname(dest)) == os.path.normcase(os.path.join(vol_path, f"{pre} - Mesh")):
            voltou[os.path.splitext(os.path.basename(dest))[0].casefold()] = os.path.dirname(origem)
    feitos = []
    for fn in sorted(os.listdir(pdir)):
        src = os.path.join(pdir, fn)
        if not os.path.isfile(src):
            continue
        stem = os.path.splitext(fn)[0].casefold()
        dono = voltou.get(stem)
        if dono is None:      # .cproxy de várias partes: "<nome>_01.cproxy", "<nome>_01_2.cproxy"
            cands = [s for s in voltou if stem.startswith(s + "_")]
            dono = voltou[max(cands, key=len)] if cands else None
        if dono is None:
            continue
        dst = os.path.join(dono, "Proxy", fn)
        if os.path.exists(dst):
            continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        shutil.move(src, dst)
        feitos.append((src, dst))
    for d in (pdir, os.path.dirname(pdir)):
        try:
            os.rmdir(d)      # só se ficou vazia
        except OSError:
            pass
    return feitos
