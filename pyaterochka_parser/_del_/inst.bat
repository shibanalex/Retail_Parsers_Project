cd C:\Retail Parsers.OUT

:: Активируем виртуальное окружение
venv\Scripts\activate

:: Устанавливаем все необходимые пакеты
pip install pandas
pip install openpyxl
pip install requests
pip install beautifulsoup4
pip install lxml
pip install selenium
pip install undetected-chromedriver
pip install colorama
pip install fake-useragent
pip install python-dotenv

:: Проверяем установку
python -c "import pandas; print(f'Pandas версии {pandas.__version__} установлен')"