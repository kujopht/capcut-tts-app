@echo off
setlocal
cd /d "%~dp0"

rem Router Control Center V0.2 — VO DESKTOP, chay tu ma nguon.
rem
rem Duong CHINH cho nguoi dung la "Router Control Center.exe" (bam doi).
rem Tep nay de chay khi CHUA build EXE, va de go loi vo desktop.
rem
rem Dung `pythonw.exe` nen KHONG co cua so console nao — giong EXE.
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
