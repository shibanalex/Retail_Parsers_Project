import sys
import os
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import cities, search_req
from parsers_core.utils import update_retail_points
from .iledebeaute_utils import get_session, fetch_api_data, process_product_json, smart_sleep

def get_all_data(shop_name):
    session = get_session()
    all_data = []

    try:
        for actual_city_name in cities:
            print(f"[{shop_name}] Поиск города: {actual_city_name}")

            for query in search_req:
                print(f"[{shop_name}] Сбор данных по запросу: {query}")
                
                size = 20
                offset = 0
                
                first_page_data = fetch_api_data(session, query, offset, size, actual_city_name, shop_name)
                
                if not first_page_data or "products" not in first_page_data:
                    print(f"[{shop_name}] Ошибка или пустой ответ по запросу '{query}'.")
                    continue

                total_products = first_page_data.get("totalHits", 0)
                if total_products == 0:
                    print(f"[{shop_name}] По запросу '{query}' найдено 0 товаров.")
                    continue

                max_pages = math.ceil(total_products / size)
                print(f"[{shop_name}] Всего найдено товаров: {total_products}. Страниц для парсинга: {max_pages}")

                for page in range(max_pages):
                    current_offset = page * size
                    
                    if page > 0:
                        smart_sleep(0.5, 1.5)
                        page_data = fetch_api_data(session, query, current_offset, size, actual_city_name, shop_name)
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
        session.close()

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    return all_data

def main(shop_name="Иль де Ботэ"):
    return get_all_data(shop_name)

if __name__ == "__main__":
    main()