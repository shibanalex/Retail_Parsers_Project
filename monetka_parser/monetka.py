# -*- coding: utf-8 -*-
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from parsers_core import katoteka
from parsers_core.names import retail_name
from image_parser_service.flyer_page_ocr import FlyerProfile

SITE_URL = "https://monetka.ru/"
SLUG = "mon"
# Каталог картинками: жёлтая плашка с ценой (цвет строго плашки, упаковки бывают такие же жёлтые),
# название под ней. У каждого региона свой каталог
PROFILE = FlyerProfile([((24, 185, 240), (30, 225, 255))], name_side="below", close=21)
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "debug_dump")
LAST_HTTP_STATUS = None


def get_all_data(shop_name=None):
    global LAST_HTTP_STATUS
    shop_name = shop_name or retail_name(SITE_URL)
    debug_dir = DEBUG_DIR if getattr(config, "debug_mode", False) else None
    try:
        return katoteka.collect_catalog(shop_name, SLUG, regional=True, flyer_profile=PROFILE, debug_dir=debug_dir)
    except Exception as e:
        print(f"[{shop_name}] Критическая ошибка работы парсера: {e}")
        raise
    finally:
        LAST_HTTP_STATUS = katoteka.LAST_HTTP_STATUS


def main(shop_name=None):
    return get_all_data(shop_name)


if __name__ == "__main__":
    print(f"rows: {len(main())}")
