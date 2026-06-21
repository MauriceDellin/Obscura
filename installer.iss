; Inno-Setup-Skript fuer die Obscura
; Erzeugt einen Windows-Installer aus der zuvor gebauten dist\Obscura-Portable.exe
;
; Voraussetzungen:
;   1) PyInstaller-Build ausgefuehrt  ->  dist\Obscura-Portable.exe existiert
;   2) Inno Setup installiert         ->  https://jrsoftware.org/isdl.php
; Bauen:  Rechtsklick auf diese Datei -> "Compile"  ODER
;         "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer.iss
; Ergebnis:  Output\Obscura-Setup.exe

#define MyAppName "Obscura"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "Maurice Dellin"
#define MyAppExeName "Obscura.exe"
#define MyAppBuildExe "Obscura-Portable.exe"

[Setup]
AppId={{B7E2B9B0-1C5E-4E2C-9C2A-0A1B2C3D4E5F}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; Installation pro Benutzer (kein Admin noetig):
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest
OutputDir=Output
OutputBaseFilename=Obscura-Setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "de"; MessagesFile: "compiler:Languages\German.isl"

[Tasks]
Name: "desktopicon"; Description: "Desktop-Verknuepfung erstellen"; GroupDescription: "Zusaetzliche Symbole:"

[Files]
; portable Build (Obscura-Portable.exe) wird als Obscura.exe installiert
Source: "dist\{#MyAppBuildExe}"; DestDir: "{app}"; DestName: "{#MyAppExeName}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{#MyAppName} deinstallieren"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{#MyAppName} jetzt starten"; Flags: nowait postinstall skipifsilent
