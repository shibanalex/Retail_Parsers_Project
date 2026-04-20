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
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d.,]', '', price_str).replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None

def check_and_bypass_waf(driver):
    src = driver.page_source.lower()
    if "заблокирован" in src or "cloudflare" in src or "qrator" in src:
        time.sleep(random.uniform(2.0, 3.5))
        driver.refresh()
        time.sleep(3)
        if "заблокирован" in driver.page_source.lower():
            return False
    return True

def set_city(driver, city_name):
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
        
        search_input.send_keys(Keys.CONTROL + "a")
        time.sleep(0.2)
        search_input.send_keys(Keys.BACKSPACE)
        time.sleep(0.5)
        
        search_input.send_keys("Москва, Красная пл, д 11")
        time.sleep(1.5)
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
    except Exception:
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
    except Exception:
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

            stock = 0
            availability_elem = card.select_one(".product__availability-text")
            if availability_elem:
                avail_text = availability_elem.text.strip()
                stock_digits = re.sub(r'\D', '', avail_text)
                if stock_digits:
                    stock = int(stock_digits)
                elif "в наличии" in avail_text.lower():
                    stock = 1
            else:
                no_stock_btn = card.select_one(".btn-mixed__link.is-disabled")
                if not no_stock_btn:
                    stock = 1

            products_dict[full_url] = {
                "url": full_url,
                "current_price": current_price,
                "promo_price": promo_price,
                "stock": stock
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
        return []

    try:
        tab_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Наличие в магазинах')]")
        driver.execute_script("arguments[0].click();", tab_btn)
        time.sleep(1)
    except Exception:
        pass

    soup = BeautifulSoup(driver.page_source, 'html.parser')
    name_elem = soup.select_one("h1") or soup.select_one(".product__name")
    name = name_elem.text.strip() if name_elem else ""

    product_id = ""
    match_id = re.search(r'/catalog/(\d+)', url)
    if match_id:
        product_id = match_id.group(1)

    photo_url = ""
    img_elem = soup.select_one(".carousel-product-preview__img")
    if img_elem:
        photo_url = img_elem.get("data-src") or img_elem.get("src") or ""
        if photo_url and photo_url.startswith('/'):
            photo_url = f"https://tvoydom.ru{photo_url}"

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

    valid_addresses = []
    store_items = soup.select("ul.ylist-list.map-product__list > li.ylist-list__item")
    
    if store_items:
        for item in store_items:
            avail_elem = item.select_one(".ylist__available")
            if avail_elem and "нет в наличии" in avail_elem.text.lower():
                continue
                
            addr_elem = item.select_one(".ylist__address-text")
            if addr_elem:
                addr_text = addr_elem.get_text(separator=" ", strip=True).replace('\xa0', ' ')
                addr_text = re.sub(r'\s+', ' ', addr_text).strip()
                
                if city_name.lower() == "москва" and "мкад" not in addr_text.lower():
                    continue
                    
                valid_addresses.append(addr_text)

    results = []
    for addr in valid_addresses:
        results.append({
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Гипермаркет",
            "Адрес Торговой точки": addr,
            "Бренд": brand,
            "Название продукта": name,
            "Цена": current_price,
            "Цена по акции": promo_price,
            "Фото товара": photo_url,
            "Ссылка на страницу": url,
            "Рейтинг": None,
            "Объем": volume,
            "Вес": weight,
            "Остаток": None,
            "GTIN": product_id
        })

    return results