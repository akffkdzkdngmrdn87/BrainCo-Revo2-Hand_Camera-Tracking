@echo off
chcp 65001 >nul 2>nul
setlocal
cd /d "%~dp0"
set "PYTHONUTF8=1"
set "MODE=robot"
rem  Small-window mode: the exact setup that worked on 2026-09-10.
rem  No fullscreen, no 720p request. Use this if the normal one fails.
call "%~dp0_run.bat" --windowed --cam-size 640x480 %*
