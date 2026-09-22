@echo off
chcp 65001 >nul 2>nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "MODE=webcam"
call "%~dp0_run.bat" %*
