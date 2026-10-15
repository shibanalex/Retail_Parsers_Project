# -*- coding: utf-8 -*-
import configparser
import os
import random
import time

CORE_DIR = os.path.dirname(os.path.abspath(__file__))
CFG_PATH = os.path.join(CORE_DIR, "share_parsers.cfg")

DEFAULTS = {"min_delay": 1.0, "max_delay": 3.0, "browser_size": "0"}


def parser_settings(section="", cfg_path=CFG_PATH):
    """Настройки из share_parsers.cfg: сначала [BROWSER], поверх — секция парсера."""
    result = dict(DEFAULTS)
    if not os.path.exists(cfg_path):
        return result
    cp = configparser.ConfigParser(inline_comment_prefixes=(";", "#"))
    try:
        cp.read(cfg_path, encoding="utf-8-sig")
    except (configparser.Error, UnicodeDecodeError):
        return result
    for sect in ("BROWSER", section.upper() if section else ""):
        if not sect or not cp.has_section(sect):
            continue
        for key in ("min_delay", "max_delay"):
            if cp.has_option(sect, key):
                try:
                    result[key] = cp.getfloat(sect, key)
                except ValueError:
                    pass
        if cp.has_option(sect, "browser_size"):
            result["browser_size"] = cp.get(sect, "browser_size").strip()
    if result["max_delay"] < result["min_delay"]:
        result["max_delay"] = result["min_delay"]
    return result


def parse_window_size(value):
    """browser_size: -1 — headless, 0 — 1920x1080, иначе ШxВ."""
    v = (str(value) if value is not None else "0").strip().lower()
    for sep in ("х", ",", "*", "×"):
        v = v.replace(sep, "x")
    if v == "-1":
        return "headless", None
    if v in ("", "0") or "x" not in v:
        return "default", (1920, 1080)
    try:
        w, h = (int(p) for p in v.split("x")[:2])
    except ValueError:
        return "default", (1920, 1080)
    return "explicit", (w, h)


def smart_sleep(source=None, fallback=None, section=""):
    """Пауза из драйвера (custom_min/max_delay). fallback — только если у драйвера их нет."""
    if source is not None and hasattr(source, "custom_min_delay"):
        lo = getattr(source, "custom_min_delay", DEFAULTS["min_delay"])
        hi = getattr(source, "custom_max_delay", DEFAULTS["max_delay"])
    elif isinstance(source, (tuple, list)) and len(source) == 2:
        lo, hi = source
    elif fallback is not None:
        time.sleep(fallback)
        return
    else:
        s = parser_settings(section)
        lo, hi = s["min_delay"], s["max_delay"]
    time.sleep(random.uniform(lo, max(lo, hi)))


def sleep_between(min_val=0.5, max_val=1.5):
    time.sleep(random.uniform(min_val, max(min_val, max_val)))
