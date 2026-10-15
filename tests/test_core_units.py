# -*- coding: utf-8 -*-
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from parsers_core import normalize, rows, settings
from parsers_core.exceptions import AuthLost, RateLimited
from parsers_core.http_client import HttpClient


@pytest.mark.parametrize("raw,expected", [
    ("1 299,00 ₽", 1299.0),
    ("79,90 руб", 79.9),
    ("289.99", 289.99),
    ("1,299.50", 1299.5),
    ("от 99", 99.0),
    (149, 149.0),
    (0, None),
    ("", None),
    ("бесплатно", None),
    (None, None),
])
def test_to_price(raw, expected):
    assert normalize.to_price(raw) == expected


@pytest.mark.parametrize("name,expected", [
    ("Коньяк Ной Араспел 7 лет 0,5 л в подарочной упаковке",
     ("Коньяк Ной Араспел 7 лет в подарочной упаковке", "0.5 л", "")),
    ("Молоко 2.5%, 900 г", ("Молоко 2.5%", "", "900 г")),
    ("Пиво светлое 4.5%", ("Пиво светлое 4.5%", "", "")),
    ("Вода 5 л", ("Вода", "5 л", "")),
    ("Сыр 1,4 кг", ("Сыр", "", "1.4 кг")),
])
def test_split_name_measure(name, expected):
    assert normalize.split_name_measure(name) == expected


def test_split_regular_promo():
    assert normalize.split_regular_promo(289.99, 389.99) == (389.99, 289.99)
    assert normalize.split_regular_promo(139.99, None) == (139.99, 0.0)
    assert normalize.split_regular_promo(100.0, 90.0) == (100.0, 0.0)


def test_make_row_keys_and_rejects():
    r = rows.make_row("Сеть", "Москва", "Товар", "149.9", stock=True)
    assert tuple(k for k in rows.ROW_KEYS) == tuple(k for k in r if k in rows.ROW_KEYS)
    assert r["Цена"] == 149.9 and r["Остаток"] == "1"
    assert rows.make_row("Сеть", "Москва", "Товар", None) is None
    assert rows.make_row("Сеть", "Москва", "Товар", 0) is None
    assert rows.make_row("Сеть", "Москва", "  ", 10) is None
    r2 = rows.make_row("С", "М", "Т", 1, extra={"_x": 1, "a_source": 2, "Артикул": "123"})
    assert "Артикул" in r2 and "_x" not in r2 and "a_source" not in r2


def test_number_and_uniform():
    data = [{"a": 1}, {"b": 2}]
    rows.uniform_keys(data)
    rows.number_rows(data)
    assert data[0]["b"] == "" and data[1]["a"] == "" and data[1]["Номер"] == 2


def test_parser_settings_override(tmp_path):
    cfg = tmp_path / "s.cfg"
    cfg.write_text("[BROWSER]\nmin_delay = 1.0\nmax_delay = 3.0\nbrowser_size = 375x812\n\n"
                   "[MYSHOP]\nmin_delay = 2.5\nbrowser_size = 0\n", encoding="utf-8")
    s = settings.parser_settings("myshop", cfg_path=str(cfg))
    assert s == {"min_delay": 2.5, "max_delay": 3.0, "browser_size": "0"}
    base = settings.parser_settings("", cfg_path=str(cfg))
    assert base["browser_size"] == "375x812"


def test_parser_settings_bom_and_missing(tmp_path):
    cfg = tmp_path / "bom.cfg"
    cfg.write_bytes("﻿[BROWSER]\nmin_delay = 0.5\n".encode("utf-8"))
    assert settings.parser_settings("", cfg_path=str(cfg))["min_delay"] == 0.5
    assert settings.parser_settings("", cfg_path=str(tmp_path / "nope.cfg")) == settings.DEFAULTS


@pytest.mark.parametrize("value,expected", [
    ("-1", ("headless", None)),
    ("0", ("default", (1920, 1080))),
    ("1366x768", ("explicit", (1366, 768))),
    ("1366х768", ("explicit", (1366, 768))),
    ("1280,900", ("explicit", (1280, 900))),
    ("мусор", ("default", (1920, 1080))),
])
def test_parse_window_size(value, expected):
    assert settings.parse_window_size(value) == expected


class _Resp:
    def __init__(self, code, text=""):
        self.status_code = code
        self.text = text


class _Session:
    def __init__(self, codes):
        self.codes = list(codes)
        self.headers = {}
        self.proxies = {}
        self.calls = 0

    def request(self, method, url, **kw):
        self.calls += 1
        code = self.codes.pop(0)
        return _Resp(code, "<html>schema.org/Product</html>" if code == 404 else "")


def _client(codes, **kw):
    return HttpClient("Тест", session=_Session(codes), backoff_start=0.0, **kw)


def test_http_ok_and_status():
    c = _client([200])
    assert c.get("u").status_code == 200 and c.last_status == 200


def test_http_429_backoff_then_ok():
    c = _client([429, 429, 200])
    assert c.get("u").status_code == 200 and c.session.calls == 3


def test_http_429_exhausted_raises():
    with pytest.raises(RateLimited):
        _client([429] * 4).get("u")


def test_http_401_403_404():
    with pytest.raises(AuthLost):
        _client([401]).get("u")
    with pytest.raises(RuntimeError, match="403"):
        _client([403]).get("u")
    with pytest.raises(RuntimeError, match="404"):
        _client([404]).get("u")


def test_http_soft_404_allowed():
    c = _client([404], soft_404_marker="schema.org/Product")
    assert c.get("u").status_code == 404


def test_http_500_returned_not_raised():
    assert _client([500]).get("u").status_code == 500


def test_build_options_window_and_profile(tmp_path):
    from parsers_core import uc_browser
    opts = uc_browser.build_options({"browser_size": "-1"}, profile_dir=str(tmp_path))
    args = opts.arguments
    assert "--headless=new" in args
    assert f"--user-data-dir={tmp_path}" in args


def test_profile_env_override(monkeypatch, tmp_path):
    from parsers_core import uc_browser
    monkeypatch.setenv(uc_browser.PROFILE_ENV, str(tmp_path / "x"))
    assert uc_browser._resolve_profile("/base", "shop_profile") == str(tmp_path / "x")
    monkeypatch.delenv(uc_browser.PROFILE_ENV)
    assert uc_browser._resolve_profile("/base", "shop_profile") == os.path.join("/base", "shop_profile")
    assert uc_browser._resolve_profile("/base", "") is None


def test_clean_profile_locks(tmp_path):
    from parsers_core import uc_browser
    (tmp_path / "Default").mkdir()
    lock = tmp_path / "Default" / "SingletonLock"
    lock.write_text("x")
    keep = tmp_path / "Default" / "Cookies"
    keep.write_text("x")
    uc_browser._clean_profile_locks(str(tmp_path))
    assert not lock.exists() and keep.exists()
