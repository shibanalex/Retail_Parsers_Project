@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

title Retail Parsers Launcher
color 0A

:: Определяем Python
set "PYTHON311=C:\Python311\python.exe"
set "PYTHON_CMD=python"

if exist "%PYTHON311%" (
    echo [✓] Найден Python 3.11 в C:\Python311
    set "PYTHON_CMD=%PYTHON311%"
    set "PIP_CMD=C:\Python311\Scripts\pip.exe"
) else (
    echo [ℹ] Использую системный Python
    set "PIP_CMD=pip"
)

:: Проверка версии
%PYTHON_CMD% --version
%PYTHON_CMD% -c "import sys; print(f'Python {sys.version_info.major}.{sys.version_info.minor}')"

:: Для Python 3.13+ особая обработка
%PYTHON_CMD% -c "import sys; exit(0) if sys.version_info.minor < 13 else exit(1)"
if errorlevel 1 (
    echo [⚠] Обнаружен Python 3.13+. Устанавливаю совместимые версии...
    %PIP_CMD% install --upgrade pip setuptools wheel
    %PIP_CMD% install numpy==1.24.3 --only-binary=:all:
    %PIP_CMD% install pandas==2.0.3 --no-deps
    %PIP_CMD% install python-dateutil pytz tzdata
) else (
    %PIP_CMD% install -r requirements.txt
)

:: Запуск
%PYTHON_CMD% main.py
pause