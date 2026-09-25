; Inno Setup script for the Smart File Organizer.
;
; Wraps the already-built onedir bundle. It deliberately installs nothing
; but the bundle: the executable is self-contained, so there is no Python
; prerequisite and nothing to uninstall beyond the install directory.
;
; The version is passed in by packaging/build.py as /DAppVersion=... so the
; single source of truth stays __version__ in the package. It is not
; restated here.
;
; Build with:
;   iscc /DAppVersion=1.0.0 smart-organizer.iss

#ifndef AppVersion
  #error "AppVersion must be defined. Build via packaging/build.py."
#endif

#define AppName "Smart File Organizer"
#define AppPublisher "Smart File Organizer Contributors"
#define AppExe "smart-organizer.exe"

[Setup]
AppId={{7C4E1B2A-9D3F-4A6E-8B21-5F0C7D9A4E11}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputBaseFilename=SmartFileOrganizer-{#AppVersion}-setup
OutputDir=..\output
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Per-user by default: no administrator rights needed, which is what a
; file-organising utility should require.
PrivilegesRequiredOverridesAllowed=dialog
PrivilegesRequired=lowest
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}
SetupIconFile=..\pyinstaller\app.ico
; Unsigned for now. Signing needs a code-signing certificate, which this
; project does not have; see docs/packaging.md. No SignTool directive is
; present because an empty one is rejected by the compiler.
[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "addtopath"; Description: "Add &smart-organizer to PATH so it can be run from any terminal"; GroupDescription: "Integration:"
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Integration:"; Flags: unchecked

[Files]
Source: "..\output\smart-organizer\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; PATH is only ever appended to, never rewritten wholesale: {olddata}
; expands to the existing value, so the user's other entries survive.
;
; HKCU only. This installer defaults to a per-user install, so it has no
; business writing HKLM, where the write would fail without elevation.
;
; There is deliberately no uninsdeletevalue here. That flag deletes the
; whole "Path" value, taking every other entry on the user's PATH with it.
; Uninstall instead removes only this application's entry, in the
; RemoveFromPath function below.
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}"; Check: NeedsAddPath(ExpandConstant('{app}')); \
    Tasks: addtopath

[Run]
; --version proves the installed copy actually runs before the user closes
; the installer, rather than discovering a broken install later.
Filename: "{app}\{#AppExe}"; Parameters: "--version"; \
    Description: "Verifying the installation"; Flags: runhidden; \
    StatusMsg: "Checking that {#AppName} runs..."

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;

{ Removes only this application's entry from the user PATH, leaving every
  other entry untouched and in its original order.

  The value is wrapped in semicolons so that an entry at either end still
  has a delimiter on both sides, which makes the match uniform. The
  separators that wrapping adds are stripped again afterwards. }
procedure RemoveFromPath(Param: string);
var
  OrigPath: string;
  Wrapped: string;
  NewPath: string;
  P: Integer;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) then
    exit;

  Wrapped := ';' + OrigPath + ';';
  P := Pos(';' + Param + ';', Wrapped);
  if P = 0 then
    exit;

  { Keep the separator that precedes Param so the surrounding entries stay
    separated, then append everything after the match. }
  NewPath := Copy(Wrapped, 2, P - 1) + Copy(Wrapped, P + Length(Param) + 2, MaxInt);
  if (Length(NewPath) > 0) and (NewPath[Length(NewPath)] = ';') then
    Delete(NewPath, Length(NewPath), 1);

  RegWriteExpandStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', NewPath);
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usUninstall then
    RemoveFromPath(ExpandConstant('{app}'));
end;
