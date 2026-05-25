import time
import random
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException

def smart_sleep(driver, fallback=2.0):
    if hasattr(driver, 'custom_min_delay') and hasattr(driver, 'custom_max_delay'):
        time.sleep(random.uniform(driver.custom_min_delay, driver.custom_max_delay))
    else:
        time.sleep(fallback)

def check_and_bypass_waf(driver, shop_name):
    page_source = driver.page_source.lower()
    if "qrator" in page_source or "ddos-guard" in page_source or "cloudflare" in page_source:
        print(f"[{shop_name}] Обнаружена защита WAF. Ожидание прохождения...")
        smart_sleep(driver, 5.0)
        if "qrator" in driver.page_source.lower():
            return False
    return True

def _get_ids_from_cookies(driver):
    city_id = "8113"
    region_id = "330001"
    for cookie in driver.get_cookies():
        if cookie['name'] == 'cityId':
            city_id = cookie['value']
        elif cookie['name'] == 'shippingRegionId':
            region_id = cookie['value']
    return {"cityId": city_id, "shippingRegionId": region_id}

def get_city_id_from_api(driver, city_name, shop_name):
    js_script = """
    var callback = arguments[arguments.length - 1];
    var cityName = arguments[0];
    fetch('https://www.letu.ru/s/api/geo/v1/city/list?cityPrefix=' + encodeURIComponent(cityName) + '&pushSite=storeMobileRU')
    .then(response => response.json())
    .then(data => callback(data))
    .catch(error => callback({'error': error.toString()}));
    """
    try:
        driver.set_script_timeout(10)
        result = driver.execute_async_script(js_script, city_name)
        if result and 'error' in result:
            print(f"[{shop_name}] Ошибка Geo API: {result['error']}")
            return None
        return result
    except Exception as e:
        print(f"[{shop_name}] Ошибка выполнения скрипта Geo API: {e}")
        return None

def set_city(driver, city_name, shop_name):
    try:
        driver.get("https://www.letu.ru/")
        if not check_and_bypass_waf(driver, shop_name):
            return 403, None

        smart_sleep(driver, 2.0)

        geo_data = get_city_id_from_api(driver, city_name, shop_name)
        
        if not geo_data or 'cityList' not in geo_data:
            print(f"[{shop_name}] Не удалось получить список городов из API.")
            return 500, None

        city_list = geo_data['cityList']
        target_city_id = None

        for c in city_list:
            if city_name.lower() in c.get('name', '').lower():
                target_city_id = c.get('id')
                break

        if not target_city_id:
            return 999, None

        driver.add_cookie({
            'name': 'cityId',
            'value': str(target_city_id),
            'domain': '.letu.ru',
            'path': '/'
        })

        driver.refresh()
        smart_sleep(driver, 3.0)

        current_ids = _get_ids_from_cookies(driver)
        
        if current_ids['cityId'] != str(target_city_id):
            current_ids['cityId'] = str(target_city_id)

        return 200, current_ids

    except Exception as e:
        print(f"[{shop_name}] Критическая ошибка при установке города через API: {e}")
        return 500, None

def fetch_api_data(driver, query, page, city_info, shop_name):
    js_script = """
    var callback = arguments[arguments.length - 1];
    var cityId = arguments[0];
    var regionId = arguments[1];
    var pageNum = arguments[2];
    var searchQuery = arguments[3];

    fetch('https://www.letu.ru/api/searcher/v1/search?pushSite=storeMobileRU', {
        method: 'POST',
        headers: {
            'Accept': 'application/json, text/plain, */*',
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({
            "locale": "ru",
            "cityId": cityId,
            "shippingRegionId": regionId,
            "sort": "default",
            "page": {"number": pageNum, "size": 36},
            "query": searchQuery,
            "filtersType": {"switch": [], "range": [], "multiselect": []},
            "noAutocorrect": false,
            "requestorInfo": [],
            "smartSearchMarker": false
        })
    })
    .then(response => response.json())
    .then(data => callback(data))
    .catch(error => callback({'error': error.toString()}));
    """
    
    try:
        driver.set_script_timeout(15)
        result = driver.execute_async_script(js_script, city_info['cityId'], city_info['shippingRegionId'], page, query)
        
        if result and 'error' in result:
            print(f"[{shop_name}] Ошибка XHR запроса: {result['error']}")
            return None
            
        return result
    except TimeoutException:
        print(f"[{shop_name}] Ошибка 504. Таймаут ответа API Лэтуаль.")
        return None
    except Exception as e:
        print(f"[{shop_name}] Ошибка выполнения скрипта fetch: {e}")
        return None

def process_product_json(item, retail_name, city_name, shop_name):
    try:
        brand = item.get("brandName", "")
        product_name = item.get("displayName", "")
        url_path = item.get("url", "")
        full_url = f"https://www.letu.ru{url_path}" if url_path else ""

        price_data = item.get("price", {})
        base_price_data = item.get("basePrice", {})
        
        p_promo = float(price_data.get("value", 0)) if price_data.get("value") else 0.0
        p_base = float(base_price_data.get("value", p_promo)) if base_price_data.get("value") else p_promo
        
        if p_promo == p_base or p_promo == 0.0:
            p_promo = None

        photo = ""
        images = item.get("images", [])
        if images:
            photo = f"https://www.letu.ru{images[0]}"

        rating = item.get("rating")
        stock = 0 if item.get("isOutOfStock") else 1
        
        sku_name = item.get("minSkuName", "")
        volume = ""
        weight = ""
        
        if sku_name:
            sku_lower = sku_name.lower()
            if "шт" in sku_lower or "г" in sku_lower or "кг" in sku_lower:
                weight = sku_name
            else:
                volume = sku_name

        gtin = ""
        sku_list = item.get("skuList", [])
        if sku_list:
            gtin = sku_list[0].get("article", "")

        return {
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Магазин",
            "Адрес Торговой точки": city_name,
            "Бренд": brand,
            "Название продукта": product_name,
            "Цена": p_base,
            "Цена по акции": p_promo,
            "Фото товара": photo,
            "Ссылка на страницу": full_url,
            "Рейтинг": rating,
            "Объем": volume,
            "Вес": weight,
            "Остаток": stock,
            "GTIN": gtin
        }
    except Exception as e:
        print(f"[{shop_name}] Ошибка разбора JSON карточки: {e}")
        return None