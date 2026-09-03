@echo off
setlocal
cd /d "%~dp0"

rem UTF-8 BAT BUOC: toan bo van ban giao dien cua Control Room la tieng Viet
rem co dau. Tren console Windows mac dinh (cp1252/cp437) chi rieng
rem `fanfic-ctl --help` da do UnicodeEncodeError trong argparse truoc khi TUI
rem kip chay — da do that:
rem   cp1252.py -> UnicodeEncodeError: 'charmap' codec can't encode
rem   characters in position 246-248
rem `PYTHONUTF8=1` bat che do UTF-8 cua Python cho ca stdout/stderr.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

rem Uu tien venv cua kho neu co: `textual` duoc khai bao o
rem requirements-control-room.txt va thuong chi cai trong .venv, con `python`
rem tren PATH cua may nay la Python he thong (khong co textual).
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m scripts.router_v3.control_room %*
) else (
  python -m scripts.router_v3.control_room %*
)
