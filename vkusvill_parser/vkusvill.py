import time
import random
import sys
import os
from urllib.parse import quote

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

try:
    import config
except ImportError:
    pass

from parsers_core.utils import update_retail_points
from .vkusvill_config import VKUSVILL_CITIES_MAP, VKUSVILL_VALID_ADDRESSES
from .browser import get_browser
from .vkusvill_utils import set_city_address, filter_dynamic_query, parse_html_to_items, smart_sleep

def get_all_data(shop_name):
    cities_to_parse = getattr(config, 'cities', [])
    search_patterns = getattr(config, 'search_req', [])
    brands_to_filter = getattr(config, 'brand', [])
    
    if not cities_to_parse or not search_patterns:
        print(f"[{shop_name}] Ошибка: Не заданы города или запросы в config.py")
        return []

    full_items_data = []
    driver = get_browser("VKUSVILL")

    try:
        for city in cities_to_parse:
            print(f"[{shop_name}] Поиск города: {city}")
            
            if city not in VKUSVILL_CITIES_MAP:
                print(f"[{shop_name}] Ошибка 999. Город '{city}' отсутствует в карте VKUSVILL_CITIES_MAP.")
                continue

            subdomain = VKUSVILL_CITIES_MAP.get(city, "")
            try:
                driver.get(f"https://{subdomain}vkusvill.ru/")
                smart_sleep(driver, 4.0)
            except Exception:
                print(f"[{shop_name}] Ошибка 404. Не удалось загрузить сайт для города {city}.")
                continue
            
            if "qrator" in driver.page_source.lower():
                print(f"[{shop_name}] Ошибка 403. Обнаружена блокировка Qrator.")
                break

            set_city_address(driver, city, shop_name)
            safe_address = VKUSVILL_VALID_ADDRESSES.get(city, f"{city}, улица Ленина, 1")
            
            city_items = []
            for query in search_patterns:
                print(f"[{shop_name}] Сбор данных по запросу: {query}")
                page = 1
                query_items_raw = [] 
                
                while True:
                    search_url = f"https://{subdomain}vkusvill.ru/search/?q={quote(query)}&PAGEN_1={page}"
                    try:
                        driver.get(search_url)
                        smart_sleep(driver, 3.5)
                        
                        if "qrator" in driver.page_source.lower():
                            print(f"[{shop_name}] Ошибка 403. Блокировка Qrator на поиске.")
                            break
                        
                        items_on_page = parse_html_to_items(driver.page_source, safe_address, brands_to_filter, shop_name)
                        
                        if not items_on_page:
                            break
                            
                        query_items_raw.extend(items_on_page)
                        
                        if "VV_Pager__Item" not in driver.page_source or page > 10:
                            break 
                            
                        page += 1
                    except Exception:
                        break
                
                clean_items = filter_dynamic_query(query_items_raw, query)
                city_items.extend(clean_items)

            full_items_data.extend(city_items)
            
            if city_items:
                try:
                    update_retail_points(shop_name, city, 1)
                except Exception:
                    pass

    finally:
        driver.quit()

    for idx, item in enumerate(full_items_data, 1):
        item["Номер"] = idx

    return full_items_data

def main(shop_name="ВкусВилл"):
    return get_all_data(shop_name)

if __name__ == "__main__":
    main()