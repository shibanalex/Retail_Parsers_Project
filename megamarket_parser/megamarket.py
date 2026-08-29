import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import config
from parsers_core.utils import update_retail_points


from .browser import get_browser
from .megamarket_utils import set_city, get_product_links, parse_product, check_and_bypass_waf

class MegamarketParserWrapper:
    def __init__(self, shop_name="Мегамаркет"):
        self.shop_name = shop_name
        self.retail_name = "Мегамаркет"

    def main(self):
        return get_all_data(self.shop_name, self.retail_name)

def get_all_data(shop_name="Мегамаркет", retail_name="Мегамаркет"):
    driver = get_browser("MEGAMARKET")
    all_data = []

    search_queries = getattr(config, "search_req", [])
    brand_queries = getattr(config, "brand", [])

    raw_queries = []
    if isinstance(search_queries, list):
        raw_queries.extend(search_queries)
    if isinstance(brand_queries, list):
        raw_queries.extend(brand_queries)

    all_queries = list(dict.fromkeys([str(q).strip() for q in raw_queries if q and str(q).strip()]))

    try:
        check_and_bypass_waf(driver, shop_name)
        cities_list = getattr(config, "cities", [])

        for actual_city_name in cities_list:
            print(f"[{shop_name}] Поиск города: {actual_city_name}")
            status_code = set_city(driver, actual_city_name, shop_name)

            if status_code == 999:
                continue
            elif status_code in (403, 404, 500):
                print(f"[{shop_name}] Ошибка {status_code}. Прерывание работы.")
                break

            for query in all_queries:
                product_links = get_product_links(driver, query, shop_name)

                if not product_links:
                    print(f"[{shop_name}] По запросу '{query}' ничего не найдено")
                    continue

                for link in product_links:
                    items = parse_product(
                        driver=driver,
                        product_url=link,
                        retail_name=retail_name,
                        city_name=actual_city_name,
                        shop_name=shop_name
                    )
                    all_data.extend(items)

            if all_data:
                try:
                    update_retail_points(all_data)
                except Exception:
                    pass

    except Exception as e:
        print(f"[{shop_name}] Ошибка 500. Критический сбой парсера: {e}")
    finally:
        driver.quit()

    for idx, row in enumerate(all_data, start=1):
        row["Номер"] = idx

    return all_data

def main(shop_name="Мегамаркет"):
    return get_all_data(shop_name, shop_name)

megamarket = MegamarketParserWrapper(shop_name="Мегамаркет")

if __name__ == "__main__":
    main()