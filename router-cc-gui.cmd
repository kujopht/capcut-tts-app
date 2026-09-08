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

rem `pythonw.exe` = khong mo cua so console kem theo. Day la khac biet giua
rem "mot app desktop" va "mot chuong trinh terminal co cua so", va bam doi
rem ma nhay ra mot khung den la dung cai an tuong ban nay phai bo.
rem
rem Uu tien venv cua kho chinh (noi PySide6 that su duoc cai), roi den venv
rem cuc bo, roi moi den PATH.
set "PYW=C:\Users\nguye\Documents\CapCut-TTS-App\.venv\Scripts\pythonw.exe"
set "PY=C:\Users\nguye\Documents\CapCut-TTS-App\.venv\Scripts\python.exe"

if exist "%PYW%" (
  start "" "%PYW%" -m scripts.control_center.gui %*
  goto :eof
)
if exist ".venv\Scripts\pythonw.exe" (
  start "" ".venv\Scripts\pythonw.exe" -m scripts.control_center.gui %*
  goto :eof
)
if exist "%PY%" (
  "%PY%" -m scripts.control_center.gui %*
  goto :eof
)

rem Khong tim thay venv nao: chay bang PATH va GIU cua so lai neu loi, de
rem thong bao "thieu PySide6" con doc duoc thay vi nhay mat.
python -m scripts.control_center.gui %*
if errorlevel 1 (
  echo.
  echo [router-cc-gui] khong mo duoc giao dien. Xem thong bao o tren.
  echo   Cai dat:  python -m pip install -r requirements-control-center-gui.txt
  echo.
  pause
)
