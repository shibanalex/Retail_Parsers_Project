import os
import undetected_chromedriver as uc

def _init_uc_driver(headless: bool = False, locale: str = "ru-RU", proxy=None):
    """Создает невидимый браузер с привязкой профиля для ВкусВилла"""
    options = uc.ChromeOptions()
    
    # СОХРАНЕНИЕ ПРОФИЛЯ ВКУСВИЛЛА 
    current_dir = os.path.dirname(os.path.abspath(__file__))
    profile_dir = os.path.join(current_dir, "vkusvill_profile")
    options.add_argument(f"--user-data-dir={profile_dir}")
    
    options.add_argument(f"--lang={locale}")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--disable-blink-features=AutomationControlled")

    if proxy:
        options.add_argument(f"--proxy-server={proxy}")

    try:
        driver = uc.Chrome(
            options=options,
            headless=headless,
            use_subprocess=True
        )
    except Exception as e:
        print(f"Ошибка запуска Chrome: {e}")
        raise e
        
    return driver