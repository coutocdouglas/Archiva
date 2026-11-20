# Etapa 0 — conclusões da leitura de F:\COLECOES (2026-11-20)

Leitura feita por `ferramentas/relatorio_vegetacao.py` (script novo, isolado, só biblioteca padrão; **somente leitura**, nenhum arquivo do F: foi alterado e nenhum código existente do Archiva foi tocado). O relatório completo, volume a volume, está em [relatorio-leitura-vegetacao.md](relatorio-leitura-vegetacao.md). Para gerar de novo:

```
py ferramentas/relatorio_vegetacao.py
```

## Números

| Coleção | Volumes | .max | Espécies | Sem prévia | Tamanho |
|---|---:|---:|---:|---:|---:|
| Maxtree | 28 (4 só compactados) | 2458 | 357 por volume / 335 distintas | 92 | 77,3 GB |
| Globe Plants | 1 (Bundle 65) | 144 | 15 | 0 | 14,3 GB |

Leitura das duas coleções em ~4 s (disco local). 17 espécies aparecem em mais de um volume (ex.: *Cocos nucifera* em 007, 015 e 148). A busca por espécie precisa agrupar esses casos, e a chave `veg:maxtree/{vol}/{espécie}` continua única.

## O que confirma o plano

- O index.xml é mesmo a melhor fonte quando existe: liga 1691 .max à prévia, com falha só no Vol 036 (6 bitmaps com nome sem `V36`, resolvidos pelo casamento "nome quase igual").
- O casamento por nome resolve sozinho os volumes sem index.xml (017, 023, 112, 125, 131, 148, 159).
- O formato do index.xml Maxtree é o descrito. O Globe usa `object/X.max` e o bitmap fica em `thumbnails/`.
- `New Library/index.xml` está vazio e é ignorado. Não existe nenhuma pasta `_DESCARTADOS` ainda.
- Globe Plants: Forest Pack (99, ligados pelo index.xml), GrowFX Corona/Vray (15+15) e Mesh Corona (15), com prévia por espécie (`Especie_PRV1.jpg`).

## O que corrige ou completa o plano

1. **Vol 130 não é "só .rar"**: tem pasta extraída (`Vol.130/Vol.130/…`, 72 .max Corona) **sem nenhuma miniatura**, e as 3 partes do .rar estão ao lado. A parte 2 é menor que a parte 1, e partes do meio deveriam ter o mesmo tamanho: **possível download incompleto** (não testei a extração). Capa só pelo PDF (etapa 2, QtPdf).
2. **Vol 134 só tem `part2.rar`**: falta a parte 1, não dá para extrair. Também não tem capa.
3. **Vol 103 e 033 só têm .rar** (103 tem o PDF dentro); **Vol 032 só tem .zip** (6 zips, inclusive FBX e GrowFX).
4. **Sem index.xml**: não é só o 148; também 017, 023, 112, 125, 130, 131 e 159.
5. **Capa do volume que falta**: 017 e 134. Os volumes 103 e 130 têm PDF dentro da pasta; 032 e 033 têm PDF ao lado.
6. **Padrão de nome `MT_PM_V{vol}_{Gênero_espécie}_{var}_{tam}` só vale do Vol 018 em diante.** Os mais antigos variam:
   - 003/004: espaço no lugar de `_` (`Anemone hupehensis`), um número só, e `_H`/`_L` (alta/baixa) no 003 e no 007;
   - 008/010: um número só (`_01`);
   - 009, 015, 017, 023: sem `V{vol}` (`MT_PM_Abies_concolor_01_01`);
   - **005: plantas só numeradas** (`MT_PM_V5_18_03`, 18 modelos), e o nome da espécie só existe no PDF;
   - 010: traz 36 arquivos `V4` e 18 `V8`. São versões diferentes (mesmo nome do 008, tamanho diferente), não cópias. Há um erro de digitação no 010 (`Hypoestes_phyllostachyaz_06.max`), por isso o index.xml aponta 2 arquivos que não existem;
   - capitalização varia entre volumes (`Asplenium Australasicum` × `australasicum`): a chave normaliza.
   - O leitor da etapa 1 precisa desse parser flexível (o do script já trata todos os casos acima).
7. **Capa da espécie por composição `_01------03`** só existe nos Vol 031, 034 e 071. Nos outros, a capa sai da miniatura do tamanho 03. No 003, 004, 007, 008 e 010 não há "tamanho", e a capa sai da primeira miniatura da espécie.
8. **Duas versões do mesmo modelo no mesmo volume** (003, 004, 005): a biblioteca Forest Pack e a pasta Mesh/Corona têm os mesmos nomes, mas tamanhos diferentes (são arquivos distintos). Ver pergunta 1.
9. **Volumes só V-Ray**: 036 e 044 (malhas), e as 9 cenas do Vol 001. Pela regra da etapa 2 ("descartar V-Ray só se houver Corona") esses ficam.
10. **Proxies que já existem**: Vol 004 tem 3 `.cproxy` (Rohdea japonica). As cenas do 041 e do 044 têm 56/50 `.cgeo` dentro de Maps.
11. **Outros conteúdos que não são espécie**: cenas (001, 041, 044) e o Greenwall Set do Vol 010 (5 painéis × Corona/V-Ray, prévias com outro nome). Ficam fora da contagem de espécies. Ver pergunta 2.
12. **Pastas aninhadas em dobro**: 031, 032, 044, 112, 125, 130, 148 e 159. A leitura por conteúdo resolve.
13. **Globe**: a prévia de *Acer platanoides Crimson King* tem o nome encurtado (`Acer-platanoides_PRV1.jpg`). O leitor aceita prefixo. Há um `Bundle65_Street_Trees_GFX.rar` (3 GB) ao lado da pasta extraída, e a regra é só avisar.
14. **Thumbs.db**: 39 no total, ignorados e não apagados.

## Perguntas para decidir antes da etapa 1

1. **Vol 003/004/005: Forest Pack × Mesh.** Mostrar como **um cartão** com as duas origens (escolher no painel) ou como **dois cartões** ("FP" e "Mesh")? Minha sugestão é um cartão, com a Mesh/Corona como padrão.
2. **Cenas e Greenwall** (Vol 001, 010, 041, 044): mostrar num grupo "Cenas e conjuntos" dentro do volume ou esconder?
3. **Vol 005 sem nomes**: exibir "Modelo 01…18" por enquanto, ou devo tentar tirar os nomes do PDF (`MT_PM_V5.pdf`) na etapa 2?
4. **Vol 130/134**: quer conferir os .rar (parte 2 do 130, parte 1 do 134 que falta) antes de seguir?
