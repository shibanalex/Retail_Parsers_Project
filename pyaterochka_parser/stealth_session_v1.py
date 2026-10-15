import time
import json
import shutil
import tempfile
from pathlib import Path
from typing import Optional, Any, Iterator
from contextlib import contextmanager
import undetected_chromedriver as uc


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
    """Старая версия запуска браузера, не используется."""
    options = uc.ChromeOptions()
    options.add_argument(f"--lang={locale}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    chrome_path = get_chrome_binary()

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
                       startup_timeout_s: float = 60.0):
    driver = _init_uc_driver(headless=headless, locale=locale, proxy=proxy)
    try:
        driver.get("https://5ka.ru/")
        time.sleep(3)
        yield driver
    finally:
        try:
            driver.quit()
        except Exception:
            pass


@contextmanager
def pyaterochka_requests_session(*args, **kwargs):
    """Заглушка."""
    import requests
    session = requests.Session()
    try:
        yield session
    finally:
        session.close()


def _get_chrome_binary(*args, **kwargs): return get_chrome_binary()


def _detect_version_main(*args, **kwargs): return None


def _get_cache_dir(*args, **kwargs): return Path(tempfile.gettempdir())