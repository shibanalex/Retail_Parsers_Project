# ============================================================
# parsers_core/proxy_utils.py
#
# ver 3.02-proxy (2026-02-05)
# ------------------------------------------------------------
# CHANGELOG:
#  - Перевели ручной выключатель прокси на busy = -1 (MANUAL OFF)
#  - Теперь:
#       busy =  0  свободен
#       busy =  1  занят (TTL освободит)
#       busy = -1  выключен вручную (никогда не используется, кодом не трогается)
#  - Убрали фильтр priority != -1 как "выключатель" (priority остаётся статистикой/весом)
#  - Добавили полную совместимость со старым интерфейсом:
#       ProxyPool, rotate_proxy, get_proxy_list, get_proxy_manager, should_use_proxy,
#       quick_proxy_check, check_proxy_health, get_healthy_proxy, ensure_proxy_healthy, __all__
# ============================================================

import os
import sqlite3
import random
import time
from datetime import datetime, timedelta
from typing import Optional, Dict, Tuple

import requests


# ============================================================
# CONSTANTS (KP)
# ============================================================

BUSY_TTL_SECONDS = 300        # ⏱️ 5 минут — автоосвобождение busy=1
PROXY_TEST_TIMEOUT = 15


# ============================================================
# HELPERS
# ============================================================

def now_iso() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def iso_to_dt(val: str) -> Optional[datetime]:
    try:
        return datetime.strptime(val, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


# ============================================================
# PROTOCOL HELPERS (оставлены для совместимости)
# ============================================================

def detect_protocol_by_port(port):
    if not isinstance(port, (int, str)):
        return 'http'
    try:
        port = int(port)
    except (ValueError, TypeError):
        return 'http'

    PROTOCOL_PORTS = {
        80: 'http', 8080: 'http', 3128: 'http', 8888: 'http', 8081: 'http',
        8000: 'http', 8008: 'http', 8010: 'http', 8880: 'http', 8088: 'http',
        8090: 'http',

        443: 'https', 8443: 'https', 9443: 'https', 10443: 'https', 8444: 'https',

        1080: 'socks4', 4145: 'socks4', 5741: 'socks4', 5742: 'socks4',

        1081: 'socks5', 9050: 'socks5', 9150: 'socks5', 9051: 'socks5',
        9052: 'socks5', 9053: 'socks5', 9054: 'socks5', 9055: 'socks5',
        10808: 'socks5', 10809: 'socks5', 10810: 'socks5',

        465: 'ssl', 993: 'ssl', 995: 'ssl',

        3129: 'transparent', 3130: 'transparent', 3131: 'transparent',

        4444: 'elite', 5555: 'elite', 6666: 'elite', 7777: 'elite',
        9999: 'elite', 10000: 'elite',

        8118: 'http', 8123: 'http', 8889: 'http', 8899: 'http',
        9000: 'http', 9001: 'http',
    }

    return PROTOCOL_PORTS.get(port, 'http')


def get_protocol_display(protocol):
    protocol_displays = {
        'http': ('HTTP', '🌐'),
        'https': ('HTTPS', '🔒'),
        'socks4': ('SOCKS4', '🧦4'),
        'socks5': ('SOCKS5', '🧦5'),
        'ssl': ('SSL', '🔐'),
        'transparent': ('TRANSP', '👁️'),
        'elite': ('ELITE', '🎭'),
        'unknown': ('UNKN', '❓')
    }
    return protocol_displays.get((protocol or 'http').lower(), ('HTTP', '🌐'))


def detect_protocol_full(proxy_data):
    if proxy_data.get('protocol'):
        protocol = str(proxy_data['protocol']).lower()
        if protocol in ['http', 'https', 'socks4', 'socks5', 'ssl', 'transparent', 'elite']:
            return protocol

    port = proxy_data.get('port')
    if port:
        protocol = detect_protocol_by_port(port)
        if protocol != 'http':
            return protocol

    note = (proxy_data.get('note') or '').lower()
    if note:
        if 'socks5' in note or 's5' in note or 'socks 5' in note:
            return 'socks5'
        if 'socks4' in note or 's4' in note or 'socks 4' in note:
            return 'socks4'
        if 'https' in note or 'ssl' in note or 'tls' in note:
            return 'https'
        if 'transparent' in note:
            return 'transparent'
        if 'elite' in note or 'anonymous' in note:
            return 'elite'
        if 'http' in note:
            return 'http'

    return 'http'


# ============================================================
# MAIN CLASS
# ============================================================

class ProxyManager:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=30)

    # --------------------------------------------------------
    # BUSY TTL CLEANUP (only busy=1)
    # --------------------------------------------------------

    def _release_stale_busy(self):
        """
        Освобождает прокси, которые зависли в busy=1 дольше TTL.
        busy=-1 (manual off) не трогаем.
        """
        cutoff = datetime.now() - timedelta(seconds=BUSY_TTL_SECONDS)

        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                SELECT id, last_run
                FROM proxys
                WHERE busy = 1
            """)
            rows = cur.fetchall()

            for pid, last_run in rows:
                dt = iso_to_dt(last_run)
                if not dt or dt < cutoff:
                    cur.execute("""
                        UPDATE proxys
                        SET busy = 0
                        WHERE id = ?
                          AND busy = 1
                    """, (pid,))
            con.commit()

    # --------------------------------------------------------
    # GET NEXT FREE PROXY (busy=0 only)
    # --------------------------------------------------------

    def get_next_free_proxy(self, exclude_current=False):
        return self.get_next_proxy()

    def get_next_proxy(self) -> Optional[Dict]:
        """
        Берем СВОБОДНЫЙ прокси:
          busy=0  подходит
          busy=1  занят
          busy=-1 отключен вручную (никогда не берём)
        """
        self._release_stale_busy()

        with self._connect() as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("""
                SELECT *
                FROM proxys
                WHERE busy = 0
                ORDER BY
                    priority DESC,
                    (count = 0) ASC,
                    fall ASC,
                    count ASC,
                    RANDOM()
            """)
            rows = cur.fetchall()

        if not rows:
            return None

        return dict(random.choice(rows))

    # --------------------------------------------------------
    # requests.proxies builder
    # --------------------------------------------------------

    def build_requests_proxy(self, row: Dict) -> Dict:
        ip = row.get("ip")
        port = row.get("port")
        user = row.get("user")
        psw = row.get("psw")
        socks = row.get("socks")

        # если socks пустой/0 — считаем SOCKS5 (ваша логика)
        scheme = "socks4" if socks == 4 else "socks5"
        auth = f"{user}:{psw}@" if user and psw else ""
        proxy_url = f"{scheme}://{auth}{ip}:{port}"

        return {"http": proxy_url, "https": proxy_url}

    def get_proxy_display_info(self, proxy_row):
        protocol = proxy_row.get('protocol', 'http')
        protocol_name, protocol_icon = get_protocol_display(protocol)
        info = f"🆔{proxy_row['id']} {protocol_icon}{protocol_name} {proxy_row['ip']}:{proxy_row['port']}"
        if proxy_row.get('note'):
            info += f" [{proxy_row['note']}]"
        return info

    # --------------------------------------------------------
    # BUSY CONTROL (protect busy=-1)
    # --------------------------------------------------------

    def mark_busy(self, proxy_id: int):
        """
        busy=1 только если proxy не выключен вручную (busy!=-1)
        """
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                UPDATE proxys
                SET busy = 1,
                    last_run = ?
                WHERE id = ?
                  AND busy != -1
            """, (now_iso(), proxy_id))
            con.commit()

    def mark_free(self, proxy_id: int):
        """
        busy=0 только если proxy не выключен вручную (busy!=-1)
        """
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("""
                UPDATE proxys
                SET busy = 0
                WHERE id = ?
                  AND busy != -1
            """, (proxy_id,))
            con.commit()

    # --------------------------------------------------------
    # STATS
    # --------------------------------------------------------

    def mark_attempt(self, proxy_id: int, success: bool):
        with self._connect() as con:
            cur = con.cursor()
            if success:
                cur.execute("""
                    UPDATE proxys
                    SET last_run = ?,
                        count = count + 1
                    WHERE id = ?
                """, (now_iso(), proxy_id))
            else:
                cur.execute("""
                    UPDATE proxys
                    SET last_run = ?,
                        count = count + 1,
                        fall  = fall  + 1
                    WHERE id = ?
                """, (now_iso(), proxy_id))
            con.commit()

    # --------------------------------------------------------
    # TEST PROXY
    # --------------------------------------------------------

    def test_proxy(self, row: Dict,
                   test_url: str = "https://httpbin.org/ip",
                   timeout: int = PROXY_TEST_TIMEOUT) -> bool:
        proxies = self.build_requests_proxy(row)
        try:
            r = requests.get(test_url, proxies=proxies, timeout=timeout)
            r.raise_for_status()
            return True
        except Exception:
            return False

    def quick_check(self, proxy_id: int, test_url="https://google.com", timeout=5) -> bool:
        try:
            with self._connect() as con:
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                cur.execute("SELECT * FROM proxys WHERE id = ?", (proxy_id,))
                row = cur.fetchone()
            if not row:
                return False
            return quick_proxy_check(dict(row), test_url=test_url, timeout=timeout)
        except Exception:
            return False

    # --------------------------------------------------------
    # FULL CYCLE GET WORKING PROXY
    # --------------------------------------------------------

    def get_working_proxy(self, test_url: str = "https://httpbin.org/ip") -> Optional[Dict]:
        tried = set()

        while True:
            row = self.get_next_proxy()
            if not row:
                return None

            pid = row.get("id")
            if pid in tried:
                return None
            tried.add(pid)

            # блокируем
            self.mark_busy(pid)

            ok = False
            try:
                ok = self.test_proxy(row, test_url=test_url)
                self.mark_attempt(pid, ok)
            except Exception:
                self.mark_attempt(pid, False)

            if ok:
                return row

            # не подошёл — освобождаем
            self.mark_free(pid)

    # --------------------------------------------------------
    # PRIORITY RECALC (optional)
    # --------------------------------------------------------

    def recalc_priorities(self):
        with self._connect() as con:
            cur = con.cursor()
            cur.execute("SELECT id, priority, fall, count FROM proxys")
            rows = cur.fetchall()

            for pid, prio, fall, cnt in rows:
                if not cnt or int(cnt) == 0:
                    continue
                if fall == 0:
                    prio = (prio or 0) + 1
                else:
                    prio = (prio or 0) - 1
                prio = max(0, min(10, prio))
                cur.execute("UPDATE proxys SET priority = ? WHERE id = ?", (prio, pid))
            con.commit()


# ============================================================
# COMPAT LAYER FUNCTIONS
# ============================================================

def should_use_proxy(proxy_path: str) -> Tuple[bool, str]:
    if not proxy_path:
        return False, ""
    if not os.path.exists(proxy_path):
        return False, ""
    try:
        conn = sqlite3.connect(proxy_path)
        conn.close()
        return True, proxy_path
    except Exception:
        return True, proxy_path


def rotate_proxy(db_path: str = None) -> Optional[Dict]:
    """
    Упрощенная функция ротации прокси.
    Совместимость: если db_path None — пробуем достать из config_loader или config.py
    """
    if db_path is None:
        try:
            from .config_loader import cfg
            db_path = cfg.get("", "sqlite_proxy_db", "proxys.sqlite")
        except Exception:
            try:
                from config import sqlite_proxy_db
                db_path = sqlite_proxy_db
            except Exception:
                db_path = "proxys.sqlite"

    try:
        pm = ProxyManager(db_path)
        return pm.get_working_proxy()
    except Exception as e:
        print(f"⚠️  rotate_proxy error: {e}")
        return None


def validate_proxy(proxy_dict: Dict, timeout: int = 10) -> bool:
    if not proxy_dict:
        return False
    try:
        tmp = ProxyManager(":memory:")
        return tmp.test_proxy(proxy_dict, timeout=timeout)
    except Exception:
        return False


def get_proxy_list(db_path: str = None) -> list:
    if db_path is None:
        try:
            from .config_loader import cfg
            db_path = cfg.get("", "sqlite_proxy_db", "proxys.sqlite")
        except Exception:
            try:
                from config import sqlite_proxy_db
                db_path = sqlite_proxy_db
            except Exception:
                return []

    try:
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM proxys")
        rows = cur.fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"⚠️ get_proxy_list error: {e}")
        return []


def get_proxy_manager(db_path: str = None) -> ProxyManager:
    if not hasattr(get_proxy_manager, "_instance"):
        if db_path is None:
            try:
                from .config_loader import cfg
                db_path = cfg.get("", "sqlite_proxy_db", "proxys.sqlite")
            except Exception:
                try:
                    from config import sqlite_proxy_db
                    db_path = sqlite_proxy_db
                except Exception:
                    db_path = "proxys.sqlite"
        get_proxy_manager._instance = ProxyManager(db_path)

    return get_proxy_manager._instance


# ============================================================
# HEALTH CHECK (compat)
# ============================================================

def quick_proxy_check(proxy_dict: Dict,
                      test_url: str = "https://google.com",
                      timeout: int = 5) -> bool:
    if not proxy_dict:
        return False
    try:
        temp_manager = ProxyManager(":memory:")
        proxies = temp_manager.build_requests_proxy(proxy_dict)
        r = requests.get(test_url, proxies=proxies, timeout=timeout,
                         headers={'User-Agent': 'Mozilla/5.0', 'Accept': 'text/html'})
        return r.status_code in (200, 301, 302)
    except Exception:
        return False


def check_proxy_health(pm: ProxyManager, proxy_id: int,
                       test_url: str = "https://httpbin.org/ip",
                       timeout: int = 10) -> Tuple[bool, str, int]:
    if not pm or not proxy_id:
        return False, "Нет ProxyManager или proxy_id", 0

    try:
        with pm._connect() as con:
            con.row_factory = sqlite3.Row
            cur = con.cursor()
            cur.execute("SELECT * FROM proxys WHERE id = ?", (proxy_id,))
            row = cur.fetchone()

        if not row:
            return False, f"Прокси #{proxy_id} не найден", 0

        proxy_dict = dict(row)
        proxies = pm.build_requests_proxy(proxy_dict)

        t0 = time.time()
        try:
            resp = requests.get(test_url, proxies=proxies, timeout=timeout,
                                headers={'User-Agent': 'Mozilla/5.0'})
            elapsed_ms = int((time.time() - t0) * 1000)

            if resp.status_code == 200:
                # optional: если колонки нет — просто пропустим
                try:
                    with pm._connect() as con:
                        cur = con.cursor()
                        cur.execute("""
                            UPDATE proxys
                            SET last_response_time = ?
                            WHERE id = ?
                        """, (elapsed_ms, proxy_id))
                        con.commit()
                except Exception:
                    pass

                return True, "Успешно", elapsed_ms

            return False, f"HTTP {resp.status_code}", elapsed_ms

        except requests.exceptions.Timeout:
            return False, f"Таймаут ({timeout} сек)", int((time.time() - t0) * 1000)
        except requests.exceptions.ConnectionError:
            return False, "Ошибка соединения", int((time.time() - t0) * 1000)
        except Exception as e:
            return False, f"Ошибка: {str(e)[:120]}", int((time.time() - t0) * 1000)

    except Exception as e:
        return False, f"Ошибка проверки: {str(e)[:120]}", 0


def get_healthy_proxy(pm: ProxyManager,
                      max_attempts: int = 3,
                      min_response_time: int = 5000,
                      test_url: str = "https://httpbin.org/ip") -> Tuple[Optional[Dict], str]:
    attempts = 0

    while attempts < max_attempts:
        attempts += 1

        proxy = pm.get_next_proxy()
        if not proxy:
            return None, "Нет доступных прокси"

        proxy_id = proxy.get("id")
        print(f"🔄 Проверка прокси #{proxy_id} ({attempts}/{max_attempts})...")

        ok, reason, ms = check_proxy_health(pm, proxy_id, test_url=test_url, timeout=5)

        if ok and ms <= min_response_time:
            pm.mark_busy(proxy_id)
            return proxy, ""

        # если не ок — учитываем как fail и освобождаем
        try:
            pm.mark_attempt(proxy_id, success=False)
        except Exception:
            pass
        pm.mark_free(proxy_id)

    return None, f"Не найдено рабочих прокси после {max_attempts} попыток"


def ensure_proxy_healthy(pm: ProxyManager, proxy_id: int, target_site: str = None) -> Tuple[bool, str]:
    ok, reason, ms = check_proxy_health(pm, proxy_id, timeout=5)
    if not ok:
        return False, f"Базовая проверка: {reason}"

    if target_site:
        try:
            with pm._connect() as con:
                con.row_factory = sqlite3.Row
                cur = con.cursor()
                cur.execute("SELECT * FROM proxys WHERE id = ?", (proxy_id,))
                row = cur.fetchone()
            if not row:
                return False, "Прокси не найден"
            proxy_dict = dict(row)
            proxies = pm.build_requests_proxy(proxy_dict)

            r = requests.get(target_site, proxies=proxies, timeout=5,
                             headers={'User-Agent': 'Mozilla/5.0'})
            if r.status_code == 403:
                return False, "Антибот (403)"
            if r.status_code >= 400:
                return False, f"HTTP {r.status_code}"
        except Exception as e:
            return False, f"Ошибка на целевом сайте: {str(e)[:120]}"

    return True, f"OK ({ms} ms)"


# ============================================================
# ProxyPool (REQUIRED BY IMPORTS)
# ============================================================

class ProxyPool:
    """
    Упрощенный пул прокси для совместимости со старым кодом.
    """
    def __init__(self, proxies: list = None):
        self.proxies = proxies or []
        self.good_proxies = self.proxies.copy()
        self.bad_proxies = []

    def get_random_proxy(self) -> Optional[Dict]:
        if not self.good_proxies:
            return None
        return random.choice(self.good_proxies)

    def validate_proxy(self, proxy: Dict, timeout: int = 5) -> bool:
        return validate_proxy(proxy, timeout)

    def refresh(self, db_path: str = None):
        self.proxies = get_proxy_list(db_path=db_path)
        self.good_proxies = self.proxies.copy()


# ============================================================
# EXPORTS
# ============================================================

__all__ = [
    'ProxyManager',
    'ProxyPool',
    'rotate_proxy',
    'validate_proxy',
    'get_proxy_list',
    'get_proxy_manager',
    'should_use_proxy',
    'check_proxy_health',
    'get_healthy_proxy',
    'quick_proxy_check',
    'ensure_proxy_healthy',
    'detect_protocol_by_port',
    'detect_protocol_full',
    'get_protocol_display',
]
