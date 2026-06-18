import time
import random
import re
import os
import requests
import urllib.parse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

_cached_pdf_url = None
_cached_catalog_products = None

def smart_sleep(driver, fallback=2.0):
    if hasattr(driver, 'custom_min_delay') and hasattr(driver, 'custom_max_delay'):
        time.sleep(random.uniform(driver.custom_min_delay, driver.custom_max_delay))
    else:
        time.sleep(fallback)

def check_and_bypass_waf(driver, shop_name):
    return True

def set_city(driver, city_name, shop_name):
    global _cached_pdf_url, _cached_catalog_products
    _cached_pdf_url = None
    _cached_catalog_products = None 
    
    try:
        driver.get("https://www.verno-info.ru/")
        smart_sleep(driver, 2.0)
        return 200
    except Exception as e:
        print(f"[{shop_name}] Ошибка 404. Не удалось загрузить страницу.")
        return 404

def get_pdf_url(driver, shop_name):
    global _cached_pdf_url
    if _cached_pdf_url:
        return _cached_pdf_url

    api_endpoints = [
        "https://www.verno-info.ru/js/catalog/data.json",
        "https://www.verno-info.ru/js/book/data.json"
    ]
    
    for api in api_endpoints:
        try:
            driver.get(api)
            smart_sleep(driver, 1.5)
            page_text = driver.find_element(By.TAG_NAME, "body").text
            page_text = page_text.replace('\\/', '/')
            match = re.search(r'(https?://[^"\'\s]+\.pdf|/storage/catalogs/[^"\'\s]+\.pdf)', page_text)
            if match:
                pdf_link = match.group(1)
                if not pdf_link.startswith('http'):
                    pdf_link = "https://www.verno-info.ru" + pdf_link
                print(f"[{shop_name}] Найден PDF в API: {pdf_link}")
                _cached_pdf_url = pdf_link
                return pdf_link
        except:
            pass

    try:
        driver.get("https://www.verno-info.ru/products")
        smart_sleep(driver, 3.0)
        source = driver.page_source.replace('\\/', '/')
        match = re.search(r'(https?://[^"\'\s]+\.pdf|/storage/catalogs/[^"\'\s]+\.pdf)', source)
        if match:
            pdf_link = match.group(1)
            if not pdf_link.startswith('http'):
                pdf_link = "https://www.verno-info.ru" + pdf_link
            print(f"[{shop_name}] Найден PDF в HTML: {pdf_link}")
            _cached_pdf_url = pdf_link
            return pdf_link
    except:
        pass

    print(f"[{shop_name}] Ссылка на PDF не найдена на странице.")
    return None

def get_product_links(driver, query, shop_name):
    pdf_url = get_pdf_url(driver, shop_name)
    if pdf_url:
        encoded_query = urllib.parse.quote(query)
        return [f"{pdf_url}#query={encoded_query}"]
    return []

def download_pdf(driver, pdf_url, save_path, shop_name):
    session = requests.Session()
    for cookie in driver.get_cookies():
        session.cookies.set(cookie['name'], cookie['value'])
        
    headers = {
        "User-Agent": driver.execute_script("return navigator.userAgent;"),
        "Accept": "*/*",
        "Referer": "https://www.verno-info.ru/"
    }
    
    print(f"[{shop_name}] Скачивание PDF каталога...")
    try:
        resp = session.get(pdf_url, headers=headers, stream=True, timeout=30)
        if resp.status_code == 200:
            with open(save_path, 'wb') as f:
                for chunk in resp.iter_content(1024):
                    if chunk:
                        f.write(chunk)
            return True
        else:
            print(f"[{shop_name}] Ошибка скачивания. Код ответа: {resp.status_code}")
            return False
    except Exception as e:
        print(f"[{shop_name}] Ошибка сети при скачивании PDF: {e}")
        return False

def parse_product(driver, product_url, retail_name, city_name, shop_name):
    global _cached_catalog_products
    results = []
    
    hash_idx = product_url.find('#query=')
    query = ""
    pdf_url = product_url
    if hash_idx != -1:
        query = urllib.parse.unquote(product_url[hash_idx + 7:])
        pdf_url = product_url[:hash_idx]

    try:
        import pdfplumber
    except ImportError:
        print(f"[{shop_name}] Ошибка. Установите библиотеку (pip install pdfplumber)")
        return results

    if _cached_catalog_products is None:
        _cached_catalog_products = []
        pdf_path = "verno_catalog_temp.pdf"
        
        if download_pdf(driver, pdf_url, pdf_path, shop_name):
            try:
                print(f"[{shop_name}] Анализ сетки каталога из PDF (разовая операция)...")
                with pdfplumber.open(pdf_path) as pdf:
                    for page_num, page in enumerate(pdf.pages, 1):
                        raw_words = page.extract_words(keep_blank_chars=False)
                        if not raw_words: continue
                        
                        words = []
                        for w in raw_words:
                            txt = w['text'].strip()
                            if not txt: continue
                            w['text'] = txt
                            w['cx'] = (w['x0'] + w['x1']) / 2
                            w['cy'] = (w['top'] + w['bottom']) / 2
                            w['height'] = w['bottom'] - w['top']
                            w['used'] = False
                            words.append(w)
                            
                        if not words: continue

                        avg_height = sum(w['height'] for w in words) / len(words)
                        
                        
                        anchors = []
                        for w in words:
                            txt_clean = re.sub(r'[^\d]', '', w['text'])
                            if not txt_clean: continue
                            
                            
                            if w['height'] > avg_height * 1.2 and txt_clean.isdigit():
                                price_val = float(txt_clean)
                                
                                
                                if len(txt_clean) >= 3 and txt_clean[-2:] in ['99', '90', '50', '00']:
                                    price_val = float(txt_clean[:-2] + '.' + txt_clean[-2:])
                                elif price_val > 999: 
                                    price_val = price_val / 100.0
                                    
                                if 9.0 <= price_val < 15000.0 and price_val not in [2022, 2023, 2024, 2025, 2026]:
                                    anchors.append({'word': w, 'val': price_val, 'box_words': []})
                                    w['used'] = True

                        valid_anchors = []
                        for a in anchors:
                            is_dup = False
                            for va in valid_anchors:
                                if abs(a['word']['cx'] - va['word']['cx']) < 40 and abs(a['word']['cy'] - va['word']['cy']) < 20:
                                    is_dup = True
                                    break
                            if not is_dup:
                                valid_anchors.append(a)

                        
                        for a in valid_anchors:
                            aw = a['word']
                            for w in words:
                                if w['used']: continue
                                if w['text'].replace('%', '') in ['99', '90', '50', '00']:
                                    if w['x0'] >= aw['x1'] - 5 and w['x0'] < aw['x1'] + 35 and abs(w['cy'] - aw['cy']) < 20:
                                        if a['val'] == float(int(a['val'])):
                                            a['val'] += float(w['text'].replace('%', '')) / 100.0
                                        w['used'] = True
                                        break

                        
                        stop_regex = re.compile(r'(период|июня|июля|августа|сентября|октября|ноября|декабря|января|февраля|марта|апреля|мая|товары\s+недели|по\s+карте|у\s+нас\s+всегда|низкие\s+цены|цена)', re.I)
                        
                        for w in words:
                            if w['used']: continue
                            txt = w['text']
                            
                            if stop_regex.search(txt) or txt.lower() in ['выгода', 'хит', 'суперцена', 'акция']:
                                continue
                                
                            best_a = None
                            min_dist = float('inf')
                            
                            for a in valid_anchors:
                                aw = a['word']
                                dx = abs(w['cx'] - aw['cx'])
                                dy = w['cy'] - aw['cy'] 
                                
                                
                                if dx < 90 and -80 < dy < 150:
                                
                                    dist = (dx * 3) ** 2 + (dy) ** 2
                                    if dist < min_dist:
                                        min_dist = dist
                                        best_a = a
                                        
                            if best_a:
                                best_a['box_words'].append(w)
                                w['used'] = True
                                    
                        for a in valid_anchors:
                            box_words = a['box_words']
                            box_words.sort(key=lambda w: (round(w['cy'] / 5), w['cx']))
                            
                            name_parts = []
                            volume = ""
                            weight = ""
                            old_prices = []
                            
                            for w in box_words:
                                txt = w['text'].strip()
                                txt_lower = txt.lower()
                                
                                if '%' in txt:
                                    continue
                                    
                                if re.search(r'\d+[.,]?\d*\s*(г|кг)\b', txt_lower):
                                    weight = txt
                                    name_parts.append(txt)
                                elif re.search(r'\d+[.,]?\d*\s*(мл|л)\b', txt_lower):
                                    volume = txt
                                    name_parts.append(txt)
                                else:
                                    clean_txt = re.sub(r'[^\d]', '', txt)
                                    if clean_txt.isdigit() and len(clean_txt) >= 2:
                                        if len(clean_txt) >= 3 and clean_txt[-2:] in ['99', '90', '50', '00']:
                                            p_val = float(clean_txt[:-2] + '.' + clean_txt[-2:])
                                        else:
                                            p_val = float(clean_txt)
                                            if p_val > 999: p_val = p_val / 100.0
                                        
                                        
                                        if p_val >= a['val'] and w['cy'] < a['word']['cy'] + 10:
                                            old_prices.append(p_val)
                                            continue 
                                            
                                    name_parts.append(txt)

                            clean_name_parts = []
                            for part in name_parts:
                                if re.match(r'^[\d.,]+$', part): continue
                                clean_name_parts.append(part)
                                
                            name = " ".join(clean_name_parts).strip()
                            if len(name) < 3:
                                name = "Товар из каталога"

                            promo_price = a['val']
                            base_price = max(old_prices) if old_prices else promo_price

                            _cached_catalog_products.append({
                                "Бренд": "",
                                "Название продукта": name,
                                "Цена": base_price,
                                "Цена по акции": promo_price if promo_price < base_price else None,
                                "Объем": volume,
                                "Вес": weight,
                            })

                print(f"[{shop_name}] В кэш добавлено {len(_cached_catalog_products)} товаров из PDF.")
            except Exception as e:
                print(f"[{shop_name}] Ошибка обработки PDF: {e}")
            finally:
                if os.path.exists(pdf_path):
                    os.remove(pdf_path)


    query_words = query.lower().split()
    
    for p in _cached_catalog_products:
        p_name = p["Название продукта"].lower()
        
        match = True
        if query_words:
            for qw in query_words:
                if qw not in p_name:
                    match = False
                    break
                    
        if match:
            results.append({
                "Номер": 0,
                "Сеть": retail_name,
                "Тип магазина": "Магазин",
                "Адрес Торговой точки": city_name,
                "Бренд": p["Бренд"],
                "Название продукта": p["Название продукта"],
                "Цена": p["Цена"],
                "Цена по акции": p["Цена по акции"],
                "Фото товара": "",
                "Ссылка на страницу": pdf_url,
                "Рейтинг": None,
                "Объем": p["Объем"],
                "Вес": p["Вес"],
                "Остаток": 1,
                "GTIN": ""
            })

    if not results:
        results.append({
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Магазин",
            "Адрес Торговой точки": "Нет в наличии / Не указано",
            "Бренд": "",
            "Название продукта": query if query else "Неизвестный товар",
            "Цена": 0.0,
            "Цена по акции": None,
            "Фото товара": "",
            "Ссылка на страницу": pdf_url,
            "Рейтинг": None,
            "Объем": "",
            "Вес": "",
            "Остаток": 0,
            "GTIN": ""
        })
        
    return results