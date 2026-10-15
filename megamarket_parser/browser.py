# -*- coding: utf-8 -*-
import os

from parsers_core.dp_browser import get_dp_page


def get_browser(parser_cfg_name="MEGAMARKET"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    page = get_dp_page(base_dir, "megamarket_profile", parser_cfg_name,
                       extra_args=("--disable-gpu", "--lang=ru-RU,ru"), use_cfg_size=False)
    page._product_cache = {}
    page.current_location_id = "50"
    return page


def init_browser():
    return get_browser("MEGAMARKET")
