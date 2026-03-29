import sys
import os

# Подключаем корень проекта, чтобы работал импорт из config и parsers_core
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import cities, search_req
from parsers_core.utils import update_retail_points
from .browser import get_browser
from .av_utils import set_city, get_product_links, parse_product

RETAIL_NAME = "Азбука Вкуса"

def get_all_data():
    driver = get_browser()
    all_data = []

    try:
        for city in cities:
            # Азбука Вкуса представлена в основном в Москве и Спб.
            if city not in ["Москва", "Санкт-Петербург", "Питер"]:
                print(f"[{RETAIL_NAME}] Пропуск города {city} (не поддерживается сайтом).")
                continue
                
            actual_city_name = "Санкт-Петербург" if city == "Питер" else city

            print(f"[{RETAIL_NAME}] 🏙️ Установка города: {actual_city_name}...")
            if not set_city(driver, actual_city_name):
                continue
            
            # Уникальные торговые точки, найденные в ходе парсинга
            unique_stores = set()

            for query in search_req:
                print(f"[{RETAIL_NAME}] 🔎 Парсинг запроса: '{query}'...")
                
                # 1. Получаем ссылки на все товары по запросу
                product_links = get_product_links(driver, query)
                print(f"[{RETAIL_NAME}] Найдено {len(product_links)} товаров по запросу '{query}'.")

                # 2. Переходим в каждый товар и собираем детали + наличие
                for i, link in enumerate(product_links, 1):
                    print(f"  [{i}/{len(product_links)}] Парсим товар: {link}")
                    product_data_list = parse_product(driver, link, actual_city_name)
                    
                    for item in product_data_list:
                        if item["Адрес Торговой точки"]:
                            unique_stores.add(item["Адрес Торговой точки"])
                            
                    all_data.extend(product_data_list)

            # Обновляем статистику по количеству торговых точек (как требует твоя архитектура)
            if unique_stores:
                update_retail_points(RETAIL_NAME, actual_city_name, len(unique_stores))

    except Exception as e:
        print(f"❌ [{RETAIL_NAME}] Критическая ошибка: {e}")
    finally:
        driver.quit()

    # Заполняем поле "Номер" по порядку
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