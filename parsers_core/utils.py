import os
import re
import unicodedata
import json
import pandas as pd
import gc
import openpyxl
from datetime import datetime
import requests
import psycopg2
import sqlite3
from typing import Optional, Union
from selenium.common.exceptions import NoSuchWindowException, WebDriverException
import time

try:
    from .config_loader import cfg
except ImportError:
    try:
        from config_loader import cfg
    except ImportError:
        cfg = None
        print("⚠️ config_loader не найден")
"""
# Пробуем получить emoji_agent из конфига
if cfg:
    try:
        emj_agent = cfg.get("", "emoji_agent", "🥷")
    except Exception:
        emj_agent = "🥷"
else:
    # Fallback если config_loader не загружен
    try:
        from config import emoji_agent
        emj_agent = emoji_agent
    except ImportError:
        emj_agent = "🥷"
"""
try:
    from main import EMOJI_AGENT
    emj_agent =  EMOJI_AGENT
except ImportError:
    emj_agent = "🥷"

class SeleniumSoftFail(Exception):
    """Мягкая ошибка Selenium (антибот / закрыто окно / CF)"""
    pass


ANSI_RESET     = "\x1b[0m"

ANSI_GREEN     = "\x1b[32m"
ANSI_YELLOW    = "\x1b[33m"
ANSI_GRAY      = "\x1b[90m"
ANSI_RED       = "\x1b[31m"
ANSI_PURPLE    = "\x1b[35m"
ANSI_BLACK_BG  = "\x1b[40m"


def set_console_mode(color: str) -> None:
    """Цвет текста на чёрном фоне, действует до reset_console_mode()."""
    print(color + ANSI_BLACK_BG, end="", flush=True)


def reset_console_mode() -> None:
    """
    Сброс ANSI-режима (возврат к дефолту).
    """
    print(ANSI_RESET, end="", flush=True)

def plural_ru(n: int, one: str, few: str, many: str) -> str:
    """plural_ru(5, 'парсер', 'парсера', 'парсеров') -> 'парсеров'."""
    n = abs(int(n))

    if 11 <= n % 100 <= 14:
        return many

    last = n % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many

def safe_open(sb, url: str, tag: str = "", retries: int = 1, sleep_sec: int = 3) -> bool:
    """Открывает страницу. При ошибке возвращает False, не падает."""

    for attempt in range(1, retries + 1):
        try:
            sb.open(url)
            return True

        except NoSuchWindowException as e:
            _safe_quit(sb)
            if attempt >= retries:
                raise SeleniumSoftFail(
                    f"{tag}: окно браузера было закрыто (CF / anti-bot)"
                ) from e
            time.sleep(sleep_sec)

        except WebDriverException as e:
            _safe_quit(sb)
            if attempt >= retries:
                raise SeleniumSoftFail(
                    f"{tag}: WebDriverException ({e.__class__.__name__})"
                ) from e
            time.sleep(sleep_sec)

        except Exception as e:
            _safe_quit(sb)
            if attempt >= retries:
                raise SeleniumSoftFail(
                    f"{tag}: неизвестная ошибка Selenium: {e}"
                ) from e
            time.sleep(sleep_sec)

    return False


def safe_json_resp(resp, where=""):
    text = getattr(resp, "text", "") or ""
    ct = ""
    try:
        ct = (resp.headers.get("content-type") or "").lower()
    except Exception:
        pass

    if not text.strip():
        raise RuntimeError(f"{where} empty body | HTTP {resp.status_code} | ct={ct}")

    if ("application/json" not in ct) and (not text.lstrip().startswith(("{", "["))):
        head = text[:200].replace("\n", " ")
        raise RuntimeError(f"{where} not-json | HTTP {resp.status_code} | ct={ct} | head={head!r}")

    try:
        return resp.json()
    except Exception as e:
        head = text[:200].replace("\n", " ")
        raise RuntimeError(f"{where} json-parse-failed | HTTP {resp.status_code} | ct={ct} | head={head!r} | err={e}")

def safe_get_cookies(sb, url: str, tag: str = ""):
    """Cookies страницы словарём {имя: значение}."""
    ok = safe_open(sb, url, tag=tag, retries=1)
    if not ok:
        return {}

    try:
        cookies = sb.driver.get_cookies()
        return {c["name"]: c["value"] for c in cookies}
    except Exception as e:
        raise SeleniumSoftFail(f"{tag}: не удалось получить cookies: {e}") from e


def _safe_quit(sb):
    """Закрывает драйвер, ошибки глушит."""
    try:
        sb.quit()
    except Exception:
        pass

def count_records(
    source_path: str,
    *,
    table: Optional[str] = None,
    sheet: Optional[Union[int, str]] = None,
    where: Optional[str] = None
) -> int:
    """Число записей в Excel, SQLite или PostgreSQL (по DSN). where — без слова WHERE."""

    source_path = source_path.strip()

    if source_path.lower().endswith((".xlsx", ".xls")):
        wb = openpyxl.load_workbook(source_path, read_only=True)
        try:
            if sheet is None:
                ws = wb[wb.sheetnames[0]]
            elif isinstance(sheet, int):
                ws = wb[wb.sheetnames[sheet]]
            else:
                ws = wb[sheet]
            return max(ws.max_row - 1, 0)
        finally:
            wb.close()

    if source_path.lower().endswith((".sqlite", ".db")):
        if not os.path.isfile(source_path):
            raise FileNotFoundError(f"SQLite файл не найден: {source_path}")

        if not table:
            raise ValueError("Для SQLite необходимо указать table")

        conn = sqlite3.connect(source_path)
        try:
            cur = conn.cursor()

            sql = f"SELECT COUNT(*) FROM {table}"
            if where:
                sql += f" WHERE {where}"

            cur.execute(sql)
            count = cur.fetchone()[0]
            return int(count)

        finally:
            conn.close()

    # Всё, что не файл — строка подключения PostgreSQL
    if not table:
        raise ValueError("Для PostgreSQL необходимо указать table")

    conn = psycopg2.connect(source_path)
    try:
        cur = conn.cursor()

        sql = f"SELECT COUNT(*) FROM {table}"
        if where:
            sql += f" WHERE {where}"

        cur.execute(sql)
        count = cur.fetchone()[0]
        return int(count)

    finally:
        conn.close()


def add_metadata_sheet(writer, data, debug_mode, assoc_debug, df):
    """Добавляет лист с метаданными"""
    try:
        version = 'N/A'
        try:
            import __main__
            if hasattr(__main__, '__version__'):
                version = __main__.__version__
            elif '__version__' in globals():
                version = globals()['__version__']
        except Exception:
            pass

        parser_name = 'Unknown'
        if data and len(data) > 0:
            parser_name = data[0].get('Сеть', 'Unknown')

        metadata = {
            'Параметр': [
                'Режим записи',
                'Время записи',
                'Количество записей',
                'Количество колонок',
                'Парсер',
                'Версия системы',
                'DEBUG_Mode',
                'ASSOC_Debug',
                'Категоризировано',
                'Брендов заполнено',
                'Весов заполнено',
                'Уникальных категорий',
                'Всего строк в файле'
            ],
            'Значение': [
                'DEBUG' if debug_mode else ('ASSOC_DEBUG' if assoc_debug else 'PRODUCTION'),
                datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                len(df),
                len(df.columns),
                parser_name,
                version,
                str(debug_mode),
                str(assoc_debug),
                f"{df['Категория'].notna().sum()}/{len(df)}" if 'Категория' in df.columns else 'N/A',
                f"{df['Бренд'].notna().sum()}/{len(df)}" if 'Бренд' in df.columns else 'N/A',
                f"{df['Вес'].notna().sum()}/{len(df)}" if 'Вес' in df.columns else 'N/A',
                f"{df['Категория'].nunique()}" if 'Категория' in df.columns else 'N/A',
                len(df)
            ]
        }
        meta_df = pd.DataFrame(metadata)
        meta_df.to_excel(writer, sheet_name='Метаданные', index=False)
        print(f"📋 Добавлен лист 'Метаданные'")

    except Exception as meta_error:
        print(f"⚠️ Не удалось добавить метаданные: {meta_error}")
def write_json(data, filename):
    try:
        folder = os.path.dirname(filename)
        if folder:
            os.makedirs(folder, exist_ok=True)

        with open(filename, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"💾 JSON сохранён: {filename}")
    except Exception as e:
        print(f"❌ Ошибка записи JSON: {e}")


def write_log(text, filename="parser_log.txt"):
    """
    Пишет текст в лог-файл с меткой времени.
    """
    try:
        os.makedirs("logs", exist_ok=True)
        filepath = os.path.join("logs", filename)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {text}\n")
        print(f"📝 Лог записан: {text}")
    except Exception as e:
        print(f"⚠️ Ошибка записи в лог: {e}")

    """
    Универсальная запись лога.
    Формат строки:
    YYYY-MM-DD \t HH:MM \t <text>
    """

def _load_telegram_bot_cfg() -> Optional[dict]:
    """TelegramBot из config.py, иначе из scheduler.config."""
    try:
        from parsers_core.tlgcfg import TelegramBot as TB
        if isinstance(TB, dict):
            return TB
    except Exception:
        pass

    try:
        from ..scheduler_core.config_loader import load_scheduler_config
        cfg = load_scheduler_config()
        tb = cfg.get("telegram_bot")
        if isinstance(tb, dict):
            return tb
    except Exception:
        pass

    return None

class TelegramBot:
    """Обёртка над SendTelegram/SendTelegramFile для старого кода."""

    @staticmethod
    def get(key: str, default=None):
        cfg = _load_telegram_bot_cfg()
        if not cfg:
            return default
        return cfg.get(key, default)

    @staticmethod
    def send(message: str) -> bool:
        return bool(SendTelegram(message))

    @staticmethod
    def send_file(filepath: str, caption: str = "") -> bool:
        return bool(SendTelegramFile(filepath, caption))

def SendTelegramFile(filepath: str, caption: str = ""):
    """Отправляет файл в Telegram. Настройки из config.TelegramBot."""
    TelegramBot = _load_telegram_bot_cfg()
    if not TelegramBot:
        return False
    tg_cfg = TelegramBot

    send_flag = TelegramBot.get("send", False)
    if not send_flag:
        print("📴 Отправка файлов в Telegram отключена (send=False).")
        return False

    token = TelegramBot.get("TOKEN")
    chat_id = TelegramBot.get("CHAT_ID")
    my_id = TelegramBot.get("MY_ID")

    if not token or not chat_id:
        print("⚠️ Ошибка: TOKEN или CHAT_ID не указаны в config.TelegramBot")
        return False

    if not os.path.exists(filepath):
        print(f"⚠️ Файл не найден: {filepath}")
        return False

    caption = f"{emj_agent} {my_id} {emj_agent}\n{caption}"

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    with open(filepath, "rb") as file_data:
        files = {"document": file_data}
        data = {"chat_id": chat_id, "caption": caption}

        try:
            response = requests.post(url, data=data, files=files, timeout=30)
            if response.status_code == 200:
                print(f"📤 Файл {os.path.basename(filepath)} отправлен в Telegram.")
                return True
            else:
                print(f"⚠️ Ошибка Telegram API: {response.status_code} {response.text}")
                return False
        except Exception as e:
            print(f"❌ Ошибка при отправке файла в Telegram: {e}")
            return False

def SendTelegram(message: str):
    """Отправляет сообщение в Telegram (HTML). Настройки из config.TelegramBot."""

    TelegramBot = _load_telegram_bot_cfg()
    if not TelegramBot:
        return False

    tg_cfg = TelegramBot
    send_flag = TelegramBot.get("send", False)
    if not send_flag:
        print("📴 Отправка в Telegram отключена (send=False).")
        return False

    token = TelegramBot.get("TOKEN")
    chat_id = TelegramBot.get("CHAT_ID")
    my_id = TelegramBot.get("MY_ID")
    time_now = datetime.now().strftime("%H:%M:%S")
    if not token or not chat_id:
        print("⚠️ Ошибка: TOKEN или CHAT_ID не указаны в config.TelegramBot")
        return False

    message = f"{emj_agent} {my_id} {emj_agent}   ⏱️ {time_now}  \n{message}"

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }

    try:
        response = requests.post(url, data=data, timeout=5)
        if response.status_code != 200:
            return False
        return True

    except (requests.exceptions.Timeout,
            requests.exceptions.ConnectionError):
        return False

    except Exception:
        return False


def debug_mode(cfg_param: dict = None) -> bool:
    """True только при DEBUG_MODE = true / 1 / yes."""
    if cfg_param is None:
        if cfg:
            debug_value = cfg.get("", "DEBUG_MODE", "")
        else:
            try:
                from config import DEBUG_MODE
                debug_value = DEBUG_MODE
            except Exception:
                debug_value = ""
    else:
        debug_value = cfg_param.get("DEBUG_MODE", "")

    return str(debug_value).lower() in ("true", "1", "yes")


def update_retail_points(parser_name: str, city: str, count: int, filename: str = None) -> bool:
    """Число точек сети в DB_Retail_Points_MAP.xlsx. Файл под блокировкой — для параллельного запуска."""
    if filename is None:
        try:
            from config import db_retail_map
        except Exception:
            print("⚠️ update_retail_points: нет db_retail_map в config.py — пропуск")
            return False
        filename = db_retail_map

    if not filename.lower().endswith(".xlsx"):
        filename += ".xlsx"

    from .filelock import locked, LockTimeout

    for attempt in range(5):
        try:
            with locked(filename, timeout=60):
                return _update_retail_points_unlocked(filename, parser_name, city, count)
        except PermissionError:
            if attempt == 4:
                print(f"⚠️ update_retail_points: {filename} занят (открыт в Excel?) — пропуск {parser_name} / {city}")
                return False
            time.sleep(2)
        except LockTimeout as e:
            print(f"⚠️ update_retail_points: {e} — пропуск {parser_name} / {city}")
            return False
    return False


def _update_retail_points_unlocked(filename, parser_name, city, count):
    if not os.path.exists(filename):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["Дата", "Время", "Имя парсера", "Город", "Количество ТТ"])
        wb.save(filename)
    else:
        wb = openpyxl.load_workbook(filename)
        ws = wb.active

    updated = False
    today = datetime.now().strftime("%Y-%m-%d")
    now_time = datetime.now().strftime("%H:%M:%S")

    old_count = None
    found = False

    for row in ws.iter_rows(min_row=2, max_col=5):
        parser_cell = row[2].value
        city_cell = row[3].value

        if (parser_cell and str(parser_cell).strip().lower() == parser_name.lower() and
                city_cell and str(city_cell).strip().lower() == city.lower()):

            old_count = row[4].value
            found = True

            if old_count is None or count > int(old_count):
                row[0].value = today
                row[1].value = now_time
                row[2].value = parser_name
                row[3].value = city
                row[4].value = count
                updated = True
                print(f"➡️ Обновлено: {parser_name} — {city} количество ТТ 🏪  {old_count} → {count} 🆕🏪   ")

            break

    if not found:
        ws.append([today, now_time, parser_name, city, count])
        updated = True
        print(f"➕ Добавлено: {parser_name} — {city} количество ТТ 🏪 = {count} 🆕")

    if not updated and found:
        print(f"ℹ️ Без изменений: {parser_name} — {city} количество ТТ 🏪 {count} <= {old_count} 📇")

    if updated:
        wb.save(filename)

    return updated


def write_sql_draft(data, debug_mode=False, assoc_debug=False):
    """Дописывает данные в retail_draft (PostgreSQL). Набор полей зависит от debug_mode / assoc_debug."""

    if cfg:
        try:
            SQL = cfg.get("SQL", {})
            TelegramBot = cfg.get("TelegramBot", {})
        except Exception:
            SQL = {}
            TelegramBot = {}
    else:
        try:
            from config import SQL, TelegramBot
        except Exception as e:
            print(f"⚠️🧯 SQL Draft пропущен — нет SQL/TelegramBot в config.py: {e}")
            return "FAILED"

    if not isinstance(SQL, dict) or not SQL.get("DB_Draft"):
        print("⚠️🧯 SQL Draft пропущен — нет DB_Draft")
        return "FAILED"

    dbtable = SQL.get("TABLE_Draft")
    if not dbtable:
        print("⚠️🧯 SQL Draft пропущен — TABLE_Draft не задан")
        return "FAILED"

    if not data:
        print("⚠️🧯 SQL Draft пропущен — нет данных")
        return "FAILED"

    print(f"\n{'=' * 60}")
    print(f"📝 ПОДГОТОВКА ДАННЫХ ДЛЯ POSTGRESQL")
    print(f"{'=' * 60}")

    prepared_data = []

    for item in data:
        new_item = item.copy()

        normalized_brand = item.get('Бренд (нормализованный)') or item.get('normalized_brand')
        if normalized_brand:
            new_item['Бренд'] = normalized_brand
            new_item['normalized_brand'] = normalized_brand

        weight_volume = item.get('weight_volume')
        current_weight = item.get('Вес') or item.get('weight')
        if weight_volume and not current_weight:
            new_item['Вес'] = weight_volume

        uni_cat = item.get('uni_cat')
        if uni_cat:
            new_item['Категория'] = uni_cat

        current_gtin = item.get('GTIN') or item.get('gtin')
        article = item.get('Артикул') or item.get('article')
        if not current_gtin and article:
            new_item['GTIN'] = article

        prepared_data.append(new_item)

    if debug_mode:
        mode_label = "DEBUG (data_enricher)"
        data_for_sql = prepared_data
        print(f"🔧 Режим: {mode_label} - все технические поля")

        normalized_count = sum(
            1 for item in prepared_data if 'Бренд (нормализованный)' in item and item['Бренд (нормализованный)'])
        weight_fixed = sum(1 for item in prepared_data if item.get('weight_volume') and not item.get('Вес'))
        cat_normalized = sum(1 for item in prepared_data if item.get('uni_cat'))
        print(f"📊 Нормализация: {normalized_count} брендов, {weight_fixed} весов, {cat_normalized} категорий")

    elif assoc_debug:
        mode_label = "ASSOC_DEBUG"
        technical_fields_to_hide = [
            '_data_quality', '_enriched_timestamp', 'brand_source',
            'cat_source', 'normalized_name', 'weight_volume', 'packaging',
            'Бренд (нормализованный)', 'normalized_name'
        ]

        filtered_data = []
        for item in prepared_data:
            new_item = {}
            for key, value in item.items():
                if key not in technical_fields_to_hide:
                    new_item[key] = value
            filtered_data.append(new_item)

        data_for_sql = filtered_data
        print(f"🔍 Режим: {mode_label} - поля для отладки ассоциаций")

    else:
        mode_label = "PRODUCTION"
        technical_fields_to_hide = [
            '_data_quality', '_enriched_timestamp', 'brand_source',
            'cat_source', 'normalized_name', 'weight_volume', 'packaging',
            'code_cat', 'rule_id', 'confidence', 'retail_cat',
            'Бренд (нормализованный)', 'normalized_name', 'normalized_brand',
            'ID правила', 'Уверенность', 'Категория ритейлера'
        ]

        filtered_data = []
        for item in prepared_data:
            new_item = {}
            for key, value in item.items():
                if key not in technical_fields_to_hide:
                    new_item[key] = value
            filtered_data.append(new_item)

        data_for_sql = filtered_data
        print(f"📤 Режим: {mode_label} - только production поля для КП")

    print(f"📊 Записей для записи: {len(data_for_sql)}")

    try:
        print(f"\n🔗 Подключение к PostgreSQL...")
        conn = psycopg2.connect(
            host=SQL.get("host"),
            port=SQL.get("port", 5432),
            user=SQL.get("user"),
            password=SQL.get("password"),
            dbname=SQL.get("DB_Draft")
        )
        conn.autocommit = False
        cursor = conn.cursor()
        print(f"✅ Подключение успешно")

    except Exception as e:
        print(f"❌🗄️🔌 Ошибка подключения к PostgreSQL: {e}")
        print(f"🔄 Переход к SQLite...")
        SendTelegram(f"❌🗄️🔌 SQL Draft: ошибка подключения\n{e}")
        return write_sqlite_draft(prepared_data, debug_mode=debug_mode, assoc_debug=assoc_debug)

    DB_TABLE = dbtable
    date_now = datetime.now().strftime("%Y-%m-%d")
    time_now = datetime.now().strftime("%H:%M:%S")
    agent = TelegramBot.get("MY_ID", "unknown")

    try:
        check_table_sql = f"""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = '{DB_TABLE}'
            );
        """
        cursor.execute(check_table_sql)
        table_exists = cursor.fetchone()[0]

        if table_exists:
            count_sql = f'SELECT COUNT(*) FROM "{DB_TABLE}"'
            cursor.execute(count_sql)
            old_count = cursor.fetchone()[0]
            print(f"📊 Таблица существует, записей: {old_count}")
        else:
            old_count = 0
            print(f"📊 Таблица не существует, будет создана")

        if not table_exists:
            create_table_sql = f"""
                CREATE TABLE "{DB_TABLE}" (
                    id SERIAL PRIMARY KEY,
                    data_date TEXT NOT NULL,
                    data_time TEXT NOT NULL,
                    agent TEXT,
                    retailer TEXT,
                    store_type TEXT,
                    address TEXT,
                    brand TEXT,
                    product_name TEXT,
                    price REAL,
                    promo_price REAL,
                    photo_url TEXT,
                    product_url TEXT,
                    rating REAL,
                    volume TEXT,
                    weight TEXT,
                    stock TEXT,
                    category TEXT,
                    gtin TEXT,
                    flag BOOLEAN DEFAULT FALSE,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            """

            if debug_mode or assoc_debug:
                create_table_sql += """,
                    rule_id TEXT,
                    confidence REAL,
                    retail_category TEXT,
                    normalized_brand TEXT
                """

                if debug_mode:
                    create_table_sql += """,
                        code_cat INTEGER,
                        brand_source TEXT,
                        cat_source TEXT,
                        normalized_name TEXT,
                        weight_volume TEXT,
                        packaging TEXT,
                        data_quality TEXT,
                        enriched_timestamp TEXT
                    """

            create_table_sql += ");"

            cursor.execute(create_table_sql)
            print(f"✅ Таблица создана")

        print(f"\n💾 Вставка {len(data_for_sql)} записей...")

        inserted_count = 0
        skipped_count = 0

        for row in data_for_sql:
            try:
                brand = row.get("Бренд") or row.get("brand") or ""
                product_name = row.get("Название продукта") or row.get("product_name") or ""
                price = row.get("Цена") or row.get("price") or 0
                promo_price = row.get("Цена по акции") or row.get("promo_price") or 0

                category = row.get("Категория") or row.get("category") or row.get("uni_cat") or ""

                weight = row.get("Вес") or row.get("weight") or row.get("weight_volume") or ""

                gtin = row.get("GTIN") or row.get("gtin") or ""
                if not gtin:
                    gtin = row.get("Артикул") or row.get("article") or ""

                base_fields = [
                    "data_date", "data_time", "agent", "retailer", "store_type", "address",
                    "brand", "product_name", "price", "promo_price", "photo_url", "product_url",
                    "rating", "volume", "weight", "stock", "category", "gtin", "flag"
                ]

                base_values = [
                    date_now,
                    time_now,
                    agent,
                    row.get("Сеть") or row.get("retailer") or "",
                    row.get("Тип магазина") or row.get("store_type") or "",
                    row.get("Адрес Торговой точки") or row.get("address") or "",
                    brand,
                    product_name,
                    price,
                    promo_price,
                    row.get("Фото товара") or row.get("photo_url") or "",
                    row.get("Ссылка на страницу") or row.get("product_url") or "",
                    row.get("Рейтинг") or row.get("rating") or 0,
                    row.get("Объем") or row.get("volume") or "",
                    weight,
                    row.get("Остаток") or row.get("stock") or "",
                    category,
                    gtin,
                    False
                ]

                extra_fields = []
                extra_values = []

                if debug_mode or assoc_debug:
                    rule_id = row.get("rule_id") or row.get("ID правила") or ""
                    confidence_val = row.get("confidence") or row.get("Уверенность") or 0.0
                    retail_category = row.get("retail_cat") or row.get("Категория ритейлера") or ""
                    normalized_brand_val = row.get("normalized_brand") or brand

                    try:
                        confidence_val = float(confidence_val)
                        if confidence_val > 1.0:
                            confidence_val = 1.0
                        elif confidence_val < 0.0:
                            confidence_val = 0.0
                    except Exception:
                        confidence_val = 0.0

                    extra_fields.extend(["rule_id", "confidence", "retail_category", "normalized_brand"])
                    extra_values.extend([rule_id, confidence_val, retail_category, normalized_brand_val])

                    if debug_mode:
                        extra_fields.extend([
                            "code_cat", "brand_source", "cat_source",
                            "normalized_name", "weight_volume", "packaging",
                            "data_quality", "enriched_timestamp"
                        ])

                        extra_values.extend([
                            row.get("code_cat") or -1,
                            row.get("brand_source") or "",
                            row.get("cat_source") or "",
                            row.get("normalized_name") or "",
                            row.get("weight_volume") or "",
                            row.get("packaging") or "",
                            row.get("_data_quality") or "",
                            row.get("_enriched_timestamp") or ""
                        ])

                all_fields = base_fields + extra_fields
                all_values = base_values + extra_values

                placeholders = ", ".join(["%s"] * len(all_fields))
                fields_str = ", ".join(all_fields)

                insert_sql = f"""
                    INSERT INTO "{DB_TABLE}" ({fields_str})
                    VALUES ({placeholders})
                """

                cursor.execute(insert_sql, all_values)
                inserted_count += 1

                if inserted_count % 50 == 0:
                    print(f"   ... записано {inserted_count} из {len(data_for_sql)}")

            except Exception as row_error:
                skipped_count += 1
                if skipped_count <= 3:
                    print(f"⚠️ Пропущена запись: {row_error}")

        conn.commit()

        cursor.execute(f'SELECT COUNT(*) FROM "{DB_TABLE}"')
        total_count = cursor.fetchone()[0]
        new_added = total_count - old_count

        print(f"\n✅ POSTGRESQL ({mode_label}): УСПЕШНО")
        print(f"📊 Статистика:")
        print(f"   • Было записей: {old_count}")
        print(f"   • Добавлено новых: {new_added}")
        print(f"   • Всего записей: {total_count}")
        print(f"   • Успешно вставлено: {inserted_count}")
        print(f"   • Пропущено: {skipped_count}")

        print(f"\n📊 НОРМАЛИЗАЦИЯ ДАННЫХ:")
        if new_added > 0:
            print(f"   • Бренды нормализованы: да (если данные были)")
            print(f"   • Веса из weight_volume: да (если нужно было)")
            print(f"   • Категории из uni_cat: да (если были)")
            print(f"   • GTIN из Артикула: да (если GTIN пустой)")

        SendTelegram(f"✅🗄️♻️ PostgreSQL ({mode_label}): +{new_added} записей, всего {total_count}")
        return "POSTGRES"

    except Exception as e:
        conn.rollback()
        print(f"\n❌️🗄️ Ошибка записи в PostgreSQL: {e}")
        print(f"🔄 Переход к SQLite...")
        SendTelegram(f"❌🗄️ SQL Draft: ошибка записи\n{e}")

        try:
            cursor.close()
            conn.close()
        except Exception:
            pass

        return write_sqlite_draft(prepared_data, debug_mode=debug_mode, assoc_debug=assoc_debug)

    finally:
        try:
            cursor.close()
            conn.close()
            print(f"🔗 Соединение закрыто")
            print(f"{'=' * 60}")
        except Exception:
            pass


def write_sqlite_draft(data, debug_mode=False, assoc_debug=False):
    """Запасная запись в SQLite, если PostgreSQL недоступен."""

    if cfg:
        try:
            sqlite_file = cfg.get("", "sqlite_file", "")
            TelegramBot = cfg.get("TelegramBot", {})
            SQL = cfg.get("SQL", {})
        except Exception:
            sqlite_file = ""
            TelegramBot = {}
            SQL = {}
    else:
        try:
            from config import sqlite_file, TelegramBot, SQL
        except Exception as e:
            print(f"⚠️🛟 SQLite Draft пропущен — нет sqlite_file/SQL/TelegramBot in config.py: {e}")
            return "FAILED"

    DB_TABLE = SQL.get("TABLE_Draft")
    if not DB_TABLE:
        print("⚠️🛟 SQLite Draft пропущен — TABLE_Draft не задан")
        return "FAILED"

    if not sqlite_file:
        print("⚠️🛟 SQLite Draft пропущен — sqlite_file не задан в config.py")
        return "FAILED"

    if not data:
        print("⚠️🛟 SQLite Draft пропущен — нет данных")
        return "FAILED"

    print(f"\n{'=' * 60}")
    print(f"📝 ПОДГОТОВКА ДАННЫХ ДЛЯ SQLITE")
    print(f"{'=' * 60}")

    prepared_data = []

    for item in data:
        new_item = item.copy()

        normalized_brand = item.get('Бренд (нормализованный)') or item.get('normalized_brand')
        if normalized_brand:
            new_item['Бренд'] = normalized_brand
            new_item['normalized_brand'] = normalized_brand

        weight_volume = item.get('weight_volume')
        current_weight = item.get('Вес') or item.get('weight')
        if weight_volume and not current_weight:
            new_item['Вес'] = weight_volume

        uni_cat = item.get('uni_cat')
        if uni_cat:
            new_item['Категория'] = uni_cat

        current_gtin = item.get('GTIN') or item.get('gtin')
        article = item.get('Артикул') or item.get('article')
        if not current_gtin and article:
            new_item['GTIN'] = article

        prepared_data.append(new_item)

    if debug_mode:
        mode_label = "DEBUG (data_enricher)"
        data_for_sqlite = prepared_data
        print(f"🔧 Режим: {mode_label}")

    elif assoc_debug:
        mode_label = "ASSOC_DEBUG"
        technical_fields_to_hide = [
            '_data_quality', '_enriched_timestamp', 'brand_source',
            'cat_source', 'normalized_name', 'weight_volume', 'packaging',
            'Бренд (нормализованный)', 'normalized_name'
        ]

        filtered_data = []
        for item in prepared_data:
            new_item = {}
            for key, value in item.items():
                if key not in technical_fields_to_hide:
                    new_item[key] = value
            filtered_data.append(new_item)

        data_for_sqlite = filtered_data
        print(f"🔍 Режим: {mode_label}")

    else:
        mode_label = "PRODUCTION"
        technical_fields_to_hide = [
            '_data_quality', '_enriched_timestamp', 'brand_source',
            'cat_source', 'normalized_name', 'weight_volume', 'packaging',
            'code_cat', 'rule_id', 'confidence', 'retail_cat',
            'Бренд (нормализованный)', 'normalized_name', 'normalized_brand',
            'ID правила', 'Уверенность', 'Категория ритейлера'
        ]

        filtered_data = []
        for item in prepared_data:
            new_item = {}
            for key, value in item.items():
                if key not in technical_fields_to_hide:
                    new_item[key] = value
            filtered_data.append(new_item)

        data_for_sqlite = filtered_data
        print(f"📤 Режим: {mode_label}")

    print(f"📊 Записей для записи: {len(data_for_sqlite)}")

    path = sqlite_file

    try:
        folder = os.path.dirname(path)
        if folder:
            os.makedirs(folder, exist_ok=True)
            print(f"📁 Создана папка: {folder}")
    except Exception:
        pass

    try:
        print(f"\n🔗 Подключение к SQLite...")
        conn = sqlite3.connect(path)
        cur = conn.cursor()
        print(f"✅ Подключение успешно")

        cur.execute(f"""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='{DB_TABLE}'
        """)
        table_exists = cur.fetchone() is not None

        if table_exists:
            cur.execute(f'SELECT COUNT(*) FROM "{DB_TABLE}"')
            old_count = cur.fetchone()[0]
            print(f"📊 Таблица существует, записей: {old_count}")
        else:
            old_count = 0
            print(f"📊 Таблица не существует, будет создана")

        table_definition = f"""
            CREATE TABLE IF NOT EXISTS "{DB_TABLE}" (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data_date TEXT NOT NULL,
                data_time TEXT NOT NULL,
                agent TEXT,
                retailer TEXT,
                store_type TEXT,
                address TEXT,
                brand TEXT,
                product_name TEXT,
                price REAL,
                promo_price REAL,
                photo_url TEXT,
                product_url TEXT,
                rating REAL,
                volume TEXT,
                weight TEXT,
                stock TEXT,
                category TEXT,
                gtin TEXT,
                flag INTEGER DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        """

        if debug_mode or assoc_debug:
            table_definition += """,
                rule_id TEXT,
                confidence REAL,
                retail_category TEXT,
                normalized_brand TEXT
            """

            if debug_mode:
                table_definition += """,
                    code_cat INTEGER,
                    brand_source TEXT,
                    cat_source TEXT,
                    normalized_name TEXT,
                    weight_volume TEXT,
                    packaging TEXT,
                    data_quality TEXT,
                    enriched_timestamp TEXT
                """

        table_definition += ")"

        cur.execute(table_definition)

        if not table_exists:
            print(f"✅ Таблица создана")

        date_now = datetime.now().strftime("%Y-%m-%d")
        time_now = datetime.now().strftime("%H:%M:%S")
        agent = TelegramBot.get("MY_ID", "unknown")

        print(f"\n💾 Вставка {len(data_for_sqlite)} записей...")

        added = 0
        skipped = 0

        for row in data_for_sqlite:
            try:
                brand = row.get("Бренд") or row.get("brand") or ""
                product_name = row.get("Название продукта") or row.get("product_name") or ""

                category = row.get("Категория") or row.get("category") or row.get("uni_cat") or ""

                weight = row.get("Вес") or row.get("weight") or row.get("weight_volume") or ""

                gtin = row.get("GTIN") or row.get("gtin") or ""
                if not gtin:
                    gtin = row.get("Артикул") or row.get("article") or ""

                base_values = [
                    date_now,
                    time_now,
                    agent,
                    row.get("Сеть") or row.get("retailer") or "",
                    row.get("Тип магазина") or row.get("store_type") or "",
                    row.get("Адрес Торговой точки") or row.get("address") or "",
                    brand,
                    product_name,
                    row.get("Цена") or row.get("price") or 0,
                    row.get("Цена по акции") or row.get("promo_price") or 0,
                    row.get("Фото товара") or row.get("photo_url") or "",
                    row.get("Ссылка на страницу") or row.get("product_url") or "",
                    row.get("Рейтинг") or row.get("rating") or 0,
                    row.get("Объем") or row.get("volume") or "",
                    weight,
                    row.get("Остаток") or row.get("stock") or "",
                    category,
                    gtin,
                    0
                ]

                extra_values = []
                if debug_mode or assoc_debug:
                    rule_id = row.get("rule_id") or row.get("ID правила") or ""
                    confidence_val = row.get("confidence") or row.get("Уверенность") or 0.0
                    retail_category = row.get("retail_cat") or row.get("Категория ритейлера") or ""
                    normalized_brand_val = row.get("normalized_brand") or brand

                    try:
                        confidence_val = float(confidence_val)
                        if confidence_val > 1.0:
                            confidence_val = 1.0
                        elif confidence_val < 0.0:
                            confidence_val = 0.0
                    except Exception:
                        confidence_val = 0.0

                    extra_values.extend([rule_id, confidence_val, retail_category, normalized_brand_val])

                    if debug_mode:
                        extra_values.extend([
                            row.get("code_cat") or -1,
                            row.get("brand_source") or "",
                            row.get("cat_source") or "",
                            row.get("normalized_name") or "",
                            row.get("weight_volume") or "",
                            row.get("packaging") or "",
                            row.get("_data_quality") or "",
                            row.get("_enriched_timestamp") or ""
                        ])

                all_values = base_values + extra_values

                placeholders = ", ".join(["?"] * len(all_values))
                cur.execute(f"""
                    INSERT INTO "{DB_TABLE}" VALUES (NULL, {placeholders})
                """, all_values)

                added += 1

                if added % 50 == 0:
                    print(f"   ... записано {added} из {len(data_for_sqlite)}")

            except Exception as row_error:
                skipped += 1
                if skipped <= 3:
                    print(f"⚠️ Пропущена запись: {row_error}")

        conn.commit()
        conn.close()

        n = count_records(sqlite_file, table=DB_TABLE)
        new_added = n - old_count

        print(f"\n✅ SQLITE ({mode_label}): УСПЕШНО")
        print(f"📊 Статистика:")
        print(f"   • Было записей: {old_count}")
        print(f"   • Добавлено новых: {new_added}")
        print(f"   • Всего записей: {n}")
        print(f"   • Успешно вставлено: {added}")
        print(f"   • Пропущено: {skipped}")
        print(f"   📁 Файл: {path}")

        if new_added > 0:
            print(f"\n📊 НОРМАЛИЗАЦИЯ ДАННЫХ:")
            print(f"   • Данные нормализованы: да (бренд, вес, категория, GTIN)")

        SendTelegram(f"💾🛟 SQLite ({mode_label}): +{new_added} записей, всего {n}")
        return "SQLITE"

    except Exception as e:
        print(f"\n❌️🛟 SQLite Draft: ошибка записи\n{e}")
        SendTelegram(f"❌️🛟 SQLite Draft: ошибка записи\n{e}")
        try:
            conn.close()
        except Exception:
            pass
        print(f"{'=' * 60}")
        return "FAILED"

def write_excel(data, filename, sheet_name="Data", debug_mode=False, assoc_debug=False):
    """Дописывает данные в Excel. Набор полей зависит от debug_mode / assoc_debug."""
    if not data:
        print("⚠️ Нет данных для записи в Excel")
        return

    try:
        df = pd.DataFrame(data)

        print(f"\n{'=' * 60}")
        print(f"📝 ПОДГОТОВКА ДАННЫХ ДЛЯ EXCEL")
        print(f"{'=' * 60}")

        if 'Бренд (нормализованный)' in df.columns:
            mask = df['Бренд (нормализованный)'].notna()
            if mask.any():
                df.loc[mask, 'Бренд'] = df.loc[mask, 'Бренд (нормализованный)']
                normalized_count = mask.sum()
                print(f"🏷️  Нормализовано {normalized_count} брендов")

        if 'weight_volume' in df.columns:
            if 'Вес' not in df.columns:
                df['Вес'] = None
            mask = df['weight_volume'].notna() & (df['Вес'].isna() | (df['Вес'] == ''))
            if mask.any():
                df.loc[mask, 'Вес'] = df.loc[mask, 'weight_volume']
                weight_fixed = mask.sum()
                print(f"⚖️  Перенесено {weight_fixed} весов/объемов из weight_volume")

        if 'uni_cat' in df.columns:
            if 'Категория' not in df.columns:
                df['Категория'] = df['uni_cat']
            else:
                mask = df['uni_cat'].notna() & (df['Категория'].isna() | (df['Категория'] == ''))
                if mask.any():
                    df.loc[mask, 'Категория'] = df.loc[mask, 'uni_cat']
            cat_normalized = df['uni_cat'].notna().sum()
            print(f"📦  Нормализовано {cat_normalized} категорий из uni_cat")

        if 'Артикул' in df.columns:
            if 'GTIN' not in df.columns:
                df['GTIN'] = df['Артикул']
            else:
                mask = df['Артикул'].notna() & (df['GTIN'].isna() | (df['GTIN'] == ''))
                if mask.any():
                    df.loc[mask, 'GTIN'] = df.loc[mask, 'Артикул']
                    gtin_fixed = mask.sum()
                    print(f"🔢  Заполнено {gtin_fixed} GTIN из Артикулов")

        if debug_mode:
            mode_name = "DEBUG (data_enricher)"
            print(f"🔧 Режим: {mode_name} - все технические поля")
        elif assoc_debug:
            mode_name = "ASSOC_DEBUG"
            print(f"🔍 Режим: {mode_name} - поля для отладки ассоциаций")
        else:
            mode_name = "PRODUCTION"
            print(f"📤 Режим: {mode_name} - только production поля для КП")

        main_fields = [
            'Номер', 'Сеть', 'Тип магазина', 'Адрес Торговой точки',
            'Бренд', 'Название продукта', 'Цена', 'Цена по акции',
            'Фото товара', 'Ссылка на страницу', 'Рейтинг',
            'Объем', 'Вес', 'Остаток', 'Категория', 'GTIN'
        ]

        category_fields = ['ID правила', 'Уверенность', 'Категория ритейлера']

        technical_fields = [
            'uni_cat', 'code_cat', 'brand', 'brand_source',
            'normalized_name', 'weight_volume', 'packaging',
            '_data_quality', '_enriched_timestamp', 'cat_source',
            'Бренд (нормализованный)', 'rule_id', 'confidence', 'retail_cat'
        ]

        if debug_mode:
            all_fields = main_fields + technical_fields
            other_fields = [f for f in df.columns if f not in all_fields]
            all_fields = all_fields + other_fields

        elif assoc_debug:
            all_fields = main_fields + category_fields
            all_fields = [f for f in all_fields if f not in technical_fields]
            other_fields = [f for f in df.columns if f not in all_fields and f not in technical_fields]
            all_fields = all_fields + other_fields

        else:
            all_fields = main_fields.copy()
            technical_fields_to_exclude = [
                'uni_cat', 'code_cat', 'brand', 'brand_source',
                'normalized_name', 'weight_volume', 'packaging',
                '_data_quality', '_enriched_timestamp', 'cat_source',
                'Бренд (нормализованный)', 'rule_id', 'confidence',
                'retail_cat', 'ID правила', 'Уверенность', 'Категория ритейлера'
            ]
            all_fields = [f for f in all_fields if f not in technical_fields_to_exclude]

            other_fields = [f for f in df.columns
                            if f not in all_fields
                            and f not in technical_fields_to_exclude
                            and not f.startswith('_')
                            and not f.endswith('_source')
                            and not f.endswith('_timestamp')
                            and 'normalized' not in f.lower()]
            all_fields = all_fields + other_fields

        existing_fields = [field for field in all_fields if field in df.columns]

        seen = set()
        final_fields = [x for x in existing_fields if not (x in seen or seen.add(x))]

        print(f"📊 Колонки в {mode_name} режиме ({len(final_fields)}):")
        for i, col in enumerate(final_fields[:15], 1):
            print(f"   {i:2d}. {col}")
        if len(final_fields) > 15:
            print(f"   ... и еще {len(final_fields) - 15} колонок")

        df = df[final_fields]

        if debug_mode or assoc_debug:
            column_renames = {}

            if debug_mode:
                debug_renames = {
                    'code_cat': 'Код категории',
                    'brand_source': 'Источник бренда',
                    'cat_source': 'Источник категории',
                    'normalized_name': 'Нормализованное название',
                    'weight_volume': 'Вес/объем (тех.)',
                    'packaging': 'Упаковка',
                    '_data_quality': 'Качество данных',
                    '_enriched_timestamp': 'Время обогащения',
                    'Бренд (нормализованный)': 'Бренд (норм., тех.)',
                    'uni_cat': 'Категория (исходная)',
                    'rule_id': 'ID правила',
                    'confidence': 'Уверенность',
                    'retail_cat': 'Категория ритейлера'
                }

                for old_name, new_name in debug_renames.items():
                    if old_name in df.columns:
                        column_renames[old_name] = new_name

            elif assoc_debug:
                assoc_renames = {
                    'rule_id': 'ID правила',
                    'confidence': 'Уверенность',
                    'retail_cat': 'Категория ритейлера'
                }

                for old_name, new_name in assoc_renames.items():
                    if old_name in df.columns:
                        column_renames[old_name] = new_name

            if column_renames:
                df = df.rename(columns=column_renames)

        print(f"\n📊 СТАТИСТИКА ДАННЫХ:")

        essential_cols = ['Бренд', 'Вес', 'Категория', 'GTIN']
        for col in essential_cols:
            if col in df.columns:
                filled = df[col].notna().sum()
                total = len(df)
                percent = (filled / total * 100) if total > 0 else 0
                status = "✓" if percent > 80 else "⚠️"
                print(f"   {status} {col}: {filled}/{total} заполнено ({percent:.1f}%)")

        if 'Категория' in df.columns:
            categorized = df['Категория'].notna().sum()
            total = len(df)
            if total > 0:
                percent = categorized / total * 100
                unique_cats = df['Категория'].nunique()
                status = "✓" if percent > 80 else "⚠️"
                print(f"   {status} Категории: {categorized}/{total} ({percent:.1f}%), уникальных: {unique_cats}")

        print(f"\n💾 ЗАПИСЬ В EXCEL:")

        file_exists = os.path.exists(filename)

        if file_exists:
            print(f"📁 Файл существует: {filename}")

            try:
                existing_df = pd.read_excel(filename, sheet_name=sheet_name)
                old_count = len(existing_df)
                print(f"📊 В файле уже есть: {old_count} строк")

                if not existing_df.columns.equals(df.columns):
                    print("⚠️ Колонки не совпадают, пытаемся объединить...")

                    all_columns = list(dict.fromkeys(list(existing_df.columns) + list(df.columns)))

                    existing_df = existing_df.reindex(columns=all_columns)
                    df = df.reindex(columns=all_columns)

                    print(f"   Объединенные колонки: {len(all_columns)}")

                combined_df = pd.concat([existing_df, df], ignore_index=True, sort=False)
                new_count = len(combined_df)
                added_count = new_count - old_count

                print(f"📈 Объединяем: {old_count} старых + {len(df)} новых")
                print(f"📊 Итого будет: {new_count} строк (+{added_count})")

                with pd.ExcelWriter(filename, engine='openpyxl', mode='w') as writer:
                    combined_df.to_excel(writer, sheet_name=sheet_name, index=False)

                    if (debug_mode or assoc_debug) and len(data) > 0:
                        add_metadata_sheet(writer, data, debug_mode, assoc_debug, combined_df)

                print(f"✅ Данные успешно дописаны")

            except Exception as e:
                print(f"❌ Ошибка при чтении/объединении файла: {e}")
                print(f"📝 Создаем новый файл с текущими данными")

                with pd.ExcelWriter(filename, engine='openpyxl', mode='w') as writer:
                    df.to_excel(writer, sheet_name=sheet_name, index=False)

                    if (debug_mode or assoc_debug) and len(data) > 0:
                        add_metadata_sheet(writer, data, debug_mode, assoc_debug, df)

                print(f"📁 Создан новый файл")

        else:
            print(f"📁 Файл не существует, создаем новый: {filename}")

            with pd.ExcelWriter(filename, engine='openpyxl', mode='w') as writer:
                df.to_excel(writer, sheet_name=sheet_name, index=False)

                if (debug_mode or assoc_debug) and len(data) > 0:
                    add_metadata_sheet(writer, data, debug_mode, assoc_debug, df)

            print(f"📝 Создан новый файл с {len(df)} строками")

        try:
            final_df = pd.read_excel(filename, sheet_name=sheet_name)
            print(f"\n✅ ФАЙЛ УСПЕШНО СОХРАНЕН")
            print(f"📁 Файл: {filename}")
            print(f"📊 Итоговое количество строк: {len(final_df)}")
            print(f"📊 Итоговое количество колонок: {len(final_df.columns)}")

            cols_list = final_df.columns.tolist()
            print(f"📋 Колонки в файле ({len(cols_list)}):")
            for i, col in enumerate(cols_list[:20], 1):
                print(f"   {i:2d}. {col}")
            if len(cols_list) > 20:
                print(f"   ... и еще {len(cols_list) - 20} колонок")

        except Exception as e:
            print(f"⚠️ Не удалось проверить сохраненный файл: {e}")

        print(f"{'=' * 60}")

    except Exception as e:
        print(f"\n❌ ОШИБКА ЗАПИСИ В EXCEL: {e}")
        import traceback
        traceback.print_exc()
        print(f"{'=' * 60}")


def MakeSafeTableName(name: str, max_len: int = 80) -> str:
    """Имя без запрещённых символов для листа Excel, таблицы или файла."""
    if name is None:
        name = ""
    name = str(name).strip()

    safe = re.sub(r"[^0-9A-Za-zА-Яа-я._-]+", "_", name, flags=re.UNICODE)
    safe = re.sub(r"_+", "_", safe).strip("._- ")

    if not safe:
        safe = "table"

    if max_len and len(safe) > max_len:
        safe = safe[:max_len].rstrip("._- ")

    return safe


def MakeSafeFileName(name: str, max_len: int = 120) -> str:
    return MakeSafeTableName(name, max_len=max_len)

def SaveToExcel(*args, **kwargs):
    """Заглушка для main.py v4.20–4.22."""
    try:
        if 'WriteExcel' in globals():
            return globals()['WriteExcel'](*args, **kwargs)

        if 'ExportToExcel' in globals():
            return globals()['ExportToExcel'](*args, **kwargs)

        if 'save_xlsx' in globals():
            return globals()['save_xlsx'](*args, **kwargs)

        print("⚠️ SaveToExcel: реальная функция сохранения не найдена, пропуск.")

    except Exception as e:
        print(f"❌ SaveToExcel error: {e}")

def NormalizeText(text: str) -> str:
    """Текст для сравнения: NFKD, нижний регистр, без мусора и лишних пробелов."""
    if text is None:
        return ""

    try:
        s = str(text)
    except Exception:
        return ""

    s = unicodedata.normalize("NFKD", s)

    s = s.lower()

    s = re.sub(r"[^0-9a-zа-яё]+", " ", s, flags=re.IGNORECASE)

    s = re.sub(r"\s+", " ", s).strip()

    return s

def FormatElapsed(seconds: float) -> str:
    """Секунды -> 01:01:11 или 1д 02:03:04."""
    try:
        sec = int(seconds)
    except Exception:
        return "00:00:00"

    if sec < 0:
        sec = 0

    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    if days > 0:
        return f"{days}д {hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"


def FormatETA(seconds: float) -> str:
    """Оставшееся время -> 'ETA 00:01:05'."""
    try:
        if seconds is None:
            return "ETA ?"
        sec = int(float(seconds))
    except Exception:
        return "ETA ?"

    if sec <= 0:
        return "ETA 00:00:00"

    days, rem = divmod(sec, 86400)
    hours, rem = divmod(rem, 3600)
    minutes, seconds = divmod(rem, 60)

    if days > 0:
        return f"ETA {days}д {hours:02d}:{minutes:02d}:{seconds:02d}"
    else:
        return f"ETA {hours:02d}:{minutes:02d}:{seconds:02d}"

def MakeStatusBar(current: int, total: int, width: int = 20) -> str:
    """[████░░░░] 40% (4/10)"""
    try:
        cur = int(current)
        tot = int(total)
    except Exception:
        return "[????????????????????] ?% (0/?)"

    if tot <= 0:
        return "[░" * width + "] 0% (0/0)"

    if cur < 0:
        cur = 0
    if cur > tot:
        cur = tot

    pct = int((cur / tot) * 100)
    filled = int((cur / tot) * width)
    empty = width - filled

    bar = "█" * filled + "░" * empty
    return f"[{bar}] {pct:3d}% ({cur}/{tot})"

def ClearStatusBar() -> None:
    """Стирает строку прогресса в консоли."""
    try:
        print("\r" + " " * 140 + "\r", end="", flush=True)
    except Exception:
        pass


try:
    from colorama import Fore as _Fore, Style as _Style
except Exception:
    class _Fore:
        BLACK = RED = GREEN = YELLOW = BLUE = MAGENTA = CYAN = WHITE = RESET = ""

    class _Style:
        DIM = NORMAL = BRIGHT = RESET_ALL = ""

Fore = _Fore
Style = _Style

