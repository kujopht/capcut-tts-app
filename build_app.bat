@echo off
REM ============================================================
REM  Build EXE cho Fanfic Audio Studio bang PyInstaller
REM  Ket qua: dist\FanficAudioStudio\FanficAudioStudio.exe
REM ============================================================
setlocal
cd /d "%~dp0"

title Build Fanfic Audio Studio

if not exist ".venv\Scripts\python.exe" (
    echo [LOI] Khong tim thay .venv
    echo     python -m venv .venv
    echo     .\.venv\Scripts\Activate.ps1
    echo     pip install -r requirements-gui.txt
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

".venv\Scripts\python.exe" -c "import PyInstaller" 1>nul 2>nul
if errorlevel 1 (
    echo [LOI] Chua cai PyInstaller trong .venv
    echo     .\.venv\Scripts\Activate.ps1
    echo     pip install -r requirements-gui.txt
    pause
    exit /b 1
)

if not exist "assets\app_icon.ico" (
    echo Dang tao icon...
    ".venv\Scripts\python.exe" assets\make_icon.py
)
if not exist "assets\app_icon.png" (
    echo [LOI] Thieu assets\app_icon.png - logo sidebar se khong hien thi.
    pause
    exit /b 1
)

echo.
echo === Xoa ban build cu ===
if exist "build\FanficAudioStudio" rmdir /s /q "build\FanficAudioStudio"
if exist "dist\FanficAudioStudio" rmdir /s /q "dist\FanficAudioStudio"

echo.
echo === Bat dau build (onedir, windowed) ===
echo.

REM LUU Y: KHONG dong goi device.json / token / credential vao EXE.
REM edge_tts / piper / onnxruntime duoc import LAZY trong provider nen
REM PyInstaller khong tu phat hien; phai --collect-all, nhat la thu muc
REM espeak-ng-data cua piper (thieu no thi Piper khong chay tren may nguoi dung).
REM QtMultimedia KHONG duoc loai tru: nut "Nghe thu" dung QMediaPlayer de phat/dung.
REM Nguoi dung tu nhap device.json trong Cai dat; file duoc luu o AppData.
".venv\Scripts\python.exe" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --onedir ^
    --windowed ^
    --name "FanficAudioStudio" ^
    --icon=assets\app_icon.ico ^
    --add-data "Voice.json;." ^
    --add-data "assets;assets" ^
    --hidden-import "desktop_app" ^
    --collect-submodules "desktop_app" ^
    --collect-submodules "capcut_tts_api" ^
    --hidden-import "edge_tts" ^
    --collect-all "edge_tts" ^
    --hidden-import "piper" ^
    --collect-all "piper" ^
    --hidden-import "onnxruntime" ^
    --collect-all "onnxruntime" ^
    --exclude-module "gradio" ^
    --exclude-module "gradio_client" ^
    --exclude-module "matplotlib" ^
    --exclude-module "pandas" ^
    --exclude-module "tkinter" ^
    --exclude-module "PySide6.QtWebEngineCore" ^
    --exclude-module "PySide6.QtWebEngineWidgets" ^
    --exclude-module "PySide6.Qt3DCore" ^
    --exclude-module "PySide6.QtQuick" ^
    --exclude-module "PySide6.QtQml" ^
    app.py

set EXITCODE=%ERRORLEVEL%
echo.

if not "%EXITCODE%"=="0" (
    echo ============================================================
    echo  [LOI] Build that bai (ma loi %EXITCODE%)
    echo ============================================================
    pause
    exit /b %EXITCODE%
)

if not exist "dist\FanficAudioStudio\FanficAudioStudio.exe" (
    echo [LOI] Khong tim thay file EXE sau khi build.
    pause
    exit /b 1
)

echo === Kiem tra assets da duoc dong goi ===
if not exist "dist\FanficAudioStudio\_internal\assets\app_icon.png" (
    echo [LOI] Khong tim thay _internal\assets\app_icon.png trong ban build.
    echo       Logo sidebar se khong hien thi. Kiem tra lai --add-data "assets;assets".
    pause
    exit /b 1
)

echo === Kiem tra goi TTS da duoc dong goi day du ===
if not exist "dist\FanficAudioStudio\_internal\piper\espeak-ng-data" (
    echo [LOI] Thieu _internal\piper\espeak-ng-data - Piper se khong chay duoc.
    pause
    exit /b 1
)
if not exist "dist\FanficAudioStudio\_internal\onnxruntime" (
    echo [LOI] Thieu onnxruntime trong ban build - Piper se khong chay duoc.
    pause
    exit /b 1
)
if not exist "dist\FanficAudioStudio\_internal\PySide6\Qt6Multimedia.dll" (
    echo [LOI] Thieu QtMultimedia - nut "Nghe thu" se khong phat duoc.
    pause
    exit /b 1
)

echo === Kiem tra khong lot device.json / credential vao ban build ===
if exist "dist\FanficAudioStudio\device.json" (
    echo [CANH BAO] Tim thay device.json trong ban build - dang xoa...
    del /f /q "dist\FanficAudioStudio\device.json"
)
if exist "dist\FanficAudioStudio\_internal\device.json" (
    echo [CANH BAO] Tim thay device.json trong _internal - dang xoa...
    del /f /q "dist\FanficAudioStudio\_internal\device.json"
)

echo.
echo ============================================================
echo  BUILD XONG
echo ============================================================
echo  EXE:  dist\FanficAudioStudio\FanficAudioStudio.exe
echo.
echo  Buoc tiep theo (tuy chon) - tao bo cai dat:
echo    Mo installer.iss bang Inno Setup roi bam Compile
echo    Ket qua: installer_output\FanficAudioStudioSetup.exe
echo ============================================================
echo.
pause
exit /b 0
