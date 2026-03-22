@echo off
chcp 65001 >nul
call "venv\Scripts\activate.bat"

python main.py
::set "py_errorlevel=%ERRORLEVEL%"

call "venv\Scripts\deactivate.bat"
echo.
echo 🧾 main.py завершился с кодом %py_errorlevel%
echo.
pause