# -*- coding: utf-8 -*-
import requests

from parsers_core.settings import parser_settings

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept": "*/*",
    "Accept-Language": "ru-RU,ru;q=0.9",
    "Content-Type": "application/json",
    "Origin": "https://gulliver-ul.ru",
    "Referer": "https://gulliver-ul.ru/",
    "x-hive-brand": "1",
}


class RequestsWrapper:
    """Не браузер: requests-сессия к API gulliver-ul.ru."""

    def __init__(self, parser_cfg_name=""):
        self.session = requests.Session()
        self.session.headers.update(HEADERS)
        settings = parser_settings(parser_cfg_name)
        self.custom_min_delay = settings["min_delay"]
        self.custom_max_delay = settings["max_delay"]
        self.shop_id = "7"

    def quit(self):
        self.session.close()


def get_browser(parser_cfg_name=""):
    return RequestsWrapper(parser_cfg_name)
