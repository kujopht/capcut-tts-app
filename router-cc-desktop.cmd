@echo off
setlocal
cd /d "%~dp0"

rem Router Control Center V0.2 — VO DESKTOP, chay tu ma nguon.
rem
rem Duong CHINH cho nguoi dung la "Router Control Center.exe" (bam doi).
rem Tep nay de chay khi CHUA build EXE, va de go loi vo desktop.
rem
rem Dung `pythonw.exe` nen KHONG co cua so console nao — giong EXE.
rem
rem 2026-09-10 — VI SAO TEP NAY CUNG LA DUONG DEV KHUYEN NGHI DUOI SMART APP
rem CONTROL: may nay bat Smart App Control cuong che. Ban EXE PyInstaller KHONG
rem KY chi mo duoc neu dam may ISG tra "known good" cho DUNG bam cua ban do; moi
rem lan dung lai la mot bam moi, nen "mo duoc" la xo so (dist-v0612 chay,
rem dist-v061 dung lai tu cung ma bi chan). `pythonw.exe` cua Python Software
rem Foundation (ke ca launcher trong venv) da KY hop le boi CA cong cong nen
rem Smart App Control cho chay; ma Python (payload) khong thuoc pham vi kiem
rem cua no o ca hai cach dong goi — khong co gi bi noi. Do that: cua so len
rem sau 4 s, 0 su kien Code Integrity. Xem docs/reports/SMART_APP_CONTROL_V061.md.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set "PY="
set "PYW="
if exist "C:\Users\nguye\Documents\CapCut-TTS-App\.venv\Scripts\python.exe" (
  set "PY=C:\Users\nguye\Documents\CapCut-TTS-App\.venv\Scripts\python.exe"
  set "PYW=C:\Users\nguye\Documents\CapCut-TTS-App\.venv\Scripts\pythonw.exe"
) else if exist ".venv\Scripts\python.exe" (
  set "PY=.venv\Scripts\python.exe"
  set "PYW=.venv\Scripts\pythonw.exe"
) else (
  set "PY=python"
  set "PYW=pythonw"
)

rem Kiem phu thuoc bang python CO console, vi duoi `pythonw` thi khong co
rem stderr nao de doc. `desktop.py` cung tu bat MessageBox, nen ca hai duong
rem deu co thong bao.
"%PY%" -m scripts.control_center.desktop --check
if errorlevel 1 (
  echo.
  echo [router-cc-desktop] Khong mo duoc — xem thong bao o tren.
  echo.
  pause
  exit /b 2
)

if exist "%PYW%" (
  start "" "%PYW%" -m scripts.control_center.desktop %*
  exit /b 0
)
"%PY%" -m scripts.control_center.desktop %*
exit /b %errorlevel%
