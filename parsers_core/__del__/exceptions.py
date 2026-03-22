"""
Пользовательские исключения
"""


class ParserError(Exception):
    """Базовое исключение для парсеров"""
    pass


class ConfigError(ParserError):
    """Ошибка конфигурации"""
    pass


class ProxyError(ParserError):
    """Ошибка прокси"""
    pass


class ValidationError(ParserError):
    """Ошибка валидации"""
    pass


class RetryExhaustedError(ParserError):
    """Исчерпаны все попытки повтора"""
    pass


class DatabaseError(ParserError):
    """Ошибка базы данных"""
    pass


class NetworkError(ParserError):
    """Сетевая ошибка"""
    pass