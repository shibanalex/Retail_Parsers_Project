@echo off
chcp 65001 >nul
echo Запуск Retail Parsers...

:: Создание виртуального окружения
if not exist venv (
    echo Создание виртуального окружения...
    python -m venv venv
)

:: Активация и установка зависимостей
call venv\Scripts\activate
pip install -r requirements.txt

:: Запуск
python main.py
pause