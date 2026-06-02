import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import cities, search_req, parsers
from parsers_core.utils import update_retail_points
from .magnit_cosmetic_utils import get_session, get_store_codes, fetch_api_data, process_product_json, smart_sleep

def get_all_data(shop_name):
    session = get_session()
    all_data = []

    try:
        for actual_city_name in cities:
            print(f"[{shop_name}] Поиск магазинов для города: {actual_city_name}")
            
            stores = get_store_codes(session, actual_city_name, shop_name)
            
            if not stores:
                print(f"[{shop_name}] Ошибка. Магазины в городе '{actual_city_name}' не найдены.")
                continue

            print(f"[{shop_name}] Найдено {len(stores)} магазинов в городе {actual_city_name}")

            for store_code, address in stores:
                print(f"[{shop_name}] Парсинг магазина {store_code} ({address})")
                
                for query in search_req:
                    print(f"[{shop_name}] Сбор данных по запросу: {query}")
                    
                    limit = 36
                    offset = 0
                    page = 0
                    
                    while True:
                        if page > 0:
                            smart_sleep(0.5, 1.5)
                        
                        page_data = fetch_api_data(session, query, offset=offset, limit=limit, store_code=store_code, shop_name=shop_name)
                        
                        if not page_data or "items" not in page_data:
                            print(f"[{shop_name}] Ошибка или пустой ответ по запросу '{query}' на смещении {offset}.")
                            break
                        
                        items = page_data["items"]
                        if not items:
                            break

                        for item in items:
                            product_dict = process_product_json(item, shop_name, address, shop_name)
                            if product_dict:
                                all_data.append(product_dict)

                        if len(items) < limit:
                            break

                        offset += limit
                        page += 1

            if all_data:
                try:
                    update_retail_points(shop_name, actual_city_name, len(stores))
                except Exception:
                    pass

    except Exception as e:
        print(f"[{shop_name}] Критическая ошибка работы парсера: {e}")
    finally:
        session.close()

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    return all_data

def main(shop_name=None):
    if not shop_name:
        shop_name = parsers.get("https://cosmetic.magnit.ru/", "В конфиге не указано название для https://cosmetic.magnit.ru/")
    return get_all_data(shop_name)

if __name__ == "__main__":
    main()