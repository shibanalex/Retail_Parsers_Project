# -*- coding: utf-8 -*-
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from image_parser_service.flyer_page_ocr import FlyerProfile, parse_flyer_images
from parsers_core.exceptions import NoShopsError
from parsers_core.katoteka import city_region, match_queries
from parsers_core.names import retail_name
from parsers_core.normalize import split_name_measure, split_regular_promo
from parsers_core.rows import make_row, number_rows
from parsers_core.utils import update_retail_points
from . import magnolia_utils
from .browser import get_browser

SITE_URL = "https://mgnl.ru/"
# Зелёная и оливковая плашки с ценой, название над плашкой. Подписи чёрные, латиницы почти нет
PROFILE = FlyerProfile([((45, 80, 40), (85, 255, 170)), ((30, 100, 110), (42, 255, 200))], name_side="above",
                       close=9, lang="rus", drop_upper=True, dark_text=True)
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "debug_dump")
LAST_HTTP_STATUS = None


def get_all_data(shop_name=None):
    global LAST_HTTP_STATUS
    shop_name = shop_name or retail_name(SITE_URL)
    cities = getattr(config, "cities", []) or []
    queries = list(getattr(config, "search_req", []) or []) or list(getattr(config, "brand", []) or [])
    debug_mode = getattr(config, "debug_mode", False)

    served = [c for c in cities if city_region(c) == "mow"]
    no_shops = [c for c in cities if c not in served]
    for city in no_shops:
        print(f"[{shop_name}] Ошибка 999. Город '{city}' не обслуживается сетью.")

    all_data = []
    if served:
        driver = get_browser("MAGNOLIA")
        try:
            pdf_url = magnolia_utils.open_booklet(driver)
            print(f"[{shop_name}] Буклет: {pdf_url}")
            pdf = magnolia_utils.download(driver, pdf_url)
        except Exception as e:
            print(f"[{shop_name}] Критическая ошибка работы парсера: {e}")
            raise
        finally:
            LAST_HTTP_STATUS = magnolia_utils.LAST_HTTP_STATUS
            driver.quit()

        with tempfile.TemporaryDirectory() as tmp:
            out_dir = DEBUG_DIR if debug_mode else tmp
            os.makedirs(out_dir, exist_ok=True)
            pages = magnolia_utils.booklet_pages(pdf, out_dir)
            print(f"[{shop_name}] Страниц в буклете: {len(pages)}, распознаю...")
            results = parse_flyer_images([p for _, p in pages], PROFILE)
        items = []
        for (num, _), page_items in zip(pages, results):
            for it in page_items:
                it["page"] = num
                items.append(it)
        print(f"[{shop_name}] Позиций в буклете: {len(items)}")
        if queries:
            items = [it for it in items if match_queries(it["name"], queries)]
            for q in queries:
                if not any(match_queries(it["name"], [q]) for it in items):
                    print(f"[{shop_name}] По запросу '{q}' ничего не найдено.")

        for city in served:
            for it in items:
                regular, promo = split_regular_promo(it["price"], it.get("old_price"))
                name, volume, weight = split_name_measure(it["name"])
                row = make_row(shop_name, city, name, regular, store_type="Магазин", promo_price=promo,
                               url=f"{pdf_url}#page={it['page']}", volume=volume, weight=weight, stock="1")
                if row:
                    all_data.append(row)
            try:
                update_retail_points(shop_name, city, 1)
            except Exception:
                pass

    if not all_data and no_shops and not served:
        raise NoShopsError(parser_name=shop_name, city=", ".join(no_shops))
    return number_rows(all_data)


def main(shop_name=None):
    return get_all_data(shop_name)


if __name__ == "__main__":
    print(f"rows: {len(main())}")
