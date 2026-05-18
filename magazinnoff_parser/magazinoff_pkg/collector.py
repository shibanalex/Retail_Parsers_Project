import time
import random
import traceback
import config
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from parsers_core.utils import update_retail_points
from .browser import init_driver
from parsers_core.captcha_bypass import bypass_cloudflare_humanity
from .html_parser import transliterate_city, parse_stores, parse_search_results, parse_product_details

BASE_URL = "https://www.magazinnoff.ru"

def smart_sleep(driver, fallback=2.0):
    if hasattr(driver, 'custom_min_delay') and hasattr(driver, 'custom_max_delay'):
        time.sleep(random.uniform(driver.custom_min_delay, driver.custom_max_delay))
    else:
        time.sleep(fallback)

def get_details_in_tab(driver, link, fallback_name):
    brand, weight, volume, exact_price, category = None, None, None, None, None
    if not link: 
        return brand, weight, volume, exact_price, category

    original_window = driver.current_window_handle
    try:
        driver.execute_script("window.open(arguments[0], '_blank');", link)
        smart_sleep(driver, 1.5)
        
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

def run_collection(shop_name):
    cities = getattr(config, 'cities', [])
    products = getattr(config, 'search_req', [])
    brands = getattr(config, 'brand', [])
    targets = getattr(config, 'agrigator', [])

    queries = []
    if products and brands:
        for p in products:
            for b in brands: queries.append(f"{p} {b}")
    else:
        queries = list(set(products + brands))

    if not cities or not queries:
        return []

    driver = init_driver("MAGAZINNOFF", headless=False)
    all_results = []

    try:
        try:
            driver.get(BASE_URL)
            bypass_cloudflare_humanity(driver)
        except TimeoutException:
            pass

        for city in cities:
            print(f"[{shop_name}] Поиск города: {city}")
            slug = transliterate_city(city)
            city_url = f"{BASE_URL}/category/produkty/city/{slug}"
            
            try:
                driver.get(city_url)
            except TimeoutException:
                print(f"[{shop_name}] Ошибка 404. Тайм-аут при загрузке города {city}.")
                continue
            
            if "404" in driver.title or "Страница не найдена" in driver.page_source:
                print(f"[{shop_name}] Ошибка 999. Город '{city}' не найден на сайте.")
                continue

            if not bypass_cloudflare_humanity(driver):
                print(f"[{shop_name}] Ошибка 403. Блокировка защиты при доступе к городу {city}.")
                continue

            stores_map = parse_stores(driver.page_source, city, targets)
            if not stores_map:
                print(f"[{shop_name}] В городе '{city}' не найдено целевых сетей.")
                continue

            for s_slug, s_name in stores_map.items():
                print(f"[{shop_name}] Сбор данных для сети: {s_name}")

                for q in queries:
                    print(f"[{shop_name}] Сбор данных по запросу: {q}")
                    try:
                        shop_url = f"{BASE_URL}/magazin/{s_slug}/c/{slug}"
                        
                        try:
                            driver.get(shop_url)
                        except TimeoutException:
                            print(f"[{shop_name}] Ошибка загрузки страницы сети {s_name}.")
                            continue
                            
                        smart_sleep(driver, 1.5)

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
                        smart_sleep(driver, 2.5)

                        items_list = parse_search_results(driver.page_source, s_name)
                        if not items_list:
                            print(f"[{shop_name}] По запросу '{q}' ничего не найдено.")
                            continue

                        for item in items_list:
                            brand, weight, volume, exact_price, category = get_details_in_tab(
                                driver, item.get('link'), item['name']
                            )

                            final_price = exact_price if exact_price else item['price']

                            record = {
                                "Номер": 0, 
                                "Сеть": s_name,
                                "Тип магазина": "Агрегатор",
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

                    except Exception as e:
                        print(f"[{shop_name}] Ошибка обработки запроса '{q}': {e}")
                        continue
            
            try:
                update_retail_points(shop_name, city, len(stores_map))
            except Exception:
                pass

    except Exception as e:
        print(f"[{shop_name}] Ошибка выполнения: {e}")
    finally:
        if driver:
            driver.quit()
            
    for idx, item in enumerate(all_results, 1):
        item["Номер"] = idx
    
    return all_results