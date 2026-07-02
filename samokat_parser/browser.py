import os
import configparser
from DrissionPage import ChromiumPage, ChromiumOptions

class DPWrapper:
    def __init__(self, parser_cfg_name=""):
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
            except Exception:
                pass

        profile_dir = os.path.join(base_dir, "samokat_dp_profile")
        
        co = ChromiumOptions()
        co.set_user_data_path(profile_dir)
        co.headless(False) 
        
        
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        co.set_argument('--disable-blink-features=AutomationControlled')
        co.set_argument('--log-level=3') 
        
        if b_size != "0" and b_size != "-1" and "x" in b_size:
            width, height = b_size.split("x")
            co.set_argument(f'--window-size={width},{height}')
        else:
            co.set_argument('--window-size=1920,1080')

        self.page = ChromiumPage(co)
        self.custom_min_delay = min_delay
        self.custom_max_delay = max_delay

    def quit(self):
        self.page.quit()

def get_browser(parser_cfg_name=""):
    return DPWrapper(parser_cfg_name)