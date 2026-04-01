import os
import time
import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Any
from contextlib import contextmanager
import undetected_chromedriver as uc

from parsers_core.captcha_bypass import bypass_pyaterochka_antibot

def get_chrome_binary(*args, **kwargs) -> Optional[str]:
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        path = shutil.which(name)
        if path: return path
    return None

def detect_chrome_version_main(*args, **kwargs) -> Optional[int]:
    return None

def is_forbidden_ban(text):
    return "Access denied" in text or "Forbidden" in text

@contextmanager
def local_proxy_for(proxy):
    yield proxy, None

def _init_uc_driver(headless: bool, locale: str, proxy: Optional[str]):
    """Создает браузер с привязкой профиля для сохранения кук и обхода защит"""
    options = uc.ChromeOptions()
    
    current_dir = os.path.dirname(os.path.abspath(__file__))
    parser_root = os.path.dirname(current_dir)
    profile_dir = os.path.join(current_dir, "pyaterochka_profile")
    options.add_argument(f"--user-data-dir={profile_dir}")
    

    options.add_argument(f"--lang={locale}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-blink-features=AutomationControlled")

    if proxy:
        options.add_argument(f"--proxy-server={proxy}")

    chrome_path = get_chrome_binary()

    try:
        driver = uc.Chrome(
            options=options,
            headless=headless,
            use_subprocess=True,
            browser_executable_path=chrome_path,
            version_main=146
        )
    except:
        driver = uc.Chrome(
            options=options,
            headless=headless,
            use_subprocess=True,
            browser_executable_path=chrome_path
        )
        
    return driver

def driver_get_json(driver, url: str, params: Optional[dict] = None, timeout_s: float = 15.0) -> Any:
    from urllib.parse import urlencode
    full_url = url
    if params:
        full_url += "?" + urlencode(params)

    driver.get(full_url)
    time.sleep(1)  

    try:
        text = driver.find_element("tag name", "body").text
        return json.loads(text)
    except Exception as e:
        if is_forbidden_ban(driver.page_source):
            raise RuntimeError("IP_BANNED: Доступ к Пятерочке ограничен.")
        return {}

@contextmanager
def pyaterochka_driver(headless: bool = False, locale: str = "ru-RU", proxy: Optional[str] = None,
                       startup_timeout_s: float = 120):
    driver = _init_uc_driver(headless=headless, locale=locale, proxy=proxy)
    try:
        driver.get("https://5ka.ru/")
        
        # ! ВЫЗОВ ОБХОДА КАПЧИ !
        bypass_pyaterochka_antibot(driver, timeout=startup_timeout_s)
        
        yield driver
    finally:
        try:
            driver.quit()
        except:
            pass

@contextmanager
def pyaterochka_requests_session(*args, **kwargs):
    import requests
    session = requests.Session()
    try:
        yield session
    finally:
        session.close()

def _get_chrome_binary(*args, **kwargs): return get_chrome_binary()
def _detect_version_main(*args, **kwargs): return None
def _get_cache_dir(*args, **kwargs): return Path(tempfile.gettempdir())