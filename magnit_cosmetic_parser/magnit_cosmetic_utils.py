import time
import random
import re
import uuid
import requests

def smart_sleep(min_val=0.5, max_val=1.5):
    time.sleep(random.uniform(min_val, max_val))

def get_session():
    session = requests.Session()
    device_id = str(uuid.uuid4())
    
    session.headers.update({
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": "https://cosmetic.magnit.ru",
        "Referer": "https://cosmetic.magnit.ru/",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
        "X-Client-Name": "cosmetic",
        "X-Device-Platform": "Web",
        "X-New-Magnit": "true",
        "X-Device-Id": device_id
    })
    return session

def get_store_codes(session, city_name, shop_name):
    url = "https://cosmetic.magnit.ru/webgate/v1/stores-facade/search/detail"
    offset = 0
    size = 50
    stores = []
    
    while True:
        payload = {
            "filters": {
                "query": city_name,
                "deliveryTypeList": ["DELIVERY_TYPE_PICKUP"],
                "storeTypeListV2": ["DG"]
            },
            "pagination": {
                "offset": offset,
                "size": size
            },
            "sorting": {
                "sortBy": "SORT_BY_CITY",
                "sortType": "SORT_TYPE_ASC"
            }
        }

        try:
            response = session.post(url, json=payload, timeout=15)
            if response.status_code == 200:
                data = response.json().get("data", [])
                if not data:
                    break
                
                for store in data:
                    store_code = store.get("externalId", {}).get("storeCode")
                    address = store.get("address")
                    if store_code:
                        stores.append((store_code, address))
                        
                if len(data) < size:
                    break
                
                offset += size
                smart_sleep(0.5, 1.0)
            else:
                print(f"[{shop_name}] Ошибка получения магазинов. Код ответа: {response.status_code}")
                break
        except Exception as e:
            print(f"[{shop_name}] Исключение при получении магазинов для {city_name}: {e}")
            break
            
    return stores

def fetch_api_data(session, query, offset, limit, store_code, shop_name):
    url = "https://cosmetic.magnit.ru/webgate/v2/goods/search"
    payload = {
        "term": query,
        "pagination": {
            "offset": offset,
            "limit": limit
        },
        "sort": {
            "order": "desc",
            "type": "popularity"
        },
        "storeCode": str(store_code),
        "storeType": "cosmetic",
        "catalogType": "3",
        "includeAdultGoods": True
    }

    try:
        response = session.post(url, json=payload, timeout=15)
        if response.status_code == 200:
            return response.json()
        elif response.status_code in [403, 429]:
            print(f"[{shop_name}] Ошибка {response.status_code}. API ограничило запросы.")
            return None
        else:
            print(f"[{shop_name}] Ошибка API товаров: код {response.status_code}")
            return None
    except requests.exceptions.Timeout:
        print(f"[{shop_name}] Ошибка 504. Таймаут ответа API Магнит Косметик.")
        return None
    except Exception as e:
        print(f"[{shop_name}] Ошибка выполнения POST запроса товаров: {e}")
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

def process_product_json(item, retail_name, address, shop_name):
    try:
        brand = "" 
        product_name = item.get("name", "")
        
        product_id = item.get("productId") or item.get("id", "")
        full_url = f"https://cosmetic.magnit.ru/product/{product_id}/" if product_id else ""

        current_price_raw = item.get("price")
        current_price = (float(current_price_raw) / 100) if current_price_raw else 0.0
        
        promo = item.get("promotion", {})
        old_price_raw = promo.get("oldPrice")
        old_price = (float(old_price_raw) / 100) if old_price_raw else current_price
        
        if current_price < old_price and current_price != 0.0:
            p_base = old_price
            p_promo = current_price
        else:
            p_base = current_price
            p_promo = None

        gallery = item.get("gallery", [])
        photo = gallery[0].get("url", "") if gallery else ""

        ratings = item.get("ratings", {})
        rating = ratings.get("rating") if ratings else None
        
        stock = item.get("quantity", 0)

        volume, weight = _extract_volume_weight(product_name)
        gtin = item.get("id", "")

        return {
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Магазин",
            "Адрес Торговой точки": address,
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