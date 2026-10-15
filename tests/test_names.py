# -*- coding: utf-8 -*-
import glob
import os
import re
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import config
from parsers_core.names import retail_name, site_key


@pytest.mark.parametrize("url", ["https://www.Letu.ru/", "letu.ru", "http://letu.ru", "https://letu.ru"])
def test_site_key(url):
    assert site_key(url) == "letu.ru"


def test_retail_name_from_messy_config_keys(monkeypatch):
    monkeypatch.setattr(config, "parsers", {
        "https://Luding.ru": "Luding",
        "www.wildberries.ru": "Wildberries",
        "https://www.letu.ru/": "Лэтуаль",
    }, raising=False)
    assert retail_name("https://luding.ru/") == "Luding"
    assert retail_name("https://www.wildberries.ru/") == "Wildberries"
    assert retail_name("https://letu.ru/") == "Лэтуаль"


def test_retail_name_falls_back_to_domain(monkeypatch):
    monkeypatch.setattr(config, "parsers", {}, raising=False)
    assert retail_name("https://www.tvoydom.ru/") == "tvoydom.ru"


def test_no_hardcoded_shop_names():
    bad = []
    pattern = re.compile(r'def (main|get_all_data)\([^)]*shop_name\s*=\s*["\']')
    for path in glob.glob(os.path.join(ROOT, "*_parser", "*.py")):
        if pattern.search(open(path, encoding="utf-8").read()):
            bad.append(os.path.relpath(path, ROOT))
    assert not bad, bad
