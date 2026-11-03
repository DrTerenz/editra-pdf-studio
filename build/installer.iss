; Installer di Editra PDF Studio (Inno Setup 6)
; Compilazione: ISCC.exe build\installer.iss  (dopo aver creato dist\EditraPDFStudio con PyInstaller)

#define AppName "Editra PDF Studio"
#define AppVersion "1.2.0"
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
VersionInfoDescription={#AppName} setup
ShowLanguageDialog=auto

[Languages]
Name: "en"; MessagesFile: "compiler:Default.isl"
Name: "it"; MessagesFile: "compiler:Languages\Italian.isl"

[CustomMessages]
en.Shortcuts=Shortcuts:
it.Shortcuts=Collegamenti:
en.DesktopIcon=Create a desktop shortcut
it.DesktopIcon=Crea un collegamento sul desktop
en.Associations=File associations:
it.Associations=Associazioni:
en.AssocPdf=Open PDF files with {#AppName}
it.AssocPdf=Apri i file PDF con {#AppName}
en.AssocP7m=Open signed .p7m files with {#AppName}
it.AssocP7m=Apri i file firmati .p7m con {#AppName}
en.DocPdf=PDF document
it.DocPdf=Documento PDF
en.DocP7m=Digitally signed document
it.DocP7m=Documento firmato digitalmente
en.AppDescription=PDF reader and editor
it.AppDescription=Lettore ed editor PDF
en.Launch=Launch {#AppName}
it.Launch=Avvia {#AppName}

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:Shortcuts}"
Name: "assocpdf"; Description: "{cm:AssocPdf}"; GroupDescription: "{cm:Associations}"
Name: "assocp7m"; Description: "{cm:AssocP7m}"; GroupDescription: "{cm:Associations}"

[Files]
Source: "..\dist\EditraPDFStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; tipo di documento dell'app
Root: HKA; Subkey: "Software\Classes\{#ProgId}"; ValueType: string; ValueData: "{cm:DocPdf}"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\{#ProgId}\DefaultIcon"; ValueType: string; ValueData: """{app}\{#AppExe}"",0"
Root: HKA; Subkey: "Software\Classes\{#ProgId}\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""
Root: HKA; Subkey: "Software\Classes\{#ProgId}.p7m"; ValueType: string; ValueData: "{cm:DocP7m}"; Flags: uninsdeletekey
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
Root: HKA; Subkey: "Software\Editra\Capabilities"; ValueType: string; ValueName: "ApplicationDescription"; ValueData: "{cm:AppDescription}"
Root: HKA; Subkey: "Software\Editra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".pdf"; ValueData: "{#ProgId}"
Root: HKA; Subkey: "Software\Editra\Capabilities\FileAssociations"; ValueType: string; ValueName: ".p7m"; ValueData: "{#ProgId}.p7m"
Root: HKA; Subkey: "Software\RegisteredApplications"; ValueType: string; ValueName: "{#AppName}"; ValueData: "Software\Editra\Capabilities"; Flags: uninsdeletevalue
; associazioni scelte durante l'installazione (Windows 10/11 può comunque chiedere conferma la prima volta)
Root: HKA; Subkey: "Software\Classes\.pdf"; ValueType: string; ValueData: "{#ProgId}"; Tasks: assocpdf; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\.p7m"; ValueType: string; ValueData: "{#ProgId}.p7m"; Tasks: assocp7m; Flags: uninsdeletevalue

[INI]
; al primo avvio il programma usa la lingua scelta per l'installazione (poi si cambia dalle Impostazioni)
Filename: "{userappdata}\EditraPDFStudio\impostazioni.ini"; Section: "General"; Key: "language"; String: "{language}"; Flags: createkeyifdoesntexist

[Run]
Filename: "{app}\{#AppExe}"; Description: "{cm:Launch}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"
