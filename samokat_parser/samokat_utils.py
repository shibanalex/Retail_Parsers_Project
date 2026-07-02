import time
import random
import re
import urllib.parse
from bs4 import BeautifulSoup

MAX_PRODUCTS_PER_QUERY = 100
_cached_catalog_products = {}

def smart_sleep(driver, fallback=2.0):
    if hasattr(driver, 'custom_min_delay') and hasattr(driver, 'custom_max_delay'):
        time.sleep(random.uniform(driver.custom_min_delay, driver.custom_max_delay))
    else:
        time.sleep(fallback)

def check_and_bypass_waf(page):
    try:
        cookie_btn = page.ele('text:Понятно', timeout=1) or page.ele('text:Принять', timeout=1)
        if cookie_btn:
            cookie_btn.click()
    except:
        pass

def set_city(driver, city_name, shop_name):
    global _cached_catalog_products
    _cached_catalog_products = {}
    page = driver.page
    
    try:
        page.get("https://samokat.ru/")
        smart_sleep(driver, 3.0)
        check_and_bypass_waf(page)

        header = page.ele('tag:header', timeout=2)
        if header:
            if city_name.lower() in header.text.lower():
                return 200

        addr_btn = page.ele('text:Указать адрес', timeout=2) or page.ele('text:Выбрать адрес', timeout=1) or page.ele('text:Доставка', timeout=1)
        if addr_btn:
            addr_btn.click()
            time.sleep(1.5)

        search_inp = page.ele('@placeholder:Улица', timeout=2) or page.ele('@placeholder:Введите адрес', timeout=1) or page.ele('tag:input', timeout=1)
        if search_inp:
            search_inp.clear()
            search_inp.input(f"{city_name}, Ленина, 1")
            time.sleep(3.0) 
            
            sugg = page.ele('text:Ленина', timeout=3) or page.ele('css:ul > li', timeout=1)
            if sugg:
                sugg.click()
                time.sleep(1.5)
                
                submit = page.ele('text:Продолжить', timeout=2) or page.ele('text:Выбрать', timeout=1) or page.ele('text:Сохранить', timeout=1)
                if submit:
                    submit.click()
                    time.sleep(3.0)
                    
        return 200
    except Exception as e:
        print(f"[{shop_name}] Ошибка установки адреса: {e}")
        return 404

def get_product_links(driver, query, shop_name):
    global _cached_catalog_products
    page = driver.page
    links = []

    try:
        page.get("https://samokat.ru/search")
        smart_sleep(driver, 2.0)
        check_and_bypass_waf(page)

        print(f"[{shop_name}] Перехват API-пакетов включен...")
        page.listen.start('api-web.samokat.ru/search/products')

        search_input = page.ele('@type=text', timeout=2) or page.ele('@placeholder:Искать', timeout=1)
        if search_input:
            
            search_input.clear()
            time.sleep(0.5)
            
            search_input.input(query + '\n')
        else:
            encoded_query = urllib.parse.quote(query)
            page.get(f"https://samokat.ru/search?value={encoded_query}")

        packet = page.listen.wait(timeout=10)
        
        if packet and packet.response and packet.response.body:
            data = packet.response.body
            
            if 'result' in data and len(data['result']) > 0:
                items = data['result'][0].get('items', [])
                for item in items:
                    slug = item.get('slug')
                    if not slug: continue
                    url = f"https://samokat.ru/product/{slug}"
                    
                    prices = item.get('prices', {})
                    price_cur = prices.get('current', 0) / 100.0
                    price_old = prices.get('old', price_cur * 100) / 100.0
                    
                    stock = item.get('quantity', 1) 
                    rating = item.get('rating', {}).get('average', None)
                    
                    photo = ""
                    if item.get('media'):
                        photo = item['media'][0].get('url', '')
                        
                    name = item.get('name', 'Неизвестный товар')
                    
                    
                    volume, weight = "", ""
                    net_unit = item.get('attributes', {}).get('netContentUnit', '')
                    variants = item.get('variants', {}).get('items', [])
                    
                    if variants:
                        val = variants[0].get('text', '')
                        if net_unit == 'ML' or net_unit == 'L':
                            volume = f"{val} {net_unit.lower()}"
                        elif net_unit == 'G' or net_unit == 'KG':
                            weight = f"{val} {net_unit.lower()}"
                    
                    
                    if not volume and not weight:
                        txt_lower = name.lower()
                        w_match = re.search(r'(\d+[.,]?\d*)\s*(г|кг)\b', txt_lower)
                        if w_match: weight = w_match.group(0)
                            
                        v_match = re.search(r'(\d+[.,]?\d*)\s*(мл|л)\b', txt_lower)
                        if v_match: volume = v_match.group(0)
                    
                    _cached_catalog_products[url] = {
                        "Название продукта": name,
                        "Цена": price_old if price_old > price_cur else price_cur,
                        "Цена по акции": price_cur if price_old > price_cur else None,
                        "Остаток": stock,
                        "Рейтинг": rating,
                        "Фото товара": photo,
                        "Объем": volume,
                        "Вес": weight,
                        "GTIN": item.get('id', ''), 
                    }
                    
                    links.append(url)
                    if len(links) >= MAX_PRODUCTS_PER_QUERY:
                        break

        page.listen.stop()
        
        if not links:
            smart_sleep(driver, 3.0)
            soup = BeautifulSoup(page.html, 'html.parser')
            cards = soup.find_all('a', href=re.compile(r'/product/'))
            for card in cards:
                href = card.get('href', '')
                clean_url = "https://samokat.ru" + href.split('?')[0] if not href.startswith('http') else href
                if clean_url not in links:
                    links.append(clean_url)
                if len(links) >= MAX_PRODUCTS_PER_QUERY:
                    break

        print(f"[{shop_name}] Найдено {len(links)} ссылок на карточки товаров.")
        return links

    except Exception as e:
        print(f"[{shop_name}] Ошибка при поиске '{query}': {e}")
        try:
            page.listen.stop()
        except:
            pass
        return []

def extract_volume_weight(name):
    weight, volume = "", ""
    txt_lower = name.lower()
    w_match = re.search(r'(\d+[.,]?\d*)\s*(г|кг)\b', txt_lower)
    if w_match: weight = w_match.group(0)
    v_match = re.search(r'(\d+[.,]?\d*)\s*(мл|л)\b', txt_lower)
    if v_match: volume = v_match.group(0)
    return volume, weight

def parse_product(driver, product_url, retail_name, city_name, shop_name):
    global _cached_catalog_products
    
    if product_url in _cached_catalog_products:
        cached = _cached_catalog_products[product_url]
        return [{
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Даркстор",
            "Адрес Торговой точки": f"{city_name} (Даркстор Самокат)",
            "Бренд": "", 
            "Название продукта": cached["Название продукта"],
            "Цена": cached["Цена"],
            "Цена по акции": cached["Цена по акции"],
            "Фото товара": cached["Фото товара"],
            "Ссылка на страницу": product_url,
            "Рейтинг": cached["Рейтинг"],
            "Объем": cached["Объем"],
            "Вес": cached["Вес"],
            "Остаток": cached["Остаток"],
            "GTIN": cached["GTIN"]
        }]

    results = []
    page = driver.page
    try:
        page.get(product_url)
        smart_sleep(driver, 2.0)
        
        soup = BeautifulSoup(page.html, 'html.parser')
        
        h1_tag = soup.find('h1')
        name = h1_tag.text.strip() if h1_tag else "Неизвестный товар"
        
        price_base = 0.0
        price_promo = None
        price_elements = soup.find_all('span', string=re.compile(r'₽'))
        prices = []
        for el in price_elements:
            cleaned = re.sub(r'[^\d.,]', '', el.text.replace(',', '.'))
            try:
                p = float(cleaned.rstrip('.'))
                if p > 0: prices.append(p)
            except: pass
                
        if prices:
            prices = sorted(list(set(prices)))
            if len(prices) >= 2:
                price_promo = prices[0]
                price_base = prices[-1]
            else:
                price_base = prices[0]

        photo_url = ""
        img_tag = soup.find('img', alt=name) or soup.find('img', fetchpriority="high")
        if img_tag and 'src' in img_tag.attrs:
            photo_url = img_tag['src']
            if not photo_url.startswith('http') and not photo_url.startswith('data:'): 
                photo_url = "https://samokat.ru" + photo_url

        volume, weight = extract_volume_weight(name)

        stock_int = 1
        if soup.find(string=re.compile(r'Нет в наличии|Раскупили', re.I)):
            stock_int = 0

        results.append({
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Даркстор",
            "Адрес Торговой точки": f"{city_name}",
            "Бренд": "",
            "Название продукта": name,
            "Цена": price_base,
            "Цена по акции": price_promo,
            "Фото товара": photo_url,
            "Ссылка на страницу": product_url,
            "Рейтинг": None,
            "Объем": volume,
            "Вес": weight,
            "Остаток": stock_int,
            "GTIN": ""
        })

    except Exception as e:
        print(f"[{shop_name}] Ошибка при парсинге резервной карточки: {e}")
        
    return results