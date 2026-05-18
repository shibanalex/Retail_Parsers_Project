import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import cities, search_req
from parsers_core.utils import update_retail_points
from .browser import get_browser
from .amwine_utils import select_shop, get_product_links, parse_product

def get_all_data(shop_name):
    # Указываем секцию для парсера
    driver = get_browser("AMWINE")
    all_data = []

    try:
        for actual_city_name in cities:
            print(f"[{shop_name}] Поиск города: {actual_city_name}")
            
            visited_addresses = set()
            shop_counter = 1

            while True:
                status_code, address = select_shop(driver, actual_city_name, visited_addresses, shop_name)
                
                if status_code == 999:
                    print(f"[{shop_name}] Ошибка 999. Город '{actual_city_name}' не найден на сайте.")
                    break
                elif status_code in (403, 404, 500):
                    print(f"[{shop_name}] Ошибка {status_code}. Проблема с доступом к сайту.")
                    break

                if not address:
                    break
                    
                visited_addresses.add(address)
                print(f"[{shop_name}] Выбран магазин: {address}")

                for query in search_req:
                    print(f"[{shop_name}] Сбор данных по запросу: {query}")
                    product_links = get_product_links(driver, query, shop_name)
                    
                    if not product_links:
                        print(f"[{shop_name}] По запросу '{query}' ничего не найдено.")
                        continue

                    for link in product_links:
                        product_data_list = parse_product(driver, link, shop_name, actual_city_name, address, shop_name)
                        all_data.extend(product_data_list)
                
                shop_counter += 1

            if all_data:
                try:
                    update_retail_points(shop_name, actual_city_name, shop_counter - 1)
                except Exception:
                    pass

    except Exception as e:
        print(f"[{shop_name}] Критическая ошибка работы парсера: {e}")
    finally:
        driver.quit()

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    return all_data

def main(shop_name="Ароматный Мир"):
    return get_all_data(shop_name)

if __name__ == "__main__":
    main()