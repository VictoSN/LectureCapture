; Inno Setup script — packages the PyInstaller one-folder build (dist\LectureCapture)
; into a single Windows installer (installer\LectureCapture-Setup.exe).
;
; Build the app first:   venv\Scripts\pyinstaller.exe --noconfirm LectureCapture.spec
; Then compile this:     "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss

#define MyAppName "LectureCapture"
#define MyAppVersion "2.1.0"
#define MyAppPublisher "LectureCapture"
#define MyAppExeName "LectureCapture.exe"

[Setup]
AppId={{8A3C1B2D-9E4F-4A56-B7C8-1D2E3F4A5B6C}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=LectureCapture-Setup
SetupIconFile=assets\icons\logo.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; Program Files install needs admin; the app writes its data to %APPDATA% and the HF
; model cache to the user profile, so the read-only install dir is fine.
PrivilegesRequired=admin

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "dist\LectureCapture\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
