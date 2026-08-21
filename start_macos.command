#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

if command -v python3.12 >/dev/null 2>&1; then
  PYTHON_BIN=python3.12
elif command -v python3.13 >/dev/null 2>&1; then
  PYTHON_BIN=python3.13
elif command -v python3 >/dev/null 2>&1; then
  PYTHON_BIN=python3
else
  echo "Python 3 was not found. Install Python 3.12 or 3.13 from python.org first."
  read -r -p "Press Enter to close..."
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  echo "Creating local Python environment..."
  "$PYTHON_BIN" -m venv .venv
fi

echo "Installing/updating dependencies..."
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt

echo "Starting Following blowing at http://localhost:8501"
exec ./.venv/bin/python -m streamlit run streamlit_app.py
