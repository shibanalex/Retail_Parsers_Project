import time
import traceback
import config
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from parsers_core.utils import update_retail_points
from .browser import init_driver, save_debug_html
from parsers_core.captcha_bypass import bypass_cloudflare_humanity
from .html_parser import transliterate_city, parse_stores, parse_search_results, parse_product_details

BASE_URL = "https://www.magazinnoff.ru"

def get_details_in_tab(driver, link, fallback_name):
    brand, weight, volume, exact_price, category = None, None, None, None, None
    if not link: 
        return brand, weight, volume, exact_price, category

    original_window = driver.current_window_handle
    try:
        driver.execute_script("window.open(arguments[0], '_blank');", link)
        time.sleep(1)
        
        new_window = [w for w in driver.window_handles if w != original_window][0]
        driver.switch_to.window(new_window)
        
        bypass_cloudflare_humanity(driver, timeout=5)
        brand, weight, volume, exact_price, category = parse_product_details(driver.page_source, fallback_name)
    except Exception:
        pass
    finally:
        try:
            if len(driver.window_handles) > 1:
                driver.close()
            driver.switch_to.window(original_window)
        except:
            pass

    return brand, weight, volume, exact_price, category

def run_collection():
    cities = getattr(config, 'cities', [])
    products = getattr(config, 'search_req', [])
    brands = getattr(config, 'brand', [])
    targets = getattr(config, 'agrigator', [])

    parser_key = "https://www.magazinnoff.ru/"
    parsers_dict = getattr(config, 'parsers', {})
    PARSER_NAME = parsers_dict.get(parser_key, "Magazinnoff")

    queries = []
    if products and brands:
        for p in products:
            for b in brands: queries.append(f"{p} {b}")
    else:
        queries = list(set(products + brands))

    if not cities or not queries:
        return []

    driver = init_driver(headless=False)
    all_results = []

    try:
        try:
            driver.get(BASE_URL)
            bypass_cloudflare_humanity(driver)

        except TimeoutException:
            pass

        for city in cities:
            slug = transliterate_city(city)
            city_url = f"{BASE_URL}/category/produkty/city/{slug}"
            
            print(f"🏙️ Город: {city}")
            try:
                driver.get(city_url)
            except TimeoutException:
                continue
            
            if not bypass_cloudflare_humanity(driver):
                continue

            stores_map = parse_stores(driver.page_source, city, targets)
            if not stores_map:
                continue
            
            city_total_items = 0

            for s_slug, s_name in stores_map.items():
                print(f"  🏪 {s_name}...")

                for q in queries:
                    try:
                        shop_url = f"{BASE_URL}/magazin/{s_slug}/c/{slug}"
                        
                        try:
                            driver.get(shop_url)
                        except TimeoutException:
                            continue
                            
                        time.sleep(1.5)

                        js_search = f"""
                        var f=document.createElement('form');
                        f.method='POST';
                        f.action='/magazin/{s_slug}/search';
                        var i=document.createElement('input');
                        i.type='hidden';i.name='search_name';i.value='{q}';
                        f.appendChild(i);
                        document.body.appendChild(f);
                        f.submit();
                        """
                        driver.execute_script(js_search)

                        try:
                            WebDriverWait(driver, 6).until(
                                EC.presence_of_element_located((By.CLASS_NAME, "strip"))
                            )
                        except:
                            pass

                        bypass_cloudflare_humanity(driver, timeout=10)
                        
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                        time.sleep(2)

                        items_list = parse_search_results(driver.page_source, s_name)
                        if items_list:
                            print(f"    🔎 [{q}]: Найдено {len(items_list)} шт.")

                        for item in items_list:
                            brand, weight, volume, exact_price, category = get_details_in_tab(
                                driver, item.get('link'), item['name']
                            )

                            final_price = exact_price if exact_price else item['price']

                            record = {
                                "Номер": 0, 
                                "Сеть": s_name,
                                "Тип магазина": PARSER_NAME,
                                "Адрес Торговой точки": city,
                                "Бренд": brand,
                                "Название продукта": item['name'],
                                "Цена": final_price,
                                "Цена по акции": None,
                                "Фото товара": item['img'],
                                "Ссылка на страницу": item['link'],
                                "Рейтинг": None,
                                "Объем": volume,
                                "Вес": weight,
                                "Остаток": None,
                                "Категория": category
                            }
                            all_results.append(record)
                            city_total_items += 1

                    except Exception:
                        continue
            
            update_retail_points(PARSER_NAME, city, city_total_items)

    except Exception as e:
        traceback.print_exc()
    finally:
        if driver:
            driver.quit()
            
    for idx, item in enumerate(all_results, 1):
        item["Номер"] = idx
    
    return all_results