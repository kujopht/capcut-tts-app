@echo off
setlocal
cd /d "%~dp0"

rem Router Control Center V0.1 — xem docs/CONTROL_CENTER.md
rem
rem UTF-8 BAT BUOC, cung ly do da ghi trong `fanfic-ctl.cmd`: toan bo van
rem ban giao dien la tieng Viet co dau, va tren console Windows mac dinh
rem (cp1252/cp437) chi rieng `--help` da do UnicodeEncodeError trong
rem argparse TRUOC khi TUI kip chay. Da vap that o Control Room.
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

rem Uu tien venv cua kho: `textual` khai o requirements-control-room.txt va
rem thuong chi cai trong .venv, con `python` tren PATH la Python he thong.
if exist ".venv\Scripts\python.exe" (
  ".venv\Scripts\python.exe" -m scripts.control_center %*
) else (
  python -m scripts.control_center %*
)
