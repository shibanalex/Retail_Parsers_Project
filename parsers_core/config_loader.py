"""
Универсальный загрузчик конфигурации с поддержкой значений по умолчанию,
обработкой ошибок и преобразованием типов. Регистронезависимый.
Расположение: parsers_core/config_loader.py
"""
import os
import sys
from typing import Any, Optional, Union, Dict, List, Callable, overload
from pathlib import Path

# Добавляем родительскую директорию в путь для поиска config.py
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

class CaseInsensitiveDict(dict):
    """Словарь, нечувствительный к регистру ключей"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._lower_keys = {k.lower(): k for k in self.keys()}
    
    def __getitem__(self, key):
        if isinstance(key, str):
            key_lower = key.lower()
            if key_lower in self._lower_keys:
                return super().__getitem__(self._lower_keys[key_lower])
        return super().__getitem__(key)
    
    def __setitem__(self, key, value):
        if isinstance(key, str):
            key_lower = key.lower()
            if key_lower in self._lower_keys:
                # Обновляем существующий ключ
                original_key = self._lower_keys[key_lower]
                super().__setitem__(original_key, value)
            else:
                # Добавляем новый ключ
                super().__setitem__(key, value)
                self._lower_keys[key.lower()] = key
        else:
            super().__setitem__(key, value)
    
    def __contains__(self, key):
        if isinstance(key, str):
            return key.lower() in self._lower_keys
        return super().__contains__(key)
    
    def get(self, key, default=None):
        if isinstance(key, str):
            key_lower = key.lower()
            if key_lower in self._lower_keys:
                return super().__getitem__(self._lower_keys[key_lower])
        return super().get(key, default)
    
    def pop(self, key, default=None):
        if isinstance(key, str):
            key_lower = key.lower()
            if key_lower in self._lower_keys:
                original_key = self._lower_keys.pop(key_lower)
                return super().pop(original_key, default)
        return super().pop(key, default)


class ConfigLoader:
    """Загрузчик конфигурации из Python файлов (регистронезависимый)"""
    
    # Поддерживаемые значения для True/False
    TRUE_VALUES = {'true', '1', 'yes', 'y', 'on', 'да', 'включено', 'enable', 'enabled'}
    FALSE_VALUES = {'false', '0', 'no', 'n', 'off', 'нет', 'выключено', 'disable', 'disabled'}
    
    def __init__(self, config_path: Optional[str] = None, case_sensitive: bool = False):
        """
        Инициализация загрузчика конфигурации
        
        Args:
            config_path: Путь к файлу конфигурации
            case_sensitive: Чувствительность к регистру (по умолчанию False)
        """
        self.case_sensitive = case_sensitive
        self.config = {} if case_sensitive else CaseInsensitiveDict()
        self.config_path = config_path
        
        if config_path:
            self._load_config(config_path)
        else:
            self._find_and_load_config()
    
    def _find_and_load_config(self):
        """Поиск и загрузка config.py"""
        possible_paths = [
            "config.py",
            "../config.py",
            "config/config.py",
            os.path.join(os.path.dirname(__file__), "config.py"),
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.py")
        ]
        
        for path in possible_paths:
            if os.path.exists(path):
                self._load_config(path)
                return
        
        print("⚠️  Файл config.py не найден. Используется пустая конфигурация.")
    
    def _load_config(self, config_path: str):
        """Загрузка конфигурации из Python файла"""
        try:
            config_path = os.path.abspath(config_path)
            config_dir = os.path.dirname(config_path)
            
            if config_dir not in sys.path:
                sys.path.insert(0, config_dir)
            
            config_module_name = os.path.basename(config_path).replace('.py', '')
            
            if config_module_name in sys.modules:
                del sys.modules[config_module_name]
            
            import importlib.util
            spec = importlib.util.spec_from_file_location(config_module_name, config_path)
            config_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(config_module)
            
            # Собираем все переменные
            config_dict = config_module.__dict__
            for key, value in config_dict.items():
                if not key.startswith('_') and not callable(value) and not isinstance(value, type):
                    if isinstance(value, dict) and not self.case_sensitive:
                        value = self._make_case_insensitive(value)
                    self.config[key] = value
            
            print(f"✅ Конфигурация загружена из {config_path}")
            
        except Exception as e:
            print(f"❌ Ошибка загрузки конфигурации из {config_path}: {e}")
            self.config = {} if self.case_sensitive else CaseInsensitiveDict()
    
    def _make_case_insensitive(self, data):
        """Рекурсивное преобразование словарей в CaseInsensitiveDict"""
        if isinstance(data, dict):
            result = CaseInsensitiveDict()
            for key, value in data.items():
                if isinstance(value, dict):
                    result[key] = self._make_case_insensitive(value)
                elif isinstance(value, list):
                    result[key] = [
                        self._make_case_insensitive(item) if isinstance(item, dict) else item
                        for item in value
                    ]
                else:
                    result[key] = value
            return result
        return data
    
    def _parse_bool(self, value: Any) -> bool:
        """Преобразование значения в bool с поддержкой разных форматов"""
        if isinstance(value, bool):
            return value
        
        if isinstance(value, (int, float)):
            return bool(value)
        
        if isinstance(value, str):
            value_str = str(value).strip().lower()
            if value_str in self.TRUE_VALUES:
                return True
            elif value_str in self.FALSE_VALUES:
                return False
        
        try:
            num_value = float(value)
            return bool(num_value)
        except:
            print(f"⚠️  Не удалось распознать bool значение: '{value}'. Используется False")
            return False
    
    def _normalize_key(self, key: str) -> str:
        """Нормализация ключа в зависимости от настроек регистра"""
        return key if self.case_sensitive else key.lower()
    
    @overload
    def get(self, section: str, required: bool = False) -> Any: ...
    
    @overload
    def get(self, section: str, key: str, default: Any = None, required: bool = False) -> Any: ...
    
    def get(self, section: str, key: Optional[str] = None, default: Any = None, required: bool = False) -> Any:
        """
        Основной метод получения значений из конфигурации
        
        Использование:
        1. cfg.get("TelegramBot") - вернёт весь раздел
        2. cfg.get("TelegramBot", "token") - вернёт конкретный ключ
        3. cfg.get("TelegramBot", "token", default="") - с значением по умолчанию
        
        Args:
            section: Раздел конфигурации (регистронезависимый)
            key: Ключ внутри раздела (регистронезависимый)
            default: Значение по умолчанию
            required: Обязательный ли параметр
        
        Returns:
            Значение параметра или default
        """
        # Нормализуем имя раздела
        section_norm = self._normalize_key(section) if isinstance(section, str) else section
        
        # Проверяем наличие раздела
        if section_norm not in self.config:
            if required and key is None:
                raise ValueError(f"Обязательный раздел '{section}' отсутствует в конфигурации")
            return default if key is not None else None
        
        # Получаем данные раздела
        if self.case_sensitive:
            section_data = self.config.get(section)
        else:
            section_data = self.config.get(section_norm)
        
        if section_data is None:
            if required and key is None:
                raise ValueError(f"Раздел '{section}' пустой")
            return default if key is not None else None
        
        # Если key не указан, возвращаем весь раздел
        if key is None:
            return section_data
        
        # Нормализуем ключ
        key_norm = self._normalize_key(key) if isinstance(key, str) else key
        
        # Получаем значение из раздела
        if isinstance(section_data, dict):
            if self.case_sensitive:
                value = section_data.get(key)
            else:
                # Ищем ключ без учёта регистра
                if isinstance(section_data, CaseInsensitiveDict):
                    value = section_data.get(key_norm)
                else:
                    # Если это обычный dict, ищем вручную
                    key_lower = key_norm if isinstance(key_norm, str) else key_norm
                    for dict_key, dict_value in section_data.items():
                        if isinstance(dict_key, str) and dict_key.lower() == key_lower:
                            value = dict_value
                            break
                    else:
                        value = None
        elif hasattr(section_data, '__dict__'):
            # Ищем в атрибутах объекта
            if self.case_sensitive:
                value = getattr(section_data, key, None)
            else:
                # Ищем атрибут без учёта регистра
                key_lower = key_norm
                for attr_name in dir(section_data):
                    if not attr_name.startswith('_') and attr_name.lower() == key_lower:
                        value = getattr(section_data, attr_name)
                        break
                else:
                    value = None
        else:
            value = None
        
        # Обработка отсутствующего значения
        if value is None:
            if required:
                raise ValueError(f"Обязательный параметр '{section}.{key}' отсутствует в конфигурации")
            return default
        
        return value
    
    def get_bool(self, section: str, key: str, default: bool = False) -> bool:
        """Получение bool параметра (регистронезависимый)"""
        value = self.get(section, key, default)
        return self._parse_bool(value)
    
    def get_int(self, section: str, key: str, default: int = 0) -> int:
        """Получение int параметра (регистронезависимый)"""
        value = self.get(section, key, default)
        try:
            return int(value)
        except (ValueError, TypeError):
            print(f"⚠️  Не удалось преобразовать '{value}' в int. Используется default: {default}")
            return default
    
    def get_float(self, section: str, key: str, default: float = 0.0) -> float:
        """Получение float параметра (регистронезависимый)"""
        value = self.get(section, key, default)
        try:
            return float(value)
        except (ValueError, TypeError):
            print(f"⚠️  Не удалось преобразовать '{value}' в float. Используется default: {default}")
            return default
    
    def get_str(self, section: str, key: str, default: str = "") -> str:
        """Получение string параметра (регистронезависимый)"""
        value = self.get(section, key, default)
        return str(value)
    
    def get_list(self, section: str, key: str, default: Optional[list] = None) -> list:
        """Получение list параметра (регистронезависимый)"""
        if default is None:
            default = []
        value = self.get(section, key, default)
        if isinstance(value, list):
            return value
        elif isinstance(value, (tuple, set)):
            return list(value)
        else:
            if isinstance(value, str) and value:
                return [item.strip() for item in value.split(',')]
            return default
    
    def get_dict(self, section: str, key: Optional[str] = None, default: Optional[dict] = None) -> dict:
        """Получение dict параметра (регистронезависимый)"""
        if default is None:
            default = {}
        
        value = self.get(section, key, default) if key else self.get(section, default=default)
        
        if isinstance(value, dict):
            return value
        else:
            print(f"⚠️  Значение '{section}.{key if key else ''}' не является словарём. Используется default")
            return default
    
    def section_exists(self, section: str) -> bool:
        """Проверка существования раздела (регистронезависимая)"""
        section_norm = self._normalize_key(section) if isinstance(section, str) else section
        return section_norm in self.config
    
    def key_exists(self, section: str, key: str) -> bool:
        """Проверка существования ключа в разделе (регистронезависимая)"""
        if not self.section_exists(section):
            return False
        
        section_data = self.get(section)
        if section_data is None:
            return False
        
        key_norm = self._normalize_key(key) if isinstance(key, str) else key
        
        if isinstance(section_data, dict):
            if self.case_sensitive:
                return key in section_data
            else:
                if isinstance(section_data, CaseInsensitiveDict):
                    return key_norm in section_data
                else:
                    # Ищем в обычном dict
                    return any(
                        isinstance(k, str) and k.lower() == key_norm
                        for k in section_data.keys()
                    )
        elif hasattr(section_data, '__dict__'):
            if self.case_sensitive:
                return hasattr(section_data, key)
            else:
                # Ищем атрибут без учёта регистра
                return any(
                    not attr_name.startswith('_') and attr_name.lower() == key_norm
                    for attr_name in dir(section_data)
                )
        
        return False


# Глобальный экземпляр для удобства
_cfg_instance = None

def get_config(config_path: Optional[str] = None, case_sensitive: bool = False) -> ConfigLoader:
    """
    Получение экземпляра ConfigLoader
    
    Args:
        config_path: Путь к файлу конфигурации
        case_sensitive: Чувствительность к регистру
        
    Returns:
        Экземпляр ConfigLoader
    """
    global _cfg_instance
    if _cfg_instance is None:
        _cfg_instance = ConfigLoader(config_path, case_sensitive)
    elif config_path and _cfg_instance.config_path != config_path:
        # Пересоздаём если путь изменился
        _cfg_instance = ConfigLoader(config_path, case_sensitive)
    
    return _cfg_instance

def _extract_parsers(cfg_obj: dict) -> dict:
    """
    Достаём parsers из конфига максимально мягко:
    - приоритет: parsers
    - fallback: PARSERS / parsers_map / PARSERS_MAP
    """
    if not isinstance(cfg_obj, dict):
        return {}

    # основной ключ
    p = cfg_obj.get("parsers")
    if isinstance(p, dict) and p:
        return p

    # fallback ключи
    for k in ("PARSERS", "parsers_map", "PARSERS_MAP"):
        p = cfg_obj.get(k)
        if isinstance(p, dict) and p:
            return p

    return {}

# Алиас для удобства (по умолчанию регистронезависимый)
cfg = get_config()