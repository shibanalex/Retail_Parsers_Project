import time
import random
from urllib.parse import quote

try:
    import config
except ImportError:
    print("⚠️ ВкусВилл: Не найден config.py")

from parsers_core.utils import update_retail_points

from .vkusvill_config import RETAIL_NAME_GLOBAL, VKUSVILL_CITIES_MAP, VKUSVILL_VALID_ADDRESSES
from .stealth_session import _init_uc_driver
from .vkusvill_utils import set_city_address, filter_dynamic_query, parse_html_to_items


def get_all_data(cities_list=None, search_list=None, brand_list=None):
    cities_to_parse = cities_list if cities_list is not None else getattr(config, 'cities', [])
    search_patterns = search_list if search_list is not None else getattr(config, 'search_req', [])
    brands_to_filter = brand_list if brand_list is not None else getattr(config, 'brand', [])
    
    if not cities_to_parse or not search_patterns:
        print(f"⚠️ {RETAIL_NAME_GLOBAL}: Не заданы города или запросы.")
        return []

    full_items_data = []

    print(f"🚀 Запуск браузера для {RETAIL_NAME_GLOBAL}...")
    driver = _init_uc_driver(headless=False, locale="ru-RU", proxy=None)

    try:
        for city in cities_to_parse:
            subdomain = VKUSVILL_CITIES_MAP.get(city, "")
            print(f"\n{'='*60}\n🏙️ ГОРОД: {city}")
            
            driver.get(f"https://{subdomain}vkusvill.ru/")
            time.sleep(4)
            
            set_city_address(driver, city)
            
            safe_address = VKUSVILL_VALID_ADDRESSES.get(city, f"{city}, улица Ленина, 1")
            
            city_items = []
            
            for query in search_patterns:
                print(f"🔎 Поиск: '{query}'...")
                
                page = 1
                query_items_raw = [] 
                
                while True:
                    search_url = f"https://{subdomain}vkusvill.ru/search/?q={quote(query)}&PAGEN_1={page}"
                    
                    try:
                        driver.get(search_url)
                        time.sleep(random.uniform(3.0, 5.0))
                        
                        while "qrator" in driver.page_source.lower() or "just a moment" in driver.title.lower():
                            print("   🛑 Обнаружен антибот Qrator! Ждем 10 сек...")
                            time.sleep(10)
                        
                        # Передаем safe_address в парсер
                        items_on_page = parse_html_to_items(driver.page_source, safe_address, brands_to_filter)
                        
                        if not items_on_page:
                            break
                            
                        query_items_raw.extend(items_on_page)
                        print(f"   📄 Стр {page}: собрано {len(items_on_page)} шт.")
                        
                        if "VV_Pager__Item" not in driver.page_source:
                            break 
                            
                        page += 1
                        time.sleep(random.uniform(1.0, 3.0))
                        
                    except Exception as e:
                        print(f"   ❌ Ошибка загрузки страницы {page}: {e}")
                        break
                
                clean_items = filter_dynamic_query(query_items_raw, query)
                print(f"    Осталось {len(clean_items)} из {len(query_items_raw)}")
                
                city_items.extend(clean_items)

            full_items_data.extend(city_items)

            try:
                update_retail_points(RETAIL_NAME_GLOBAL, city, 1)
            except Exception:
                pass

    finally:
        print("🛑 Закрытие браузера.")
        driver.quit()

    for idx, item in enumerate(full_items_data, 1):
        item["Номер"] = idx

    return full_items_data


def main():
    start = time.time()
    all_data = get_all_data()
    finish = time.time()
    print(f"⌛ Парсинг ВкусВилл завершен за {(finish - start) / 60:.2f} мин.")
    return all_data


if __name__ == "__main__":
    main()