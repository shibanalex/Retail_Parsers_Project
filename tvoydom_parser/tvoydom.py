import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import cities, search_req, parsers
from parsers_core.utils import update_retail_points
from .browser import get_browser
from .tvoydom_utils import set_city, get_product_links, parse_product

RETAIL_NAME = parsers.get("https://tvoydom.ru/", "Твой Дом")

def get_all_data():
    driver = get_browser()
    all_data = []

    try:
        if "Москва" not in cities:
            print(f"[{RETAIL_NAME}] В конфиге нет Москвы. Парсинг остановлен.")
            return []

        actual_city_name = "Москва"
        print(f"[{RETAIL_NAME}] 🏙️ Проверка города: {actual_city_name}...")
        set_city(driver, actual_city_name)

        points_count = 1

        for query in search_req:
            print(f"[{RETAIL_NAME}] 🔎 Парсинг запроса: '{query}'...")
            
            product_links = get_product_links(driver, query)
            print(f"[{RETAIL_NAME}] Найдено {len(product_links)} целевых товаров по запросу '{query}'.")

            for i, link in enumerate(product_links, 1):
                print(f"  [{i}/{len(product_links)}] Парсим товар: {link}")
                
                product_data_list = parse_product(driver, link, RETAIL_NAME, actual_city_name)
                all_data.extend(product_data_list)

        if all_data:
            update_retail_points(RETAIL_NAME, actual_city_name, points_count)

    except Exception as e:
        print(f"❌ [{RETAIL_NAME}] Критическая ошибка: {e}")
    finally:
        driver.quit()

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    return all_data

def main():
    print(f"🚀 Запуск парсера {RETAIL_NAME}...")
    return get_all_data()

if __name__ == "__main__":
    result = main()
    print(f"Успешно спарсено {len(result)} записей.")