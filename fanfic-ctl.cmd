@echo off
setlocal
cd /d "%~dp0"
python -m scripts.router_v3.control_room %*
