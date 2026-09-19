@echo off
title CYBER SERPENT 3D
cd /d "%~dp0"
if exist "..\.venv\Scripts\python.exe" (
    start "" "..\.venv\Scripts\python.exe" desktop_3d.py
) else (
    start "" index.html
)
