import os
import configparser
import requests

class RequestsWrapper:
    def __init__(self, parser_cfg_name=""):
        self.session = requests.Session()
        
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "ru-RU,ru;q=0.9",
            "Content-Type": "application/json",
            "Origin": "https://gulliver-ul.ru",
            "Referer": "https://gulliver-ul.ru/",
            "x-hive-brand": "1"
        })

        base_dir = os.path.dirname(os.path.abspath(__file__))
        root_dir = os.path.dirname(base_dir)
        cfg_path = os.path.join(root_dir, "parsers_core", "share_parsers.cfg")

        min_delay = 1.0
        max_delay = 3.0

        if os.path.exists(cfg_path):
            config = configparser.ConfigParser()
            try:
                config.read(cfg_path, encoding='utf-8')
                if config.has_section('BROWSER'):
                    min_delay = config.getfloat('BROWSER', 'min_delay', fallback=min_delay)
                    max_delay = config.getfloat('BROWSER', 'max_delay', fallback=max_delay)
                
                if parser_cfg_name and config.has_section(parser_cfg_name):
                    min_delay = config.getfloat(parser_cfg_name, 'min_delay', fallback=min_delay)
                    max_delay = config.getfloat(parser_cfg_name, 'max_delay', fallback=max_delay)
            except Exception:
                pass

        self.custom_min_delay = min_delay
        self.custom_max_delay = max_delay
        
        
        self.shop_id = "7" 

    def quit(self):
        self.session.close()

def get_browser(parser_cfg_name=""):
    return RequestsWrapper(parser_cfg_name)