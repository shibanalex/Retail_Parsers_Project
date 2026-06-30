import time
import random
import re
import urllib.parse
from bs4 import BeautifulSoup


#Переменная количества
MAX_PRODUCTS_PER_QUERY = 30  

def smart_sleep(driver, fallback=2.0):
    if hasattr(driver, 'custom_min_delay') and hasattr(driver, 'custom_max_delay'):
        time.sleep(random.uniform(driver.custom_min_delay, driver.custom_max_delay))
    else:
        time.sleep(fallback)

def check_and_bypass_waf(driver, shop_name):
    page = driver.page
    try:
        for _ in range(4):
            title = page.title.lower()
            html = page.html.lower()
            
            if "just a moment" in title or "checking" in html or "cloudflare" in title or "qrator" in title:
                print(f"[{shop_name}] Антибот активен.")
                time.sleep(5)
                
                try:
                    cb = page.ele('@type=checkbox')
                    if cb:
                        cb.click()
                        print(f"[{shop_name}] Кликнули по чекбоксу Cloudflare.")
                        time.sleep(3)
                except:
                    pass
            else:
                break
    except:
        pass
    
    try:
        cookie_btn = page.ele('text:Принять', timeout=1) or page.ele('text:ОК', timeout=1)
        if cookie_btn:
            cookie_btn.click()
    except:
        pass

    return True

def set_city(driver, city_name, shop_name):
    page = driver.page
    try:
        page.get("https://www.ozon.ru/")
        smart_sleep(driver, 3.0)
        check_and_bypass_waf(driver, shop_name)
        return 200
    except Exception as e:
        print(f"[{shop_name}] Ошибка 404. Не удалось загрузить Ozon.")
        return 404

def get_product_links(driver, query, shop_name):
    page = driver.page
    links = set()
    try:
        page.get("https://www.ozon.ru/")
        smart_sleep(driver, 3.0)
        check_and_bypass_waf(driver, shop_name)
        
        search_input = page.ele('@name=text')
        if search_input:
            search_input.clear()
            search_input.input(query)
            smart_sleep(driver, 1.0)
            search_input.input('\n') 
        else:
            encoded_query = urllib.parse.quote(query)
            page.get(f"https://www.ozon.ru/search/?text={encoded_query}&from_global=true")
            
        smart_sleep(driver, 5.0)
        check_and_bypass_waf(driver, shop_name)
        
        retries = 0       
        max_retries = 3   
        
        while True:
            soup = BeautifulSoup(page.html, 'html.parser')
            product_cards = soup.find_all('a', href=re.compile(r'/product/'))
            
            links_count_before = len(links)
            
            for card in product_cards:
                href = card.get('href', '')
                if '/product/' in href and not 'reviews' in href and not 'questions' in href:
                    clean_url = href.split('?')[0]
                    if not clean_url.startswith('http'):
                        clean_url = f"https://www.ozon.ru{clean_url}"
                    links.add(clean_url)
                    
                    if len(links) >= MAX_PRODUCTS_PER_QUERY:
                        break
                        
            if len(links) >= MAX_PRODUCTS_PER_QUERY:
                break
                    
            if len(links) > links_count_before:
                retries = 0
            else:
                retries += 1
                
            if retries >= max_retries:
                break
                
            try:
                page.scroll.down(800)
            except:
                pass
                
            smart_sleep(driver, 2.0)
            
        print(f"[{shop_name}] Найдено ссылок для сбора: {len(links)}")
        
    except Exception as e:
        print(f"[{shop_name}] Ошибка при поиске '{query}'.")
        
    return list(links)[:MAX_PRODUCTS_PER_QUERY]

def clean_price(price_str):
    if not price_str: return 0.0
    price_str = price_str.lower().split('за')[0]
    cleaned = re.sub(r'[^\d.,]', '', price_str.replace(',', '.'))
    try:
        return float(cleaned.rstrip('.'))
    except:
        return 0.0

def parse_product(driver, product_url, retail_name, city_name, shop_name):
    page = driver.page
    results = []
    try:
        page.get(product_url)
        smart_sleep(driver, 3.0)
        check_and_bypass_waf(driver, shop_name)
        
        try:
            page.wait.ele_displayed('tag:h1', timeout=10)
        except:
            pass
            
        try:
            btn = page.ele('text:Перейти к описанию', timeout=1) or page.ele('text:Все характеристики', timeout=1)
            if btn: btn.click()
        except:
            pass
            
        try:
            page.scroll.down(1200)
            smart_sleep(driver, 1.5)
        except:
            pass

        soup = BeautifulSoup(page.html, 'html.parser')
        
        h1_tag = soup.find('h1')
        product_name = h1_tag.text.strip() if h1_tag else "Неизвестный товар"
        
        photo_url = ""
        img_tags = soup.find_all('img', src=re.compile(r'/s3/multimedia'))
        for img in img_tags:
            src = img.get('src', '')
            if 'wc1000' in src or 'wc500' in src:
                photo_url = src
                break
        if not photo_url and img_tags:
            photo_url = img_tags[0].get('src', '')
            
        if photo_url:
            photo_url = re.sub(r'/wc\d+/', '/wc1000/', photo_url)
            
        price_base = 0.0
        price_promo = None
        price_widget = soup.find(attrs={"data-widget": "webPrice"})
        if price_widget:
            price_spans = price_widget.find_all('span', string=re.compile(r'₽'))
            prices = []
            for span in price_spans:
                p = clean_price(span.text)
                if p > 0:
                    prices.append(p)
            if prices:
                prices = sorted(list(set(prices)))
                if len(prices) >= 2:
                    price_promo = prices[0]
                    price_base = prices[-1]
                else:
                    price_base = prices[0]

        brand = ""
        volume = ""
        weight = ""
        gtin = ""
        
        brand_link = soup.find('a', href=re.compile(r'/brand/'))
        if brand_link:
            brand = brand_link.get_text(" ", strip=True).replace('Бренд • Оригинал', '').strip()

        specs = {}
        for node in soup.find_all(string=True):
            text_val = node.strip()
            if not text_val: continue
            
            text_lower = text_val.lower().replace(':', '').replace('\xa0', ' ')
            keys = ['бренд', 'объем', 'объём', 'вес', 'артикул', 'штрихкод']
            
            is_key = False
            for k in keys:
                if text_lower == k or text_lower.startswith(f"{k},") or text_lower.startswith(f"{k} "):
                    is_key = True
                    break
                    
            if is_key and len(text_lower) < 30:
                p = node.parent
                for _ in range(4):
                    if not p: break
                    sib = p.find_next_sibling()
                    if sib and sib.name in ['div', 'dd', 'span', 'p']:
                        val = sib.get_text(" ", strip=True)
                        if val:
                            specs[text_lower] = val
                            break
                    p = p.parent

        for k, v in specs.items():
            if 'бренд' in k and not brand:
                brand = v
            elif 'объем' in k or 'объём' in k:
                volume = v
            elif 'вес' in k:
                weight = v
            elif 'артикул' in k or 'штрихкод' in k:
                gtin = v

        rating = None
        reviews = 0
        review_link = soup.find('a', href=re.compile(r'/reviews/'))
        if review_link:
            text = review_link.get_text(" ", strip=True)
            match = re.search(r'(\d+[.,]\d+).*?([\d\s]+)\s*отзыв', text, re.I)
            if match:
                try:
                    rating = float(match.group(1).replace(',', '.'))
                    reviews = int(re.sub(r'[^\d]', '', match.group(2)))
                except:
                    pass

        stock_int = 1
        
        full_text = soup.get_text(separator=" ", strip=True).lower()
        
        if re.search(r'нет в наличии|товар закончился', full_text):
            stock_int = 0
        else:
            stock_match = re.search(r'(\d[\d\s\xa0\u2009]*?)\s*(?:шт\.?|единиц[а-я]?)\s*осталось', full_text)
            if stock_match:
                try:
                    num_str = re.sub(r'\D', '', stock_match.group(1))
                    if num_str:
                        stock_int = int(num_str)
                except:
                    pass

        results.append({
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Маркетплейс",
            "Адрес Торговой точки": f"{city_name} (Интернет-магазин / Доставка)",
            "Бренд": brand,
            "Название продукта": product_name,
            "Цена": price_base,
            "Цена по акции": price_promo,
            "Фото товара": photo_url,
            "Ссылка на страницу": product_url,
            "Рейтинг": rating,
            "Объем": volume,
            "Вес": weight,
            "Остаток": stock_int,
            "GTIN": gtin
        })

    except Exception as e:
        print(f"[{shop_name}] Ошибка при парсинге карточки товара.")
        
    return results