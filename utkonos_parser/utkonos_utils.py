import time
import random
import re
import urllib.parse

MAX_PRODUCTS_PER_QUERY = 40
_cached_catalog_products = {}

def smart_sleep(driver, fallback=2.0):
    if hasattr(driver, 'custom_min_delay') and hasattr(driver, 'custom_max_delay'):
        time.sleep(random.uniform(driver.custom_min_delay, driver.custom_max_delay))
    else:
        time.sleep(fallback)

def check_and_bypass_waf(page):
    try:
        if "qrator" in page.title.lower():
            time.sleep(5)
    except:
        pass

def set_city(driver, city_name, shop_name):
    global _cached_catalog_products
    _cached_catalog_products = {}
    page = driver.page
    
    try:
        
        page.get("https://www.utkonos.ru/")
        time.sleep(3.0)
        check_and_bypass_waf(page)

        
        header = page.ele('tag:header', timeout=2)
        if header and city_name.lower() in header.text.lower():
            return 200

        
        addr_btn = page.ele('text:Укажите адрес', timeout=1) or page.ele('css:[class*="address"]', timeout=1) or page.ele('text:Доставка', timeout=1) or page.ele('text:Москва', timeout=1)
        if addr_btn:
            addr_btn.click()
            time.sleep(2.0)
            
            
            inp = page.ele('tag:input', timeout=2) or page.ele('@placeholder:Введите', timeout=1)
            if inp:
                inp.clear()
                
                inp.input(f"{city_name}, Ленина, 1")
                time.sleep(3.0) 
                
                
                sugg = page.ele('css:li', timeout=2) or page.ele('text:Ленина', timeout=1)
                if sugg:
                    sugg.click()
                    time.sleep(1.5)
                    
                    
                    submit = page.ele('text:Сохранить', timeout=1) or page.ele('text:Выбрать', timeout=1) or page.ele('text:Подтвердить', timeout=1)
                    if submit:
                        submit.click()
                        time.sleep(2.0)

        return 200
    except Exception as e:
        print(f"[{shop_name}] Ошибка установки города: {e}")
        return 404

def get_product_links(driver, query, shop_name):
    global _cached_catalog_products
    page = driver.page
    links = []

    try:
        encoded_query = urllib.parse.quote(query)
        search_url = f"https://www.utkonos.ru/search/{encoded_query}/"

        print(f"[{shop_name}] Включаю перехват API-пакетов...")
        
        page.listen.start('api-gateway/v1/catalog/items')
        
        
        page.get(search_url)
        check_and_bypass_waf(page)

        
        packet = page.listen.wait(timeout=10)
        
        if packet and packet.response and packet.response.body:
            data = packet.response.body
            items = data.get("items", [])
            
            for item in items:
                item_id = str(item.get("id") or item.get("sku", ""))
                slug = str(item.get("slug", ""))
                if not item_id: continue
                
                url = f"https://www.utkonos.ru/product/{slug}" if slug else f"https://www.utkonos.ru/item/{item_id}"
                name = item.get("name") or item.get("title", "Неизвестный товар")
                
                
                price_base = 0.0
                price_promo = None
                
                prices = item.get("prices", {})
                
                
                p_reg = prices.get("priceRegular", 0) / 100.0
                p_card = prices.get("price", 0) / 100.0
                
                if p_reg > 0 and p_card > 0 and p_card < p_reg:
                    price_base = p_reg
                    price_promo = p_card
                else:
                    price_base = p_reg if p_reg > 0 else p_card
                
                
                photo = ""
                images = item.get("images", [])
                if images:
                    img_obj = images[0]
                    photo = img_obj.get("original") or img_obj.get("large") or img_obj.get("medium") or ""
                
                
                stock_int = int(item.get("count", 1))
                
                
                rating_val = None
                rating_dict = item.get("rating", {})
                if rating_dict:
                    rate = rating_dict.get("rate", 0)
                    if rate > 0:
                        rating_val = float(rate)
                    
                
                volume, weight = "", ""
                
                
                package = item.get("display", {}).get("package", "")
                if not package:
                    package = item.get("weight", {}).get("package", "")
                    
                if "мл" in package.lower() or "л" in package.lower() or "ml" in package.lower() or "l" in package.lower():
                    volume = package
                elif "г" in package.lower() or "кг" in package.lower():
                    weight = package

                
                brand = ""
                brand_match = re.search(r'([A-ZА-ЯA-ZА-Я0-9-]{3,})', name)
                if brand_match:
                    
                    words = [w for w in name.split() if w.isupper() and len(w) > 2]
                    if words:
                        brand = " ".join(words)

                
                _cached_catalog_products[url] = {
                    "Название продукта": name,
                    "Цена": price_base,
                    "Цена по акции": price_promo,
                    "Остаток": stock_int,
                    "Рейтинг": rating_val,
                    "Фото товара": photo,
                    "Бренд": brand,
                    "GTIN": str(item_id),
                    "Объем": volume,
                    "Вес": weight
                }
                links.append(url)
                if len(links) >= MAX_PRODUCTS_PER_QUERY:
                    break
                    
        page.listen.stop()
        print(f"[{shop_name}] Найдено {len(links)} ссылок (успешно вытащено через перехват POST /items).")
        return links

    except Exception as e:
        print(f"[{shop_name}] Ошибка API поиска '{query}': {e}")
        try: page.listen.stop() 
        except: pass
        return []

def parse_product(driver, product_url, retail_name, city_name, shop_name):
    global _cached_catalog_products
    
    
    if product_url in _cached_catalog_products:
        c = _cached_catalog_products[product_url]
        return [{
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Магазин",
            "Адрес Торговой точки": f"{city_name}",
            "Бренд": c["Бренд"], 
            "Название продукта": c["Название продукта"],
            "Цена": c["Цена"],
            "Цена по акции": c["Цена по акции"],
            "Фото товара": c["Фото товара"],
            "Ссылка на страницу": product_url,
            "Рейтинг": c["Рейтинг"],
            "Объем": c["Объем"],
            "Вес": c["Вес"],
            "Остаток": c["Остаток"],
            "GTIN": c["GTIN"]
        }]
        
    return []