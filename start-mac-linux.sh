#!/usr/bin/env bash
set -e
cd "$(dirname "$0")/backend"
PY=$(command -v python3.12 || command -v python3.11 || command -v python3 || command -v python)
[ -d .venv ] || "$PY" -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip >/dev/null
pip install -r requirements.txt
pip install -r requirements-ocr.txt || echo "[warning] OCR packages unavailable - images/scans will be flagged for manual review."
pip install -r requirements-postgres.txt >/dev/null 2>&1 || true
python run.py
