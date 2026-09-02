@echo off
REM Worker TTS production tren laptop Windows nay - vong lap tu khoi dong lai.
REM
REM KHONG dung schtasks/Scheduled Task: co chu dich, xem
REM deploy/windows/README.md muc "Vi sao Startup folder, khong phai
REM Scheduled Task". Duoc goi tu deploy/windows/start_worker_silent.vbs, ma
REM file do duoc dat trong Startup folder cua Windows de tu chay khi dang nhap.
REM
REM Doc credential tu server\.env.production (khong bao gio in ra noi dung).

setlocal enabledelayedexpansion
cd /d "%~dp0..\.."

set FAS_ENV_FILE=server\.env.production
set LOG_DIR=server\var\worker\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

if not exist "server\.env.production" (
    echo [%date% %time%] LOI: server\.env.production khong ton tai - dung han. >> "%LOG_DIR%\worker.log"
    exit /b 1
)

if not exist ".venv\Scripts\python.exe" (
    echo [%date% %time%] LOI: khong thay .venv\Scripts\python.exe - dung han. >> "%LOG_DIR%\worker.log"
    exit /b 1
)

:loop
echo [%date% %time%] Khoi dong worker (pid se hien trong nhat ky worker rieng) >> "%LOG_DIR%\worker.log"
".venv\Scripts\python.exe" -m server.worker --require-env production >> "%LOG_DIR%\worker.log" 2>&1
echo [%date% %time%] Worker thoat voi ma loi %errorlevel% - khoi dong lai sau 10 giay >> "%LOG_DIR%\worker.log"
timeout /t 10 /nobreak >nul
goto loop
