import time
import random
import re
import urllib.parse


MAX_PRODUCTS_PER_QUERY = 100 


_cached_catalog_products = {}

WB_CITY_DEST = {
    "москва": "-1257786",
    "санкт-петербург": "-1029256",
    "казань": "-1221148",
    "новосибирск": "-1221185",
    "екатеринбург": "-1221151",
    "краснодар": "-1221148"
}

def smart_sleep(driver, fallback=2.0):
    if hasattr(driver, 'custom_min_delay') and hasattr(driver, 'custom_max_delay'):
        time.sleep(random.uniform(driver.custom_min_delay, driver.custom_max_delay))
    else:
        time.sleep(fallback)

def check_and_bypass_waf(driver, shop_name):
    return True

def safe_get(session, url, shop_name, max_retries=3):
    """Безопасный запрос с обработкой ошибки 429 (Too Many Requests)"""
    delay = 3.0
    for attempt in range(max_retries):
        try:
            resp = session.get(url, timeout=10)
            if resp.status_code == 200:
                return resp
            elif resp.status_code == 429:
                print(f"[{shop_name}] Ошибка 429. Авто-пауза {delay} сек. перед повтором...")
                time.sleep(delay)
                delay *= 2.0  
            else:
                break
        except Exception:
            time.sleep(1.5)
    return None

def set_city(driver, city_name, shop_name):
    global _cached_catalog_products
    _cached_catalog_products = {}
    
    city_lower = city_name.lower().strip()
    driver.dest = WB_CITY_DEST.get(city_lower, "-1257786")
    return 200

def get_wb_basket_number(vol):
    if 0 <= vol <= 143: return '01'
    if 144 <= vol <= 287: return '02'
    if 288 <= vol <= 431: return '03'
    if 432 <= vol <= 719: return '04'
    if 720 <= vol <= 1007: return '05'
    if 1008 <= vol <= 1061: return '06'
    if 1062 <= vol <= 1115: return '07'
    if 1116 <= vol <= 1169: return '08'
    if 1170 <= vol <= 1313: return '09'
    if 1314 <= vol <= 1601: return '10'
    if 1602 <= vol <= 1655: return '11'
    if 1656 <= vol <= 1919: return '12'
    if 1920 <= vol <= 2045: return '13'
    if 2046 <= vol <= 2189: return '14'
    if 2190 <= vol <= 2405: return '15'
    if 2406 <= vol <= 2621: return '16'
    if 2622 <= vol <= 2837: return '17'
    if 2838 <= vol <= 3053: return '18'
    if 3054 <= vol <= 3269: return '19'
    if 3270 <= vol <= 3485: return '20'
    if 3486 <= vol <= 3701: return '21'
    return '22'

def extract_volume_weight_from_name(name):
    """Резервное извлечение объема и веса из названия товара"""
    weight, volume = "", ""
    txt_lower = name.lower()
    
    
    w_m = re.search(r'(\d+[.,]?\d*)\s*(г|кг)\b', txt_lower)
    if w_m:
        weight = w_m.group(0)
        
    
    v_m = re.search(r'(\d+[.,]?\d*)\s*(мл|л)\b', txt_lower)
    if v_m:
        volume = v_m.group(0)
        
    return volume, weight

def get_product_links(driver, query, shop_name):
    global _cached_catalog_products
    session = driver.session
    links = []
    
    encoded_query = urllib.parse.quote(query)
    dest = getattr(driver, "dest", "-1257786")
    
    page_num = 1
    
    while len(links) < MAX_PRODUCTS_PER_QUERY:
        search_url = (
            f"https://search.wb.ru/exactmatch/ru/common/v18/search"
            f"?appType=1&curr=rub&dest={dest}&lang=ru&page={page_num}"
            f"&query={encoded_query}&resultset=catalog&sort=popular&spp=30"
        )
        
        resp = safe_get(session, search_url, shop_name)
        if not resp:
            print(f"[{shop_name}] Прерывание сбора на стр. {page_num}.")
            break
            
        try:
            data = resp.json()
            products = data.get("data", {}).get("products", [])
            if not products:
                products = data.get("products", [])
                
            if not products:
                break
                
            for p in products:
                item_id = p.get("id")
                if not item_id:
                    continue
                    
                item_id = int(item_id)
                url = f"https://www.wildberries.ru/catalog/{item_id}/detail.aspx"
                
                if url in _cached_catalog_products:
                    continue
                    
                name = p.get("name", "Неизвестный товар")
                brand = p.get("brand", "")
                
                price_base = 0.0
                price_promo = None
                sizes = p.get("sizes", [])
                if sizes:
                    price_data = sizes[0].get("price", {})
                    b_price = price_data.get("basic", 0) / 100.0
                    p_price = price_data.get("product", 0) / 100.0
                    
                    if b_price > 0:
                        price_base = b_price
                        if p_price > 0 and p_price < b_price:
                            price_promo = p_price
                        else:
                            price_base = p_price if p_price > 0 else b_price
                
                rating = p.get("reviewRating") or p.get("rating", 0)
                rating = float(rating) if rating else None
                stock_int = p.get("totalQuantity", 1)
                
                _cached_catalog_products[url] = {
                    "id": item_id,
                    "name": name,
                    "brand": brand,
                    "price_base": price_base,
                    "price_promo": price_promo,
                    "rating": rating,
                    "stock": stock_int
                }
                
                links.append(url)
                if len(links) >= MAX_PRODUCTS_PER_QUERY:
                    break
                    
            page_num += 1
            smart_sleep(driver, 1.5) 
            
        except Exception as e:
            print(f"[{shop_name}] Ошибка при обработке JSON поиска '{query}': {e}")
            break
            
    print(f"[{shop_name}] Найдено {len(links)} карточек товаров.")
    return links

def parse_product(driver, product_url, retail_name, city_name, shop_name):
    global _cached_catalog_products
    session = driver.session
    results = []
    
    if product_url not in _cached_catalog_products:
        return results
        
    c = _cached_catalog_products[product_url]
    item_id = c["id"]
    
    vol = item_id // 100000
    part = item_id // 1000
    basket = get_wb_basket_number(vol)
    
    photo_url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{item_id}/images/big/1.jpg"
    info_url = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{item_id}/info/ru/info.json"
    
    volume = ""
    weight = ""
    gtin = ""
    
    
    resp = safe_get(session, info_url, shop_name, max_retries=2)
    if resp:
        try:
            info_data = resp.json()
            options = info_data.get("options", [])
            for opt in options:
                name_attr = opt.get("name", "").lower()
                val_attr = str(opt.get("value", ""))
                
                if "вес" in name_attr and not "с упаковкой" in name_attr:
                    weight = val_attr
                elif "объем" in name_attr or "объём" in name_attr:
                    volume = val_attr
                elif "штрихкод" in name_attr or "gtin" in name_attr or "barcode" in name_attr:
                    gtin = val_attr
            
            if not weight:
                for opt in options:
                    if "вес" in opt.get("name", "").lower():
                        weight = str(opt.get("value", ""))
                        break
        except Exception:
            pass

    
    fallback_vol, fallback_wt = extract_volume_weight_from_name(c["name"])
    if not volume:
        volume = fallback_vol
    if not weight:
        weight = fallback_wt

    results.append({
        "Номер": 0,
        "Сеть": retail_name,
        "Тип магазина": "Маркетплейс",
        "Адрес Торговой точки": f"{city_name} (ПВЗ / Доставка)",
        "Бренд": c["brand"],
        "Название продукта": c["name"],
        "Цена": c["price_base"],
        "Цена по акции": c["price_promo"],
        "Фото товара": photo_url,
        "Ссылка на страницу": product_url,
        "Рейтинг": c["rating"],
        "Объем": volume,
        "Вес": weight,
        "Остаток": c["stock"],
        "GTIN": gtin
    })
        
    return results