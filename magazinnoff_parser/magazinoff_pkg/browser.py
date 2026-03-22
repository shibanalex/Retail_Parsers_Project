import os
import time
from selenium import webdriver
from selenium_stealth import stealth
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

current_dir = os.path.dirname(os.path.abspath(__file__))
parser_root = os.path.dirname(current_dir)
PROFILE_DIR = os.path.join(parser_root, "magazinnoff_profile")

def init_driver(headless=False):
    print(f"🌐 Профиль Chrome: {PROFILE_DIR}")
    
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-popup-blocking")
    
    # Подавление системного мусора в консоли
    options.add_argument("--log-level=3")      
    options.add_argument("--disable-logging")  
    options.add_argument("--disable-features=OptimizationGuideModelDownloading,OptimizationHints")

    # Ускорение: не ждем полной загрузки тяжелых скриптов
    options.page_load_strategy = 'eager'
    
    if headless:
        options.add_argument("--headless=new")

    try:
        driver = webdriver.Chrome(options=options)
        # Жесткий таймаут на загрузку страницы
        driver.set_page_load_timeout(30)
    except Exception as e:
        print(f"❌ Не удалось запустить драйвер: {e}")
        raise e

    stealth(driver,
        languages=["ru-RU", "ru"],
        vendor="Google Inc.",
        platform="Win32",
        webgl_vendor="Intel Inc.",
        renderer="Intel Iris OpenGL Engine",
        fix_hairline=True,
    )
    return driver


def save_debug_html(driver, name_prefix):
    debug_dir = os.path.join(parser_root, "debug")
    if not os.path.exists(debug_dir):
        os.makedirs(debug_dir)
        
    filename = os.path.join(debug_dir, f"{name_prefix}.html")
    with open(filename, "w", encoding="utf-8") as f:
        f.write(driver.page_source)