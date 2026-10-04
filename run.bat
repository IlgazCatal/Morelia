@echo off
setlocal ENABLEEXTENSIONS
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Virtualenv missing. Run setup.bat first.
  exit /b 1
)
"%~dp0.venv\Scripts\python.exe" main.py %*
endlocal
