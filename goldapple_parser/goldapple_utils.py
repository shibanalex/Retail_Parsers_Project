import time
import random
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException


CITY_IDS = {
    "москва": "0c5b2444-70a0-4932-980c-b4dc0d3f02b5",
    "санкт-петербург": "c2deb16a-0330-4f05-821f-1d09c93331e6",
    "екатеринбург": "2763c110-cb8b-416a-9dac-ad28a55b4402",
    "краснодар": "7dfa745e-aa19-4688-b121-b655c11e482f",
    "ростов-на-дону": "c1cfe4b9-f7c2-423c-abfa-6ed1c05a15c5",
    "самара": "bb035cc3-1dc2-4627-9d25-a1bf2d4b936b",
    "новосибирск": "8dea00e3-9aab-4d8e-887c-ef2aaa546456",
    "казань": "93b3df57-4c89-44df-ac42-96f05e9cd3b9",
    "нижний новгород": "555e7d61-d9a7-4ba6-9770-6caa8198c483",
    "воронеж": "5bf5ddff-6353-4a3d-80c4-6fb27f00c6c1",
    "челябинск": "a376e68d-724a-4472-be7c-891bdb09ae32",
    "уфа": "7339e834-2cb4-4734-a4c7-1fca2c66e562"
}

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

def set_city(driver, city_name, shop_name):
    city_id = CITY_IDS.get(city_name.lower().strip())
    if not city_id:
        return 999, None

    try:
        driver.get("https://goldapple.ru/")
        if not check_and_bypass_waf(driver, shop_name):
            return 403, None
        
        smart_sleep(driver, 3.0)
        return 200, city_id
    except Exception as e:
        print(f"[{shop_name}] Ошибка инициализации сессии браузера: {e}")
        return 500, None

def fetch_api_data(driver, query, page_num, city_id, shop_name):
    js_script = """
    var callback = arguments[arguments.length - 1];
    var query = arguments[0];
    var pageNum = arguments[1];
    var cityId = arguments[2];

    fetch('https://goldapple.ru/front/api/catalog/search-products?locale=ru', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'application/json, text/plain, */*',
            'plaid-city-id': cityId,
            'plaid-region-id': cityId,
            'plaid-platform': 'web',
            'plaid-store-id': 'ru',
            'plaid-language-id': 'ru_RU'
        },
        body: JSON.stringify({
            "pageNumber": pageNum,
            "filters": [{
                "value": query,
                "id": "q",
                "type": "queryType",
                "name": "q",
                "key": "q",
                "isFast": false
            }],
            "cityId": cityId,
            "regionId": cityId,
            "geoPolygons": []
        })
    })
    .then(response => response.json())
    .then(data => callback(data))
    .catch(error => callback({'error': error.toString()}));
    """
    
    try:
        driver.set_script_timeout(15)
        result = driver.execute_async_script(js_script, query, page_num, city_id)
        
        if result and 'error' in result:
            print(f"[{shop_name}] Ошибка XHR запроса: {result['error']}")
            return None
            
        return result
    except TimeoutException:
        print(f"[{shop_name}] Ошибка 504. Таймаут ответа API.")
        return None
    except Exception as e:
        print(f"[{shop_name}] Ошибка выполнения скрипта fetch: {e}")
        return None

def process_product_json(item, retail_name, city_name, shop_name):
    try:
        brand = item.get("brand", "")
        product_name = item.get("name", "")
        
        url_path = item.get("url", "")
        full_url = f"https://goldapple.ru{url_path}" if url_path else ""

        price_obj = item.get("price", {})
        p_promo = float(price_obj.get("actual", {}).get("amount", 0.0) if price_obj.get("actual") else 0.0)
        p_base = float(price_obj.get("regular", {}).get("amount", p_promo) if price_obj.get("regular") else p_promo)
        
        if p_promo == p_base or p_promo == 0.0:
            p_promo = None

        photo = ""
        image_urls = item.get("imageUrls", [])
        if image_urls:
            raw_url = image_urls[0].get("url", "")
            photo = raw_url.replace("${screen}", "fullhd").replace("${format}", "webp")

        rating = item.get("reviews", {}).get("rating")
        stock = 1 if item.get("inStock") else 0
        gtin = str(item.get("itemId", ""))

        volume = ""
        weight = ""
        units = item.get("attributes", {}).get("units", {})
        if units:
            val = units.get("currentUnitValue", "")
            unit_name = units.get("name", "").lower()
            combined = f"{val} {unit_name}".strip()
            
            if "шт" in unit_name or "г" in unit_name or "кг" in unit_name:
                weight = combined
            else:
                volume = combined

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