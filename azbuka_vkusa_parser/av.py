import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import cities, search_req, parsers
from parsers_core.utils import update_retail_points
from .browser import get_browser
from .av_utils import set_city, get_product_links, parse_product

RETAIL_NAME = parsers.get("https://av.ru/", "Азбука Вкуса")

def get_all_data():
    driver = get_browser()
    all_data = []

    try:
        for city in cities:
            if city not in ["Москва", "Санкт-Петербург", "Питер"]:
                print(f"[{RETAIL_NAME}] Пропуск города {city} (не поддерживается сайтом).")
                continue
                
            actual_city_name = "Санкт-Петербург" if city == "Питер" else city

            print(f"[{RETAIL_NAME}] 🏙️ Установка города: {actual_city_name}...")
            if not set_city(driver, actual_city_name):
                continue
            
            unique_stores = set()

            for query in search_req:
                print(f"[{RETAIL_NAME}] 🔎 Парсинг запроса: '{query}'...")
                
                product_links = get_product_links(driver, query)
                print(f"[{RETAIL_NAME}] Найдено {len(product_links)} целевых товаров по запросу '{query}'.")

                for i, link in enumerate(product_links, 1):
                    print(f"  [{i}/{len(product_links)}] Парсим товар: {link}")
                    
                    product_data_list = parse_product(driver, link, RETAIL_NAME)
                    
                    for item in product_data_list:
                        if item["Адрес Торговой точки"]:
                            unique_stores.add(item["Адрес Торговой точки"])
                            
                    all_data.extend(product_data_list)

            if unique_stores:
                update_retail_points(RETAIL_NAME, actual_city_name, len(unique_stores))

    except Exception as e:
        print(f"❌ [{RETAIL_NAME}] Критическая ошибка: {e}")
    finally:
        driver.quit()

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    return all_data

def main():
    print(f"🚀 Запуск парсера {RETAIL_NAME}...")
    data = get_all_data()
    return data

if __name__ == "__main__":
    result = main()
    print(f"Успешно спарсено {len(result)} записей.")