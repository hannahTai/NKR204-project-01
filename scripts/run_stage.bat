@echo off
rem Rebuild the stage tables in MySQL from all raw files (crawler/stage.py), after running the tests.
rem Output is appended to data\stage.log
rem (Comments are in English on purpose: cmd may misread UTF-8 Chinese in .bat files.)

cd /d "%~dp0.."
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
set UV_LINK_MODE=copy

if not exist data mkdir data
echo ===== %date% %time% >> data\stage.log
uv run pytest -q >> data\stage.log 2>&1
if errorlevel 1 (
    echo tests failed, stage not rebuilt >> data\stage.log
    exit /b 1
)
uv run python -m crawler.stage >> data\stage.log 2>&1
echo exit code %errorlevel% >> data\stage.log
