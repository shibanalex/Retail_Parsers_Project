import os
import time
import configparser
from selenium import webdriver
from selenium_stealth import stealth

current_dir = os.path.dirname(os.path.abspath(__file__))
parser_root = os.path.dirname(current_dir)
PROFILE_DIR = os.path.join(parser_root, "magazinnoff_profile")

def init_driver(headless=False):
    options = webdriver.ChromeOptions()
    options.add_argument(f"--user-data-dir={PROFILE_DIR}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-popup-blocking")
    
    options.add_argument("--log-level=3")      
    options.add_argument("--disable-logging")  
    options.add_argument("--disable-features=OptimizationGuideModelDownloading,OptimizationHints")

    options.page_load_strategy = 'eager'
    
    cfg_path = os.path.join(parser_root, "plugin", "plugins.cfg")
    window_size = "1920,1080"
    
    if os.path.exists(cfg_path):
        config = configparser.ConfigParser()
        try:
            config.read(cfg_path, encoding='utf-8')
            if config.has_section('BROWSER'):
                size_h = config.get('BROWSER', 'size_h', fallback=None)
                size_v = config.get('BROWSER', 'size_v', fallback=None)
                if size_h and size_v:
                    window_size = f"{size_h},{size_v}"
        except Exception:
            pass

    options.add_argument(f"--window-size={window_size}")
    
    if headless:
        options.add_argument("--headless=new")

    try:
        driver = webdriver.Chrome(options=options)
        driver.set_page_load_timeout(30)
    except Exception as e:
        print(f"[Browser] Ошибка запуска драйвера: {e}")
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