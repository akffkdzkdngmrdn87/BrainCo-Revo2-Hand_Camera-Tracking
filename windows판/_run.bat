@echo off
rem ==================================================================
rem   Shared launcher. Do not double-click this file.
rem   Use the three Korean-named .bat files next to it instead.
rem
rem   Messages here are in English on purpose: the Windows console
rem   may not render Korean before chcp takes effect.
rem ==================================================================
cd /d "%~dp0"
set "PYTHONUTF8=1"

echo.
echo ==================================================================
echo   Hand tracking for BrainCo Revo2       mode: %MODE%
echo   TOP ROBOTICS
echo ==================================================================
echo.

set "SETUP=%~dp0_setup.py"
if not exist "%SETUP%" goto NOFILES

set "PYSTORE=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
set "PY="

py -3 -c "pass" 1>nul 2>nul
if not errorlevel 1 set "PY=py -3"
if defined PY goto RUN

python -c "pass" 1>nul 2>nul
if not errorlevel 1 set "PY=python"
if defined PY goto RUN

if exist "%PYSTORE%" set PY="%PYSTORE%"
if defined PY goto RUN

goto GETPY

:RUN
%PY% "%SETUP%" --mode %MODE% %*
goto DONE

:GETPY
echo   Python is not installed on this PC.
echo   Python 3.12.10 will be downloaded from python.org and installed
echo   for your account only. No administrator rights are needed.
echo.
echo   Download size about 26 MB, install takes 2 to 5 minutes.
echo   An internet connection is required.
echo.
echo   Press any key to continue, or close this window to stop.
pause 1>nul
echo.

set "PYURL=https://www.python.org/ftp/python/3.12.10/python-3.12.10-amd64.exe"
set "PYEXEC=%TEMP%\python-3.12.10-amd64.exe"

echo   Downloading ...
where curl 1>nul 2>nul
if errorlevel 1 goto GETPY_PS
curl -L --fail --silent --show-error -o "%PYEXEC%" "%PYURL%"
goto GETPY_CHECK

:GETPY_PS
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%PYURL%' -OutFile '%PYEXEC%'"

:GETPY_CHECK
if not exist "%PYEXEC%" goto ERR_DL

echo   Installing Python. Please wait, do not close this window ...
start /wait "" "%PYEXEC%" /quiet InstallAllUsers=0 PrependPath=1 Include_launcher=1 Include_test=0

if not exist "%PYSTORE%" goto ERR_INST
del "%PYEXEC%" 1>nul 2>nul
echo   Python installed.
echo.
set PY="%PYSTORE%"
goto RUN

:ERR_DL
echo.
echo   [ERROR] Could not download the Python installer.
echo   Check your internet connection or company firewall.
echo.
echo   You can also install it by hand:
echo     1. open  https://www.python.org/downloads/windows/
echo     2. get Python 3.12, Windows installer, 64-bit
echo     3. tick  Add python.exe to PATH  at the bottom of the setup screen
echo     4. run this file again
goto FAIL

:ERR_INST
echo.
echo   [ERROR] The Python installation did not complete.
echo   If another installer is running, wait for it to finish and retry.
goto FAIL

:NOFILES
echo   [ERROR] _setup.py was not found next to this file.
echo   Please unzip the whole folder again and keep all files together.
goto FAIL

:FAIL
echo.
pause
exit /b 1

:DONE
exit /b 0
