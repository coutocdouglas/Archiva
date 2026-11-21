# Plano: aba Vegetação (aprovado em 2026-11-20)

Desenho das telas: https://claude.ai/artifact/675Hq5cGtudddEcRv8LqP3 (7 telas no canvas "Archiva — aba Vegetação").

## Regra de ouro
O programa atual funciona perfeitamente. Tudo da Vegetação entra em módulos novos, num branch próprio, sem alterar o comportamento da Biblioteca. Mexer em código existente só onde for inevitável (menu lateral, registro da aba), com teste antes e depois.

## Navegação (4 níveis)
Coleções (Globe Plants, Maxtree) → Volumes → Espécies → Arquivos (todas as opções da espécie). O arrasto para o Max sai dos cartões do nível 4. O painel lateral (320 px) mostra informações, tags, favorito e o seletor "Versão a importar" (Mesh | Proxy).

Primeira página: barra de busca por espécie em todas as coleções, faixa de Favoritos e cartões das coleções.

As coleções **nunca são procuradas automaticamente**: cada pessoa indica a pasta raiz de cada uma (Maxtree, Globe Plants) em "Adicionar coleção", porque nem todo mundo organiza a biblioteca assim. A lista fica em `%APPDATA%\GerenciadorAssets3D\vegetacao.json`; "Tirar da Vegetação" só esquece a pasta, não apaga nada.

## Padrão de leitura
- Acha todos os .max da coleção, recursivamente, e liga cada um à prévia. index.xml é a fonte principal (.max ↔ jpg ↔ objeto ↔ material); casamento por nome é o plano B.
- Funciona por conteúdo, não por posição de pasta (há pastas aninhadas em dobro; Vol 130 só tem .rar, mostrado como "compactado").
- Ignora: Thumbs.db (não apaga), índices de biblioteca vazios (New Library/index.xml), _DESCARTADOS.
- .rar ao lado de pasta extraída: só avisa, nunca apaga sozinho (reusar "Comparar pasta × compactado").
- Nomes Maxtree: MT_PM_V{vol}_{Genero_especie}_{variação}_{tamanho 01–06}.max. Capa da espécie = composição "…_01------03.jpg" se existir, senão miniatura do tamanho 03. Capa do volume = jpg ao lado da pasta (faltam nos Vol 017, 103, 130, 134; 032/033 só têm PDF).
- Formato do index.xml Maxtree: `<item class="maxobject"><name/><bitmap/><maxfile>.\x.max</maxfile><object/><matlib>…</matlib><material/></item>`. O Vol 148 não tem index.xml.
- Globe Plants Bundle 65: Forest Pack\Bundle65\object (99 .max), GrowFX (Corona/Vray), Mesh\Corona (15), Maps, Preview, PDF. Aqui o "volume" é o Bundle.

## Padrão de pastas (decidido em 2026-11-20)
Todo volume organizado fica assim. O leitor lê direto os volumes no padrão, e os que ainda não estão continuam sendo lidos pelo leitor flexível, com o selo "não organizado".

```
Maxtree - Plant Models Vol 071                ← pasta do volume (nome atual mantido)
├─ MT_PM_V071 - Mesh                          ← .max com o nome original + prévia .jpg com o mesmo nome
│   ├─ index.xml, matlib\, mtlib.ms           ← biblioteca Forest Pack, quando existe
│   └─ MT_PM_V071 - Proxy                     ← proxies (.cproxy/.cgeo + .max pequeno)
├─ MT_PM_V071 - Maps                          ← texturas
├─ MT_PM_V071 - PDF                           ← PDF do volume + capas das espécies (composições "_01------03", páginas do PDF)
├─ MT_PM_V071 - Outros                        ← tudo que não tem lugar no padrão
└─ archiva.json                               ← marca de organizado: versão do padrão, data, o que foi movido (para desfazer)
```

- **Prefixo**: Maxtree `MT_PM_V{vol com 3 dígitos}`; Globe Plants `GP_B{bundle com 3 dígitos}` (ex.: `GP_B065 - Mesh`). Mesma lógica nas duas coleções.
- **Mesh**: só as malhas que ficam depois das decisões da etapa 0. Cada .max com a prévia ao lado, com o mesmo nome. Se a prévia está em outra pasta (thumbnails, por espécie no Globe), ela é **copiada** para o lado do .max com o nome dele. **Cenas entram na Mesh quando são a única fonte de malha do volume** (Vol 001).
- **index.xml** fica na Mesh junto dos .max. No Maxtree os caminhos já são `.rquivo.max` e continuam valendo. No Globe o índice aponta para `object/…` e `thumbnails/…`: ao mover, o programa reescreve esses caminhos e guarda o original em Outros.
- **Outros**: GrowFX, bibliotecas de material (.mat), prévias de render soltas, FBX, textos, miniaturas que viraram cópia e tudo o mais. Na tela de organizar, cada item de Outros aparece **desmarcado (manter)**; só sai o que o usuário marcar, e sai para `_DESCARTADOS` com desfazer.
- **Ignorados**: Thumbs.db e desktop.ini ficam onde estão.
- Pastas aninhadas em dobro (`X\X`) somem na organização.
- Volume corrompido ou com compactado que não extraiu (Vol 130, 134) **não é organizado**; só aparece com o aviso.
- Texturas: depois de mover, o `archiva_texturas.ms` religa pelo nome procurando na pasta `- Maps` do volume. Testar num volume copiado antes de organizar os outros.

## Chaves estáveis
Favoritos e tags usam chave por coleção/volume/espécie (ex.: `veg:maxtree/071/phoenix-canariensis`), nunca o caminho do arquivo, para sobreviver à reorganização da etapa 2. Índice de vegetação separado do da Biblioteca, com versão própria.

## Etapas
| # | Etapa | Modelo |
|---|---|---|
| 0 | Relatório de leitura (sem interface): o que achou, ignorou, órfãos | Opus |
| 1 | Leitor + 4 níveis + busca por espécie, somente leitura | Opus |
| 2 | Organizar: pôr cada volume no **padrão de pastas** (seção abaixo). O que não tem lugar no padrão vai para `- Outros`, e o usuário escolhe manter ou descartar. Descartes das decisões da etapa 0 (versão repetida, cena em volume com malhas, V-Ray quando há Corona, compactado já extraído); gerar capa do jpg ou da página 1 do PDF (QtPdf); tudo que sai vai para _DESCARTADOS com tela de conferência, desfazer e modo simulação. Testar primeiro num volume copiado | Opus |
| 3 | Arrastar para o Max com as texturas da pasta Maps do volume, com o seletor de versão | Opus |
| 4 | Proxy automático (.cgeo + .max pequeno na pasta `- Proxy`, dentro da pasta `- Mesh` do volume) | Opus |
| 5 | Favoritos (plantas e volumes), tags e seção Vegetação na aba Tags | Sonnet |
| 6 | Futuro: escolher no arrasto criar Forest Pack ou Scatter a partir do bloco | Opus |

## Proxy
- Só na Vegetação; a Biblioteca não muda.
- Proxy é sempre selecionável e vem como padrão. Se ainda não existe, o painel avisa que será criado no momento do arrasto e salvo na pasta do volume. Mesh sempre importa o arquivo original.
- Cartões: selo "mesh" quando só há mesh; "mesh + proxy" quando o proxy existe.
- Só malha (mesh). GrowFX procedural fica fora. Exige Corona no Max.
- Usa o script de inicialização do Max (archiva_texturas.ms), que já religa texturas por nome; no arrasto de vegetação ele também deve procurar na pasta Maps do volume.
- Teste de proxy no Max do usuário deve ser feito cedo, em paralelo (pegar um .max de Phoenix e converter na mão).

## Decisões depois da etapa 0 (2026-11-20)
Respostas do usuário às perguntas de `docs/etapa0-conclusoes.md`. "Apagar" aqui sempre quer dizer **mover para `_DESCARTADOS`**, com a tela de conferência, o desfazer e o modo simulação da etapa 2. Nada é apagado de vez sem confirmação.

1. **Duas versões do mesmo modelo** (Vol 003, 004, 005: biblioteca Forest Pack × pasta Mesh/Corona): fica só uma, de preferência a da pasta **Corona**. A outra vai para `_DESCARTADOS` na etapa 2. Até lá, a etapa 1 mostra um cartão só, apontando para a versão Corona. Se só existir a versão V-Ray (Vol 036, 044), ela fica.
2. **Cenas**: se o volume **não** tem pasta de malhas (mesh V-Ray, mesh Corona ou Forest Pack), as cenas valem como itens, cada uma com a sua prévia (Vol 001: `sceneNN.max` ↔ `sceneNN_1.jpg`, `sceneNN_2.jpg`). Se o volume **tem** pasta de malhas e também pasta de cena, a pasta de cena vai para `_DESCARTADOS` (Vol 041 e 044). Conferido: ~95% das texturas de planta dessas cenas existem também no Maps do volume, com prefixo `MT_PM_V{n}_` em vez de `MT_`; o resto é chão/céu da cena. O Greenwall Set (Vol 010) não é cena: continua como conjunto.
3. **Vol 005 sem nomes**: o usuário pediu para buscar o nome de cada modelo no PDF, quando existir. Conferido: o `MT_PM_V5.pdf` é só imagem (sem texto) e cada página mostra apenas o código (`MT_PM_V5_18_01------03`), sem o nome da espécie. Fica como "Modelo 01…18". As páginas do PDF servem como capa de cada modelo (etapa 2).
4. **Compactados**:
   - já extraído, com as pastas de Maps e de malhas presentes → o compactado vai para `_DESCARTADOS` (vale para todos os que concluírem a extração);
   - não extraído → tentar extrair; se der erro, marcar o volume como **"corrompido ou fora do padrão"** e não mexer em mais nada;
   - extração e descarte são da etapa 2 (com simulação). Na etapa 0 os compactados só foram testados (`rar t` / `zipfile.testzip`, sem gravar nada); resultado em `docs/etapa0-conclusoes.md`.

## Etapa 2 entregue (2.0.16)
- `app/vegetacao/organizar.py`: planejar (simulação, só lê) › aplicar (move, nunca apaga; diário `archiva.json`) › desfazer (lê o diário de trás para a frente). Organização interrompida no meio deixa `archiva.json.parcial` e bloqueia uma nova até desfazer.
- `app/vegetacao/conferencia.py`: tela de conferência (Resumo, Outros com caixas — desmarcado = manter —, _DESCARTADOS com o motivo, todos os movimentos).
- `app/vegetacao/extrair.py`: extrai numa pasta temporária dentro do volume; deu certo → `archiva_extracao.json` com `ok`; deu erro → marca "corrompido ou fora do padrão" e apaga só a extração parcial.
- Capa do volume: 1ª página do PDF (QtPdf). Capa da espécie: composição `_01------03` › imagem com o nome da espécie (Vol 003–010) › `_PRV1` (Globe) › tamanho 03.
- Testado: organizar › ler › desfazer em todos os 24 volumes organizáveis (esqueleto) e no Bundle 65, cópias reais dos Vol 001 e 004 (byte a byte), extração de zip, rar em partes e rar corrompido, e o fluxo inteiro pela página.
- Ainda não feito: esvaziar `_DESCARTADOS` (apagar de vez) e organizar vários volumes de uma vez.

## Etapa 3 entregue (2.0.17)
- `app/vegetacao/arrastar.py` (sem Qt): decide o que vai para o Max e grava o aviso `ultimo_arrasto.txt` do `archiva_texturas.ms` (o mesmo da Biblioteca, sem mudança). O aviso leva a pasta do .max, a do proxy e **as pastas Maps do volume** com subpastas (critério do leitor: "maps" no caminho; sem Maps, todas as pastas do volume). Pula `_DESCARTADOS`, `- Outros` e extrações em andamento.
- `app/vegetacao/arrastar_ui.py`: seletor **Versão a importar** (Mesh | Proxy) no painel lateral e o arrasto dos cartões do nível 4 (só deles). A preferência fica em `%APPDATA%\GerenciadorAssets3D\vegetacao_arrasto.json`; padrão Proxy.
- Proxy: o .max pequeno numa pasta `… - Proxy` (ou `Proxy`) ao lado do .max da malha, **com o mesmo nome** do .max original; o `.cproxy` fica junto. O leitor agora liga esse .max ao arquivo (selo "mesh + proxy") e não o mostra como malha nova. Sem proxy pronto, Proxy leva a malha e o painel avisa. **A etapa 4 deve criar o proxy exatamente nesse lugar e com esse nome.**
- Os .max Maxtree/Globe guardam cada textura só pelo nome (stream `FileAssetMetaData3`) e trazem o material dentro (CoronaMtl/Multi), inclusive os da biblioteca Forest Pack; o `matlib\*.mat` não é necessário para o arrasto.
- Testado: leitura das duas coleções reais idêntica antes e depois da mudança no leitor (384 espécies, 2.331 arquivos); para todos os 2.323 .max com lista de texturas, **108.106 de 109.966 texturas (98,3%)** achadas pelo nome nas pastas do aviso. As que faltam não existem em lugar nenhum das coleções (Vol 130 incompleto, `UV_Checker.png`, cópias "- Copy"). Fluxo pela página numa cópia (volume não organizado e volume no padrão com `- Proxy`), todas as páginas abrindo.
- 2.0.18: na 2.0.17 o arrasto não começava (o modelo dos cartões não marcava `Qt.ItemIsDragEnabled`; o teste chamava `startDrag` direto e não pegou). Corrigido em `_CardModel.flags` e testado com eventos de mouse (apertar + mover): falhava na 2.0.17, funciona na 2.0.18. Testes de arrasto daqui em diante devem usar eventos de mouse.
- Não testado por mim: soltar de fato no 3ds Max (o 3dsmaxbatch pede a licença da Autodesk). O caminho é o mesmo da Biblioteca (Merge › `#filePostMerge` › religar as que faltam).
- Atenção para a etapa 4: o desfazer da organização (etapa 2) não conhece a pasta `- Proxy`; se ela for criada depois de organizar, o desfazer deve deixá-la (ou levá-la junto) sem perder os proxies.

## Pedidos para a próxima versão
- ✅ (2.0.16) **Seta de voltar no topo** da aba Vegetação (pedido do usuário depois da 2.0.15): ao lado das migalhas, uma seta "‹" que sobe um nível (arquivos › espécies › volumes › coleções › início). Na busca, volta para onde estava antes de buscar. Esconder no início.

## Pontos a validar
- Bibliotecas de material do Globe Plants: confirmar que as texturas estão embutidas no .max (conferido só no Vol 071).
- ✅ QtPdf empacotado no exe (2.0.16): os PDFs novos da Maxtree são protegidos (sem senha para abrir) e só o QtPdf desenha a 1ª página; se ele faltar, o Archiva tenta a primeira imagem JPEG do PDF.
- Forest Pack: provavelmente scriptável; Chaos Scatter: não confirmado.
- Favoritos pessoais por biblioteca; tags compartilhadas como as atuais.

## Versionamento
Cada atualização só muda o último número da versão. Quando uma mudança merecer 1.1.0 ou 2.0.0 (ou próximo minor/major), sugerir a numeração ao usuário em vez de escolher. O app dele recebe as atualizações direto do GitHub. **Decidido em 2026-11-20:** cada etapa pronta e testada vai para a `main` como versão nova (VERSION + seção no NOVIDADES.md), para chegar como atualização no Archiva instalado. Toda versão publicada chega a todos os computadores com o Archiva, então só vai para a `main` o que já foi testado (abrir o programa, outras páginas abrindo, a aba funcionando) e que não muda o comportamento da Biblioteca. O trabalho de cada etapa continua no branch `vegetacao` até ficar pronto.
