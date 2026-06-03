; Inno Setup Script for Aegis Optimizer (Phase 12)
; Installs to per-user Local AppData to avoid administrative privilege requirements.

[Setup]
AppName=Aegis Optimizer
AppVersion=1.0.0
AppPublisher=Aegis Team
DefaultDirName={localappdata}\Programs\Aegis
DefaultGroupName=Aegis Optimizer
OutputDir=dist
OutputBaseFilename=AegisSetup
SetupIconFile=logo.ico
Compression=lzma
SolidCompression=yes
PrivilegesRequired=lowest
DisableWelcomePage=no
DisableDirPage=no
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\AegisOptimizer.exe

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "dist\AegisOptimizer.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Aegis Optimizer"; Filename: "{app}\AegisOptimizer.exe"
Name: "{userdesktop}\Aegis Optimizer"; Filename: "{app}\AegisOptimizer.exe"; Tasks: desktopicon

[Run]
Filename: "{app}\AegisOptimizer.exe"; Description: "{cm:LaunchProgram,Aegis Optimizer}"; Flags: nowait postinstall skipifsilent

[Code]
function InitializeSetup(): Boolean;
var
  ResultCode: Integer;
begin
  Result := True;
  // Kill any running instances of AegisOptimizer.exe before proceeding
  Exec('taskkill.exe', '/f /im AegisOptimizer.exe', '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
end;
