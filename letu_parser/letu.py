import sys
import os
import math
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import cities, search_req
from parsers_core.utils import update_retail_points
from .browser import get_browser
from .letu_utils import set_city, fetch_api_data, process_product_json, smart_sleep

def get_all_data(shop_name):
    driver = get_browser("LETU")
    all_data = []

    try:
        for actual_city_name in cities:
            print(f"[{shop_name}] Поиск города: {actual_city_name}")
            
            status_code, city_info = set_city(driver, actual_city_name, shop_name)
            
            if status_code == 999:
                print(f"[{shop_name}] Ошибка 999. Город '{actual_city_name}' не найден на сайте.")
                continue
            elif status_code in (403, 404, 500):
                print(f"[{shop_name}] Ошибка {status_code}. Проблема с доступом к сайту или защитой.")
                break

            for query in search_req:
                print(f"[{shop_name}] Сбор данных по запросу: {query}")
                
                first_page_data = fetch_api_data(driver, query, 1, city_info, shop_name)
                
                if not first_page_data or "products" not in first_page_data:
                    print(f"[{shop_name}] Ошибка или пустой ответ по запросу '{query}'.")
                    continue

                total_products = first_page_data.get("totalProducts", 0)
                if total_products == 0:
                    print(f"[{shop_name}] По запросу '{query}' найдено 0 товаров.")
                    continue

                page_size = 36
                max_pages = math.ceil(total_products / page_size)
                print(f"[{shop_name}] Всего найдено товаров: {total_products}. Страниц для парсинга: {max_pages}")

                for page in range(1, max_pages + 1):
                    if page > 1:
                        smart_sleep(driver, 1.5)
                        page_data = fetch_api_data(driver, query, page, city_info, shop_name)
                        if not page_data or not page_data.get("products"):
                            break
                        items = page_data["products"]
                    else:
                        items = first_page_data["products"]

                    for item in items:
                        product_dict = process_product_json(item, shop_name, actual_city_name, shop_name)
                        if product_dict:
                            all_data.append(product_dict)

            if all_data:
                try:
                    update_retail_points(shop_name, actual_city_name, 1)
                except Exception:
                    pass

    except Exception as e:
        print(f"[{shop_name}] Критическая ошибка работы парсера: {e}")
    finally:
        driver.quit()

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    return all_data

def main(shop_name="Лэтуаль"):
    return get_all_data(shop_name)

if __name__ == "__main__":
    main()