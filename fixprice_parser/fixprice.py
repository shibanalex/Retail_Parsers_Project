# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from parsers_core import katoteka
from parsers_core.names import retail_name

SITE_URL = "https://fix-price.com/"
SLUG = "fix"
# Один каталог на всю страну, цена без скидок
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "debug_dump")
LAST_HTTP_STATUS = None


def get_all_data(shop_name=None):
    global LAST_HTTP_STATUS
    shop_name = shop_name or retail_name(SITE_URL)
    debug_dir = DEBUG_DIR if getattr(config, "debug_mode", False) else None
    try:
        return katoteka.collect_catalog(shop_name, SLUG, served=None, debug_dir=debug_dir)
    except Exception as e:
        print(f"[{shop_name}] Критическая ошибка работы парсера: {e}")
        raise
    finally:
        LAST_HTTP_STATUS = katoteka.LAST_HTTP_STATUS


def main(shop_name=None):
    return get_all_data(shop_name)


if __name__ == "__main__":
    print(f"rows: {len(main())}")
