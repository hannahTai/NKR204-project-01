@echo off
rem Backfill: fetch raw files for a date range (pipeline/extract/producer.py init), then T raw to parquet (pipeline.transform.stage) -> L parquet to MySQL (pipeline.load.mysql).
rem Usage:  scripts\run_init.bat 20261001            (20261001 to today)
rem         scripts\run_init.bat 20261001 20261031   (fixed range)
rem Double-click also works: it asks for the start date.
rem Output goes to the screen; start time and exit codes are appended to data\init.log
rem (Comments are in English on purpose: cmd may misread UTF-8 Chinese in .bat files.)

cd /d "%~dp0.."
set PYTHONUTF8=1
set PYTHONUNBUFFERED=1
set UV_LINK_MODE=copy

set START=%~1
set END=%~2
if "%START%"=="" set /p START=Start date (YYYYMMDD): 
if "%START%"=="" (
    echo No start date given.
    exit /b 1
)
set END_ARG=
if not "%END%"=="" set END_ARG=--end %END%

if not exist data mkdir data
echo ===== %date% %time% init %START% %END% >> data\init.log
uv run python -m pipeline.extract.producer init --start %START% %END_ARG%
set FETCH_EXIT=%errorlevel%

rem Rebuild stage even if some fetches failed: stage is rebuilt from whatever raw exists.
echo ----- stage
uv run python -m pipeline.transform.stage
if not errorlevel 1 uv run python -m pipeline.load.mysql
set STAGE_EXIT=%errorlevel%

echo fetch exit %FETCH_EXIT%, stage exit %STAGE_EXIT% >> data\init.log
echo fetch exit %FETCH_EXIT%, stage exit %STAGE_EXIT%
if not "%FETCH_EXIT%%STAGE_EXIT%"=="00" exit /b 1
