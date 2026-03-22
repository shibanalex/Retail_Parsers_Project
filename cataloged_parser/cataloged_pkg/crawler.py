import time
import requests
import config
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from parsers_core.utils import update_retail_points
from .browser import init_driver
from parsers_core.captcha_bypass import bypass_cataloged_antibot
from .html_parser import transliterate_city, parse_shops_list, parse_products_page, get_max_page, get_category_from_html

PARSER_NAME = "Cataloged"

def is_product_match(name, keywords):
    if not keywords: return True 
    n_low = name.lower().replace(",", ".").replace("ё", "е")
    for query in keywords:
        req_words = query.lower().replace(",", ".").replace("ё", "е").split()
        if all(word in n_low for word in req_words):
            return True
    return False

def fetch_page_raw(session, url, page_num, keywords, city, shop_name, parser_type):
    try:
        time.sleep(random.uniform(0.5, 1.5))
        resp = session.get(url, timeout=25)
        
        if "Loading..." in resp.text or "adblock-blocker" in resp.text:
            return []
            
        products = parse_products_page(resp.text)
        matches = []
        for p in products:
            if is_product_match(p['name'], keywords):
                category = None
                try:
                    if p['link']:
                        prod_resp = session.get(p['link'], timeout=15)
                        category = get_category_from_html(prod_resp.text)
                except:
                    pass

                if p.get('old_price'):
                    final_regular = p['old_price']
                    final_promo = p['price']
                else:
                    final_regular = p['price']
                    final_promo = None

                matches.append({
                    "Номер": 0, 
                    "Сеть": shop_name,
                    "Тип магазина": parser_type,
                    "Адрес Торговой точки": city,
                    "Бренд": None,
                    "Название продукта": p['name'],
                    "Цена": final_regular,
                    "Цена по акции": final_promo,
                    "Фото товара": p['img'],
                    "Ссылка на страницу": p['link'],
                    "Рейтинг": None,
                    "Объем": None,
                    "Вес": None,
                    "Остаток": None,
                    "Категория": category
                })
        return matches
    except:
        return []

def run_collection():
    cities = getattr(config, 'cities', [])
    keywords = getattr(config, 'search_req', []) + getattr(config, 'brand', [])
    targets = getattr(config, 'agrigator', [])
    
    parser_key = "https://www.cataloged.ru/"
    parsers_dict = getattr(config, 'parsers', {})
    PARSER_TYPE = parsers_dict.get(parser_key, "Агрегатор") 
    
    if not cities: return []
    
    driver = init_driver(headless=False)
    all_results = []

    try:
        for city in cities:
            slug = transliterate_city(city)
            driver.get(f"https://www.cataloged.ru/gorod/{slug}/")
            bypass_cataloged_antibot(driver) 
            
            shops = parse_shops_list(driver.page_source, targets)
            city_total = 0

            for shop_name, shop_url in shops.items():
                print(f"   🏪 {shop_name}")
                base_url = shop_url.rstrip('/') + "/?filter=produkty"
                driver.get(base_url)
                bypass_cataloged_antibot(driver) 
                
                max_p = get_max_page(driver.page_source)
                print(f"      📄 Страниц: {max_p}")
                
                session = requests.Session()
                user_agent = driver.execute_script("return navigator.userAgent;")
                session.headers.update({
                    "User-Agent": user_agent,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    "Referer": base_url
                })
                for c in driver.get_cookies():
                    session.cookies.set(c['name'], c['value'])

                tasks_urls = []
                for p in range(1, max_p + 1):
                    u = base_url if p == 1 else f"{base_url}&page{p}"
                    tasks_urls.append((u, p))

                with ThreadPoolExecutor(max_workers=5) as executor:
                    futures = [executor.submit(fetch_page_raw, session, u, p, keywords, city, shop_name, PARSER_TYPE) for u, p in tasks_urls]
                    for f in as_completed(futures):
                        res = f.result()
                        if res:
                            all_results.extend(res)
                            city_total += len(res)
                
                print(f"      ✅ Найдено: {city_total}")

            update_retail_points(PARSER_NAME, city, city_total)

    except Exception as e:
        print(f"Ошибка: {e}")
    finally:
        driver.quit()
        
    for idx, item in enumerate(all_results, 1):
        item["Номер"] = idx

    return all_results