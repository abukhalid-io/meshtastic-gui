@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Membuat virtual environment...
    python -m venv .venv
)

call ".venv\Scripts\activate.bat"
pip install -q -e .
python main.py
