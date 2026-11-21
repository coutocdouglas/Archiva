# Archiva — regras de trabalho

Responder sempre em português.

## Onde estamos
- Trabalho da Vegetação só na branch `vegetacao`. O plano e o histórico das etapas estão em
  `docs/plano-vegetacao.md` (ler antes de começar; a coluna "Modelo" diz o modelo de cada etapa).
- Versão atual: arquivo `VERSION`. Notas de cada versão: `NOVIDADES.md`.

## Regras de código
- Só módulos novos. Mexer no código existente apenas onde for inevitável (ex.: registrar a aba
  ou um botão), e nesse caso testar o comportamento antigo antes e depois da mudança.
- Quando eu disser "apagar" arquivos de uma coleção, isso significa mover para
  `<coleção>\_DESCARTADOS\<volume>` com simulação, conferência e desfazer — nunca apagar de vez.

## Testes
- Testar sempre em cópias (alguns volumes copiados para uma pasta temporária), nunca direto no `F:`.
- Rodar o app a partir do código com `APPDATA`, `LOCALAPPDATA` e `TEMP` apontando para uma pasta
  temporária (senão ele usa as configurações e o banco do Archiva instalado).
- Nenhuma janela na minha tela: Qt com `QT_QPA_PLATFORM=offscreen`. Nunca abrir o 3ds Max nem o
  `3dsmaxbatch.exe` (abre o aviso de licença); para conferir um `.max`, ler o arquivo com `olefile`.
  Se algo realmente precisar abrir na tela, perguntar antes.
- Python: usar `py` (o `python` é atalho da Store). Precisa de um venv com PySide6 + Pillow
  (+ olefile para os testes). Scripts de teste ficam no scratchpad da sessão.

## Entrega
- Etapa pronta e testada (o app abre, as outras páginas abrem, a novidade funciona) é entregue como
  atualização publicada: avançar a `main` até a `vegetacao`, subir o último número de `VERSION`,
  escrever a seção `## x.y.z` em `NOVIDADES.md` e dar push. O workflow "Publicar versão" gera o
  instalador e o Archiva instalado oferece "Atualizar". Não precisa perguntar o jeito de entregar;
  só avisar em uma linha que a versão chega a todos os PCs com Archiva. Sugerir (não escolher)
  quando valer subir o número do meio ou o primeiro.
- O git não tem identidade configurada: fazer commit com `-c user.name=... -c user.email=...`
  iguais aos dos commits anteriores. O `gh` não está instalado.

## Conversa
- Antes de cada etapa, dizer qual modelo é melhor para ela, com um motivo de uma linha
  (Opus para etapas que movem arquivos ou mexem com o 3ds Max; Sonnet para interface simples).
- Quando a conversa ficar grande, avisar e me dar a mensagem exata para abrir uma conversa nova
  (branch, versão atual, o que foi entregue, próxima etapa).
