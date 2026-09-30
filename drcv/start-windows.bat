@echo off
title DRCV - Digital Record Context Verification
cd /d "%~dp0backend"
set PY=
for %%V in (3.12 3.11 3.13 3.10) do (
  if not defined PY ( py -%%V -c "import sys" >nul 2>&1 && set PY=py -%%V )
)
if not defined PY ( set PY=python )
if not exist .venv (
  echo Creating Python environment...
  %PY% -m venv .venv || ( echo Python 3.10+ is required: https://www.python.org/downloads/ & pause & exit /b 1 )
)
call .venv\Scripts\activate.bat
echo Installing dependencies (first run only takes a few minutes)...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt || ( echo Dependency install failed. & pause & exit /b 1 )
pip install -r requirements-ocr.txt || echo [warning] OCR packages could not be installed - images/scans will be flagged for manual review.
pip install -r requirements-postgres.txt >nul 2>&1
python run.py
pause
