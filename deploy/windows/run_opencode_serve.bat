@echo off
REM Khoi dong "opencode serve" - HTTP server ma scripts/router_v3/opencode_adapter.py
REM can de bao cao Health.HEALTHY. Khong co tien trinh nay, Router V3 luon
REM thay OPENCODE01 la UNAVAILABLE du CLI da cai va da dang nhap - day CHINH
REM la lo hong "discovery cu" phat hien khi dieu tra mission "Chinese Media
REM Watcher + Drive Archive Proof" (2026-09-02), khong phai loi trong ma
REM nguon router. Cung mau voi run_worker.bat: vong lap tu khoi dong lai.

setlocal enabledelayedexpansion
set LOG_DIR=%~dp0..\..\server\var\worker\logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

:loop
echo [%date% %time%] Khoi dong opencode serve >> "%LOG_DIR%\opencode_serve.log"
opencode serve --port 4096 --hostname 127.0.0.1 >> "%LOG_DIR%\opencode_serve.log" 2>&1
echo [%date% %time%] opencode serve thoat voi ma loi %errorlevel% - khoi dong lai sau 10 giay >> "%LOG_DIR%\opencode_serve.log"
timeout /t 10 /nobreak >nul
goto loop
