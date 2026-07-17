; Inno Setup script — packages the PyInstaller one-folder build (dist\LectureCapture)
; into a single Windows installer (installer\LectureCapture-Setup.exe).
;
; Build the app first:   venv\Scripts\pyinstaller.exe --noconfirm LectureCapture.spec
; Then compile this:     "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" installer.iss

#define MyAppName "LectureCapture"
#define MyAppVersion "3.1.2"
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

[Code]
{ Uninstalling the program folder leaves the user's data behind, in three places:
    - saved sessions  -> %APPDATA%\LectureCapture (SQLite DB, slide images, custom sounds)
    - settings        -> HKCU\Software\LectureCapture (QSettings)
    - speech models   -> the Hugging Face cache under the user profile
  On uninstall we offer to reclaim space by removing the settings and the (large) models,
  while ALWAYS keeping the saved sessions. Defaults to "No" so a reinstall keeps everything.
  Note: with an admin install these user-profile constants resolve for the uninstalling
  user, which is the normal single-user case. }

procedure DeleteCachedModels(HubDir, Pattern: String);
var
  FindRec: TFindRec;
begin
  if FindFirst(HubDir + '\' + Pattern, FindRec) then
  begin
    try
      repeat
        if (FindRec.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
          DelTree(HubDir + '\' + FindRec.Name, True, True, True);
      until not FindNext(FindRec);
    finally
      FindClose(FindRec);
    end;
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  HubDir: String;
begin
  if CurUninstallStep = usUninstall then
  begin
    if MsgBox('Also remove the downloaded speech models and app settings?' + #13#10#13#10 +
              'Your saved sessions are always kept. Choose No to also keep the models ' +
              '(useful if you plan to reinstall).',
              mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    begin
      { Settings (QSettings writes to HKCU\Software\LectureCapture\LectureCapture).
        Sessions in %APPDATA%\LectureCapture are intentionally left untouched. }
      RegDeleteKeyIncludingSubkeys(HKEY_CURRENT_USER, 'Software\{#MyAppName}');
      { Downloaded faster-whisper models in the Hugging Face cache. }
      HubDir := ExpandConstant('{%USERPROFILE}\.cache\huggingface\hub');
      DeleteCachedModels(HubDir, 'models--Systran--faster-whisper-*');
      DeleteCachedModels(HubDir, 'models--Systran--faster-distil-whisper-*');
    end;
  end;
end;
