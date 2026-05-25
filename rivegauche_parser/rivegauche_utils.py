import time
import random
import re
import requests

CITY_CODES = {
    "москва": "city_4400",
    "санкт-петербург": "city_4962",
    "воронеж": "city_3538",
    "екатеринбург": "city_5106",
    "казань": "city_5269",
    "калининград": "city_3770",
    "краснодар": "city_4079",
    "красноярск": "city_4149",
    "нижний новгород": "city_3612",
    "новосибирск": "city_4549",
    "омск": "city_4580",
    "ростов-на-дону": "city_4848",
    "самара": "city_4917",
    "тюмень": "city_5395",
    "уфа": "city_3345"
}

def smart_sleep(min_val=0.5, max_val=1.5):
    time.sleep(random.uniform(min_val, max_val))

def get_session():
    session = requests.Session()
    session.headers.update({
        "Accept": "application/json",
        "Origin": "https://rivegauche.ru",
        "Referer": "https://rivegauche.ru/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    })
    return session

def set_city(session, city_name, shop_name):
    city_key = city_name.lower().strip()
    city_code = CITY_CODES.get(city_key)

    if not city_code:
        return 999

    try:
        session.cookies.set(
            "newRG-customer-location-approved-city-code",
            city_code,
            domain=".rivegauche.ru"
        )
        return 200
    except Exception as e:
        print(f"[{shop_name}] Ошибка установки города {city_name}: {e}")
        return 500

def fetch_api_data(session, query, offset, size, shop_name):
    url = "https://api.rivegauche.ru/rg/v1/newRG/products/ac-search"
    params = {
        "fields": "BASIC",
        "offset": offset,
        "size": size,
        "st": query,
        "rmSessionId": str(random.randint(100000, 999999))
    }

    try:
        response = session.get(url, params=params, timeout=15)
        if response.status_code == 200:
            return response.json()
        elif response.status_code in [403, 429]:
            print(f"[{shop_name}] Ошибка {response.status_code}. API ограничило запросы.")
            return None
        else:
            print(f"[{shop_name}] Ошибка API: код {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        print(f"[{shop_name}] Ошибка 504. Таймаут ответа API Рив Гош.")
        return None
    except Exception as e:
        print(f"[{shop_name}] Ошибка выполнения GET запроса: {e}")
        return None

def _extract_volume_weight(product_name):
    volume = ""
    weight = ""
    match = re.search(r'(\d+[\.,]?\d*)\s*(мл|л|г|кг|шт\.?)', product_name.lower())
    if match:
        val, unit = match.groups()
        if "шт" in unit or "г" in unit or "кг" in unit:
            weight = f"{val} {unit}"
        else:
            volume = f"{val} {unit}"
    return volume, weight

def process_product_json(item, retail_name, city_name, shop_name):
    try:
        brand = item.get("brand", "")
        product_name = item.get("name", "")
        
        url_path = item.get("linkUrl", "")
        full_url = f"https://rivegauche.ru{url_path}" if url_path else ""

        current_price = float(item.get("price") or 0.0)
        old_price = float(item.get("oldPrice") or current_price)
        
        if current_price == old_price or current_price == 0.0:
            p_base = current_price
            p_promo = None
        else:
            p_base = old_price
            p_promo = current_price

        photo = item.get("imageUrl", "")
        if photo and not photo.startswith("http"):
            photo = f"https://api.rivegauche.ru{photo}"

        rating = item.get("externalRating")
        stock = 1 if item.get("available") else 0

        volume = ""
        weight = ""
        attributes = item.get("attributes", {})
        
        for key, val in attributes.items():
            if not val:
                continue
            key_lower = key.lower()
            
            if "объем" in key_lower:
                unit = key_lower.split(',')[-1].strip() if ',' in key_lower else ""
                v_str = "/".join(str(x) for x in val)
                volume = f"{v_str} {unit}".strip()
            elif "вес" in key_lower:
                unit = key_lower.split(',')[-1].strip() if ',' in key_lower else ""
                w_str = "/".join(str(x) for x in val)
                weight = f"{w_str} {unit}".strip()

        if not volume and not weight:
            volume, weight = _extract_volume_weight(product_name)

        gtin = ""
        barcodes = attributes.get("barcode", [])
        if barcodes:
            gtin = str(barcodes[0])

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