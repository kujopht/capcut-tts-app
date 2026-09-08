@echo off
setlocal
cd /d "%~dp0"

rem Router Control Center V0.1.1 — GIAO DIEN DO HOA.
rem
rem Tep nay BAM DOI duoc tu Explorer. Do la yeu cau nghiem thu so 1, nen
rem no khong duoc doi hoi bat ky bien moi truong nao duoc dat truoc.
rem
rem UTF-8 BAT BUOC, cung ly do da ghi o `router-cc.cmd`: toan bo van ban
rem giao dien la tieng Viet co dau, va tren console Windows mac dinh
rem (cp1252/cp437) chi rieng `--help` da do UnicodeEncodeError trong
rem argparse TRUOC khi cua so kip mo.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

rem Chon trinh thong dich: uu tien venv kho chinh (noi PySide6 that su
rem duoc cai), roi venv cuc bo, roi PATH.
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

rem KIEM PHU THUOC TRUOC, bang python CO console.
rem
rem VI SAO BUOC NAY TON TAI: duong chinh chay bang `pythonw.exe` de khong
rem nhay ra mot cua so console den. Nhung duoi `pythonw` thi KHONG co
rem stderr nao de doc — nen neu PySide6 chua duoc cai, bam doi vao tep nay
rem se HOAN TOAN IM LANG. Kiem truoc bang `python` co console thi thong
rem bao con doc duoc, va con giu duoc cua so lai de nguoi dung kip doc.
rem (`__main__.py` cung tu bat mot MessageBox qua ctypes, nen ca hai duong
rem deu co thong bao — mot cai rao khong nen chi co mot lop.)
"%PY%" -m scripts.control_center.gui --check
if errorlevel 1 (
  echo.
  echo [router-cc-gui] Khong mo duoc giao dien — xem thong bao o tren.
  echo.
  pause
  exit /b 2
)

rem Phu thuoc du: mo giao dien KHONG kem cua so console.
rem
rem Neu khong co `pythonw.exe` (mot so ban Python rut gon khong kem no),
rem chay bang `python` con console — cham hon ve tham my nhung VAN MO
rem DUOC, va do la thu quan trong hon.
if exist "%PYW%" (
  start "" "%PYW%" -m scripts.control_center.gui %*
  exit /b 0
)
"%PY%" -m scripts.control_center.gui %*
exit /b %errorlevel%
