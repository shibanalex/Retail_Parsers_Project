import time
import random
import re
import requests

# Города должны совпадать с апи
REGION_MAP = {
    "москва": "Москва и Московская область",
    "санкт-петербург": "Санкт-Петербург",
    "екатеринбург": "Екатеринбург",
    "казань": "Казань",
    "краснодар": "Краснодар",
    "новосибирск": "Новосибирск",
}

def smart_sleep(min_val=0.5, max_val=1.5):
    time.sleep(random.uniform(min_val, max_val))

def get_session():
    session = requests.Session()
    session.headers.update({
        "Accept": "*/*",
        "Origin": "https://iledebeaute.ru",
        "Referer": "https://iledebeaute.ru/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36"
    })
    return session

def fetch_api_data(session, query, offset, size, city_name, shop_name):
    url = "https://sort.diginetica.net/search"
    
    region_id = REGION_MAP.get(city_name.lower().strip(), city_name)

    params = {
        "st": query,
        "apiKey": "O08Q4M2T51",
        "strategy": "advanced_xname_test,zero_queries",
        "fullData": "true",
        "withCorrection": "true",
        "withFacets": "false",
        "treeFacets": "true",
        "regionId": region_id,
        "useCategoryPrediction": "false",
        "size": size,
        "offset": offset,
        "showUnavailable": "false",
        "unavailableMultiplier": "0.2",
        "preview": "false",
        "withSku": "true",
        "sort": "DEFAULT"
    }

    try:
        response = session.get(url, params=params, timeout=15)
        if response.status_code == 200:
            return response.json()
        elif response.status_code in [403, 429]:
            print(f"[{shop_name}] Ошибка {response.status_code}. Блокировка от Diginetica.")
            return None
        else:
            print(f"[{shop_name}] Ошибка API: код {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        print(f"[{shop_name}] Ошибка 504. Таймаут ответа API.")
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
        
        url_path = item.get("link_url", "")
        full_url = f"https://iledebeaute.ru{url_path}" if url_path else ""

        current_price = float(item.get("price") or 0.0)
        old_price = float(item.get("oldPrice") or current_price)
        
        if current_price == old_price or current_price == 0.0:
            p_base = current_price
            p_promo = None
        else:
            p_base = old_price
            p_promo = current_price

        photo = item.get("image_url", "")
        if photo and not photo.startswith("http"):
            photo = f"https://iledebeaute.ru{photo}"

        rating = None 
        stock = 1 if item.get("available") else 0

        volume, weight = _extract_volume_weight(product_name)

        gtin = str(item.get("id", ""))

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