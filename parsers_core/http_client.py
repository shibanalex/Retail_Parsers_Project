# -*- coding: utf-8 -*-
import time

import requests

from .exceptions import AuthLost, RateLimited

DEFAULT_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36")


class HttpClient:
    """requests с реакциями по ТЗ: 429 — повтор с паузой, 401/403/404 — исключение, 500 отдаётся как есть."""

    def __init__(self, retail, session=None, proxy=None, timeout=20,
                 max_429_attempts=4, backoff_start=5.0, headers=None,
                 soft_404_marker=None):
        self.retail = retail
        self.session = session or requests.Session()
        self.session.headers.setdefault("User-Agent", DEFAULT_UA)
        self.session.headers.setdefault("Accept-Language", "ru-RU,ru;q=0.9")
        if headers:
            self.session.headers.update(headers)
        if proxy:
            self.session.proxies.update(proxy)
        self.timeout = timeout
        self.max_429_attempts = max_429_attempts
        self.backoff_start = backoff_start
        self.soft_404_marker = soft_404_marker
        self.last_status = None

    def request(self, method, url, **kw):
        kw.setdefault("timeout", self.timeout)
        delay = self.backoff_start
        for attempt in range(self.max_429_attempts):
            r = self.session.request(method, url, **kw)
            self.last_status = r.status_code
            if r.status_code != 429:
                break
            if attempt < self.max_429_attempts - 1:
                time.sleep(delay)
                delay *= 2

        code = r.status_code
        if code == 401:
            raise AuthLost(f"{self.retail}: сессия не принята (401) на {url}")
        if code == 429:
            raise RateLimited(f"{self.retail}: ограничение частоты запросов (429) на {url}")
        if code == 403:
            raise RuntimeError("Ошибка 403")
        if code == 404:
            # Некоторые сайты отдают 404 на пустой поиск — это не ошибка
            if not (self.soft_404_marker and self.soft_404_marker in r.text):
                raise RuntimeError("Ошибка 404")
        return r

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def close(self):
        try:
            self.session.close()
        except Exception:
            pass
