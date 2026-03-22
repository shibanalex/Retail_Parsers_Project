import os
import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Вычисляем путь к папке профиля относительно текущего файла
current_dir = os.path.dirname(os.path.abspath(__file__))
parser_root = os.path.dirname(current_dir)
PROFILE_DIR = os.path.join(parser_root, "cataloged_profile")

def init_driver(headless=False):
    options = uc.ChromeOptions()
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--disable-popup-blocking")
    
    if headless:
        options.add_argument("--headless=new")

    try:
        # Пытаемся запустить с привязкой к версии
        driver = uc.Chrome(options=options, version_main=145, use_subprocess=True)
    except:
        # Если версия не подошла, запускаем как есть
        driver = uc.Chrome(options=options, use_subprocess=True)

    # Скрываем признаки автоматизации
    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    return driver
