import time
import random
import re
import urllib.parse
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def clean_price(price_str):
    """Очистка строки"""
    if not price_str:
        return None
    # Очищаем от букв (включая "б", "руб"), пробелов и оставляем только цифры с точкой
    cleaned = re.sub(r'[^\d.,]', '', price_str).replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None

def check_and_bypass_waf(driver):
    """Проверка на капчу"""
    src = driver.page_source.lower()
    if "заблокирован" in src or "cloudflare" in src or "qrator" in src:
        print("⚠️ [Антибот] Обнаружена блокировка WAF! Имитируем ожидание...")
        time.sleep(random.uniform(2.0, 3.5))
        driver.refresh()
        time.sleep(3)
        if "заблокирован" in driver.page_source.lower():
            return False
    return True

def set_city(driver, city_name):
    """
    Установка адреса на сайте
    """
    driver.get("https://tvoydom.ru/")
    
    if not check_and_bypass_waf(driver):
        return False

    try:
        badge = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".location-badge__city"))
        )
        if "москва" in badge.text.lower():
            return True
            
        WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, ".location-badge"))).click()
        
        search_input = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.ID, "street"))
        )
        
        search_input.click()
        time.sleep(0.5)
        search_input.send_keys(Keys.DELETE)
        time.sleep(0.5)
        
        address_text = "Москва, Красная пл, д11"
        for char in address_text:
            search_input.send_keys(char)
            time.sleep(0.05) 
            
        time.sleep(2)
        search_input.send_keys(Keys.DOWN)
        time.sleep(0.5)
        search_input.send_keys(Keys.ENTER)
        
        time.sleep(1)
        
        save_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "button.location-popup__button"))
        )
        save_btn.click()
        
        time.sleep(2)
        return True
    except Exception as e:
        print(f"⚠️ Окно адреса не найдено или город уже установлен. Идем дальше.")
        return True 

def get_product_links(driver, query):
    driver.get("https://tvoydom.ru/")
    
    if not check_and_bypass_waf(driver):
        return []

    try:
        search_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "input.js-search-suggest-field, input[type='search']"))
        )
        search_input.clear()
        search_input.send_keys(query)
        time.sleep(0.5)
        search_input.send_keys(Keys.ENTER)
        

        try:
            products_filter_xpath = "//li[contains(@class, 'search-categories')]//p[contains(text(), 'Продукты')]"
            products_filter = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, products_filter_xpath)))
            driver.execute_script("arguments[0].click();", products_filter)
            time.sleep(2)
        except (TimeoutException, NoSuchElementException):
            time.sleep(1.5) 

    except Exception as e:
        print(f"⚠️ Ошибка при поиске '{query}': {e}")
        return []

    main_keyword = query.split()[0].lower() if query else ""
    
    products_dict = {}
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    while True:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        cards = soup.select('.product')
        
        for card in cards:
            link_elem = card.select_one('.product__link')
            if not link_elem:
                continue
                
            title = link_elem.text.strip()
            
            if main_keyword and main_keyword not in title.lower():
                continue
                
            href = link_elem.get('href')
            if not href:
                continue
                
            full_url = f"https://tvoydom.ru{href}" if href.startswith('/') else href
            

            if full_url in products_dict:
                continue


            promo_price = None
            current_price = None
            
            curr_price_elem = card.select_one(".product__price-current")
            old_price_elem = card.select_one(".product__price-old")
            
            if old_price_elem and curr_price_elem:
                current_price = clean_price(old_price_elem.text)
                promo_price = clean_price(curr_price_elem.text)
            elif curr_price_elem:
                current_price = clean_price(curr_price_elem.text)

            products_dict[full_url] = {
                "url": full_url,
                "current_price": current_price,
                "promo_price": promo_price
            }
                
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1) 
        
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            time.sleep(1.5)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
        last_height = new_height

    return list(products_dict.values())

def parse_product(driver, product_data, retail_name, city_name):
    url = product_data["url"]
    cat_current_price = product_data["current_price"]
    cat_promo_price = product_data["promo_price"]
    
    driver.get(url)
    
    if not check_and_bypass_waf(driver):
        return []

    try:
        WebDriverWait(driver, 6).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "h1, .product__name"))
        )
    except TimeoutException:
        print(f"⚠️ Товар не загрузился: {url}")
        return []

    soup = BeautifulSoup(driver.page_source, 'html.parser')

    # Название
    name_elem = soup.select_one("h1") or soup.select_one(".product__name")
    name = name_elem.text.strip() if name_elem else ""

    # Артикул
    product_id = ""
    match_id = re.search(r'/catalog/(\d+)', url)
    if match_id:
        product_id = match_id.group(1)

    # Фото товара
    photo_url = ""
    img_elem = soup.select_one(".carousel-product-preview__img")
    if img_elem:
        photo_url = img_elem.get("data-src") or img_elem.get("src") or ""
        if photo_url and photo_url.startswith('/'):
            photo_url = f"https://tvoydom.ru{photo_url}"

    # Парсинг Цены из блока карточек
    promo_price = None
    current_price = None
    price_box = soup.select_one(".page-product__price-box")
    
    if price_box:
        new_price_elem = price_box.select_one(".price--new")
        old_price_elem = price_box.select_one(".price--old")
        
        if new_price_elem and old_price_elem:
            current_price = clean_price(old_price_elem.text)
            promo_price = clean_price(new_price_elem.text)
        else:
            reg_price_elem = price_box.select_one(".page-product__price")
            if reg_price_elem:
                current_price = clean_price(reg_price_elem.text)

    if current_price is None:
        current_price = cat_current_price
        promo_price = cat_promo_price

    # Бренд, Вес, Объем
    weight = None
    volume = None
    brand = "Твой Дом"
    
    brand_link = soup.select_one("a[href*='/brands/']")
    if brand_link:
        href = brand_link.get('href', '')
        match = re.search(r'/brands/([^/]+)', href)
        if match:
            brand = urllib.parse.unquote(match.group(1)).strip().rstrip('/')


    features = soup.select(".features-list__item")
    for f in features:
        f_name_elem = f.select_one(".features-list__name")
        f_val_elem = f.select_one(".features-list__desc")
        
        if f_name_elem and f_val_elem:
            f_name = f_name_elem.text.strip().lower()
            f_val = f_val_elem.text.strip()
            
            if "бренд" in f_name or "торговая марка" in f_name:
                brand = f_val
            elif "вес" in f_name:
                if "(кг)" in f_name:
                    weight = f_val + " кг"
                elif "(г)" in f_name:
                    weight = f_val + " г"
                else:
                    weight = f_val
            elif "объём" in f_name or "объем" in f_name:
                if "(л)" in f_name:
                    volume = f_val + " л"
                elif "(мл)" in f_name:
                    volume = f_val + " мл"
                else:
                    volume = f_val

    stock = 0
    availability_elem = soup.select_one(".product__availability-text")
    if availability_elem:
        avail_text = availability_elem.text.strip()
        stock_digits = re.sub(r'\D', '', avail_text)
        if stock_digits:
            stock = int(stock_digits)
        elif "в наличии" in avail_text.lower():
            stock = 1
            
    no_stock_btn = soup.select_one(".btn-mixed__link.is-disabled")
    if no_stock_btn and "нет в наличии" in no_stock_btn.text.lower():
        stock = 0

    return [{
        "Номер": 0,
        "Сеть": retail_name,
        "Тип магазина": "Гипермаркет",
        "Адрес Торговой точки": "",
        "Бренд": brand,
        "Название продукта": name,
        "Цена": current_price,
        "Цена по акции": promo_price,
        "Фото товара": photo_url,
        "Ссылка на страницу": url,
        "Рейтинг": None,
        "Объем": volume,
        "Вес": weight,
        "Остаток": stock,
        "GTIN": product_id
    }]