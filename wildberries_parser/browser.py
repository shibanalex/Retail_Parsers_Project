# -*- coding: utf-8 -*-
from curl_cffi import requests

from parsers_core.settings import parser_settings


class CurlCFFIWrapper:
    """Не браузер: сессия curl_cffi с отпечатком Chrome."""

    def __init__(self, parser_cfg_name=""):
        self.session = requests.Session(impersonate="chrome120")
        self.dest = "-1257786"
        settings = parser_settings(parser_cfg_name)
        self.custom_min_delay = settings["min_delay"]
        self.custom_max_delay = settings["max_delay"]

    def quit(self):
        self.session.close()


def get_browser(parser_cfg_name=""):
    return CurlCFFIWrapper(parser_cfg_name)
