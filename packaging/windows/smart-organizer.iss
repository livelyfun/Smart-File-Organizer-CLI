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
; Adds the install directory to the user PATH without clobbering the
; existing value. ReadRegStr/RegWriteStringValue expand the existing
; content, so a user's other PATH entries are preserved.
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}"; Check: NeedsAddPath(ExpandConstant('{app}')); \
    Tasks: addtopath
Root: HKLM; Subkey: "Environment"; ValueType: expandsz; ValueName: "Path"; \
    ValueData: "{olddata};{app}"; Check: NeedsAddPath(ExpandConstant('{app}')); \
    Tasks: addtopath; Flags: uninsdeletevalue

[Run]
; --version proves the installed copy actually runs before the user closes
; the installer, rather than discovering a broken install later.
Filename: "{app}\{#AppExe}"; Parameters: "--version"; \
    Description: "Verifying the installation"; Flags: runhidden; \
    StatusMsg: "Checking that {#AppName} runs..."; BeforeHalt: skipifsilent

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
begin
  if not RegQueryStringValue(HKEY_CURRENT_USER, 'Environment', 'Path', OrigPath) and
     not RegQueryStringValue(HKEY_LOCAL_MACHINE, 'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Param + ';', ';' + OrigPath + ';') = 0;
end;
