; Inno Setup script for the GeoLab Windows installer.
;   iscc /DAppVersion=2.7.0 installer\geolab.iss      (after python build.py)
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6C1E3F4A-0B7D-4C55-9E7A-6A9D3B2F7E10}
AppName=GeoLab
AppVersion={#AppVersion}
AppPublisher=GeoLab
AppPublisherURL=https://github.com/ArghoAdhikary/GeoLab
DefaultDirName={autopf}\GeoLab
DefaultGroupName=GeoLab
UninstallDisplayIcon={app}\GeoLab.exe
OutputDir=..\release
OutputBaseFilename=GeoLab-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ChangesAssociations=yes
LicenseFile=..\LICENSE

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "assoc"; Description: "Open .slab project files with GeoLab"; GroupDescription: "File types:"

[Files]
Source: "..\dist\GeoLab\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\GeoLab"; Filename: "{app}\GeoLab.exe"
Name: "{group}\GeoLab User Manual"; Filename: "{app}\_internal\help\GeoLab-User-Manual.pdf"; Check: FileExists(ExpandConstant('{app}\_internal\help\GeoLab-User-Manual.pdf'))
Name: "{group}\Uninstall GeoLab"; Filename: "{uninstallexe}"
Name: "{autodesktop}\GeoLab"; Filename: "{app}\GeoLab.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.slab"; ValueType: string; ValueName: ""; ValueData: "GeoLab.Project"; Flags: uninsdeletevalue; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\GeoLab.Project"; ValueType: string; ValueName: ""; ValueData: "GeoLab project"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\GeoLab.Project\DefaultIcon"; ValueType: string; ValueName: ""; ValueData: "{app}\GeoLab.exe,0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\GeoLab.Project\shell\open\command"; ValueType: string; ValueName: ""; ValueData: """{app}\GeoLab.exe"" ""%1"""; Tasks: assoc

[Run]
Filename: "{app}\GeoLab.exe"; Description: "{cm:LaunchProgram,GeoLab}"; Flags: nowait postinstall skipifsilent
