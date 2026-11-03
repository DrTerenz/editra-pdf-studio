; Installer di Editra PDF Studio (Inno Setup 6)
; Compilazione: ISCC.exe build\installer.iss  (dopo aver creato dist\EditraPDFStudio con PyInstaller)

#define AppName "Editra PDF Studio"
#define AppVersion "1.0.0"
#define AppExe "EditraPDFStudio.exe"
#define ProgId "EditraPDFStudio.Documento"

[Setup]
AppId={{4E3B8F21-6C7A-4D5E-B1F2-9A8C7E6D5F43}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=Giacomo Terenzi
LicenseFile=..\LICENSE
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=..\installer
OutputBaseFilename=EditraPDFStudio_Setup_{#AppVersion}
SetupIconFile=EditraPDFStudio.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
LZMANumBlockThreads=2
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
CloseApplications=yes
ChangesAssociations=yes
VersionInfoVersion={#AppVersion}
VersionInfoDescription={#AppName} - installazione

[Languages]
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[Tasks]
Name: "desktopicon"; Description: "Crea un collegamento sul desktop"; GroupDescription: "Collegamenti:"
Name: "assocpdf"; Description: "Apri i file PDF con {#AppName}"; GroupDescription: "Associazioni:"
Name: "assocp7m"; Description: "Apri i file firmati .p7m con {#AppName}"; GroupDescription: "Associazioni:"

[Files]
Source: "..\dist\EditraPDFStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; tipo di documento dell'app
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueData: "Documento PDF"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueData: """{app}\{#AppExe}"",0"
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\{#ProgId}.p7m"; ValueType: string; ValueData: "Documento firmato digitalmente"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#ProgId}.p7m\DefaultIcon"; ValueType: string; ValueData: """{app}\{#AppExe}"",0"
Root: HKA; Subkey: "Software\Classes\{#ProgId}.p7m\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Editra"; Flags: uninsdeletekeyifempty
; "Apri con" e impostazioni delle app predefinite di Windows
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.p7m\OpenWithProgids"; ValueType: string; ValueName: "{#ProgId}.p7m"; ValueData: ""; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".pdf"; ValueData: ""; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\SupportedTypes"; ValueType: string; ValueName: ".p7m"; ValueData: ""
Root: HKA; Subkey: "Software\Classes\Applications\{#AppExe}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Editra\Capabilities"; ValueType: string; ValueName: "ApplicationName"; ValueData: "{#AppName}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Editra\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "Lettore ed editor PDF"
Root: HKA; Subkey: "Software\Editra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "{#ProgId}"
Root: HKA; Subkey: "Software\Editra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".p7m"; ValueData: "{#ProgId}.p7m"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#AppName}"; ValueData: "Software\Editra\Capabilities"; Flags: uninsdeletevalue
; associazioni scelte durante l'installazione (Windows 10/11 può comunque chiedere conferma la prima volta)
Root: HKA; Subkey: "Software\Classes\.pdf"; ValueType: string; ValueData: "{#ProgId}"; Tasks: assocpdf; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.p7m"; ValueType: string; ValueData: "{#ProgId}.p7m"; Tasks: assocp7m; Flags: uninsdeletevalue

[Run]
Filename: "{app}\{#AppExe}"; Description: "Avvia {#AppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"



