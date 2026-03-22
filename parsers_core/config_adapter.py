# config_adapter.py
"""
Адаптер для обратной совместимости со старыми парсерами.
Все парсеры должны импортировать из этого файла, а не напрямую из config.py
"""

import sys
import os

# Добавляем путь к parsers_core
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from parsers_core.config_loader import cfg
    
    # Экспортируем все нужные параметры с поддержкой разных регистров
    debug_mode = cfg.get_bool("", "debug_mode", False)
    DEBUG_Mode = debug_mode  # Алиас для обратной совместимости
    DEBUG_MODE = debug_mode  # Ещё один алиас
    
    # Основные параметры
    cities = cfg.get_list("", "cities", [])
    search_req = cfg.get_list("", "search_req", [])
    brand = cfg.get_str("", "brand", "")
    
    # Параметры Telegram
    MY_ID = cfg.get("TelegramBot", "MY_ID", "")
    TOKEN = cfg.get("TelegramBot", "TOKEN", "")
    
    # Другие параметры
    proxy = cfg.get_str("", "proxy", "")
    table_name = cfg.get_str("", "table_name", "")
    sqlite_file = cfg.get_str("", "sqlite_file", "")
    
    # Экспортируем сам cfg для продвинутого использования
    __all__ = [
        'debug_mode', 'DEBUG_Mode', 'DEBUG_MODE',
        'cities', 'search_req', 'brand',
        'MY_ID', 'TOKEN', 'proxy',
        'table_name', 'sqlite_file', 'cfg'
    ]
    
except Exception as e:
    print(f"⚠️ Ошибка загрузки конфигурации: {e}")
    # Значения по умолчанию
    debug_mode = DEBUG_Mode = DEBUG_MODE = False
    cities = search_req = brand = []
    MY_ID = TOKEN = proxy = table_name = sqlite_file = ""
    cfg = None