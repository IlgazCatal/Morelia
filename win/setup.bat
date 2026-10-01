@echo off
REM Set up the Morelia virtualenv and install Python dependencies on Windows.
REM
REM wxPython provides official wheels for CPython 3.13 on Windows, so no
REM sysroot/GTK unpacking is needed. This script mirrors setup.sh's venv
REM bootstrap behavior (handling ensurepip being missing and the externally-
REM managed environment).
setlocal ENABLEEXTENSIONS

cd /d "%~dp0"

set "VENV=.venv"

if not exist "%VENV%" (
  echo ==^> Creating %VENV%
  python -m venv --without-pip "%VENV%"
)

if not exist "%VENV%\Scripts\pip.exe" (
  echo ==^> Bootstrapping pip into %VENV%
  python -m pip --python "%VENV%\Scripts\python.exe" install --upgrade pip
)

echo ==^> Installing Python requirements
"%VENV%\Scripts\pip.exe" install -r requirements.txt

echo.
echo Done.
echo.
echo   %VENV%\Scripts\python.exe main.py
endlocal
