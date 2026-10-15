"""Старые парсеры импортируют параметры отсюда."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from parsers_core.config_loader import cfg

    debug_mode = cfg.get_bool("", "debug_mode", False)
    DEBUG_Mode = debug_mode
    DEBUG_MODE = debug_mode

    cities = cfg.get_list("", "cities", [])
    search_req = cfg.get_list("", "search_req", [])
    brand = cfg.get_str("", "brand", "")

    MY_ID = cfg.get("TelegramBot", "MY_ID", "")
    TOKEN = cfg.get("TelegramBot", "TOKEN", "")

    proxy = cfg.get_str("", "proxy", "")
    table_name = cfg.get_str("", "table_name", "")
    sqlite_file = cfg.get_str("", "sqlite_file", "")

    __all__ = [
        'debug_mode', 'DEBUG_Mode', 'DEBUG_MODE',
        'cities', 'search_req', 'brand',
        'MY_ID', 'TOKEN', 'proxy',
        'table_name', 'sqlite_file', 'cfg'
    ]
    
except Exception as e:
    print(f"⚠️ Ошибка загрузки конфигурации: {e}")
    debug_mode = DEBUG_Mode = DEBUG_MODE = False
    cities = search_req = brand = []
    MY_ID = TOKEN = proxy = table_name = sqlite_file = ""
    cfg = None