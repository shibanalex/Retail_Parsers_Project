"""
parsers_core - ядро парсеров
"""

from .config_loader import ConfigLoader, get_config, cfg
from .retail_manager import get_retail_manager, RetailManager
from .proxy_utils import ProxyManager
from .utils import (
    ANSI_RESET, ANSI_GREEN, ANSI_YELLOW, ANSI_GRAY, ANSI_RED,
    ANSI_PURPLE, ANSI_BLACK_BG,

    set_console_mode, reset_console_mode, plural_ru,
    safe_open, safe_get_cookies, _safe_quit,
    count_records, write_excel, write_json, write_log,
    SendTelegram, SendTelegramFile,
    update_retail_points,
    write_sql_draft, write_sqlite_draft, debug_mode,

    SeleniumSoftFail
)

from .proxy_utils import (
    ProxyManager,
    ProxyPool,
    rotate_proxy,
    validate_proxy,
    get_proxy_list,
    get_proxy_manager,
    should_use_proxy,
    detect_protocol_by_port,
    get_protocol_display,
    detect_protocol_full,
)

__version__ = '1.0.1'
__all__ = [
    'ConfigLoader', 'get_config', 'cfg',

    'ANSI_RESET', 'ANSI_GREEN', 'ANSI_YELLOW', 'ANSI_GRAY',
    'ANSI_RED', 'ANSI_PURPLE', 'ANSI_BLACK_BG',

    'set_console_mode', 'reset_console_mode', 'plural_ru',
    'safe_open', 'safe_get_cookies', '_safe_quit',
    'count_records', 'write_excel', 'write_json', 'write_log',
    'SendTelegram', 'SendTelegramFile', 'update_retail_points',
    'write_sql_draft', 'write_sqlite_draft', 'debug_mode',

    'SeleniumSoftFail',

    'cfg',
    'get_retail_manager', 
    'retail',
    'get_assoc_saver',  
    'assoc_saver',   
    'ProxyManager',
    'detect_protocol_by_port',
    'get_protocol_display', 
    'detect_protocol_full',
    'ProxyPool',
    'rotate_proxy',
    'validate_proxy',
    'get_proxy_list',
    'should_use_proxy',
    'RetailManager',  
]