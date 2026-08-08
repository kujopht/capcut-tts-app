@echo off
REM ============================================================
REM  BAN DU PHONG - Giao dien Gradio cu (3 giong tieng Viet)
REM  Ung dung chinh la Fanfic Audio Studio: chay run_app.bat
REM ============================================================
setlocal
cd /d "%~dp0"

title CapCut TTS (Gradio - ban du phong)

if not exist ".venv\Scripts\python.exe" (
    echo [LOI] Khong tim thay moi truong ao .venv
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

".venv\Scripts\python.exe" -c "import gradio, requests" 1>nul 2>nul
if errorlevel 1 (
    echo [LOI] Thieu package gradio hoac requests trong .venv
    echo.
    echo     .\.venv\Scripts\Activate.ps1
    echo     pip install -r requirements-gui.txt
    echo.
    pause
    exit /b 1
)

echo Dang khoi dong giao dien Gradio (ban du phong)...
echo Dia chi local: http://127.0.0.1:7860
echo Dong cua so nay hoac nhan Ctrl+C de tat.
echo.

".venv\Scripts\python.exe" legacy_gradio_app.py
set EXITCODE=%ERRORLEVEL%

echo.
if not "%EXITCODE%"=="0" (
    echo [LOI] Ket thuc voi ma loi %EXITCODE%. Xem thong bao ben tren.
) else (
    echo Da dong.
)
pause
exit /b %EXITCODE%
