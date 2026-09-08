@echo off
setlocal
cd /d "%~dp0"

rem Router Control Center V0.2 — GIAO DIEN WEB (duong chinh).
rem
rem Tep nay BAM DOI duoc tu Explorer. Khong can PowerShell, khong can Node,
rem khong can dat bien moi truong nao truoc.
rem
rem UTF-8 BAT BUOC, cung ly do da ghi o `router-cc.cmd`: toan bo van ban la
rem tieng Viet co dau, va tren console Windows mac dinh (cp1252/cp437) chi
rem rieng `--help` da do UnicodeEncodeError trong argparse.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

rem Chon trinh thong dich: uu tien venv kho chinh (noi fastapi/uvicorn that
rem su duoc cai), roi venv cuc bo, roi PATH.
set "PY="
if exist "C:\Users\nguye\Documents\CapCut-TTS-App\.venv\Scripts\python.exe" (
  set "PY=C:\Users\nguye\Documents\CapCut-TTS-App\.venv\Scripts\python.exe"
) else if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
) else (
  set "PY=python"
)

rem KIEM PHU THUOC TRUOC. Neu thieu, `--check` bat mot MessageBox va thoat
rem 2, nen nguoi bam doi van doc duoc thong bao thay vi thay cua so nhay
rem roi mat.
"%PY%" -m scripts.control_center.webmain --check
if errorlevel 1 (
  echo.
  echo [router-cc-web] Khong mo duoc giao dien — xem thong bao o tren.
  echo.
  pause
  exit /b 2
)

rem Chay server. Cua so console NAY la nhat ky cua server, va giu no lai la
rem co y: dong cua so = tat server. Trinh duyet tu mo sau ~0.8s.
echo Dang mo giao dien web... (dong cua so nay se TAT server)
"%PY%" -m scripts.control_center.webmain %*
if errorlevel 1 pause
