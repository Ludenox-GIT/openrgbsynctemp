; OpenRGB Temp Sync - Inno Setup Script
#define MyAppName "OpenRGB Temp Sync"
#define MyAppVersion "1.0.0"
#define MyAppPublisher "OpenRGB Temp Sync Contributors"
#define MyAppURL "https://openrgb.org"
#define MyAppExeName "OpenRGBTempSync.exe"

[Setup]
AppId={{E57D8BE1-8C52-47C2-9A4E-66911D7B4810}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}
DefaultDirName={autopf}\{#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\release
OutputBaseFilename=OpenRGBTempSync-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "startuptask"; Description: "Start with Windows (elevated logon task)"; GroupDescription: "Windows Startup:"

[Files]
Source: "..\dist\OpenRGBTempSync\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\third_party\THIRD-PARTY-NOTICES.md"; DestDir: "{app}\licenses"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "schtasks.exe"; Parameters: "/Create /F /TN ""OpenRGBTempSync"" /TR ""\""{app}\{#MyAppExeName}\"""" /SC ONLOGON /RL HIGHEST"; Tasks: startuptask; Flags: runhidden
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "powershell.exe"; Parameters: "-NoProfile -NonInteractive -ExecutionPolicy Bypass -Command ""Get-Process -Name 'OpenRGBTempSync' -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -and ($_.Path.ToLower() -eq '{app}\{#MyAppExeName}'.ToLower()) } | Stop-Process -Force"""; Flags: runhidden; RunOnceId: "StopApplication"
Filename: "schtasks.exe"; Parameters: "/Delete /F /TN ""OpenRGBTempSync"""; Flags: runhidden; RunOnceId: "RemoveStartupTask"

[Code]
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  LocalAppDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    LocalAppDir := ExpandConstant('{localappdata}\OpenRGBTempSync');
    if DirExists(LocalAppDir) then
    begin
      if MsgBox('Do you want to delete your saved configurations, logs, and backups in ' + LocalAppDir + '?', mbConfirmation, MB_YESNO) = IDYES then
      begin
        DelTree(LocalAppDir, True, True, True);
      end;
    end;
  end;
end;
