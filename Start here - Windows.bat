@echo off
REM Double-click me. If Windows SmartScreen warns you, choose "More info" then "Run anyway".
cd /d "%~dp0"

REM Test that the interpreter actually runs, not just that it's on PATH.
REM The Microsoft Store aliases are "shortcuts" that open the Store instead of running Python.
py -3 -c "import sys" >nul 2>nul
if %errorlevel%==0 (
  py -3 scripts\quickstart.py
  goto done
)
python -c "import sys" >nul 2>nul
if %errorlevel%==0 (
  python scripts\quickstart.py
  goto done
)
echo.
echo Python 3 isn't installed yet.
echo Install it from https://www.python.org/downloads/ and tick "Add python.exe to PATH" in the installer.
echo.
echo If you see this after installing Python, open Settings ^> Apps ^> Advanced app settings ^> App execution aliases
echo and turn OFF the python.exe and python3.exe entries, then try again.
echo.
:done
pause
