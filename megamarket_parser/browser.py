import os
import configparser
from DrissionPage import ChromiumPage, ChromiumOptions

def get_browser(parser_cfg_name="MEGAMARKET"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    profile_dir = os.path.join(base_dir, "megamarket_profile")
    os.makedirs(profile_dir, exist_ok=True)

    min_delay = 1.5
    max_delay = 3.0
    browser_size = "1920,1080"

    root_dir = os.path.dirname(base_dir)
    cfg_path = os.path.join(root_dir, "parsers_core", "share_parsers.cfg")

    if not os.path.exists(cfg_path):
        cfg_path = os.path.join(base_dir, "parsers_core", "share_parsers.cfg")

    if os.path.exists(cfg_path):
        config = configparser.ConfigParser()
        try:
            config.read(cfg_path, encoding="utf-8")
            if config.has_section("BROWSER"):
                min_delay = config.getfloat("BROWSER", "min_delay", fallback=min_delay)
                max_delay = config.getfloat("BROWSER", "max_delay", fallback=max_delay)
                browser_size = config.get("BROWSER", "browser_size", fallback=browser_size)
            
            if parser_cfg_name and config.has_section(parser_cfg_name):
                min_delay = config.getfloat(parser_cfg_name, "min_delay", fallback=min_delay)
                max_delay = config.getfloat(parser_cfg_name, "max_delay", fallback=max_delay)
        except Exception:
            pass

    co = ChromiumOptions()
    co.set_user_data_path(profile_dir)
    co.set_argument("--no-sandbox")
    co.set_argument("--disable-dev-shm-usage")
    co.set_argument("--disable-gpu")
    co.set_argument(f"--window-size={browser_size}")
    co.set_argument("--lang=ru-RU,ru")

    page = ChromiumPage(addr_or_opts=co)
    page.custom_min_delay = min_delay
    page.custom_max_delay = max_delay
    
    page._product_cache = {}
    page.current_location_id = "50"

    return page

def init_browser():
    return get_browser("MEGAMARKET")