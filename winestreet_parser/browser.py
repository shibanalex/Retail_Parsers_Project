import os
import re
import configparser
import subprocess
import undetected_chromedriver as uc

def _get_chrome_major_version():
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in chrome_paths:
        if os.path.exists(path):
            try:
                result = subprocess.run(
                    f'powershell -NoProfile -Command "(Get-Item \'{path}\').VersionInfo.FileVersion"',
                    capture_output=True, text=True, shell=True, timeout=10
                )
                m = re.match(r"(\d+)", result.stdout.strip())
                if m: return int(m.group(1))
            except: pass
    return None

def get_browser(parser_cfg_name=""):
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(base_dir)
    cfg_path = os.path.join(root_dir, "parsers_core", "share_parsers.cfg")

    min_delay = 1.0
    max_delay = 3.0
    b_size = "0"

    if os.path.exists(cfg_path):
        config = configparser.ConfigParser()
        try:
            config.read(cfg_path, encoding='utf-8')
            if config.has_section('BROWSER'):
                min_delay = config.getfloat('BROWSER', 'min_delay', fallback=min_delay)
                max_delay = config.getfloat('BROWSER', 'max_delay', fallback=max_delay)
                b_size = config.get('BROWSER', 'browser_size', fallback=b_size)
            
            if parser_cfg_name and config.has_section(parser_cfg_name):
                min_delay = config.getfloat(parser_cfg_name, 'min_delay', fallback=min_delay)
                max_delay = config.getfloat(parser_cfg_name, 'max_delay', fallback=max_delay)
                b_size = config.get(parser_cfg_name, 'browser_size', fallback=b_size)
        except Exception as e:
            print(f"[Browser] Ошибка чтения {cfg_path}: {e}")

    if b_size == "-1":
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    elif b_size == "0":
        options.add_argument("--window-size=1920,1080")
    elif "x" in b_size:
        options.add_argument(f"--window-size={b_size.replace('x', ',')}")

    profile_dir = os.path.join(base_dir, "winestreet_profile")
    options.add_argument(f"--user-data-dir={profile_dir}")

    chrome_major = _get_chrome_major_version()
    driver = uc.Chrome(options=options, version_main=chrome_major or 148)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    })

    driver.custom_min_delay = min_delay
    driver.custom_max_delay = max_delay

    return driver