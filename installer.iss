; ============================================================
;  Inno Setup script - Fanfic Audio Studio
;  Yeu cau: da chay build_app.bat truoc (co dist\FanficAudioStudio\)
;  Ket qua:  installer_output\FanficAudioStudioSetup.exe
;
;  Ban cai dat nay KHONG yeu cau nguoi dung co Python:
;  PyInstaller da dong goi san Python runtime + PySide6 vao dist\.
;
;  KHONG dong goi device.json / token / credential.
; ============================================================

#define MyAppName "Fanfic Audio Studio"
#define MyAppShortName "FanficAudioStudio"
#define MyAppVersion "2.0.0"
#define MyAppPublisher "Fanfic Audio Studio"
#define MyAppExeName "FanficAudioStudio.exe"

[Setup]
AppId={{8E4C1F62-3A71-4D58-9C2E-7B5A9D0F16C4}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=installer_output
OutputBaseFilename=FanficAudioStudioSetup
SetupIconFile=assets\app_icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
ArchitecturesAllowed=x64compatible
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "vietnamese"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Tao shortcut tren Desktop"; \
    GroupDescription: "Shortcut:"; Flags: unchecked

[Files]
; Toan bo ban build --onedir cua PyInstaller
Source: "dist\{#MyAppShortName}\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "dist\{#MyAppShortName}\*"; DestDir: "{app}"; \
    Flags: ignoreversion recursesubdirs createallsubdirs; \
    Excludes: "device.json,*.token,*.secret,*.pem,*.key,make_icon.py"

; Bo chung chi goc cua certifi: BAT BUOC cho HTTPS (thu vien requests doc file
; nay qua certifi.where()). Day la chung chi goc CONG KHAI, khong phai credential.
; Phai them lai o day vi bo loc "*.pem" ben tren da loai no ra - neu thieu file
; nay thi ban CAI DAT se loi SSL khi goi API, trong khi ban dist van chay binh thuong.
Source: "dist\{#MyAppShortName}\_internal\certifi\cacert.pem"; \
    DestDir: "{app}\_internal\certifi"; Flags: ignoreversion

; Tai lieu
Source: "README_GUI.md"; DestDir: "{app}"; Flags: ignoreversion isreadme

[Icons]
; Start Menu
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    IconFilename: "{app}\{#MyAppExeName}"
; Desktop (tuy chon)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; \
    IconFilename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; \
    Description: "Mở {#MyAppName} ngay"; \
    Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Chi xoa cache do app tao trong thu muc cai dat.
; KHONG xoa outputs cua nguoi dung (nam trong Documents) va KHONG xoa
; device.json runtime trong AppData - nguoi dung tu quyet dinh.
Type: filesandordirs; Name: "{app}\__pycache__"

[Messages]
vietnamese.WelcomeLabel2=Trình cài đặt sẽ cài [name/ver] vào máy của bạn.%n%nỨng dụng đã đóng gói sẵn Python nên bạn KHÔNG cần cài Python.%n%nKết quả audio sẽ được lưu trong Documents\Fanfic Audio Studio\outputs.
