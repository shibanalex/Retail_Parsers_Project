import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import cities, search_req
from parsers_core.utils import update_retail_points
from .browser import get_browser
from .av_utils import set_city, get_product_links, parse_product

def get_all_data(shop_name):
    driver = get_browser()
    all_data = []

    try:
        for city in cities:
            print(f"[{shop_name}] Поиск города: {city}")
            
            status_code = set_city(driver, city, shop_name)
            
            if status_code == 999:
                print(f"[{shop_name}] Ошибка 999. Город '{city}' не найден на сайте.")
                continue
            elif status_code in (403, 404, 500):
                print(f"[{shop_name}] Ошибка {status_code}. Проблема с доступом к сайту.")
                break

            unique_stores = set()

            for query in search_req:
                print(f"[{shop_name}] Сбор данных по запросу: {query}")
                
                product_links = get_product_links(driver, query, shop_name)
                if not product_links:
                    print(f"[{shop_name}] По запросу '{query}' ничего не найдено.")
                    continue

                for link in product_links:
                    product_data_list = parse_product(driver, link, shop_name, shop_name)
                    
                    for item in product_data_list:
                        if item.get("Адрес Торговой точки"):
                            unique_stores.add(item["Адрес Торговой точки"])
                            
                    all_data.extend(product_data_list)

            if unique_stores:
                try:
                    update_retail_points(shop_name, city, len(unique_stores))
                except Exception:
                    pass

    except Exception as e:
        print(f"[{shop_name}] Критическая ошибка работы парсера: {e}")
    finally:
        driver.quit()

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    return all_data

def main(shop_name="Азбука Вкуса"):
    return get_all_data(shop_name)

if __name__ == "__main__":
    main()