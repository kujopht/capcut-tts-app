@echo off
title ASTRAL DRAGON 3D - Solar Odyssey
cd /d "%~dp0"
if exist "..\.venv\Scripts\python.exe" (
    start "" "..\.venv\Scripts\python.exe" desktop_dragon.py
) else (
    start "" index.html
)
