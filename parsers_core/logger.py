"""
Настройка логгера
"""
import logging
import sys
from datetime import datetime
from pathlib import Path
from .config_loader import cfg


def setup_logger(
    name: str = "parser",
    log_level: str = None,
    log_file: str = None
) -> logging.Logger:
    """
    Настройка логгера
    
    Args:
        name: Имя логгера
        log_level: Уровень логирования (DEBUG, INFO, WARNING, ERROR)
        log_file: Путь к файлу логов
    
    Returns:
        Настроенный логгер
    """
    # Получаем настройки из конфига
    if log_level is None:
        log_level = cfg.get_str("", "LOG_LEVEL", "INFO").upper()
    
    if log_file is None:
        log_file = cfg.get_str("", "LOG_FILE", "parser.log")
    
    # Создаем логгер
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, log_level, logging.INFO))
    
    # Очищаем существующие обработчики
    logger.handlers.clear()
    
    # Форматтер
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Консольный обработчик
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Файловый обработчик
    if log_file:
        # Создаем директорию для логов если нужно
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def get_logger(name: str = "parser") -> logging.Logger:
    """Получение логгера по имени"""
    logger = logging.getLogger(name)
    
    # Если логгер еще не настроен, настраиваем
    if not logger.handlers:
        setup_logger(name)
    
    return logger


def log_execution_time(func):
    """Декоратор для логирования времени выполнения"""
    import time
    import functools
    
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        logger = get_logger(func.__module__)
        start_time = time.time()
        
        try:
            result = func(*args, **kwargs)
            execution_time = time.time() - start_time
            
            logger.info(
                f"Function '{func.__name__}' executed in {execution_time:.2f} seconds"
            )
            
            return result
        except Exception as e:
            logger.error(f"Error in function '{func.__name__}': {e}")
            raise
    
    return wrapper