import time
import random
import re
import os
import json
import requests
import urllib.parse
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

try:
    import google.generativeai as genai
except ImportError:
    pass

GEMINI_API_KEY = "AIzaSyBoD0ClB3JHWf3nFcD_AUTkXQY65ICcAU8"

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
        return [f"{pdf_url}
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

def extract_products_with_ai(text, shop_name):
    if not GEMINI_API_KEY or GEMINI_API_KEY == "твой_ключ_gemini_здесь":
        print(f"[{shop_name}] Ошибка: Не указан API ключ Google Gemini!")
        return None

    prompt = f"""Ты — точный экстрактор данных. Я передаю тебе сырой текст со страницы каталога супермаркета.
Твоя задача — найти все товары и вернуть их строго в виде JSON-массива. 
ВАЖНО: ВОЗВРАЩАЙ ТОЛЬКО МАССИВ [ ... ], БЕЗ КАВЫЧЕК MARKDOWN, БЕЗ СЛОВ "Вот результат" И Т.Д.
Правила:
1. Цены могут быть слипшимися (например "199 90" = 199.90, "15 99" = 15.99).
2. Старая (зачеркнутая) цена обычно больше новой. Если цены две, бóльшая = price_base, меньшая = price_promo. Если цена одна = price_base.
3. Игнорируй рекламный мусор, даты (19-22 июня), слова "выгода", "суперцена", "товары недели".
4. Верни массив объектов в формате:
[
  {{
    "name": "Название товара (например: МОЛОКО ДОМИК В ДЕРЕВНЕ)",
    "price_base": 199.90,
    "price_promo": 159.90,
    "volume": "1 л" (или пустая строка ""),
    "weight": "400 г" (или пустая строка "")
  }}
]
Если товаров нет, верни [].

Текст страницы:
{text}
"""

    try:
        genai.configure(api_key=GEMINI_API_KEY)
        model = genai.GenerativeModel('gemini-flash-latest')
        
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.0,
            )
        )
        
        answer = response.text.strip()
        
        if "```json" in answer:
            answer = answer.split("```json")[1].split("```")[0].strip()
        elif "```" in answer:
            answer = answer.split("```")[1].split("```")[0].strip()
            
        start_idx = answer.find('[')
        end_idx = answer.rfind(']')
        if start_idx != -1 and end_idx != -1:
            answer = answer[start_idx:end_idx+1]
            
        products = json.loads(answer)
        if isinstance(products, list):
            return products
            
    except Exception as e:
        print(f"[{shop_name}] Ошибка ИИ-парсинга Gemini: {e}")
        
    return None

def extract_products_fallback(text):
    results = []
    lines = [line.strip() for line in text.split('\n') if line.strip()]
    
    for i, line in enumerate(lines):
        match = re.search(r'(\d+)\s*(99|90|50|00|95)\b', line)
        if match:
            rub = match.group(1)
            kop = match.group(2)
            try:
                price = float(f"{rub}.{kop}")
                if 9.0 <= price < 15000.0 and price not in [2022, 2023, 2024, 2025, 2026]:
                    name = lines[i+1] if i+1 < len(lines) else "Товар из каталога"
                    if len(name) < 3 or re.search(r'\d{1,2}\s*(июня|июля|августа|сентября|мая)', name, re.I):
                        name = "Товар по акции"
                        
                    results.append({
                        "name": name,
                        "price_base": price,
                        "price_promo": None,
                        "volume": "",
                        "weight": ""
                    })
            except:
                pass
    return results

def parse_product(driver, product_url, retail_name, city_name, shop_name):
    global _cached_catalog_products
    results = []
    
    hash_idx = product_url.find('
    query = ""
    pdf_url = product_url
    if hash_idx != -1:
        query = urllib.parse.unquote(product_url[hash_idx + 7:])
        pdf_url = product_url[:hash_idx]

    try:
        import pdfplumber
    except ImportError:
        print(f"[{shop_name}] Ошибка. Установите библиотеку (pip install pdfplumber google-generativeai)")
        return results

    if _cached_catalog_products is None:
        _cached_catalog_products = []
        pdf_path = "verno_catalog_temp.pdf"
        
        if download_pdf(driver, pdf_url, pdf_path, shop_name):
            try:
                print(f"[{shop_name}] Запуск ИИ-парсинга каталога через Google Gemini...")
                with pdfplumber.open(pdf_path) as pdf:
                    for page_num, page in enumerate(pdf.pages, 1):
                        text = page.extract_text(layout=True)
                        if not text or len(text.strip()) < 20:
                            continue
                            
                        print(f"[{shop_name}] ИИ обрабатывает страницу {page_num} из {len(pdf.pages)}...")
                        ai_products = extract_products_with_ai(text, shop_name)
                        
                        if ai_products is None:
                            print(f"[{shop_name}] Включение резервного регулярного парсера для страницы {page_num}...")
                            ai_products = extract_products_fallback(text)
                        
                        for p in ai_products:
                            _cached_catalog_products.append({
                                "Бренд": "",
                                "Название продукта": p.get("name", "Товар из каталога"),
                                "Цена": float(p.get("price_base") or 0.0),
                                "Цена по акции": float(p.get("price_promo")) if p.get("price_promo") else None,
                                "Объем": p.get("volume", ""),
                                "Вес": p.get("weight", ""),
                                "Страница": page_num
                            })
                            
                        time.sleep(3)
                            
                print(f"[{shop_name}] В кэш добавлено {len(_cached_catalog_products)} товаров.")
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
                "Ссылка на страницу": f"{pdf_url} (Стр. {p.get('Страница', 1)})",
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