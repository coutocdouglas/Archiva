"""Etapa 6: ao soltar a planta no 3ds Max, criar também um Forest Pack ou um Chaos Scatter com ela (2.0.27).

Decidido com o usuário (2026-11-22):
  * o objeto Forest/Scatter nasce **vazio** (sem superfície nem área), no ponto onde o mouse soltou, com a planta
    já carregada como item/modelo; a superfície e a área a pessoa escolhe depois, no painel do plugin;
  * o modelo da planta **fica visível na cena**, como num arrasto normal (Mesh ou Proxy, o que foi escolhido).

Nem a Itoo nem a Chaos publicam referência de MAXScript. Os nomes usados vêm dos próprios plugins instalados
(cadeias de texto do ForestPackPro.dlo e do ScatterMax_Release-2024.dll, e o forestpack.ms que acompanha o Forest
Pack, onde `cobjlist` e `namelist` andam juntos, um por item):
  * Forest Pack: classe `Forest_Pro`; itens em `cobjlist` (nós), `namelist`, `problist`, `geomlist`.
  * Chaos Scatter: classe `ChaosScatter`; modelos em `modelNodes` (ou `models`), `modelFrequencies`.
Por isso o script é defensivo: tenta cada nome com `hasProperty`, nunca deixa um erro desfazer o Merge e, na 1ª vez
de cada sessão do Max, mostra no Listener (F11) as propriedades do objeto criado (`showProperties`) e o que foi
gravado, para conferir. Este módulo não usa Qt.
"""
from __future__ import annotations

NADA = "nada"
FOREST = "forest"
SCATTER = "scatter"
OPCOES = (NADA, FOREST, SCATTER)
ROTULO = {NADA: "Só o modelo", FOREST: "Forest Pack", SCATTER: "Chaos Scatter"}
CURTO = {NADA: "Nada", FOREST: "Forest", SCATTER: "Scatter"}      # no seletor do painel (320 px)

# Funções MAXScript coladas no script do arrasto (proxy.SOLTAR_SCRIPT). Devolvem #(ok?, mensagem).
FUNCOES = r"""
	-- etapa 6: o que vira item/modelo do Forest/Scatter (um nó; vários objetos soltos viram um grupo)
	fn fonteDoEspalhamento nos nome =
	(
		local vivos = for o in nos where (isValidNode o) collect o
		local topo = for o in vivos where o.parent == undefined or (findItem vivos o.parent) == 0 collect o
		if topo.count == 1 then topo[1]
		else if topo.count == 0 then undefined
		else (group topo name:(uniqueName (nome + " ")) select:false)
	)

	fn mostrarPropsUmaVez obj chave =
	(
		global ArchivaEspalharVistos
		if ArchivaEspalharVistos == undefined do ArchivaEspalharVistos = #()
		if (findItem ArchivaEspalharVistos chave) == 0 do
		(
			append ArchivaEspalharVistos chave
			format "   propriedades de % (para conferir; mande isto se algo nao ficou certo):\n" ((classOf obj) as string)
			try (showProperties obj) catch ()
		)
	)

	fn tentarProp obj nomes valor =
	(
		local feito = undefined
		for nm in nomes where feito == undefined and (hasProperty obj nm) do
			try (setProperty obj nm valor; feito = nm) catch ()
		feito
	)

	-- 2.0.32: o icone do Forest/Scatter com 2x o tamanho da planta (a maior medida dela), para ficar visivel
	fn tamanhoIcone obj fonte =
	(
		local d = try (fonte.max - fonte.min) catch ([0, 0, 0])
		local t = amax #(d.x, d.y, d.z)
		if t > 0 then
		(
			local usado = tentarProp obj #(#iconSize, #iconsize, #icon_size) (t * 2.0)
			format "   icone: % = % (2x a planta, que mede %)\n" usado (t * 2.0) t
			usado
		)
		else undefined
	)

	fn criarForest fonte pt nome =
	(
		local f = undefined
		local erro = ""
		if Forest_Pro == undefined then erro = "Forest Pack nao encontrado neste 3ds Max: ficou so o modelo."
		else try (f = Forest_Pro()) catch (erro = "o Forest Pack nao criou o objeto (" + (getCurrentException()) + "). Ficou so o modelo.")
		if f != undefined do
		(
			mostrarPropsUmaVez f #forest
			local n0 = try (f.cobjlist.count) catch (0)
			if (tentarProp f #(#cobjlist) #(fonte)) == undefined then
			(
				try (delete f) catch ()
				f = undefined
				erro = "o Forest Pack nao aceitou a planta como item (cobjlist). Ficou so o modelo."
			)
			else
			(
				-- as outras listas por item ficam com 1 elemento (o 1o, padrao do plugin), sem sobras de itens de exemplo
				if n0 > 1 do for nm in (getPropNames f) where nm != #cobjlist and (matchPattern (nm as string) pattern:"*list") do
				(
					local v = try (getProperty f nm) catch (undefined)
					if classOf v == Array and v.count == n0 do try (setProperty f nm #(v[1])) catch ()
				)
				tentarProp f #(#namelist) #(nome)
				tentarProp f #(#problist) #(100)
				-- tipo do item "objeto proprio" (custom object): os valores do geomlist nao sao documentados;
				-- o Listener mostra o antes e o depois para conferir
				local g = try (f.geomlist) catch (undefined)
				format "   Forest: geomlist antes = %\n" g
				if classOf g == Array and g.count >= 1 do try (f.geomlist = #(2)) catch ()
				f.name = uniqueName ("Archiva Forest " + nome + " ")
				if pt != undefined do f.pos = pt
				tamanhoIcone f fonte
				try (fonte.layer.addNode f) catch ()
				format "   Forest: itens = %, nomes = %, geomlist = %\n" (try (f.cobjlist) catch ("?")) (try (f.namelist) catch ("?")) (try (f.geomlist) catch ("?"))
			)
		)
		if f == undefined then #(false, erro)
		else
		(
			select f
			#(true, "Forest Pack criado: " + f.name + " (sem superficie: escolha a superficie/area no painel do Forest).")
		)
	)

	fn criarScatter fonte pt nome =
	(
		local s = undefined
		local erro = ""
		if ChaosScatter == undefined then erro = "Chaos Scatter nao encontrado neste 3ds Max: ficou so o modelo."
		else try (s = ChaosScatter()) catch (erro = "o Chaos Scatter nao criou o objeto (" + (getCurrentException()) + "). Ficou so o modelo.")
		if s != undefined do
		(
			mostrarPropsUmaVez s #scatter
			local usado = tentarProp s #(#modelNodes, #models, #instances, #instanceNodes) #(fonte)
			if usado == undefined then
			(
				try (delete s) catch ()
				s = undefined
				erro = "o Chaos Scatter nao aceitou a planta como modelo. Ficou so o modelo."
			)
			else
			(
				tentarProp s #(#modelFrequencies) #(100.0)
				s.name = uniqueName ("Archiva Scatter " + nome + " ")
				if pt != undefined do s.pos = pt
				tamanhoIcone s fonte
				try (fonte.layer.addNode s) catch ()
				format "   Scatter: modelos em % = %\n" usado (try (getProperty s usado) catch ("?"))
			)
		)
		if s == undefined then #(false, erro)
		else
		(
			select s
			#(true, "Chaos Scatter criado: " + s.name + " (sem superficie: escolha a superficie/area no painel do Scatter).")
		)
	)

	fn criarEspalhamento modo nos pt nome =
	(
		local fonte = fonteDoEspalhamento nos nome
		if fonte == undefined then #(false, "nenhum objeto para espalhar.")
		else if modo == "forest" then criarForest fonte pt nome
		else if modo == "scatter" then criarScatter fonte pt nome
		else #(true, "")
	)
"""


def valido(modo: str | None) -> str:
    return modo if modo in OPCOES else NADA
