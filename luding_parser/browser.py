# -*- coding: utf-8 -*-
import os

from parsers_core.uc_browser import get_browser as _get_browser


def get_browser(parser_cfg_name="LUDING"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    driver = _get_browser(base_dir, "luding_profile", parser_cfg_name,
                          extra_args=("--disable-gpu", "--lang=ru-RU,ru"), window_size="1920x1080")
    driver.implicitly_wait(2)
    return driver


def init_browser():
    return get_browser("LUDING")
