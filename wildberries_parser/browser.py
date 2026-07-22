import os
import configparser
from curl_cffi import requests

class CurlCFFIWrapper:
    def __init__(self, parser_cfg_name=""):
        self.session = requests.Session(impersonate="chrome120")
        self.dest = "-1257786" 
        
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

    def quit(self):
        self.session.close()

def get_browser(parser_cfg_name=""):
    return CurlCFFIWrapper(parser_cfg_name)