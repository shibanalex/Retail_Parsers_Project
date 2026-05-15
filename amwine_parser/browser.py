import os
import configparser
import undetected_chromedriver as uc

def get_browser():
    """
    Initializes and returns an undetected Chrome WebDriver instance.
    Reads window size preferences from ../plugin/plugins.cfg if available.
    """
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    
    options.add_argument("--disable-backgrounding-occluded-windows")
    options.add_argument("--disable-background-timer-throttling")
    options.add_argument("--disable-renderer-backgrounding")

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
        except Exception as e:
            print(f"Failed to read plugins.cfg: {e}")

    options.add_argument(f"--window-size={window_size}")

    profile_dir = os.path.join(base_dir, "profile")
    options.add_argument(f"--user-data-dir={profile_dir}")

    driver = uc.Chrome(options=options, version_main=148)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            });
            window.navigator.chrome = {
              runtime: {},
            };
            Object.defineProperty(navigator, 'languages', {
              get: () =>['ru-RU', 'ru', 'en-US', 'en']
            });
            Object.defineProperty(navigator, 'plugins', {
              get: () =>[1, 2, 3],
            });
        """
    })

    return driver