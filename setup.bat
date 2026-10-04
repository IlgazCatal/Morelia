@echo off
setlocal ENABLEEXTENSIONS
cd /d "%~dp0"
set "VENV=.venv"
if not exist "%VENV%" (
  python -m venv --without-pip "%VENV%"
)
if not exist "%VENV%\Scripts\pip.exe" (
  python -m pip --python "%VENV%\Scripts\python.exe" install --upgrade pip
)
"%VENV%\Scripts\pip.exe" install -r requirements.txt
echo Done.
endlocal
