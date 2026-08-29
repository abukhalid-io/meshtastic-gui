#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -f ".venv/bin/python" ]; then
    echo "Membuat virtual environment..."
    python3 -m venv .venv
fi

source .venv/bin/activate
pip install -q -e .
python main.py
