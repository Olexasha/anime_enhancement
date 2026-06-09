#define AppName "Anime Enhancement"
#define AppVersion "0.1.0"
#define AppPublisher "anime_enhancement"
#define AppExeName "AnimeEnhancement.exe"
#define ProjectRoot "..\.."
#define DistDir ProjectRoot + "\dist\AnimeEnhancement"
#define AssetsDir "assets"
#define ShortcutIcon "{app}\_internal\assets\branding\anime_enhancement.ico"

[Setup]
AppId={{5F08A8E5-1A6D-4F36-9E4A-8A91B6F884D8}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\AnimeEnhancement
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir={#ProjectRoot}\release\windows
OutputBaseFilename=AnimeEnhancementSetup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#AppExeName}
SetupIconFile={#AssetsDir}\anime_enhancement.ico
LicenseFile={#ProjectRoot}\LICENSE
WizardSmallImageFile={#AssetsDir}\wizard-small.bmp
WizardImageFile={#AssetsDir}\wizard-large.bmp
PrivilegesRequired=lowest

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Создать ярлык на рабочем столе"; GroupDescription: "Дополнительные ярлыки:"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{#ShortcutIcon}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; WorkingDir: "{app}"; IconFilename: "{#ShortcutIcon}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Запустить {#AppName}"; Flags: nowait postinstall skipifsilent
