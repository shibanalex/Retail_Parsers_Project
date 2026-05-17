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

def get_browser():
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    base_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.dirname(base_dir)
    cfg_path = os.path.join(root_dir, "plugin", "plugins.cfg")

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
        except: pass

    options.add_argument(f"--window-size={window_size}")
    profile_dir = os.path.join(base_dir, "winestreet_profile")
    options.add_argument(f"--user-data-dir={profile_dir}")

    chrome_major = _get_chrome_major_version()
    driver = uc.Chrome(options=options, version_main=chrome_major)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', { get: () => undefined });"
    })
    return driver