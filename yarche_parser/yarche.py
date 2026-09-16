# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))

import requests

import config
from parsers_core.utils import update_retail_points
from . import yarche_utils
from .yarche_utils import (
    bootstrap_token,
    is_served_city,
    search_products,
    filter_by_brand,
    to_row,
    smart_sleep,
)

DEBUG_DIR = os.path.join(os.path.dirname(__file__), "debug_dump")

RETAIL = "Ярче!"
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

    served_cities, no_shops_cities = [], []
    for city in cities:
        (served_cities if is_served_city(city) else no_shops_cities).append(city)

    all_data = []
    _error = None
    session = requests.Session()
    if proxy:
        session.proxies.update(proxy)

    try:
        if served_cities and queries:
            token = bootstrap_token(session)

            products_by_query = {}
            for q in queries:
                print(f"[{shop_name}] Сбор данных по запросу: {q}")
                products = search_products(session, token, q, debug_dir=debug_dir)
                if filter_brand:
                    products = filter_by_brand(products, brand)
                if not products:
                    print(f"[{shop_name}] По запросу '{q}' ничего не найдено.")
                products_by_query[q] = products
                smart_sleep()

            for city in served_cities:
                print(f"[{shop_name}] Поиск города: {city}")
                seen_ids = set()
                for q in queries:
                    for product in products_by_query.get(q, []):
                        pid = product.get("id")
                        if pid in seen_ids:
                            continue
                        seen_ids.add(pid)
                        row = to_row(product, shop_name, city)
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
        LAST_HTTP_STATUS = yarche_utils.LAST_HTTP_STATUS
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
