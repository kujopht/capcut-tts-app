# Launcher ben cho worker TTS PRODUCTION tren Windows — Task Scheduler goi vao.
#
# VI SAO TON TAI: worker chay trong mot terminal se chet cung terminal do.
# Task Scheduler goi script nay luc dang nhap VA lap lai moi 5 phut; script
# tu bao dam MOT instance duy nhat nen viec goi lap chi la luoi an toan, khong
# phai nguon sinh worker trung.
#
# MOT INSTANCE — HAI LOP:
#   1. KHOA FILE exclusive (worker.lock trong var-production): rao chinh.
#      Khoa kernel nen thay duoc nhau bat chap elevation/phien — dieu ma viec
#      doc CommandLine cua tien trinh khac KHONG lam duoc (CIM tra NULL khi
#      khac elevation; da vap that ngay 13/08/2026, sinh worker trung).
#      Launcher giu khoa suot vong doi worker; chet kieu gi OS cung nha khoa.
#   2. Quet tien trinh python co 'server.worker': luoi phu, bat truong hop
#      ai do chay worker TAY khong qua launcher o CUNG elevation.
#   Task Scheduler con dat MultipleInstances=IgnoreNew o tang task.
#   => Khi can chay worker TAY, hay chay CHINH SCRIPT NAY thay vi go lenh
#      python truc tiep — de duoc huong khoa file.
#
# LOG: server\var-production\logs\worker-YYYYMMDD.log — chi stdout/stderr cua
# worker, khong bao gio in gia tri bien moi truong hay bi mat.
#
# DUNG TAY:
#   Stop-ScheduledTask -TaskName 'FanficWorld TTS Worker (production)'
#   (tat han: Disable-ScheduledTask cung ten; bat lai: Enable-ScheduledTask)
# KIEM TRA SUC KHOE:
#   Get-ScheduledTaskInfo -TaskName 'FanficWorld TTS Worker (production)'
#   Get-Content server\var-production\logs\worker-*.log -Tail 20

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot   # script nam trong server\ -> repo
Set-Location $repo

$varDir = Join-Path $repo 'server\var-production'
$logDir = Join-Path $varDir 'logs'
New-Item -ItemType Directory -Force $logDir | Out-Null
$log = Join-Path $logDir ('worker-{0:yyyyMMdd}.log' -f (Get-Date))

# -- lop 2 truoc (re): quet tien trinh cung elevation -------------------------
$dangChay = Get-CimInstance Win32_Process -Filter "Name like 'python%'" |
    Where-Object { $_.CommandLine -match 'server\.worker' }
if ($dangChay) { exit 0 }

# -- lop 1 (quyet dinh): khoa file exclusive -----------------------------------
$lockPath = Join-Path $varDir 'worker.lock'
try {
    $lock = [System.IO.File]::Open($lockPath, 'OpenOrCreate', 'ReadWrite', 'None')
} catch {
    # Nguoi khac dang giu khoa -> worker dang song o dau do. Thoat im lang.
    exit 0
}

try {
    $env:FAS_ENV_FILE = 'server/.env.production'
    $env:FAS_VAR_DIR  = $varDir

    Add-Content $log ('[{0:u}] launcher: khoi dong worker' -f (Get-Date))
    # Chan (khong Start-Process): vong doi task = vong doi worker, nen khoa
    # file duoc giu suot, va lan lap 5 phut sau bi IgnoreNew/khoa chan lai.
    # Out-File -Encoding UTF8 thay vi `*>>`: PowerShell 5.1 redirect truc tiep
    # ghi UTF-16 (log day ky tu gian cach, kho doc/grep).
    & "$repo\.venv\Scripts\python.exe" -m server.worker --require-env production 2>&1 |
        Out-File -FilePath $log -Append -Encoding UTF8
    $ma = $LASTEXITCODE
    Add-Content $log ('[{0:u}] launcher: worker thoat ma {1}' -f (Get-Date), $ma)
    # Ma 2 = rao chan --require-env tu choi (env file sai). Task se thu lai o
    # lan lap sau nhung cung se thoat ma 2 — doc log de biet vi sao.
    exit $ma
} finally {
    $lock.Dispose()
}
