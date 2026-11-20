# Plano: aba Vegetação (aprovado em 2026-11-20)

Desenho das telas: https://claude.ai/artifact/675Hq5cGtudddEcRv8LqP3 (7 telas no canvas "Archiva — aba Vegetação").

## Regra de ouro
O programa atual funciona perfeitamente. Tudo da Vegetação entra em módulos novos, num branch próprio, sem alterar o comportamento da Biblioteca. Mexer em código existente só onde for inevitável (menu lateral, registro da aba), com teste antes e depois.

## Navegação (4 níveis)
Coleções (Globe Plants, Maxtree) → Volumes → Espécies → Arquivos (todas as opções da espécie). O arrasto para o Max sai dos cartões do nível 4. O painel lateral (320 px) mostra informações, tags, favorito e o seletor "Versão a importar" (Mesh | Proxy).

Primeira página: barra de busca por espécie em todas as coleções, faixa de Favoritos e cartões das coleções.

## Padrão de leitura
- Acha todos os .max da coleção, recursivamente, e liga cada um à prévia. index.xml é a fonte principal (.max ↔ jpg ↔ objeto ↔ material); casamento por nome é o plano B.
- Funciona por conteúdo, não por posição de pasta (há pastas aninhadas em dobro; Vol 130 só tem .rar, mostrado como "compactado").
- Ignora: Thumbs.db (não apaga), índices de biblioteca vazios (New Library/index.xml), _DESCARTADOS.
- .rar ao lado de pasta extraída: só avisa, nunca apaga sozinho (reusar "Comparar pasta × compactado").
- Nomes Maxtree: MT_PM_V{vol}_{Genero_especie}_{variação}_{tamanho 01–06}.max. Capa da espécie = composição "…_01------03.jpg" se existir, senão miniatura do tamanho 03. Capa do volume = jpg ao lado da pasta (faltam nos Vol 017, 103, 130, 134; 032/033 só têm PDF).
- Formato do index.xml Maxtree: `<item class="maxobject"><name/><bitmap/><maxfile>.\x.max</maxfile><object/><matlib>…</matlib><material/></item>`. O Vol 148 não tem index.xml.
- Globe Plants Bundle 65: Forest Pack\Bundle65\object (99 .max), GrowFX (Corona/Vray), Mesh\Corona (15), Maps, Preview, PDF. Aqui o "volume" é o Bundle.

## Chaves estáveis
Favoritos e tags usam chave por coleção/volume/espécie (ex.: `veg:maxtree/071/phoenix-canariensis`), nunca o caminho do arquivo, para sobreviver à reorganização da etapa 2. Índice de vegetação separado do da Biblioteca, com versão própria.

## Etapas
| # | Etapa | Modelo |
|---|---|---|
| 0 | Relatório de leitura (sem interface): o que achou, ignorou, órfãos | Opus |
| 1 | Leitor + 4 níveis + busca por espécie, somente leitura | Opus |
| 2 | Organizar: descartar V-Ray (só se houver Corona), lixo e bibliotecas de material; gerar capa do jpg ou da página 1 do PDF (QtPdf); tudo vai para _DESCARTADOS com tela de conferência, desfazer e modo simulação. Testar primeiro num volume copiado | Opus |
| 3 | Arrastar para o Max com as texturas da pasta Maps do volume, com o seletor de versão | Opus |
| 4 | Proxy automático (.cgeo + .max pequeno em `_PROXY` dentro da pasta do volume) | Opus |
| 5 | Favoritos (plantas e volumes), tags e seção Vegetação na aba Tags | Sonnet |
| 6 | Futuro: escolher no arrasto criar Forest Pack ou Scatter a partir do bloco | Opus |

## Proxy
- Só na Vegetação; a Biblioteca não muda.
- Proxy é sempre selecionável e vem como padrão. Se ainda não existe, o painel avisa que será criado no momento do arrasto e salvo na pasta do volume. Mesh sempre importa o arquivo original.
- Cartões: selo "mesh" quando só há mesh; "mesh + proxy" quando o proxy existe.
- Só malha (mesh). GrowFX procedural fica fora. Exige Corona no Max.
- Usa o script de inicialização do Max (archiva_texturas.ms), que já religa texturas por nome; no arrasto de vegetação ele também deve procurar na pasta Maps do volume.
- Teste de proxy no Max do usuário deve ser feito cedo, em paralelo (pegar um .max de Phoenix e converter na mão).

## Pontos a validar
- Bibliotecas de material do Globe Plants: confirmar que as texturas estão embutidas no .max (conferido só no Vol 071).
- QtPdf empacotado no exe.
- Forest Pack: provavelmente scriptável; Chaos Scatter: não confirmado.
- Favoritos pessoais por biblioteca; tags compartilhadas como as atuais.

## Versionamento
Cada atualização só muda o último número da versão. Quando uma mudança merecer 1.1.0 ou 2.0.0 (ou próximo minor/major), sugerir a numeração ao usuário em vez de escolher. O app dele recebe as atualizações direto do GitHub, então nada vai para a `main` antes de a Biblioteca ser testada e aprovada por ele.
