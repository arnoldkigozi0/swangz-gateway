; Swangz for Windows: the installer around the PyInstaller program (dist\Swangz.exe).
;
;   ISCC /DAppVersion=0.1.0 /DSourceExe=dist\Swangz.exe /DOutputDir=artifacts packaging\windows\swangz.iss
;
; What it does, and nothing else:
;   - installs for the signed-in person only (no administrator rights, nothing machine-wide, no security setting touched)
;     into %LOCALAPPDATA%\Programs\Swangz;
;   - a Start-menu entry, and optional tasks: a desktop shortcut and starting Swangz when the person signs in to Windows
;     (the same HKCU Run value, "Swangz", that the app's own "Start with Windows" switch reads and writes);
;   - uninstall: runs `Swangz.exe cleanup` as the person (it signs the device out, so the Hub disconnects it, removes what
;     the app put on this computer even when the Hub cannot be reached, and deletes the saved browser sign-ins), names
;     whatever it could not delete, then removes the program, the shortcuts and the Run value.
; It carries no key or other secret; the app's sign-in starts with the Swangz Hub address. The installer installs no
; updater and schedules nothing; in-app updates stay off until signed releases exist (swangz_client/release_keys.py).
; The program and this installer are UNSIGNED until Swangz holds a code-signing certificate (packaging/README.md).

#ifndef AppVersion
  #error Pass /DAppVersion=<version>
#endif
#ifndef SourceExe
  #define SourceExe "..\..\dist\Swangz.exe"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\artifacts"
#endif

[Setup]
AppId={{2027a02e-ebf5-41b9-8a7d-9e10a26e1770}
AppName=Swangz
AppVersion={#AppVersion}
AppVerName=Swangz {#AppVersion}
AppPublisher=Swangz Avenue
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Swangz AI Hub desktop app (UNSIGNED)
PrivilegesRequired=lowest
DefaultDirName={autopf}\Swangz
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
UninstallDisplayIcon={app}\Swangz.exe
UninstallDisplayName=Swangz
OutputDir={#OutputDir}
OutputBaseFilename=Swangz-Setup-{#AppVersion}-UNSIGNED
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no
SetupLogging=yes
; Reproducible builds: keep the program's own (source-dated) file time instead of stamping the compile time.
TouchDate=none
TouchTime=none

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked
Name: "startup"; Description: "Start Swangz when I sign in to Windows"; GroupDescription: "Start-up:"; Flags: unchecked

[Files]
Source: "{#SourceExe}"; DestDir: "{app}"; DestName: "Swangz.exe"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Swangz"; Filename: "{app}\Swangz.exe"; Comment: "Swangz AI Hub"
Name: "{autodesktop}\Swangz"; Filename: "{app}\Swangz.exe"; Comment: "Swangz AI Hub"; Tasks: desktopicon

[Registry]
; Only when the task is chosen; removed on uninstall either way (the app's own switch writes the same value).
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Swangz"; ValueData: """{app}\Swangz.exe"" --background"; Tasks: startup; Flags: uninsdeletevalue

[Run]
Filename: "{app}\Swangz.exe"; Description: "Open Swangz"; Flags: postinstall nowait skipifsilent

[Code]
const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{2027a02e-ebf5-41b9-8a7d-9e10a26e1770}_is1';

// One part of a MAJOR.MINOR.PATCH version as a number; a missing or non-numeric part counts as 0.
function VersionPart(var Rest: String): Integer;
var
  P: Integer;
  Part: String;
begin
  P := Pos('.', Rest);
  if P > 0 then begin
    Part := Copy(Rest, 1, P - 1);
    Delete(Rest, 1, P);
  end else begin
    Part := Rest;
    Rest := '';
  end;
  Result := StrToIntDef(Trim(Part), 0);
end;

// -1 when A is older than B, 0 when equal, 1 when newer.
function CompareVersions(A, B: String): Integer;
var
  I, X, Y: Integer;
begin
  Result := 0;
  for I := 1 to 3 do begin
    X := VersionPart(A);
    Y := VersionPart(B);
    if X < Y then begin Result := -1; Exit; end;
    if X > Y then begin Result := 1; Exit; end;
  end;
end;

// An older build never replaces a newer one: installing it would roll back fixes without anyone noticing.
// Reinstalling the same version and upgrading are allowed. Silent installs end with exit code 1 and the reason in the log.
function InitializeSetup(): Boolean;
var
  Installed: String;
begin
  Result := True;
  if RegQueryStringValue(HKEY_CURRENT_USER, UninstallKey, 'DisplayVersion', Installed) and
     (CompareVersions('{#AppVersion}', Installed) < 0) then begin
    Log('Refused: Swangz ' + Installed + ' is installed; this installer is the older version {#AppVersion}.');
    SuppressibleMsgBox('Swangz ' + Installed + ' is already installed. This installer is an older version ({#AppVersion}) and will not replace it.',
      mbCriticalError, MB_OK, IDOK);
    Result := False;
  end;
end;

// The app's own "Start with Windows" switch writes the same Run value outside the installer's knowledge; remove it too.
// Before any file goes. First stop this person's running copy (started at sign-in, it would hold Swangz.exe and the
// browser folders open): only processes named Swangz.exe that belong to the person uninstalling. Then the program
// removes Swangz from this account as that person: it disconnects the device, takes off what it installed and deletes
// the saved browser sign-ins. What it could not delete is shown and logged; the uninstall carries on either way.
// The program is started with the uninstaller's own rights (Inno Setup cannot start one as the original user during
// uninstall). It refuses raised rights or a folder it does not own; that is reported with the two ways to finish, and
// nothing is ever retried with more rights.
procedure RemoveFromThisAccount;
var
  Report, Message: String;
  Left: TArrayOfString;
  ResultCode, I: Integer;
  Ran: Boolean;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), ExpandConstant('/F /T /IM Swangz.exe /FI "USERNAME eq {username}"'), '',
       SW_HIDE, ewWaitUntilTerminated, ResultCode);
  Report := ExpandConstant('{tmp}\swangz-cleanup.txt');
  Ran := Exec(ExpandConstant('{app}\Swangz.exe'), 'cleanup --report "' + Report + '"', '', SW_HIDE,
              ewWaitUntilTerminated, ResultCode);
  if Ran and (ResultCode = 0) then
    exit;
  Message := 'Swangz could not remove everything from this account (code ' + IntToStr(ResultCode) + '). ' +
    'Saved browser sign-ins may still be in ' + ExpandConstant('{localappdata}\Swangz\browser-profiles') + '.' +
    #13#10 + #13#10 + 'To finish: install Swangz again, open it as yourself without administrator rights and choose ' +
    '"Remove Swangz from this account" on This device, or ask your Swangz administrator to disconnect this device ' +
    'in the console.';
  if LoadStringsFromFile(Report, Left) and (GetArrayLength(Left) > 0) then
  begin
    Message := Message + #13#10 + #13#10 + 'Not deleted:';
    for I := 0 to GetArrayLength(Left) - 1 do
      Message := Message + #13#10 + Left[I];
  end;
  Log(Message);
  if not UninstallSilent then
    MsgBox(Message, mbError, MB_OK);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RemoveFromThisAccount;
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKEY_CURRENT_USER, 'Software\Microsoft\Windows\CurrentVersion\Run', 'Swangz');
end;
