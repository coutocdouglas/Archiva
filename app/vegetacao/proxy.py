"""Proxy automático da Vegetação (etapa 4).

O Archiva não sabe gravar .cproxy sozinho (é formato do Corona): quem cria o proxy é o próprio 3ds Max, no
momento em que a pessoa solta a malha na viewport. Como funciona:

  1. Ao abrir a aba Vegetação, o Archiva instala um script de inicialização PRÓPRIO da Vegetação
     (archiva_proxy.ms, pacote "ArchivaProxy"), separado do archiva_texturas.ms da Biblioteca, que não muda.
  2. Ao arrastar um cartão com a versão Proxy escolhida e sem proxy pronto, vai a malha (como antes) e o
     Archiva grava o pedido %LOCALAPPDATA%\\Archiva\\proxy_pendente.txt: hora, o .max do proxy a criar e a malha.
     Qualquer outro arrasto apaga o pedido, para ele nunca valer para outra coisa.
  3. Depois do Merge, o script: religa as texturas (chama o ArchivaRelink da Biblioteca, se o aviso ainda está
     lá), converte cada objeto de malha que acabou de entrar num Corona Proxy (.cproxy na pasta "- Proxy"),
     põe o proxy no lugar da malha (mesmo nome, posição, material, camada), salva só os proxies num .max pequeno
     com o MESMO nome do .max da malha e tira a malha da cena. Se qualquer coisa der errado, a malha fica na
     cena como estava e o motivo aparece no MAXScript Listener (F11) e no painel do Archiva.

Onde fica o proxy (o leitor e o arrasto já procuram aí):
  * volume no padrão de pastas:  <pre> - Mesh\\<pre> - Proxy\\<nome do .max>.max  (+ <nome>.cproxy)
  * volume não organizado:       <pasta do .max>\\Proxy\\<nome do .max>.max

Nada é sobrescrito: se o .max do proxy já existe, o script não faz nada; um .cproxy de mesmo nome que sobrou de
uma tentativa anterior ganha outro nome (_2, _3…).

Este módulo não usa Qt.
"""
from __future__ import annotations

import os
import sys
import time

from .. import max_startup

SCRIPT_NAME = "archiva_proxy.ms"
PACKAGE_NAME = "ArchivaProxy"
PEDIDO = "proxy_pendente.txt"
RESULTADO = "proxy_resultado.txt"
CARREGADO = "proxy_script.txt"
VALIDADE = 15 * 60          # segundos: um pedido mais velho que isso é ignorado pelo script
VERSAO_SCRIPT = "1"

_ENC = "mbcs" if sys.platform == "win32" else "utf-8"    # o MaxScript lê e grava no código de página do Windows


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


def pedir(mesh_path: str, nome: str) -> bool:
    """Grava o pedido de proxy para o próximo Merge. Devolve False se não deu para gravar."""
    p = _path(PEDIDO)
    if not p:
        return False
    alvo = destino(mesh_path)
    text = "\n".join([str(int(time.time())), alvo, os.path.normpath(mesh_path), nome]) + "\n"
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding=_ENC, errors="replace") as fh:
            fh.write(text)
        return True
    except OSError:
        return False


def cancelar() -> None:
    """Apaga o pedido pendente (outro arrasto começou)."""
    p = _path(PEDIDO)
    if p and os.path.isfile(p):
        try:
            os.remove(p)
        except OSError:
            pass


def pedido() -> list[str] | None:
    p = _path(PEDIDO)
    try:
        with open(p, encoding=_ENC, errors="replace") as fh:
            return fh.read().splitlines()
    except (OSError, TypeError):
        return None


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


def script_ja_carregado() -> bool:
    """O 3ds Max já carregou o script do proxy alguma vez neste computador (ele grava uma marca ao carregar)."""
    p = _path(CARREGADO)
    return bool(p) and os.path.isfile(p)


# ----------------------------------------------------------------------------- o script do Max

STARTUP_SCRIPT = r"""-- Archiva: proxy automatico da Vegetacao (Corona Proxy na pasta "- Proxy" do volume).
-- Instalado automaticamente pelo Archiva (aba Vegetacao). Pode apagar se nao usar mais o Archiva.
-- So age quando o Archiva deixou um pedido em proxy_pendente.txt; qualquer outro Merge passa direto.
global ArchivaProxyPasta = @"$pasta"
global ArchivaProxyMaxHandle = -1
global ArchivaProxyCarregado
global ArchivaProxyPre
global ArchivaProxyPost
global ArchivaProxyFazer
global ArchivaProxyResposta
global ArchivaProxyEhProc
global ArchivaProxyMarca
fn ArchivaProxyEhProc o =
(
	local c = (classOf o) as string
	(matchPattern c pattern:"*GrowFX*") or (matchPattern c pattern:"*Forest*")
)
fn ArchivaProxyMarca =
(
	try
	(
		makeDir ArchivaProxyPasta all:true
		local fs = createFile (ArchivaProxyPasta + "\\$carregado")
		format "$versao\n" to:fs
		close fs
	)
	catch ()
	ok
)
fn ArchivaProxyResposta tipo malha texto =
(
	try
	(
		local fs = createFile (ArchivaProxyPasta + "\\$resultado")
		format "%\n%\n%\n" tipo malha texto to:fs
		close fs
	)
	catch ()
	ok
)
fn ArchivaProxyPre =
(
	ArchivaProxyMaxHandle = -1
	try
	(
		if doesFileExist (ArchivaProxyPasta + "\\$pedido") do
		(
			local h = 0
			for o in objects do (local x = o.inode.handle; if x > h do h = x)
			ArchivaProxyMaxHandle = h
		)
	)
	catch ()
	ok
)
fn ArchivaProxyFazer alvo malha =
(
	-- devolve #(ok?, mensagem)
	local novos = if ArchivaProxyMaxHandle < 0 then #() else for o in objects where o.inode.handle > ArchivaProxyMaxHandle collect o
	-- o Merge tem de ser do .max pedido (um Merge da Biblioteca logo depois nunca vira proxy da Vegetacao)
	local nomes = try (for x in (getMAXFileObjectNames malha quiet:true) collect toLower x) catch (#())
	local doArquivo = nomes.count > 0 and novos.count > 0
	for o in novos while doArquivo do
	(
		local nm = toLower o.name
		if findItem nomes nm == 0 and (for x in nomes where (matchPattern nm pattern:(x + "*")) collect x).count == 0 do doArquivo = false
	)
	local proc = for o in novos where (ArchivaProxyEhProc o) collect o
	local geo = for o in novos where (superClassOf o == GeometryClass) and not (isGroupHead o) and \
		not (ArchivaProxyEhProc o) and not (matchPattern ((classOf o) as string) pattern:"*Proxy*") and \
		(canConvertTo o Editable_Mesh) collect o
	if CProxy == undefined then #(false, "Corona nao encontrado neste 3ds Max: ficou a malha.")
	else if ArchivaProxyMaxHandle < 0 then #(false, "o Merge comecou antes do pedido do Archiva: ficou a malha.")
	else if not doArquivo then #(false, "o Merge nao foi do arquivo pedido: nada convertido.")
	else if proc.count > 0 then #(false, "o arquivo tem GrowFX/Forest Pack (procedural): so malha vira proxy. Ficou a malha.")
	else if geo.count == 0 then #(false, "nenhum objeto de malha entrou no Merge: nada a converter.")
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
			try (CProxy.ProxyFp.fromScene p #(n) f; okp = true) catch (e1 = getCurrentException())
			if not okp do try (p.ProxyFp.fromScene p #(n) f; okp = true) catch ()
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
			if doesFileExist alvo then
				#(true, "proxy criado: " + alvo + " (" + (proxies.count as string) + " objeto(s), " + (arquivos.count as string) + " .cproxy). Use Atualizar no Archiva.")
			else
				#(false, "o .max do proxy nao foi salvo em " + alvo + ". Os proxies ficaram na cena; a malha saiu.")
		)
	)
)
fn ArchivaProxyPost =
(
	local pedido = ArchivaProxyPasta + "\\$pedido"
	if doesFileExist pedido do
	(
		local linhas = #()
		local malha = ""
		try
		(
			local fs = openFile pedido
			if fs != undefined do (while not (eof fs) do append linhas (readLine fs); close fs)
			try (deleteFile pedido) catch ()
			if linhas.count >= 3 do malha = linhas[3]
			local agora = try (((dotNetClass "System.DateTimeOffset").UtcNow.ToUnixTimeSeconds()) as float) catch (0.0)
			local quando = try (linhas[1] as float) catch (undefined)
			if linhas.count < 3 or quando == undefined then
				format "-- Archiva: pedido de proxy ilegivel (ignorado).\n"
			else if agora > 0 and (agora - quando) > $validade then
				format "-- Archiva: pedido de proxy antigo (ignorado).\n"
			else
			(
				-- texturas primeiro (o .max do proxy sai com as texturas ja ligadas a pasta Maps do volume)
				try (if ArchivaRelink != undefined and ArchivaAvisos != undefined and (doesFileExist ArchivaAvisos[1]) do ArchivaRelink()) catch ()
				local r = ArchivaProxyFazer linhas[2] malha
				format "-- Archiva: %\n   %\n" (if linhas.count >= 4 then linhas[4] else malha) r[2]
				ArchivaProxyResposta (if r[1] then "ok" else "erro") malha r[2]
			)
		)
		catch
		(
			local e = getCurrentException()
			format "-- Archiva: erro ao criar o proxy: %\n" e
			ArchivaProxyResposta "erro" malha ("erro no 3ds Max: " + (e as string))
		)
	)
	ArchivaProxyMaxHandle = -1
	ok
)
callbacks.removeScripts id:#archivaProxy
callbacks.addScript #filePreMerge "ArchivaProxyPre()" id:#archivaProxy
callbacks.addScript #filePostMerge "ArchivaProxyPost()" id:#archivaProxy
ArchivaProxyMarca()
if ArchivaProxyCarregado != true do
(
	ArchivaProxyCarregado = true
	format "-- Archiva: proxy automatico da Vegetacao ativo.\n"
)
"""

PACKAGE_XML = """<?xml version="1.0" encoding="utf-8"?>
<ApplicationPackage SchemaVersion="1.0" AutodeskProduct="3ds Max" ProductType="Application" Name="ArchivaProxy"
    Description="Archiva: proxy automatico da Vegetacao" Author="Douglas Couto" AppVersion="1.0.0"
    ProductCode="{a3c51e7d-2f84-4b69-9d0e-71c6b5e2f834}" UpgradeCode="{e86f0b19-4d27-4c3a-b5e1-9a0d2c7f6b42}">
  <CompanyDetails Name="TILD" />
  <Components Description="post-start-up scripts parts">
    <RuntimeRequirements OS="Win64" Platform="3ds Max" SeriesMin="2018" SeriesMax="2035" />
    <ComponentEntry AppName="ArchivaProxy" Version="1.0.0" ModuleName="./Contents/archiva_proxy.ms" />
  </Components>
</ApplicationPackage>
"""


def script_text() -> str:
    pasta = _dir() or os.path.join(os.path.expanduser("~"), "AppData", "Local", "Archiva")
    return (STARTUP_SCRIPT.replace("$pasta", pasta).replace("$pedido", PEDIDO).replace("$resultado", RESULTADO)
            .replace("$carregado", CARREGADO).replace("$validade", str(VALIDADE)).replace("$versao", VERSAO_SCRIPT))


def instalar() -> bool:
    """Instala/atualiza o script do proxy (pacote do Max + startup de cada versão já usada). Idempotente."""
    text = script_text()
    ok = False
    base = os.environ.get("APPDATA")
    if sys.platform == "win32" and base:
        pkg = os.path.join(base, "Autodesk", "ApplicationPlugins", PACKAGE_NAME)
        try:
            max_startup._write_if_changed(os.path.join(pkg, "Contents", SCRIPT_NAME), text)
            max_startup._write_if_changed(os.path.join(pkg, "PackageContents.xml"), PACKAGE_XML, encoding="utf-8")
            ok = True
        except OSError:
            pass
    for d in max_startup.startup_dirs():
        try:
            max_startup._write_if_changed(os.path.join(d, SCRIPT_NAME), text)
            ok = True
        except OSError:
            continue
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
