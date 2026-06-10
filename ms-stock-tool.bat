@echo off
chcp 65001 >nul
cd /d "%~dp0"
start "" /B pythonw app.py
