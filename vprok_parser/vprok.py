# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))

import time

import config
from parsers_core.utils import update_retail_points
from . import vprok_utils
from .browser import get_browser
from .vprok_utils import (
    parse_search_page,
    extract_brand,
    check_page,
    capture_status,
    is_served_city,
    to_row,
    smart_sleep,
    dump_debug,
    _wait_ready,
    _wait_for,
    BASE_URL,
)

DEBUG_DIR = os.path.join(os.path.dirname(__file__), "debug_dump")

RETAIL = "Впрок"
LAST_HTTP_STATUS = None
MAX_PAGES = 10
_TILE_SELECTOR = "[class*='UiProductTileMain_root']"


def get_all_data(shop_name=RETAIL):
    global LAST_HTTP_STATUS
    from parsers_core.exceptions import NoShopsError

    cities = getattr(config, "cities", [])
    search_req = getattr(config, "search_req", [])
    brand = getattr(config, "brand", [])
    debug_mode = getattr(config, "debug_mode", False)
    debug_dir = DEBUG_DIR if debug_mode else None

    if brand and not search_req:
        queries = list(brand)
        filter_brand = False
    else:
        queries = list(search_req)
        filter_brand = bool(brand)

    served_cities, no_shops_cities = [], []
    for city in cities:
        (served_cities if is_served_city(city) else no_shops_cities).append(city)

    all_data = []
    _error = None
    driver = None

    try:
        if served_cities and queries:
            print(f"[{shop_name}] Инициализация браузера...")
            driver = get_browser("VPROK")

            unique_products = {}
            for q in queries:
                print(f"[{shop_name}] Сбор данных по запросу: {q}")
                found_any = False
                for page_num in range(1, MAX_PAGES + 1):
                    suffix = f"&page={page_num}" if page_num > 1 else ""
                    driver.get(f"{BASE_URL}/catalog/search?text={q}{suffix}")
                    _wait_ready(driver)
                    _wait_for(driver, _TILE_SELECTOR, 8)
                    capture_status(driver)
                    check_page(driver.page_source)
                    dump_debug(debug_dir, f"{q}_page{page_num}", driver.page_source)
                    products = parse_search_page(driver.page_source)
                    if not products:
                        break
                    added = 0
                    for p in products:
                        if p["id"] not in unique_products:
                            unique_products[p["id"]] = p
                            added += 1
                    if added:
                        found_any = True
                        print(f"[{shop_name}] Страница {page_num}: +{added} товаров")
                    if added == 0:
                        break
                    smart_sleep(driver)
                if not found_any:
                    print(f"[{shop_name}] По запросу '{q}' ничего не найдено.")

            total = len(unique_products)
            for i, (pid, p) in enumerate(unique_products.items(), 1):
                if i % 5 == 0 or i == total:
                    print(f"[{shop_name}] Обработано товаров: {i} из {total}")
                driver.get(p["url"])
                _wait_ready(driver)
                time.sleep(1)
                capture_status(driver)
                p["brand"] = extract_brand(driver.page_source)
                smart_sleep(driver)

            if filter_brand:
                wanted = [b.strip().lower() for b in brand]
                unique_products = {
                    pid: p for pid, p in unique_products.items()
                    if any(w in (p.get("brand") or "").lower() for w in wanted)
                }

            for city in served_cities:
                print(f"[{shop_name}] Поиск города: {city}")
                for p in unique_products.values():
                    row = to_row(p, shop_name, city)
                    if row is not None:
                        all_data.append(row)
                try:
                    update_retail_points(shop_name, city, 1)
                except Exception:
                    pass

        for city in no_shops_cities:
            print(f"[{shop_name}] Ошибка 999. Город '{city}' не обслуживается доставкой.")

    except Exception as e:
        _error = e
        print(f"[{shop_name}] Критическая ошибка работы парсера: {e}")
    finally:
        LAST_HTTP_STATUS = vprok_utils.LAST_HTTP_STATUS
        if driver is not None:
            driver.quit()

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    if _error is not None:
        raise _error
    if not all_data and no_shops_cities:
        raise NoShopsError(parser_name=shop_name, city=", ".join(no_shops_cities))
    return all_data


def main():
    return get_all_data()


if __name__ == "__main__":
    print(f"rows: {len(main())}")
