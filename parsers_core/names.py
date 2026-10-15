# -*- coding: utf-8 -*-
from urllib.parse import urlsplit

_warned = set()


def site_key(url):
    """'https://www.Letu.ru/' и 'letu.ru' -> 'letu.ru'."""
    s = (url or "").strip().lower()
    if "://" not in s:
        s = "http://" + s
    host = urlsplit(s).netloc
    return host[4:] if host.startswith("www.") else host


def retail_name(site_url):
    """Название сети из config.parsers. Ключ сравнивается без схемы, www и слэша. Нет записи — домен."""
    import config
    key = site_key(site_url)
    for url, name in (getattr(config, "parsers", None) or {}).items():
        if name and site_key(url) == key:
            return name
    if key not in _warned:
        _warned.add(key)
        print(f"В config.parsers нет названия для {site_url}, в выгрузке будет '{key}'")
    return key
