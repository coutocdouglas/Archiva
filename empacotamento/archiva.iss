; Inno Setup — instalador do Archiva.
; Compilar:  ISCC /DAppVersion=0.8.0 empacotamento\archiva.iss
; Instala por usuário (sem pedir administrador) em %LOCALAPPDATA%\Programs\Archiva.
; Configurações, tags e miniaturas ficam em %APPDATA% / %LOCALAPPDATA%\GerenciadorAssets3D e não são tocadas.

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{1F6B98BB-FA7B-4EBC-A319-E97225A5872E}
AppName=Archiva
AppVersion={#AppVersion}
AppVerName=Archiva {#AppVersion}
AppPublisher=TILD
AppPublisherURL=https://github.com/coutocdouglas/Archiva
AppUpdatesURL=https://github.com/coutocdouglas/Archiva/releases
DefaultDirName={localappdata}\Programs\Archiva
DefaultGroupName=Archiva
DisableProgramGroupPage=yes
DisableDirPage=yes
DisableReadyPage=yes
PrivilegesRequired=lowest
OutputDir=..\saida
OutputBaseFilename=Archiva-Setup-{#AppVersion}
SetupIconFile=..\app\recursos\icone.ico
UninstallDisplayIcon={app}\Archiva.exe
UninstallDisplayName=Archiva
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=force
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "pt"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[InstallDelete]
; limpa a versão anterior antes de copiar a nova (evita sobrar arquivo velho)
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Archiva\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Archiva"; Filename: "{app}\Archiva.exe"; AppUserModelID: "TILD.Archiva"
Name: "{autodesktop}\Archiva"; Filename: "{app}\Archiva.exe"; AppUserModelID: "TILD.Archiva"; Tasks: desktopicon

[Run]
; instalação normal: oferece abrir no final
Filename: "{app}\Archiva.exe"; Description: "Abrir o Archiva"; Flags: nowait postinstall skipifsilent
; atualização silenciosa (feita pelo próprio Archiva): reabre sozinho
Filename: "{app}\Archiva.exe"; Flags: nowait; Check: WizardSilent

[Code]
// Na atualização silenciosa, espera o Archiva antigo terminar de fechar.
function InitializeSetup(): Boolean;
begin
  if WizardSilent then
    Sleep(1500);
  Result := True;
end;
