# Archiva

Gerenciador da biblioteca de modelos 3D da TILD (3ds Max): navega pelas categorias, mostra prévias,
organiza e extrai compactados, recebe downloads novos pela **Entrada**, marca tudo com **tags** e arrasta
os modelos direto para o 3ds Max.

## Instalar
Baixe o `Archiva-Setup-x.y.z.exe` mais recente em **[Releases](../../releases/latest)** e execute.
Não pede administrador; instala em `%LOCALAPPDATA%\Programs\Archiva`.
Na primeira vez o Windows pode mostrar "O Windows protegeu o computador" (o instalador não é assinado):
clique em **Mais informações › Executar assim mesmo**.

Depois disso o Archiva avisa sozinho quando sair versão nova (rodapé › **Atualizar**).

Configurações, tags e miniaturas ficam em `%APPDATA%\GerenciadorAssets3D` e
`%LOCALAPPDATA%\GerenciadorAssets3D` e são mantidas nas atualizações. A biblioteca de modelos
só é alterada quando você usa as ações de extrair/organizar.

## Lançar uma versão nova
1. Atualize `VERSION` e acrescente a seção da versão em `NOVIDADES.md`.
2. `git commit -am "Archiva 0.8.1"` · `git push`
3. A ação **Publicar versão** monta o instalador, cria a tag `v0.8.1` e publica em Releases.

## Rodar pelo código (desenvolvimento)
```
pip install -r requirements.txt
python gerenciador.pyw
```
Montar localmente no Windows: `pip install pyinstaller`, `python empacotamento\versao.py`,
`pyinstaller empacotamento\archiva.spec --noconfirm`, e compile `empacotamento\archiva.iss`
no Inno Setup 6 (`ISCC /DAppVersion=0.8.0 empacotamento\archiva.iss`).

## Estrutura
- `gerenciador.pyw` — ponto de entrada
- `app/` — interface (PySide6/Qt) e lógica; `app/recursos/` — ícone, fontes da interface, logotipo
- `empacotamento/` — PyInstaller (`archiva.spec`) e instalador Inno Setup (`archiva.iss`)
- `.github/workflows/publicar.yml` — monta e publica as versões

Fonte da interface: ZT Nature (Zelowtype, uso comercial livre — ver `app/recursos/fontes`).
