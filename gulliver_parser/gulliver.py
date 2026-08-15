import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import config
from parsers_core.utils import update_retail_points
from .browser import get_browser
from .gulliver_utils import set_city, get_product_links, parse_product

def get_all_data(shop_name):
    driver = get_browser("GULLIVER")
    all_data = []
    
    
    search_queries = getattr(config, 'search_req', [])
    brand_queries = getattr(config, 'brand', [])
    
    
    all_queries = []
    if isinstance(search_queries, list):
        all_queries.extend(search_queries)
    if isinstance(brand_queries, list):
        all_queries.extend(brand_queries)
        
    
    all_queries = list(dict.fromkeys([str(q).strip() for q in all_queries if q and str(q).strip()]))

    try:
        for actual_city_name in getattr(config, 'cities', []):
            print(f"[{shop_name}] Установка города доставки: {actual_city_name}")
            
            status_code = set_city(driver, actual_city_name, shop_name)
            
            if status_code == 999:
                print(f"[{shop_name}] Ошибка 999. Город не найден на сайте.")
                continue
            elif status_code in (403, 404, 500):
                print(f"[{shop_name}] Ошибка {status_code}. Проблема с доступом к API.")
                break 

            points_count = 1

            
            for query in all_queries:
                print(f"[{shop_name}] Сбор данных по запросу: {query}")
                product_links = get_product_links(driver, query, shop_name)

                if not product_links:
                    print(f"[{shop_name}] По запросу ничего не найдено.")
                    continue

                for link_data in product_links:
                    product_data_list = parse_product(driver, link_data, shop_name, actual_city_name, shop_name)
                    all_data.extend(product_data_list)
            
            if all_data:
                try:
                    update_retail_points(shop_name, actual_city_name, points_count)
                except Exception:
                    pass

    except Exception as e:
        print(f"[{shop_name}] Критическая ошибка работы парсера: {e}")
    finally:
        driver.quit()

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    return all_data

def main(shop_name="Гулливер"):
    return get_all_data(shop_name)

if __name__ == "__main__":
    main()