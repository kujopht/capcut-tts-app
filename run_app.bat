@echo off
REM ============================================================
REM  Fanfic Audio Studio - ung dung desktop (PySide6)
REM  Nhap dup file nay de mo app. Khong tu cai package.
REM ============================================================
setlocal
cd /d "%~dp0"

title Fanfic Audio Studio

if not exist ".venv\Scripts\python.exe" (
    echo ============================================================
    echo  [LOI] Khong tim thay moi truong ao .venv
    echo ============================================================
    echo.
    echo Hay chay 1 lan cac lenh sau trong PowerShell tai thu muc nay:
    echo.
    echo     python -m venv .venv
    echo     .\.venv\Scripts\Activate.ps1
    echo     pip install -r requirements-gui.txt
    echo.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"
if errorlevel 1 (
    echo [LOI] Khong kich hoat duoc .venv
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -c "import PySide6, requests, docx" 1>nul 2>nul
if errorlevel 1 (
    echo ============================================================
    echo  [LOI] Thieu package trong .venv ^(PySide6 / requests / python-docx^)
    echo ============================================================
    echo.
    echo Hay chay 1 lan lenh sau trong PowerShell tai thu muc nay:
    echo.
    echo     .\.venv\Scripts\Activate.ps1
    echo     pip install -r requirements-gui.txt
    echo.
    pause
    exit /b 1
)

echo Dang khoi dong Fanfic Audio Studio...
echo (Day la ung dung desktop - khong mo trinh duyet, khong dung localhost)
echo.

".venv\Scripts\pythonw.exe" app.py
set EXITCODE=%ERRORLEVEL%

REM Chi giu cua so mo khi khoi dong that bai
if not "%EXITCODE%"=="0" (
    echo.
    echo ============================================================
    echo  [LOI] App ket thuc voi ma loi %EXITCODE%
    echo ============================================================
    echo.
    echo Chay lai bang python.exe de xem thong bao loi chi tiet:
    echo.
    ".venv\Scripts\python.exe" app.py
    echo.
    pause
    exit /b %EXITCODE%
)

exit /b 0
