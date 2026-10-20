# Novidades do Archiva

Cada versão tem uma seção `## x.y.z`. O texto da seção aparece na página da versão no GitHub e no aviso de atualização.

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
