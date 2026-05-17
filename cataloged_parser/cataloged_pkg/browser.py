import os
import configparser
import undetected_chromedriver as uc

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
        except Exception as e:
            print(f"[Browser] Ошибка чтения plugins.cfg: {e}")

    options.add_argument(f"--window-size={window_size}")

    try:
        driver = uc.Chrome(options=options, version_main=148, use_subprocess=True)
    except:
        driver = uc.Chrome(options=options, use_subprocess=True)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    })
    
    return driver