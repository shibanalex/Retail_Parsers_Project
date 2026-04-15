import os
import undetected_chromedriver as uc

def get_browser():
    """
    Инициализация undetected_chromedriver с фиксацией 146 версии и маскировкой
    """
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    base_dir = os.path.dirname(os.path.abspath(__file__))
    profile_dir = os.path.join(base_dir, "tvoydom_profile")
    options.add_argument(f"--user-data-dir={profile_dir}")

    driver = uc.Chrome(options=options, version_main=146)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', {
              get: () => undefined
            });
            window.navigator.chrome = {
              runtime: {},
            };
            Object.defineProperty(navigator, 'languages', {
              get: () => ['ru-RU', 'ru', 'en-US', 'en']
            });
            Object.defineProperty(navigator, 'plugins', {
              get: () => [1, 2, 3],
            });
        """
    })

    return driver