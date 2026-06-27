; Inno Setup script — packages the PyInstaller one-folder build (dist\LectureCapture)
; into a single Windows installer (installer\LectureCapture-Setup.exe).
;
; Build the app first:   venv\Scripts\pyinstaller.exe --noconfirm LectureCapture.spec
; Then compile this:     "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss

#define MyAppName "LectureCapture Lite"
#define MyAppVersion "2.1.2"
#define MyAppPublisher "LectureCapture"
#define MyAppExeName "LectureCapture.exe"

[Setup]
AppId={{3F7A2C1E-8B5D-4E90-A6F1-2C3D4E5F6A7B}}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=LectureCapture-Lite-Setup
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
