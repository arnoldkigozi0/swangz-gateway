; Swangz for Windows, company build: installed once for the whole computer by an administrator (D-026 B4, B5, B7).
; The per-user installer (swangz.iss) stays the one for personal devices and is not changed by this file.
;
;   python packaging\build.py --company          (the one-folder program, dist-company\Swangz)
;   ISCC /DAppVersion=0.1.0 /DSourceFolder=dist-company\Swangz /DOutputDir=artifacts packaging\windows\swangz-company.iss
;
;   Swangz-Company-Setup-<version>-UNSIGNED.exe /ALLUSERS /HUBHOST=... /EXTENSIONID=... /EXTENSIONUPDATEURL=...
;
; What it does, and nothing else:
;   - refuses to run unless it installs for all users (/ALLUSERS, with the administrator's own Windows consent);
;   - installs the program folder into %ProgramFiles%\Swangz and nowhere else, so only administrators can change it;
;   - a Start-menu entry for everyone, and an optional desktop shortcut;
;   - when all three are passed, records the company's pinned values in HKLM\Software\Swangz\Pinned (64-bit view):
;     hub_host, extension_id, extension_update_url. With none, nothing is recorded and an upgrade keeps what is there.
;     A switch that is passed empty is refused like a missing one. This installer only checks that they were typed
;     whole; whether they are acceptable is decided by the later policy step, with the validators in
;     deploy/chrome-policy/prepare.py;
;   - upgrade: first closes the running copies of this installed program, in every Windows session, and changes nothing
;     if a program file is still in use after that (exit code 7);
;   - uninstall: closes every running Swangz.exe on the computer, then removes the program, the shortcuts and the pinned
;     values. It disconnects no device and deletes nothing in anyone's profile: that would run Swangz code with
;     administrator rights over a person's own files. Disconnect each device in the console first. That does not clear
;     provider or Google sign-ins: the Swangz browser folders that hold them stay on the computer.
; It installs no browser, writes no Chrome policy, opens nothing, schedules nothing and adds no service.
; It carries no key or other secret. UNSIGNED until Swangz holds a code-signing certificate (packaging/README.md).

#ifndef AppVersion
  #error Pass /DAppVersion=<version>
#endif
#ifndef SourceFolder
  #define SourceFolder "..\..\dist-company\Swangz"
#endif
#ifndef OutputDir
  #define OutputDir "..\..\artifacts"
#endif

[Setup]
; Its own identity: the company install and a person's own install never overwrite or uninstall each other.
AppId={{c2bec2d1-7154-4e30-8880-089c20048f8e}
AppName=Swangz (company)
AppVersion={#AppVersion}
AppVerName=Swangz (company) {#AppVersion}
AppPublisher=Swangz Avenue
VersionInfoVersion={#AppVersion}
VersionInfoDescription=Swangz AI Hub desktop app, company install (UNSIGNED)
; /ALLUSERS on the command line selects the all-users install; anything else is refused in InitializeSetup.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline
DefaultDirName={autopf}\Swangz
DisableDirPage=yes
DisableProgramGroupPage=yes
DisableReadyPage=no
UninstallDisplayIcon={app}\Swangz.exe
UninstallDisplayName=Swangz (company)
OutputDir={#OutputDir}
OutputBaseFilename=Swangz-Company-Setup-{#AppVersion}-UNSIGNED
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=force
RestartApplications=no
SetupLogging=yes
; Reproducible builds: keep the program's own (source-dated) file times instead of stamping the compile time.
TouchDate=none
TouchTime=none

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut for everyone"; GroupDescription: "Shortcuts:"; Flags: unchecked

[InstallDelete]
; An upgrade leaves no file of the previous version where the program loads its code from.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "{#SourceFolder}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Swangz"; Filename: "{app}\Swangz.exe"; Comment: "Swangz AI Hub"
Name: "{autodesktop}\Swangz"; Filename: "{app}\Swangz.exe"; Comment: "Swangz AI Hub"; Tasks: desktopicon

[Registry]
; Everyone can read HKLM\Software; only administrators can write it. Removed on uninstall (CurUninstallStepChanged).
Root: HKLM64; Subkey: "Software\Swangz\Pinned"; ValueType: string; ValueName: "hub_host"; ValueData: "{param:HUBHOST|}"; Check: PinsGiven
Root: HKLM64; Subkey: "Software\Swangz\Pinned"; ValueType: string; ValueName: "extension_id"; ValueData: "{param:EXTENSIONID|}"; Check: PinsGiven
Root: HKLM64; Subkey: "Software\Swangz\Pinned"; ValueType: string; ValueName: "extension_update_url"; ValueData: "{param:EXTENSIONUPDATEURL|}"; Check: PinsGiven

[UninstallRun]
; Every process named Swangz.exe, whoever started it and wherever it runs from (a person's own copy too), with the
; programs it started, so the program folder can be removed.
Filename: "{sys}\taskkill.exe"; Parameters: "/F /T /IM Swangz.exe"; RunOnceId: "SwangzCompanyStop"; Flags: runhidden waituntilterminated

[Code]
const
  UninstallKey = 'Software\Microsoft\Windows\CurrentVersion\Uninstall\{c2bec2d1-7154-4e30-8880-089c20048f8e}_is1';

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

function PinValue(Name: String): String;
begin
  Result := ExpandConstant('{param:' + Name + '|}');
end;

// True when the switch is on the command line at all, with or without a value: PinValue cannot tell an empty one from
// an absent one.
function SwitchPassed(Name: String): Boolean;
var
  I: Integer;
  Arg: String;
begin
  Result := False;
  for I := 1 to ParamCount do begin
    Arg := Uppercase(ParamStr(I));
    if (Arg = '/' + Name) or (Pos('/' + Name + '=', Arg) = 1) then
      Result := True;
  end;
end;

// True when any of the three was passed. InitializeSetup has then already required all three, each with a value.
function PinsGiven(): Boolean;
begin
  Result := SwitchPassed('HUBHOST') or SwitchPassed('EXTENSIONID') or SwitchPassed('EXTENSIONUPDATEURL');
end;

// Present, and printable ASCII without spaces, quotes or backslashes: catches a mistyped command line, nothing more.
function TypedWhole(Value: String): Boolean;
var
  I: Integer;
begin
  Result := (Length(Value) > 0) and (Length(Value) <= 2048);
  for I := 1 to Length(Value) do
    if (Ord(Value[I]) < 33) or (Ord(Value[I]) > 126) or (Value[I] = '"') or (Value[I] = '\') then
      Result := False;
end;

function InitializeSetup(): Boolean;
var
  Problem, Installed: String;
begin
  Problem := '';
  if not IsAdminInstallMode then
    Problem := 'This is the company build. An administrator installs it for the whole computer, with /ALLUSERS.'
  else if PinsGiven() and not (TypedWhole(PinValue('HUBHOST')) and TypedWhole(PinValue('EXTENSIONID')) and
      TypedWhole(PinValue('EXTENSIONUPDATEURL'))) then
    Problem := 'Pass all three of /HUBHOST=, /EXTENSIONID= and /EXTENSIONUPDATEURL= (no spaces or quotes), or none of them.'
  // An older build never replaces a newer one: installing it would roll back fixes without anyone noticing.
  else if RegQueryStringValue(HKLM64, UninstallKey, 'DisplayVersion', Installed) and
      (CompareVersions('{#AppVersion}', Installed) < 0) then
    Problem := 'Swangz ' + Installed + ' is installed; this installer is the older version {#AppVersion}.';
  Result := Problem = '';
  if not Result then begin
    Log('Refused: ' + Problem);
    SuppressibleMsgBox(Problem, mbCriticalError, MB_OK, IDOK);
  end;
end;

// Ends the processes whose program is exactly the installed Swangz.exe, in every Windows session. A person's own copy
// elsewhere and the programs a copy started are left running. A failure here is only logged: CompanyCopiesStopped
// decides by looking at the files.
procedure EndCompanyCopies();
var
  Locator, Service, Found, Item: Variant;
  I: Integer;
  Path: String;
begin
  try
    Locator := CreateOleObject('WbemScripting.SWbemLocator');
    Service := Locator.ConnectServer('.', 'root\CIMV2');
    // another person's process can only be ended with the debug privilege an administrator holds
    Service.Security_.Privileges.AddAsString('SeDebugPrivilege', True);
    Found := Service.ExecQuery('SELECT * FROM Win32_Process WHERE Name = ''Swangz.exe''');
    for I := 0 to Found.Count - 1 do
      try
        Item := Found.ItemIndex(I);
        if not VarIsNull(Item.ExecutablePath) then begin
          Path := Item.ExecutablePath;
          if CompareText(Path, ExpandConstant('{app}\Swangz.exe')) = 0 then
            Item.Terminate();
        end;
      except
        Log('Could not end a running copy: ' + GetExceptionMessage);
      end;
  except
    Log('Could not look for running copies: ' + GetExceptionMessage);
  end;
end;

// True when nothing holds the file: it opens for writing with no sharing. Nothing is written.
function FileIsFree(Path: String): Boolean;
var
  Stream: TFileStream;
begin
  try
    Stream := TFileStream.Create(Path, fmOpenReadWrite or fmShareExclusive);
    Stream.Free;
    Result := True;
  except
    Log('In use: ' + Path);
    Result := False;
  end;
end;

function FolderIsFree(Folder: String): Boolean;
var
  Found: TFindRec;
begin
  Result := True;
  if FindFirst(Folder + '\*', Found) then
    try
      repeat
        if (Found.Name <> '.') and (Found.Name <> '..') then begin
          if (Found.Attributes and FILE_ATTRIBUTE_DIRECTORY) <> 0 then
            Result := FolderIsFree(Folder + '\' + Found.Name)
          else
            Result := FileIsFree(Folder + '\' + Found.Name);
        end;
      until not Result or not FindNext(Found);
    finally
      FindClose(Found);
    end;
end;

// Before an upgrade: close the installed copies, then wait (about 15 seconds at most) until no program file is in use.
function CompanyCopiesStopped(): Boolean;
var
  Attempt: Integer;
  Exe: String;
begin
  Exe := ExpandConstant('{app}\Swangz.exe');
  Result := False;
  for Attempt := 1 to 15 do begin
    EndCompanyCopies();
    Sleep(1000);
    Result := (not FileExists(Exe) or FileIsFree(Exe)) and FolderIsFree(ExpandConstant('{app}\_internal'));
    if Result then
      Break;
  end;
end;

// Runs before any file is deleted or written; a silent install that is refused here ends with exit code 7.
//   - /DIR= (or a saved answer file) must not move the program somewhere other people can change it;
//   - an upgrade over files that are in use would leave half of the old program and half of the new one.
function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  Result := '';
  if CompareText(RemoveBackslashUnlessRoot(ExpandConstant('{app}')), ExpandConstant('{commonpf64}\Swangz')) <> 0 then
    Result := 'The company build installs only into ' + ExpandConstant('{commonpf64}\Swangz') + '.'
  else if DirExists(ExpandConstant('{app}')) and not CompanyCopiesStopped() then
    Result := 'Swangz is still in use on this computer, so nothing was changed. Close it for every person signed in ' +
      '(or restart the computer), then run this installer again.';
  if Result <> '' then
    Log('Refused: ' + Result);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then begin
    RegDeleteKeyIncludingSubkeys(HKLM64, 'Software\Swangz\Pinned');
    RegDeleteKeyIfEmpty(HKLM64, 'Software\Swangz');
  end;
end;
