# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))

import config
from parsers_core.utils import update_retail_points
from . import winestyle_utils
from .winestyle_utils import (
    bootstrap_session,
    fetch,
    parse_cards,
    category_slug,
    is_served_city,
    is_alcohol_query,
    to_row,
    smart_sleep,
    dump_debug,
    BASE_URL,
)

DEBUG_DIR = os.path.join(os.path.dirname(__file__), "debug_dump")

_URL = "https://winestyle.ru/"
RETAIL = getattr(config, "parsers", {}).get(_URL, "Winestyle")
LAST_HTTP_STATUS = None


def get_all_data(shop_name=RETAIL, proxy=None):
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
        skipped_queries = [q for q in queries if not is_alcohol_query(q)]
        queries = [q for q in queries if is_alcohol_query(q)]
        for q in skipped_queries:
            print(f"[{shop_name}] Запрос '{q}' пропущен — не алкоголь, сеть не продаёт.")

    served_cities, no_shops_cities = [], []
    for city in cities:
        (served_cities if is_served_city(city) else no_shops_cities).append(city)

    all_data = []
    _error = None
    session = None

    try:
        if served_cities and queries:
            print(f"[{shop_name}] Инициализация браузера и сессии...")
            session = bootstrap_session()
            if proxy:
                session.proxies.update(proxy)

            unique_products = {}
            for q in queries:
                print(f"[{shop_name}] Сбор данных по запросу: {q}")
                pages = [f"{BASE_URL}/search/?text={q}"]
                slug = category_slug(q)
                if slug:
                    pages.append(f"{BASE_URL}/{slug}/")

                products = []
                for i, url in enumerate(pages):
                    r = fetch(session, url)
                    dump_debug(debug_dir, f"{q}_{i}", r.text)
                    if r.status_code == 500:
                        print(f"[{shop_name}] Ошибка 500 на {url} — пропускаю.")
                        continue
                    products.extend(parse_cards(r.text))
                    smart_sleep()

                if filter_brand:
                    products = [
                        p for p in products
                        if any(b.strip().lower() in (p.get("brand") or "").lower() for b in brand)
                    ]
                if not products:
                    print(f"[{shop_name}] По запросу '{q}' ничего не найдено.")
                else:
                    print(f"[{shop_name}] По запросу '{q}' найдено товаров: {len(products)}")
                for p in products:
                    unique_products.setdefault(p["url"], p)

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
            print(f"[{shop_name}] Ошибка 999. Город '{city}' не обслуживается сетью.")

    except Exception as e:
        _error = e
        print(f"[{shop_name}] Критическая ошибка работы парсера: {e}")
    finally:
        LAST_HTTP_STATUS = winestyle_utils.LAST_HTTP_STATUS
        if session is not None:
            session.close()

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    if _error is not None:
        raise _error
    if not all_data and no_shops_cities:
        raise NoShopsError(parser_name=shop_name, city=", ".join(no_shops_cities))
    return all_data


def main(proxy=None):
    return get_all_data(proxy=proxy)


if __name__ == "__main__":
    print(f"rows: {len(main())}")
