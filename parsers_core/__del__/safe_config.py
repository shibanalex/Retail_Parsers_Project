"""
Безопасные обертки для работы с конфигурацией  v2.0
"""
import ast
import sys
from pathlib import Path
from typing import Any, Optional, Dict, List, Union
from .config_loader import cfg, ConfigLoader
from .exceptions import ConfigError


class SafeConfig:
    """Безопасные методы для работы с конфигурацией"""
    
    def __init__(self, config_path: str = None):
        """Инициализация с возможностью загрузки Python-конфига"""
        self.config_dict = {}
        
        if config_path and config_path.endswith(('.rpc', '.py')):
            self._load_python_config(config_path)
        elif cfg:
            # Используем существующий INI-конфиг
            pass
    
    def _load_python_config(self, config_path: str):
        """Загружает Python-конфиг файл"""
        try:
            # 1. Способ через exec (для .rpc файлов)
            with open(config_path, 'r', encoding='utf-8') as f:
                config_code = f.read()
            
            # Создаем безопасное пространство имен
            config_globals = {
                '__builtins__': {
                    'list': list,
                    'dict': dict,
                    'str': str,
                    'int': int,
                    'bool': bool,
                    'False': False,
                    'True': True,
                    'None': None
                }
            }
            
            # Выполняем код конфига
            exec(config_code, config_globals)
            
            # Переносим переменные в config_dict
            for key, value in config_globals.items():
                if not key.startswith('_') and not callable(value):
                    self.config_dict[key] = value
            
            print(f"✅ Загружен Python-конфиг из {config_path}")
            
        except Exception as e:
            print(f"❌ Ошибка загрузки Python-конфига: {e}")
            raise ConfigError(f"Не удалось загрузить конфиг: {e}")
    
    def get(self, key: str, default: Any = None, section: str = None) -> Any:
        """Универсальный get для Python и INI конфигов"""
        # Если есть загруженный Python-конфиг
        if self.config_dict:
            if section:
                # Для совместимости со старым кодом
                if section in self.config_dict:
                    section_dict = self.config_dict.get(section, {})
                    if isinstance(section_dict, dict):
                        return section_dict.get(key, default)
                return default
            else:
                return self.config_dict.get(key, default)
        
        # Иначе используем старый INI-конфиг
        if section:
            return cfg.get(section, key, default)
        return cfg.get(key, default) if hasattr(cfg, 'get') else default
    
    def get_bool(self, key: str, default: bool = False, section: str = None) -> bool:
        """Получение булева значения"""
        value = self.get(key, default, section)
        
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ['true', '1', 'yes', 'on', 'да']
        return bool(value)
    
    def get_dict(self, key: str, default: dict = None, section: str = None) -> Dict:
        """Получение словаря"""
        value = self.get(key, default or {}, section)
        return dict(value) if isinstance(value, (dict, list)) else default or {}
    
    def get_list(self, key: str, default: list = None, section: str = None) -> List:
        """Получение списка"""
        value = self.get(key, default or [], section)
        return list(value) if isinstance(value, (list, tuple, set)) else default or []
    
    @staticmethod
    def get_required(section: str, key: str, error_msg: str = None) -> Any:
        """Получение обязательного параметра с обработкой ошибок"""
        try:
            value = cfg.get(section, key, required=True)
            if value is None:
                raise ConfigError(error_msg or f"Параметр '{section}.{key}' не может быть None")
            return value
        except ValueError as e:
            raise ConfigError(error_msg or str(e))
    
    # ... остальные методы остаются с небольшими изменениями
    
    def get_database_config(self) -> Dict:
        """Получение конфигурации базы данных с проверкой"""
        # Пробуем получить из Python-конфига
        sql_config = self.get('SQL', {}, section=None)
        if isinstance(sql_config, dict) and sql_config:
            return {
                'host': sql_config.get('host', 'localhost'),
                'port': sql_config.get('port', 5432),
                'database': sql_config.get('DB_Work', ''),
                'user': sql_config.get('user', ''),
                'password': sql_config.get('password', ''),
                'TABLE_Draft': sql_config.get('TABLE_Draft', ''),
            }
        
        # Иначе из INI-конфига (старый способ)
        required_keys = ['host', 'database', 'user', 'password']
        db_config = cfg.get_dict('SQL', default={})
        
        missing = [key for key in required_keys if not db_config.get(key)]
        if missing:
            raise ConfigError(f"В конфигурации SQL отсутствуют ключи: {missing}")
        
        return {
            'host': db_config.get('host', 'localhost'),
            'port': cfg.get_int('SQL', 'port', 5432),
            'database': db_config.get('database'),
            'user': db_config.get('user'),
            'password': db_config.get('password'),
            'pool_size': cfg.get_int('SQL', 'pool_size', 10),
            'echo': cfg.get_int('SQL', 'echo', 0)
        }
    
    def get_telegram_config(self) -> Dict:
        """Получение конфигурации Telegram бота"""
        # Пробуем получить из Python-конфига
        tg_config = self.get('TelegramBot', {}, section=None)
        if isinstance(tg_config, dict) and tg_config:
            return {
                'enabled': tg_config.get('send', False),
                'token': tg_config.get('TOKEN', ''),
                'chat_id': tg_config.get('CHAT_ID', ''),
                'MY_ID': tg_config.get('MY_ID', ''),
            }
        
        # Иначе из INI-конфига
        telegram_config = cfg.get_dict('TelegramBot', default={})
        
        if not telegram_config.get('token'):
            return {'enabled': False}
        
        return {
            'enabled': True,
            'token': telegram_config.get('token'),
            'chat_id': telegram_config.get('chat_id', ''),
            'admin_ids': cfg.get_list('TelegramBot', 'admin_ids', []),
            'notifications': cfg.get_bool('TelegramBot', 'notifications', True),
            'timeout': cfg.get_int('TelegramBot', 'timeout', 30)
        }
    
    def get_proxy_config(self) -> Dict:
        """Получение конфигурации прокси"""
        # Пробуем получить из Python-конфига
        proxy_value = self.get('proxy', '', section=None)
        
        return {
            'enabled': bool(proxy_value),
            'proxy_path': proxy_value if isinstance(proxy_value, str) else '',
            'proxy_list': [],
        }


# Глобальный экземпляр с загрузкой Python-конфига
_safe_config_instance = None

def get_safe_config(config_path: str = None) -> SafeConfig:
    """Получение экземпляра SafeConfig с загрузкой конфига"""
    global _safe_config_instance
    
    if _safe_config_instance is None:
        _safe_config_instance = SafeConfig(config_path)
    
    return _safe_config_instance


# Для обратной совместимости - старая функция
def config() -> SafeConfig:
    """Старая функция для обратной совместимости"""
    return get_safe_config()