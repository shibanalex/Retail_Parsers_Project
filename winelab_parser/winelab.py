# -*- coding: utf-8 -*-
import sys
import os

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))

import config
from parsers_core.utils import update_retail_points
from . import winelab_utils
from .winelab_utils import (
    bootstrap_session_and_driver,
    search_products,
    fetch_product_detail_browser,
    is_served_city,
    is_alcohol_query,
    to_row,
    smart_sleep,
)

DEBUG_DIR = os.path.join(os.path.dirname(__file__), "debug_dump")

_URL = "https://www.winelab.ru/"
RETAIL = getattr(config, "parsers", {}).get(_URL, "ВинЛаб")
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
    driver = None

    try:
        if served_cities and queries:
            print(f"[{shop_name}] Инициализация браузера и сессии...")
            session, driver = bootstrap_session_and_driver()
            if proxy:
                session.proxies.update(proxy)

            unique_cards = {}
            for q in queries:
                print(f"[{shop_name}] Сбор данных по запросу: {q}")
                cards = search_products(session, q, debug_dir=debug_dir)
                if not cards:
                    print(f"[{shop_name}] По запросу '{q}' ничего не найдено.")
                for card in cards:
                    unique_cards.setdefault(card["id"], card)
                smart_sleep()

            enriched = []
            total = len(unique_cards)
            checked = 0
            blocked = 0
            for i, (pid, card) in enumerate(unique_cards.items(), 1):
                if i % 5 == 0 or i == total:
                    print(f"[{shop_name}] Обработано товаров: {i} из {total}")
                detail = None
                if card.get("url"):
                    try:
                        detail = fetch_product_detail_browser(driver, card.get("url"))
                    except Exception:
                        detail = None
                    checked += 1
                    if detail == "blocked":
                        blocked += 1
                        detail = None
                    if checked >= 15 and blocked / checked >= 0.7:
                        winelab_utils.LAST_HTTP_STATUS = 403
                        raise RuntimeError(
                            f"Ошибка 403: страницы товара ВинЛаб отдают "
                            f"stage.winelab.ru/Qrator — заблокировано {blocked} из "
                            f"{checked} проверенных, доступ к деталям товара закрыт")
                    smart_sleep()
                if filter_brand:
                    brand_val = (detail or {}).get("brand") or ""
                    if isinstance(brand_val, dict):
                        brand_val = brand_val.get("name", "")
                    if not any(b.strip().lower() in brand_val.lower() for b in brand):
                        continue
                enriched.append((card, detail))

            for city in served_cities:
                print(f"[{shop_name}] Поиск города: {city}")
                for card, detail in enriched:
                    row = to_row(card, detail, shop_name, city)
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
        LAST_HTTP_STATUS = winelab_utils.LAST_HTTP_STATUS
        if session is not None:
            session.close()
        if driver is not None:
            driver.quit()

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
