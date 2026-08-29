import time
import random
import re
from urllib.parse import quote

MAX_PRODUCTS_PER_QUERY = 44

REGION_MAP = {
    "москва": "50",
    "санкт-петербург": "78",
    "новосибирск": "54",
    "екатеринбург": "66",
    "казань": "16",
    "нижний новгород": "52",
    "челябинск": "74",
    "самара": "63",
    "уфа": "02",
    "ростов-на-дону": "61",
    "краснодар": "23",
    "воронеж": "36",
    "пермь": "59",
    "волгоград": "34",
    "ульяновск": "73",
    "иваново": "37",
    "ярославль": "76",
    "владимир": "33",
    "тольятти": "63",
    "калуга": "40"
}

def smart_sleep(driver, fallback=1.5):
    min_d = getattr(driver, "custom_min_delay", fallback)
    max_d = getattr(driver, "custom_max_delay", fallback + 1.0)
    time.sleep(random.uniform(min_d, max_d))

def clean_price(price_val):
    if price_val is None:
        return 0.0
    if isinstance(price_val, (int, float)):
        return float(price_val)
    cleaned = re.sub(r"[^\d.,]", "", str(price_val).strip()).replace(",", ".")
    parts = cleaned.split(".")
    if len(parts) > 2:
        cleaned = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0

def extract_volume_weight(title_text):
    volume_str, weight_str = "", ""
    txt = str(title_text).lower()
    
    vol_match = re.search(r"(\d+[.,]?\d*)\s*(мл|л)\b", txt)
    if vol_match:
        volume_str = f"{vol_match.group(1)} {vol_match.group(2)}"
        
    w_match = re.search(r"(\d+[.,]?\d*)\s*(г|кг)\b", txt)
    if w_match:
        weight_str = f"{w_match.group(1)} {w_match.group(2)}"
        
    return volume_str, weight_str

def check_and_bypass_waf(driver, shop_name):
    try:
        driver.get("https://megamarket.ru/")
        time.sleep(2.5) # Даем DP прогрузить защитные скрипты Qrator
        return True
    except Exception:
        pass
    return True

def set_city(driver, city_name, shop_name):
    driver._product_cache = {}
    city_clean = city_name.strip().lower()
    
    region_id = REGION_MAP.get(city_clean)
    if not region_id:
        print(f"[{shop_name}] Город {city_name} не найден в справочнике")
        return 999
        
    driver.current_location_id = region_id
    print(f"[{shop_name}] Установлен город: {city_name} (Код: {region_id})")
    
    # Заходим на главную для установки сессии
    check_and_bypass_waf(driver, shop_name)
    return 200

def get_product_links(driver, query, shop_name):
    collected_links = []
    print(f"[{shop_name}] Сбор данных по запросу: {query}")
    
    # 1. Загружаем страницу поиска физически, чтобы обновить куки и токены для текущего запроса
    safe_query = quote(query)
    try:
        driver.get(f"https://megamarket.ru/catalog/?q={safe_query}")
        smart_sleep(driver, 1.5)
    except Exception as e:
        print(f"[{shop_name}] Ошибка при переходе на страницу поиска: {e}")

    # 2. Формируем Payload
    payload = {
        "requestVersion": 12,
        "merchant": {},
        "limit": MAX_PRODUCTS_PER_QUERY,
        "offset": 0,
        "isMultiCategorySearch": False,
        "searchByOriginalQuery": False,
        "searchText": query,
        "showNotAvailable": True,
        "sorting": 0,
        "auth": {
            "locationId": driver.current_location_id,
            "uuid": "",
            "appPlatform": "WEB",
            "appVersion": 1786947029
        }
    }

    # 3. Нативный JS Fetch (DP умеет работать с Promises)
    js_fetch = """
    return fetch('/api/mobile/v1/catalogService/catalog/search', {
        method: 'POST',
        headers: {
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        },
        body: JSON.stringify(arguments[0])
    })
    .then(r => r.json())
    .catch(e => { return {'error': e.toString()}; });
    """

    try:
        # Запускаем JS и ждем результат (JSON)
        response = driver.run_js(js_fetch, payload)
        
        if response and response.get("success"):
            items = response.get("items", [])
            for item in items:
                goods = item.get("goods", {})
                web_url = goods.get("webUrl", "")
                
                if web_url:
                    if not web_url.startswith("http"):
                        web_url = f"https://megamarket.ru{web_url}"
                        
                    # Сохраняем в кэш
                    driver._product_cache[web_url] = item
                    
                    if web_url not in collected_links:
                        collected_links.append(web_url)
        else:
            err_msg = response.get("error") if isinstance(response, dict) else "Unknown Response"
            print(f"[{shop_name}] Ошибка API-ответа или пустой результат. {err_msg}")
            
    except Exception as e:
        print(f"[{shop_name}] Исключение при API-поиске: {e}")

    return collected_links

def parse_product(driver, product_url, retail_name, city_name, shop_name):
    cached_data = getattr(driver, "_product_cache", {}).get(product_url)
    if not cached_data:
        return []

    try:
        goods = cached_data.get("goods", {})
        fav_offer = cached_data.get("favoriteOffer", {})

        product_name = goods.get("title", "")
        brand_text = goods.get("brand", "")
        gtin_text = str(goods.get("goodsId", ""))
        photo_url = goods.get("titleImage", "")
        
        rating_val = cached_data.get("rating")
        float_rating = float(rating_val) if rating_val is not None else None
        
        merchant_name = fav_offer.get("merchantName", "Мегамаркет")
        address_text = f"{city_name} ({merchant_name})"

        stock_int = int(goods.get("stocks", 0))
        if stock_int == 0 and cached_data.get("isAvailable"):
            stock_int = 1

        p_current = clean_price(fav_offer.get("finalPrice") or cached_data.get("price"))
        p_old = clean_price(fav_offer.get("oldPrice"))

        if p_old > p_current and p_current > 0:
            float_price_base = p_old
            float_price_promo = p_current
        else:
            float_price_base = p_current if p_current > 0 else p_old
            float_price_promo = None

        vol_str, weight_str = extract_volume_weight(product_name)
        
        return [{
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Маркетплейс",
            "Адрес Торговой точки": address_text,
            "Бренд": brand_text,
            "Название продукта": product_name,
            "Цена": float_price_base,
            "Цена по акции": float_price_promo,
            "Фото товара": photo_url,
            "Ссылка на страницу": product_url,
            "Рейтинг": float_rating,
            "Объем": vol_str,
            "Вес": weight_str,
            "Остаток": stock_int,
            "GTIN": gtin_text
        }]
    except Exception as e:
        print(f"[{shop_name}] Ошибка извлечения данных: {e}")
        return []