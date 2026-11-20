# Novidades do Archiva

Cada versão tem uma seção `## x.y.z`. O texto da seção aparece na página da versão no GitHub e no aviso de atualização.

## 2.0.15
- **Nova aba Vegetação** (no menu lateral, abaixo de Biblioteca). Mostra as coleções de plantas em quatro níveis: **coleções › volumes › espécies › arquivos**. Cada espécie tem sua capa e cada arquivo a sua prévia, com o tamanho e o selo **mesh** ou **mesh + proxy**. O painel da direita traz o renderizador, o tamanho do arquivo e os botões **Mostrar na pasta** e **Abrir o PDF do volume**.
- **Busca por espécie** em todas as coleções, sem se importar com acentos ou maiúsculas (por exemplo, `phoenix cana`), com filtro por coleção.
- **Você escolhe as pastas.** Nada é procurado sozinho: clique em **Adicionar coleção** e indique a pasta raiz de cada coleção (a do Maxtree, a do Globe Plants). **Tirar da Vegetação** (botão direito no cartão) só esquece a pasta, sem apagar nada.
- Nesta versão a aba **só lê** as pastas; nada é movido nem apagado. Volumes ainda compactados ou corrompidos aparecem com aviso. Arrastar para o 3ds Max, organizar os volumes, proxies, favoritos e tags chegam nas próximas versões.

## 2.0.14
- **Nuvem: bolinha de online/offline.** Cada biblioteca da Nuvem mostra uma bolinha **verde (online)** ou **vermelha (offline)**, na lista de bibliotecas, logo abaixo do nome da biblioteca aberta e no menu da seta ▾. Online quer dizer que o computador da biblioteca está ligado, com o Archiva aberto e respondendo; offline, que ele está desligado, sem internet, com o Archiva fechado ou que o convite foi revogado (passe o mouse na bolinha para ver). Cinza = verificando. A conferência é automática, a cada 20 s, e a lista na tela avisa quando a conexão cai ou volta.

## 2.0.13
- **Prévia vinda do 3DSKY.** Se o bloco não tem imagem e o Archiva acha o modelo no 3DSKY pelo código, a imagem principal da página vira a prévia do bloco (`NOME.jpg` ao lado dele). Na Entrada isso é automático quando o código confere com a página; em **Propriedades** aparece a caixa "Usar a imagem da página como prévia deste bloco" (marcada quando o código confere; nos outros casos você marca depois de conferir a imagem); no **lote** também. Nunca substitui uma prévia que já existe.
- **O atalho da Área de Trabalho não muda mais de lugar.** O instalador só cria o atalho se ele ainda não existir; atualizar não o recria. (Ao instalar esta versão ele ainda pode se mexer uma última vez.)

## 2.0.12
- **Origem na Entrada.** Ao classificar um bloco cujo nome de arquivo é um código do 3DSKY (como `9332998.6af59838593cc`), o Archiva procura o modelo no site sozinho, em segundo plano (a classificação não espera pela internet), e grava a origem só quando o código confere com a página. Os que não conferem ficam sem origem, para você ver em Propriedades. A barra de baixo mostra quantos foram preenchidos.
- **Origem… no painel da Entrada.** Para blocos sem código, selecione um e clique em **Origem…**: busca por imagem no Google ou link da página, você confere e a ficha vai junto quando o bloco for classificado. É opcional.
- Há uma caixa para desligar a busca automática pelo código. A forma de classificar e numerar os blocos não mudou. Só o administrador registra a origem.

## 2.0.11
- **Busca por imagem simplificada.** Em Propriedades › Origem, o botão agora é **Buscar por imagem no Google** (todas as páginas que o Google achar para a prévia). A opção focada no Design Connected foi escondida por enquanto, até ser afinada; a busca pelo código do 3DSKY continua como está.

## 2.0.10
- **Origem pelo código do 3DSKY.** O arquivo baixado do 3DSKY tem como nome um código (como `9332998.6af59838593cc`). Em **Propriedades › Origem**, o botão **Buscar pelo código** procura esse código no site, abre a página do modelo e só dá como certo se o mesmo código aparecer nas imagens dela. Preenche nome original, link, código e autor; você confere e salva. O botão aparece nos blocos cujo nome original a Entrada guardou (a maioria dos que você classificou pelo Archiva).
- **Em lote.** Selecione vários blocos (Ctrl+A na categoria) › botão direito › **Preencher origem pelo código guardado…**: o Archiva procura um por um, devagar, mostra a lista (achado e conferido / conferir à mão / não achado) e só grava os conferidos quando você clicar em Gravar. Se o 3DSKY recusar os pedidos, ele para sozinho.
- **Buscar por imagem.** Para blocos sem código (Design Connected e outros sites): **Buscar por imagem › Google · Design Connected** (só páginas desse site) ou **Google · geral**. Usa a mesma chave da Google Cloud Vision da busca de prévias. Você escolhe a página, e a imagem dela aparece ao lado da prévia para conferir antes de salvar.
- **Outros sites.** Colar o link da página de qualquer site agora também funciona (lê nome e imagem); a ficha guarda o site (3DSKY, Design Connected ou outro).
- A janela Propriedades agora rola quando a tela é pequena, com os botões sempre à vista.

## 2.0.9
- **Propriedades do bloco.** Botão direito no modelo › **Propriedades…** mostra o que o Archiva já sabe do item (nome, categoria, tipo, tamanho do arquivo, prévia, variações, data, tags e coleções) e a seção **Origem · 3DSKY**.
- **Origem do 3DSKY.** Cole o link da página (ou o da imagem) do modelo no 3dsky.org e clique em **Carregar**: o Archiva lê a página e preenche o **nome original**, o **link**, o **código da primeira imagem** (ex.: 8765287.69ff9ae40ba89) e o **autor**. Confira e salve. Se o site não responder, o link fica preenchido e você completa o nome e o código à mão.
- **A ficha fica com o bloco.** É guardada junto das tags (no `_ARCHIVA`), vai com a biblioteca para outro computador e acompanha o item ao renomear, mover, excluir e desfazer. Nenhum arquivo novo é gravado nas pastas dos modelos e a forma de classificar e organizar não mudou.
- **Busca.** A busca da Biblioteca também acha pelo nome original, pelo link, pelo código (inteiro ou só o número, como 8765287) e pelo autor.
- Só o administrador registra a origem; os demais podem consultar.

## 2.0.8
- **Nuvem: a primeira tela é a lista de bibliotecas.** Ao clicar em Nuvem você vê as bibliotecas conectadas (com **Abrir** e **Remover**) e o botão **Entrar com um convite…**. Só depois de escolher uma biblioteca aparecem os modelos. Dentro dela, a seta ▾ no alto tem **Todas as bibliotecas** para voltar à lista.

## 2.0.7
- **A Nuvem agora é uma aba da própria Biblioteca.** Acabou a tela inicial "Local ou Nuvem": o Archiva abre como sempre e, no menu lateral, **Nuvem** mostra a biblioteca online (use a seta ▾ no alto para trocar de biblioteca, entrar com um convite, ver o diagnóstico ou remover).
- **Mesmo visual da Biblioteca:** categorias com miniatura e subpastas, cartões, painel de detalhes com prévia grande, busca e controle do tamanho dos cartões.
- **Espaço amplia a prévia**, como na Biblioteca (também clique na prévia ou dois cliques no cartão).
- **Copiar para a minha biblioteca** (botão direito no modelo, ou o botão do painel; dá para selecionar vários): o arquivo e a prévia vão para a pasta **Entrada** com o nome `archiva_transfer_N`, e depois você classifica na aba Entrada como qualquer download. Nada é sobrescrito: se o número já existe, usa o próximo.
- **Removido:** arrastar direto para o 3ds Max e o "Baixar/Tirar do PC" da Nuvem. O caminho agora é copiar para a sua biblioteca e usar a Biblioteca normal.
- Tutoriais da Nuvem em Aprender atualizados.

## 2.0.6
- **Tutoriais da Nuvem em Aprender.** Dois tutoriais novos, no grupo **Biblioteca na Nuvem**, cada um com animação das telas reais:
  - **Acessar uma biblioteca da Nuvem** (para quem recebe o convite): abrir Nuvem, colar a linha ARCHIVA2-…, esperar a primeira conexão, baixar e arrastar para o 3ds Max.
  - **Compartilhar a sua biblioteca** (para quem tem a biblioteca): ligar o compartilhamento, salvar a chave de acesso do Tailscale, criar o convite e revogar.
- A tela **Nuvem** vazia agora indica onde está o passo a passo (Aprender › Acessar uma biblioteca da Nuvem).

## 2.0.5
- **Nuvem: corrigido o "Bad Gateway" ao abrir a biblioteca.** O Archiva pedia a lista cedo demais, antes de a conexão com o computador da biblioteca estar pronta, e a primeira tentativa falhava. Agora ele espera a rede entrar e achar o computador (mostrando "Entrando na rede…" / "Procurando o computador da biblioteca…"), tenta de novo se a primeira conversa falhar e, se a rede ficar pronta depois de uma falha, abre sozinho.
- A mensagem de erro agora traz o motivo detalhado vindo do motor de rede.

## 2.0.4
- **Nuvem: convite sem chave não passa mais despercebido.** Ao criar um convite sem a chave de acesso do Tailscale salva, o Archiva pergunta se você quer **colar a chave agora**, criar sem ela ou cancelar. O botão **Chave de acesso do Tailscale ✔** mostra que a chave está salva, e o convite criado diz em verde que "leva a chave de acesso" (a pessoa entra sem precisar de conta).
- **Para quem recebe:** se o convite veio sem chave (ou ela expirou), a tela explica em português que é preciso pedir um convite novo a quem compartilha, e que não é necessário ter conta do Tailscale. Entrar com uma conta continua possível como alternativa.

## 2.0.3
- **Nuvem: a mensagem de erro não some mais.** Antes, depois de uma falha ao abrir a biblioteca, um aviso de andamento apagava a mensagem de erro e a tela parecia travada. Agora o erro fica na tela, com o detalhe (por exemplo "este convite não vale mais", ou o tipo de falha de conexão), e vai também no relatório do Diagnóstico.
- Ajuste interno na ligação do motor de rede ao computador da biblioteca.

## 2.0.2
- **Nuvem: o aviso na tela não fica mais parado.** Enquanto a lista de modelos não chega, a tela mostra o passo atual (ligando o motor de rede, falando com o computador da biblioteca, baixando a lista) e os segundos, em vez de um "Conectando…" antigo.
- **Diagnóstico da conexão com teste:** o botão agora também testa, na hora, o caminho até o computador da biblioteca (quanto tempo leva para achar, abrir a conexão e receber a resposta, e em qual passo dá erro). O relatório mostra se cada computador está conectado direto ou por retransmissão.

## 2.0.1
- **Nuvem: diagnóstico da conexão.** Quando a biblioteca não abre, a tela agora diz o motivo em vez de ficar só em "Conectando…": mostra em qual rede o computador entrou, quais computadores do Archiva ele enxerga e há quantos segundos tenta entrar. Se os dois computadores estiverem em contas diferentes do Tailscale, o aviso explica isso e o que fazer.
- **Botão Diagnóstico da conexão…** (dentro da biblioteca da Nuvem): mostra um relatório para copiar e mandar a quem dá o suporte (sem chaves nem convites) e tem **Sair da conta e entrar de novo**, para trocar a conta do Tailscale usada naquele computador.
- **Convite revogado some da lista.** Ao revogar um convite em Compartilhar pela Nuvem, o convidado é removido da lista (antes ficava marcado como "revogado"). A chave dele deixa de valer na hora. Os que já estavam marcados como revogados também saem.
- **Conexão com limite de espera:** o motor de rede desiste de procurar o computador da biblioteca em 20 s em vez de ficar esperando.

## 2.0.0
- **Nuvem: bibliotecas de outros computadores.** O Archiva agora acessa a biblioteca de outro computador pela internet, sem instalar nada além do Archiva. A rede (Tailscale) vem embutida no instalador e roda dentro do programa, sem VPN, serviço ou administrador.
- **Quem compartilha:** em Configurações › Biblioteca › **Compartilhar pela Nuvem…**, ligue o compartilhamento (vale enquanto o Archiva estiver aberto neste computador), entre na conta do Tailscale uma vez e crie um **convite** para cada pessoa. O convite é uma linha de texto para mandar por WhatsApp ou e-mail, e pode ser **revogado** a qualquer momento.
- **Quem recebe:** no menu lateral, **Nuvem › Entrar com um convite**, cole a linha e pronto. A biblioteca aparece com categorias, busca, tags e prévias. **Baixar** (ou dois cliques) traz o modelo para este computador, já extraído, e o cartão pode ser **arrastado para o 3ds Max**, com as texturas religadas como na Biblioteca.
- **Só leitura de verdade:** quem acessa de fora não apaga, move, classifica nem extrai nada na biblioteca de origem. A regra é aplicada no computador que compartilha, não no de quem acessa.
- **Funciona desligado:** a lista e as prévias já vistas ficam guardadas, e os modelos baixados continuam disponíveis mesmo com o outro computador desligado.
- **Tela inicial:** quem tem uma biblioteca da Nuvem salva escolhe ao abrir entre **Neste computador** e **Nuvem**. Quem não usa a Nuvem abre direto na biblioteca, como antes.

## 1.2.10
- **Organizar pasta com arquivo em uso:** quando o Windows recusava mover uma textura ("O arquivo já está sendo usado por outro processo", WinError 32), o programa desistia na hora. Agora ele **tenta de novo por alguns segundos** (antivírus e miniaturas do Explorer costumam soltar o arquivo logo) e só então desiste.
- **Mensagem clara:** se o arquivo continuar preso, o aviso diz qual arquivo é, **qual programa deste computador está com ele aberto** (quando o Windows informa, ex.: 3ds Max ou Windows Explorer) e o que fazer. Como antes, nada é alterado: tudo volta ao lugar.

## 1.2.9
- **Possível correção da queda ao clicar em certos modelos:** o registro da 1.2.8 mostrou um "stack overflow" (recursão infinita) do Qt logo depois de montar o painel de detalhes. A causa mais provável é a barra de rolagem do painel, que aparecia e sumia em ciclo com textos que quebram linha. Agora a barra fica sempre presente (o fio some quando não há o que rolar), o que impede esse ciclo. **Ainda não confirmado no Windows.**
- **Registro mais detalhado:** além da última ação, ele guarda as 8 últimas (com a hora) e, ao montar o painel de um modelo, anota quantas tags, coleções e variações ele tem e o tamanho do painel. Se ainda cair, o registro mostra se foi durante a montagem ou depois, no layout.

## 1.2.8
- **Registro de falhas (Configurações › Diagnóstico):** se o programa fechar sozinho, sem mensagem, agora ele deixa um registro do que aconteceu. Ele guarda a falha interna do Qt (com o que o programa estava fazendo), erros do Python, avisos do Qt e a **última ação** antes da queda, como o modelo que foi clicado e o estado da prévia dele. Na abertura seguinte, o registro avisa "QUEDA DETECTADA" e mostra essa última ação.
- **Como usar:** em Configurações › Diagnóstico, **Salvar registro…** copia o arquivo para a pasta que você escolher (padrão: Downloads), pronto para enviar. **Abrir pasta** mostra onde ele fica e **Limpar** zera o registro. O arquivo é `registro.log`, em %APPDATA%\GerenciadorAssets3D, e não passa de cerca de 1 MB.

## 1.2.7
- **Categorias fixadas no topo:** clique com o botão direito numa categoria (ou subpasta) e escolha "Fixar no topo". Ela ganha um atalho na seção "Fixadas", logo abaixo de "Todas as categorias", na ordem em que você fixou, e continua também na lista completa. Para tirar, botão direito e "Desafixar do topo". Subpasta fixada mostra o caminho (ex.: Luminárias › Pendente).
- **É só seu:** as fixadas ficam guardadas neste computador, por biblioteca, e não aparecem para o resto da equipe. Se você esconder uma pasta em "Pastas visíveis", ela some da seção, mas a escolha é lembrada para quando voltar a mostrar.
- Enquanto você digita no filtro de categorias, a seção "Fixadas" fica escondida para a busca mostrar só a lista completa.

## 1.2.6
- **Nova barra de categorias na Biblioteca:**
  - **Miniatura em cada pasta:** a prévia mais recente da categoria aparece num quadradinho ao lado do nome, com a quantidade de itens à direita. A linha "Todas as categorias" ganhou um ícone de grade.
  - **Filtro no topo:** digite para achar uma categoria (sem diferenciar acento ou maiúscula). Se uma subpasta combina, a pasta de cima continua visível, e se a pasta combina, as subpastas aparecem. Esc limpa o filtro.
  - **Subpastas que abrem e fecham:** só as pastas que têm subpastas (como Luminárias) ganham a setinha. Elas começam fechadas, abrem sozinhas quando você vai até uma subpasta, e o que você abriu ou fechou fica lembrado.
  - A coluna ficou um pouco mais larga (mínimo de 256 px) para caber miniatura, nome e quantidade.
- **Tags em chips:** no lugar da lista com caixinhas, cada tag é um botão arredondado com a quantidade dentro, que quebra de linha. Marcada, ganha contorno dourado e um visto. Aparecem as 10 tags mais usadas (mais as que estiverem marcadas); "ver todas…" abre a lista completa, com busca. O filtro funciona como antes: o item precisa ter todas as tags marcadas.

## 1.2.5
- **A janela principal só abre com a biblioteca toda carregada.** Antes, com o índice salvo, ela aparecia na hora e ainda ficava conferindo o disco por baixo. Agora a tela de abertura espera a leitura e a conferência terminarem, e o programa abre completo.
- **A abertura mostra o que está fazendo:** "Lendo as tags e o histórico da equipe", "Lendo Poltronas · 4 de 41", "Conferindo o que mudou na biblioteca", "Montando a tela". A linha de baixo avança de verdade conforme as etapas. Só se algo travar por mais de 1 minuto o programa abre mesmo assim.
- **Cadeado nos modelos em uso por outra pessoa:** um véu cinza com um cadeado branco aparece sobre a prévia (na Biblioteca, nas Tags, nas Coleções e na Entrada) enquanto outra pessoa extrai, organiza ou mexe no item. Quando ela termina, o cadeado some sozinho. Ao passar o mouse, a dica mostra quem está usando, em qual computador e desde que horas. Item em uso não pode ser arrastado para o Max.
- **Painel de detalhes também nas Tags:** ao clicar num modelo dentro de uma tag, o painel da direita (prévia, extrair, tags, coleções, variações) aparece ali mesmo, sem precisar ir até o local do modelo na Biblioteca. Adicionar ou tirar tags pelo painel atualiza a galeria e mantém a seleção.
- Corrigido: na primeira leitura da biblioteca (e no F5) o índice local não era salvo na hora, só ao fechar o programa; se o programa fechasse de forma inesperada, a próxima abertura leria tudo de novo (ou, no F5, usaria uma lista desatualizada).

## 1.2.4
- **Organizar, Mover para… e Juntar pastas sem congelar:** os arquivos são movidos em segundo plano, com uma janela de andamento. Antes, a janela ficava parada com o cursor de espera até terminar (vários segundos com muitos itens). Travas, histórico e desfazer funcionam como antes.
- Atualizar prévia e Comparar pasta e compactado também mostram andamento em vez de travar.
- **Tags mais rápidas:** levar as tags junto ao mover itens ficou mais de 100 vezes mais rápido, e remontar as tags da equipe ficou cerca de 9 vezes mais rápido e acontece em segundo plano. Isso acontecia sozinho quando duas pessoas gravavam tags quase ao mesmo tempo, e travava a janela por 1 a 2 segundos (mais, com o tempo).
- Abrir a biblioteca pela primeira vez num computador não trava mais: a janela abre e as tags aparecem logo em seguida.
- **Histórico abre na hora:** a conferência de "dá para desfazer?" é feita em segundo plano, de cima para baixo.
- Corrigido: depois de Juntar pastas, a categoria que saiu podia continuar aparecendo vazia na lista até atualizar.

## 1.2.3
- **Extrair, mover e classificar sem engasgos:** depois de cada item pronto, o Archiva relê só aquele item, e não a categoria inteira. Num lote de 20 extrações na rede, a janela deixava de responder por uns 7 segundos no total; agora não trava.
- **Leitura da biblioteca até 10 vezes mais rápida:** o Atualizar (F5) e a primeira abertura leem várias categorias ao mesmo tempo e percorrem cada pasta de modelo uma vez só. Na rede, de uns 10 segundos para cerca de 1 segundo.
- **Trabalho com o servidor fora da janela:** tags e mudanças dos colegas, travas, limpeza do backup e de _DESCARTADOS e a conferência das categorias rodam em segundo plano. A janela não dá mais "trancos" a cada poucos segundos quando há gente usando.
- Possíveis repetidos e a Entrada usam a data e o tamanho das prévias que já vêm na leitura da pasta, sem perguntar ao servidor arquivo por arquivo.
- A primeira abertura depois de atualizar lê a biblioteca inteira uma vez (agora em poucos segundos).

## 1.2.2
- **Tags abre na hora:** a página de Tags deixou de perguntar ao servidor a data de cada prévia (na rede, ela chegava a travar uns 6 segundos ao abrir e a cada tag nova de um colega). A data agora vem junto com a leitura da pasta.
- **Miniaturas mais rápidas ao rolar:** o Archiva carrega primeiro as miniaturas que estão na tela. Ao arrastar a barra até o fim da biblioteca, as do fim aparecem logo, sem esperar todas as do caminho.
- **Menos memória:** o Archiva guarda na memória só as miniaturas usadas mais recentemente (antes guardava todas e podia passar de 1 GB). As cópias no computador que não são usadas há 4 meses são apagadas sozinhas.
- Quando um colega coloca tags, só a página que está aberta se atualiza; as outras se atualizam ao serem abertas.

## 1.2.1
- **Possíveis repetidos (Organização, administrador):** o Archiva compara as prévias da biblioteca inteira (um repetido pode estar na pasta errada) e mostra cada par lado a lado, com prévia, categoria, tipo (pasta ou compactado), tamanho, número de arquivos, resolução da prévia e quanto se parecem.
- Em cada par: **Manter A**, **Manter B** ou **Manter os dois**. O que sai vai para _DESCARTADOS (apagado depois do prazo do backup) e as tags e coleções dele passam para o que fica. Dá para desfazer pelo Histórico. "Manter os dois" marca o par como diferente para a equipe toda e ele não aparece de novo.
- A procura é automática: roda em segundo plano ao abrir e sempre que entram ou mudam itens. O botão Organização no menu lateral mostra quantos pares estão esperando.

## 1.2.0
- **Buscar a prévia na web automaticamente:** botão direito no cartão › Atualizar prévia › Buscar na web… O Archiva procura imagens iguais e parecidas no Google, baixa as candidatas em segundo plano, mede a resolução de cada uma e mostra as **3 maiores**, com o tamanho em pixels. Clique em "Usar esta" e siga para a conferência de sempre (atual × nova, _DESCARTADOS e desfazer). Imagens repetidas, quebradas ou menores que 300 px ficam de fora.
- Usa a Google Cloud Vision: o administrador cola a chave da API uma vez em Configurações › Biblioteca › "Busca de prévias na web" e ela vale para toda a equipe. As primeiras 1.000 buscas de cada mês são grátis.
- Sem chave, ou se nada servir, o botão "Abrir no Google Lens" continua disponível (o jeito da 1.1.6).

## 1.1.6
- **Buscar a prévia na web:** botão direito no cartão › Atualizar prévia › Buscar na web… O Archiva copia a prévia atual e abre o Google Lens no navegador: é só apertar Ctrl+V, escolher o resultado de melhor qualidade e salvar a imagem em Downloads. O Archiva percebe a imagem nova sozinho e abre a mesma conferência (atual × nova, com a resolução), com troca, _DESCARTADOS e desfazer como no "Buscar no PC".
- Se a imagem foi salva em outra pasta, use "Escolher arquivo…" na janela de espera.

## 1.1.5
- **Atualizar a prévia pelo Archiva:** botão direito no cartão › Atualizar prévia › Buscar no PC… Escolha a imagem (jpg, png, webp…) e confira a prévia atual ao lado da nova, com a resolução de cada uma, antes de trocar. Imagens em outro formato são convertidas para o formato da prévia.
- A prévia antiga vai para _DESCARTADOS e dá para desfazer pelo Histórico. As miniaturas das Variações que eram cópia da prévia são trocadas junto; miniaturas próprias de uma variação (ex.: um render do WIRE) ficam como estão.
- O item fica travado durante a troca, e quem estiver na rede vê a prévia nova sozinho.
- **_DESCARTADOS não acumula:** tudo o que vai para lá é apagado depois do prazo do backup (Configurações › Biblioteca). Corrigido: descartes de arquivos antigos podiam ser apagados logo na limpeza seguinte, antes do prazo, o que impedia o desfazer.

## 1.1.4
- **Texturas automáticas no Merge, sem fazer nada:** ao abrir, o Archiva instala o relink como pacote oficial do 3ds Max (vale para todas as versões do Max no computador, inclusive as que forem instaladas depois) e também na pasta de inicialização de cada Max. Feche e abra o Max uma vez; depois disso, ao arrastar um item e escolher Merge, as texturas vêm da pasta do item. Não há mais nada para arrastar nem configurar.
- O script ficou mais resistente: procura o aviso do item arrastado em mais de um lugar e, se algo der errado, escreve o motivo no Listener (F11) em vez de parar em silêncio.
- **Entrada mostra sempre as subpastas:** categorias com subpastas (ex.: LUMINARIAS › PENDENTE) aparecem sozinhas na lista, em qualquer computador. A opção "Subpastas na Entrada" saiu de Configurações.
- Saíram de Configurações a escolha do modo de arrastar (agora é sempre o Merge do Max com texturas automáticas) e o botão de instalar o relink.

## 1.1.3
- **Instalar o relink de texturas pelo próprio 3ds Max:** em Configurações › Uso há um botão "Arraste para o 3ds Max". Arraste-o uma vez para a viewport: o Max instala o script na pasta de inicialização dele e já o ativa, sem reabrir. Serve para computadores em que o Archiva não achou a pasta de scripts do Max sozinho.
- Ao abrir o Max, o Listener (F11) mostra "Archiva: relink de texturas ativo", para conferir que está funcionando.
- A instalação automática agora também funciona quando a pasta de scripts do Max ainda não existe.
- Corrigido: um arquivo de teste tinha entrado por engano no código-fonte da 1.1.1 (não afetava o programa).

## 1.1.2
- **Tela de abertura:** ao abrir o Archiva, a logo surge letra por letra enquanto a biblioteca é lida, com a versão e o nome do autor no canto. Quando a leitura termina, a abertura esmaece e o programa aparece. Ela fica pelo menos 1,8 s na tela; se a leitura passar de 8 s, o programa abre mesmo assim.
- **Dá para desligar** em Configurações › Uso › Abertura.
- Na primeira abertura (escolha de perfil e de pasta) e quando há perguntas no caminho, a abertura não atrapalha: ela sai da frente.

## 1.1.1
- **Arrastar para o Max volta a ser como antes:** o Max mostra a janela Merge / XRef e você posiciona o item com o mouse (na 1.1.0 ele caía no 0,0,0).
- **Texturas continuam sendo religadas, agora pelo próprio Max:** o Archiva instala um pequeno script na pasta de inicialização de cada 3ds Max do computador. Depois de um **Merge**, ele liga as texturas que estão faltando na cena à pasta do item arrastado (só as que faltam; o resto da cena não é tocado). Feche e abra o Max uma vez para o script começar a valer. O resumo aparece no MAXScript Listener (F11). No XRef as texturas não são religadas.
- O merge direto por script (sem janela) continua em Configurações › Uso, para quem preferir.

## 1.1.0
- **Texturas já ligadas ao entrar na cena:** ao arrastar um item para o 3ds Max, o Archiva faz o merge e aponta cada textura (Bitmap, CoronaBitmap, VRayBitmap) e cada proxy (Corona/V-Ray) para a pasta do item na biblioteca. O caminho fica salvo na cena, sem relink, mesmo depois de fechar e reabrir o Max. O resumo (religadas / não encontradas) aparece no MAXScript Listener (F11).
- **"Merge com texturas" passa a ser o modo de arrastar de todos.** Antes, o padrão arrastava o .max puro, e aí o Max fazia o merge sem religar nada. Dá para voltar em Configurações › Uso.
- **Variações no mesmo item:** pastas com vários .max do mesmo modelo (ex.: CHAIR, CHAIR WIRE, OTTOMAN, SET) mostram no painel a lista "Variações", com a miniatura de cada uma e as versões WIRE logo depois da normal. Arraste a variação que quiser para o Max; o cartão continua levando a principal.
- **Escolha da variação principal:** prefere Corona, depois a versão que não é WIRE e, entre essas, o maior arquivo (num conjunto, costuma ser o SET completo).

## 1.0.2
- **Comparar pasta e compactado:** quando um item existe como pasta e como compactado com o mesmo nome, o botão "Comparar pasta e compactado…" (no painel e no botão direito) mostra os arquivos iguais, os diferentes e os que só existem de um lado, sem extrair nada. Você escolhe: manter a pasta, manter o compactado ou ficar com os dois (o compactado vira um item novo com o próximo número). O que sai vai para _DESCARTADOS e dá para desfazer.
- **Excluir item (administrador):** botão direito › "Excluir item…", sempre com confirmação. O item some da biblioteca, das tags e das coleções. Os arquivos vão para _DESCARTADOS e, até o prazo do backup, o Histórico desfaz tudo, inclusive as tags e coleções.
- **Absorver categoria inteira:** em Organização › Juntar pastas, a pasta que sai agora pode ter subpastas (ex.: PAVIMENTOS com MADEIRA e PEDRA). Todos os itens vão para a pasta principal com o nome dela e os próximos números, as subpastas vazias são apagadas e o desfazer devolve tudo de uma vez.

## 1.0.1
- **Trava mostra quem está com o item:** quando alguém da rede está mexendo num item ou categoria, o aviso diz o nome, o computador e desde que horas (ex.: "Maria (PC-02) está extraindo desde 13:40"). A trava continua impedindo a ação. Vale também para "Mover para…", que agora trava cada item movido.
- **Campo de tags sempre vazio:** depois de aplicar uma tag, o campo não traz mais a última tag escrita ao passar para outro item.

## 1.0.0
- **Archiva 1.0:** primeira versão estável. Reúne tudo o que foi feito até aqui — Biblioteca, Entrada, Tags, Coleções, Organização, perfis e trabalho em equipe na rede, histórico com desfazer, tutoriais e atualização automática. As próximas novidades partem desta versão.

## 0.14.2
- **Adicionados recentemente (Início):** mostra só o que chegou à biblioteca por último — pela Entrada ou, nos itens antigos, pela data do arquivo baixado. Itens antigos que acabaram de ser descompactados ou organizados não aparecem mais como novos.

## 0.14.1
- **Organização mais visual:**
  - Itens fora do lugar viram cartões: miniatura do item, onde está **agora** e o motivo → para onde **vai** e o nome novo, com miniaturas dos itens vizinhos no destino. Separados em "Mover para outra pasta" e "Renomear na própria pasta"; "Trocar destino" e "Ignorar" em cada cartão.
  - Juntar pastas lado a lado: a pasta que sai à esquerda e a principal à direita (com miniaturas, quantidade e padrão de nomes), seta e botão "Inverter", e a lista "Como vai ficar" (nome atual → nome novo) antes de conferir.
  - A tela de conferência também mostra cartões com miniaturas e, quando houver, a miniatura do item parecido que já existe no destino.
- **Mover para… na Biblioteca:** botão direito no cartão › Mover para… › escolha a categoria. O item vai para lá com o próximo número da categoria nova, passando pela mesma tela de conferência (com Desfazer pelo histórico).

## 0.14.0
- **Organização** (menu lateral, só para o administrador): arrume a biblioteca sem abrir o Explorer.
  - **Itens fora do lugar:** "Procurar" encontra itens cujo nome não combina com a pasta (ex.: POLTRONA 09 dentro de MESAS) e sugere mover para a pasta certa com o próximo número de lá, ou renomear ali mesmo. Botão direito: escolher outra pasta ou ignorar o item.
  - **Juntar pastas:** escolha duas pastas e qual é a principal; os itens da outra vão para ela renomeados na sequência (ex.: MATERIAL 05 → MATERIAIS E TEXTURAS 41). A pasta que ficar vazia é apagada.
  - Sempre há uma tela de conferência antes (nome atual → nome novo, com Mover/Pular/Descartar por item), aviso de possíveis repetidos, travas para a equipe e Desfazer pelo histórico (juntar pastas desfaz tudo de uma vez). Tags e coleções acompanham os itens; o .max e as texturas dentro das pastas mantêm o nome.
- Desfazer agora também devolve as tags e coleções ao nome antigo do item, e pastas que voltam a existir reaparecem sozinhas.

## 0.13.0
- **Início mais rápido na rede:** a página não consulta mais o servidor a cada visita (as datas dos itens ficam no índice) e só é refeita quando algo mudou; voltar para o Início é instantâneo.
- **Pastas exibidas** (Configurações › Biblioteca): marque e desmarque quais categorias e subcategorias aparecem no Archiva. Vale só para você; nenhum arquivo é movido ou apagado.
- O Início cumprimenta pelo nome do seu perfil.

## 0.12.0
- **Coleções de projeto:** item novo no menu lateral. Junte os modelos usados em cada trabalho (ex.: "Apartamento Silva – Sala"), com anotação (cliente, endereço), arquivar e excluir. Toda a equipe vê as coleções, com quem criou.
  - Para adicionar: "Adicionar à coleção…" no painel da direita da Biblioteca, botão direito no cartão, ou arraste o cartão até "Coleções" no menu lateral.
  - Dentro da coleção, a faixa "Você usou recentemente" mostra o que você levou para o 3ds Max nos últimos 7 dias; marque e adicione. Nada entra numa coleção sozinho.
- **Atalhos:** Espaço amplia a prévia (de novo fecha), Ctrl+F vai para a busca, Ctrl+T para as tags, setas andam entre os cartões. Delete descarta na Entrada ou tira o item da coleção, sempre pedindo confirmação; na Biblioteca não faz nada.
- Tutoriais novos em Aprender: Coleções de projeto e Atalhos de teclado.
- Caixas de marcar com o visual do programa em todas as listas.

## 0.11.0
- **Abertura rápida:** o Archiva guarda um índice da biblioteca neste computador e abre na hora; em segundo plano confere só as categorias que mudaram (uma listagem de pasta por categoria) e relê apenas essas. Faz muita diferença com a biblioteca no servidor. "Atualizar" (F5) continua lendo tudo.
- **Testar biblioteca** (Configurações › Biblioteca › Testar…): confere acesso à pasta, permissão de gravação, relógio deste computador em relação ao servidor, velocidade da rede e quem usa a biblioteca, explicando o que fazer quando algo não estiver certo.
- **Relógio do servidor:** travas, histórico e ordem das tags passam a usar a hora do servidor, então um computador com o relógio errado não atrapalha mais.
- **Prazo do backup da biblioteca:** passa a ser um só para todos (definido pelo administrador em Configurações), em vez de um por computador.

## 0.10.3
- **Prévia ampliada:** na Biblioteca, clique na prévia do painel da direita para abrir a imagem grande numa janela própria (clique ou Esc fecha).
- **Tamanho dos cartões direto na Biblioteca:** controle deslizante ao lado dos filtros (o mesmo das Configurações).
- **Seleção mais visível:** o item selecionado ganhou um contorno cobre com fio escuro por dentro, que não se confunde com prévias de fundo branco (Biblioteca, Entrada e galeria de Tags).
- **Entrada:** a barra "Mandar para a categoria" abre a lista ao clicar em qualquer parte dela, e ganhou uma seta discreta. Todas as listas de escolha do programa agora mostram a seta.

## 0.10.2
- O cartão dos tutoriais agora tem o mesmo tamanho em todos os passos (o do texto mais longo do grupo): a moldura e os botões não mudam de lugar ao avançar, e a dica fica sempre no rodapé.

## 0.10.1
- Tutoriais com textos novos, mais explicativos: uma introdução curta, os passos numerados de "Como fazer" e uma dica em destaque.
- Diagramação mais espaçada e elegante no cartão do tutorial; a altura se ajusta ao conteúdo e a animação fica centralizada.

## 0.10.0
- **Boas-vindas:** ao abrir, uma apresentação em 7 passos com animações mostra o essencial (biblioteca, busca, arrastar para o Max, extrair, Entrada, tags e trabalho em equipe). Marque "Não mostrar ao abrir" para desligar; dá para ligar de novo em Configurações › Uso.
- **Aprender:** página nova no menu lateral com todos os tutoriais, separados por assunto. O que chegar em cada atualização aparece com o selo **Novo** e, depois de atualizar, o Archiva mostra só as novidades.
- **Corrigido:** o programa podia fechar sozinho ao atualizar a lista de categorias depois de extrair ou classificar (principalmente depois de abrir uma categoria pela página inicial).

## 0.9.0
- **Perfis:** na primeira abertura cada pessoa cria o seu perfil, com o nome que quiser e uma foto ou a inicial com cor. O perfil fica ligado ao computador e aparece no menu lateral (clique para editar).
- **Biblioteca compartilhada (servidor):** várias pessoas podem usar a mesma biblioteca ao mesmo tempo. Tags, grupos, capas, novidades e nomes da Entrada são os mesmos para todos e se atualizam sozinhos a cada poucos segundos.
- **Travas:** enquanto alguém extrai, organiza ou classifica um item, ele aparece "em uso · nome da pessoa" para os outros e os botões ficam bloqueados. Na Entrada, a categoria fica travada durante a numeração, para ninguém pegar o mesmo número. Se o programa de alguém fechar no meio, a trava some sozinha em cerca de 2 minutos.
- **Histórico e desfazer:** toda alteração de arquivos (extrair, organizar, classificar, substituir, descartar, limpar) fica registrada com quem fez, de qual computador e quando. Cada pessoa vê e desfaz as próprias alterações (menu do perfil › Minhas alterações); o administrador vê e desfaz as de todos (Histórico de todos) e escolhe outros administradores (Pessoas e administradores).
- A limpeza da revisão (V-Ray, FBX, OBJ) agora manda os arquivos para _DESCARTADOS em vez de apagar, então dá para desfazer até o prazo do backup.
- Os dados compartilhados ficam numa pasta oculta _ARCHIVA dentro da biblioteca. As suas tags antigas são levadas para lá na primeira abertura.

## 0.8.0
- Archiva agora tem instalador (Archiva-Setup.exe): instala sem pedir administrador, cria atalho no menu Iniciar e na Área de Trabalho e não precisa mais de Python.
- Aviso de versão nova: ao abrir, o Archiva consulta o GitHub; se houver versão nova, aparece "Atualizar" no rodapé. Um clique baixa, instala e reabre.
- Configurações › Atualizações: ligar/desligar a procura automática e "Procurar agora".
- Primeira instalação começa limpa: cada pessoa escolhe a pasta da sua biblioteca na tela de boas-vindas; tags, senhas e nomes da Entrada não vêm de outro computador (dá para levar as tags com Configurações › Tags › Exportar/Importar).
- Logotipo desenhado como vetor (não depende mais do arquivo da fonte).
- Diagnóstico da barra de título passou para a pasta de dados do usuário.

## 0.7.2
- Logotipo centralizado pelo desenho real das letras.

## 0.7.1
- Barra de título integrada com cantos arredondados funcionando no Windows 11.
- Faixa "Adicionados recentemente" não rouba mais a rolagem da página (use Shift + roda para andar para o lado).
- Ícone com o "A" maiúsculo do logotipo.

## 0.7.0
- Novo visual "Nogueira", novo nome (Archiva) e menu lateral.
