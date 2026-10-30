@echo off
setlocal
cd /d "%~dp0"
py -3.13 start.py %*
if errorlevel 1 pause
