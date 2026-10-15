# -*- coding: utf-8 -*-
import glob
import os
import time

from .settings import parser_settings, parse_window_size

PROFILE_ENV = "PRODEX_BROWSER_PROFILE"
STALE_LOCKS = ("SingletonLock", "SingletonCookie", "SingletonSocket", "lockfile")
HIDE_WEBDRIVER_JS = "Object.defineProperty(navigator, 'webdriver', {get: () => undefined});"


def _clean_profile_locks(profile_dir):
    for name in STALE_LOCKS:
        for path in glob.glob(os.path.join(profile_dir, "**", name), recursive=True):
            try:
                os.remove(path)
            except OSError:
                pass


def _resolve_profile(base_dir, profile_name):
    override = os.environ.get(PROFILE_ENV)
    if override:
        return override
    if profile_name:
        return os.path.join(base_dir, profile_name)
    return None


def _chrome_version():
    try:
        from .browser_utils import get_chrome_binary, detect_chrome_version_main
        return detect_chrome_version_main(get_chrome_binary())
    except Exception:
        return None


def build_options(settings, profile_dir=None, extra_args=None):
    import undetected_chromedriver as uc
    options = uc.ChromeOptions()
    mode, size = parse_window_size(settings.get("browser_size"))
    if mode == "headless":
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    else:
        options.add_argument(f"--window-size={size[0]},{size[1]}")
    for arg in ("--disable-blink-features=AutomationControlled", "--disable-notifications",
                "--no-sandbox", "--disable-dev-shm-usage"):
        options.add_argument(arg)
    if profile_dir:
        options.add_argument(f"--user-data-dir={profile_dir}")
    for arg in extra_args or ():
        options.add_argument(arg)
    return options


def get_browser(base_dir="", profile_name="", parser_cfg_name="", extra_args=None,
                capabilities=None, attempts=3, window_size=None):
    """window_size перекрывает browser_size из cfg, например "1920x1080"."""
    import undetected_chromedriver as uc

    settings = parser_settings(parser_cfg_name)
    if window_size:
        settings["browser_size"] = window_size
    profile_dir = _resolve_profile(base_dir, profile_name)
    if profile_dir:
        os.makedirs(profile_dir, exist_ok=True)
        _clean_profile_locks(profile_dir)

    version = _chrome_version()
    last_error = None
    for attempt in range(attempts):
        options = build_options(settings, profile_dir, extra_args)
        for key, value in (capabilities or {}).items():
            options.set_capability(key, value)
        kwargs = {"options": options, "user_multi_procs": attempt == 0}
        if version:
            kwargs["version_main"] = version
        try:
            driver = uc.Chrome(**kwargs)
            break
        except Exception as e:
            last_error = e
            time.sleep(2 * (attempt + 1))
    else:
        raise RuntimeError(f"Браузер не запустился за {attempts} попытки: {last_error}")

    try:
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {"source": HIDE_WEBDRIVER_JS})
    except Exception:
        pass
    driver.custom_min_delay = settings["min_delay"]
    driver.custom_max_delay = settings["max_delay"]
    return driver


def wait_ready(driver, timeout=15):
    from selenium.webdriver.support.ui import WebDriverWait
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: d.execute_script("return document.readyState") == "complete")
    except Exception:
        pass


def wait_for(driver, selector, timeout=10):
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.support.ui import WebDriverWait
    try:
        WebDriverWait(driver, timeout).until(EC.presence_of_element_located((By.CSS_SELECTOR, selector)))
    except Exception:
        pass


def quit_browser(driver):
    if driver is None:
        return
    try:
        driver.quit()
    except Exception:
        pass
