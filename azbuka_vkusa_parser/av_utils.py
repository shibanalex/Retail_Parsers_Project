import time
import random
import re
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def smart_sleep(driver, fallback=2.0):
    if hasattr(driver, 'custom_min_delay') and hasattr(driver, 'custom_max_delay'):
        time.sleep(random.uniform(driver.custom_min_delay, driver.custom_max_delay))
    else:
        time.sleep(fallback)

def clean_price(price_str):
    if not price_str:
        return None
    cleaned = re.sub(r'[^\d.,]', '', price_str).replace(',', '.')
    try:
        return float(cleaned)
    except ValueError:
        return None

def check_and_bypass_waf(driver, shop_name):
    if "Ваш запрос был заблокирован" in driver.page_source or "welcome@azbukavkusa.ru" in driver.page_source:
        print(f"[{shop_name}] Обнаружена блокировка WAF. Имитация активности.")
        for _ in range(3):
            driver.execute_script(f"window.scrollBy(0, {random.randint(100, 300)});")
            time.sleep(random.uniform(1.5, 3.5))
            
        driver.refresh()
        smart_sleep(driver, 5)
        
        if "Ваш запрос был заблокирован" in driver.page_source:
            print(f"[{shop_name}] Ошибка 403. Обход блокировки не удался.")
            return False
    return True

def set_city(driver, city_name, shop_name):
    try:
        driver.get("https://av.ru/")
        smart_sleep(driver, 3)
    except Exception as e:
        print(f"[{shop_name}] Ошибка 404. Не удалось загрузить главную страницу. {e}")
        return 404

    if not check_and_bypass_waf(driver, shop_name):
        return 403

    try:
        current_city_elem = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".header-main-city_text"))
        )
        current_city = current_city_elem.text.strip()
        
        if current_city.lower() == city_name.lower():
            return 200

        city_block = driver.find_element(By.CSS_SELECTOR, ".header-main-city")
        ActionChains(driver).move_to_element(city_block).perform()
        time.sleep(1.5) 
        
        xpath_city = f"//div[contains(@class, 'header-main-city-tooltip__item') and contains(text(), '{city_name}')]"
        
        try:
            city_option = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.XPATH, xpath_city)))
            driver.execute_script("arguments[0].click();", city_option)
            smart_sleep(driver, 3) 
            return 200
        except TimeoutException:
            return 999

    except TimeoutException:
        print(f"[{shop_name}] Ошибка загрузки элементов выбора города.")
        return 500
    except Exception as e:
        print(f"[{shop_name}] Ошибка 500 при установке города {city_name}: {e}")
        return 500

def get_product_links(driver, query, shop_name):
    url = f"https://av.ru/search?freeText={query}"
    driver.get(url)
    smart_sleep(driver, 3)
    
    if not check_and_bypass_waf(driver, shop_name):
        return []

    main_keyword = query.split()[0].lower() if query else ""
    links = set()
    last_height = driver.execute_script("return document.body.scrollHeight")
    
    while True:
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        cards = soup.select('.main-catalog-products_item')
        
        for card in cards:
            title_elem = card.select_one('.product-info_name-container')
            if not title_elem:
                continue
                
            title = title_elem.text.strip()
            
            if main_keyword and main_keyword not in title.lower():
                continue
                
            href = title_elem.get('href')
            if href:
                links.add(f"https://av.ru{href}" if href.startswith('/') else href)
                
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        smart_sleep(driver, 2.5) 
        
        new_height = driver.execute_script("return document.body.scrollHeight")
        if new_height == last_height:
            smart_sleep(driver, 3)
            new_height = driver.execute_script("return document.body.scrollHeight")
            if new_height == last_height:
                break
        last_height = new_height

    print(f"[{shop_name}] Найдено уникальных ссылок: {len(links)}")
    return list(links)

def get_store_type(address):
    addr_lower = address.lower()
    if "интернет-магазин" in addr_lower or "av.ru" in addr_lower:
        return "Интернет-магазин"
    elif "daily" in addr_lower:
        return "Минимаркет"
    elif "энотека" in addr_lower:
        return "Винотека"
    else:
        return "Супермаркет"

def parse_product(driver, url, retail_name, shop_name):
    driver.get(url)
    smart_sleep(driver, 2)
    
    if not check_and_bypass_waf(driver, shop_name):
        return []

    results = []
    
    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "[data-testid='product-name']"))
        )
    except TimeoutException:
        print(f"[{shop_name}] Ошибка загрузки карточки товара: {url}")
        return results

    soup = BeautifulSoup(driver.page_source, 'html.parser')

    name_elem = soup.select_one("[data-testid='product-name']")
    name = name_elem.text.strip() if name_elem else ""

    brand = "Азбука Вкуса"
    info_items = soup.select(".product-about-info_table_item")
    for item in info_items:
        key_elem = item.select_one(".product-about-info_table_item_name")
        if key_elem and "Бренд" in key_elem.text:
            val_elem = item.select_one(".product-about-info_table_item_value")
            if val_elem:
                brand = val_elem.text.strip()
            break

    art_elem = soup.select_one(".product-cart-header__code")
    product_id = re.sub(r'\D', '', art_elem.text.strip()) if art_elem else ""

    weight_elem = soup.select_one("[data-testid='product-measure']")
    weight = ""
    if weight_elem:
        raw_weight = weight_elem.text.strip()
        weight = raw_weight.split(',')[-1].strip()

    rating_elem = soup.select_one(".stars_cnt")
    rating = None
    if rating_elem:
        rating_clean = re.sub(r'[^\d.]', '', rating_elem.text.strip())
        if rating_clean:
            rating = float(rating_clean)

    photo_url = ""
    img_elem = soup.select_one(".default-image_image")
    if img_elem and img_elem.has_attr("style"):
        match = re.search(r'url\((.*?)\)', img_elem["style"])
        if match:
            photo_url = match.group(1).replace('"', '').replace("'", '').replace("&quot;", "").strip()
            
    if photo_url.startswith('/'):
        photo_url = f"https://av.ru{photo_url}"

    promo_price = None
    current_price = None
    price_box = soup.select_one(".product-cart-special_main")
    if price_box:
        curr_price_elem = price_box.select_one(".product-cart-special_main_price_num")
        old_price_elem = price_box.select_one(".product-cart-special_main_sale_num")
        
        if curr_price_elem:
            current_price = clean_price(curr_price_elem.text)
        if old_price_elem:
            promo_price = current_price
            current_price = clean_price(old_price_elem.text)

    has_stock_data = False
    try:
        stock_btn_xpath = "//div[contains(@class, 'button_content') and contains(text(), 'Наличие в магазинах')]/.."
        stock_btn = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((By.XPATH, stock_btn_xpath)))
        driver.execute_script("arguments[0].click();", stock_btn)
        
        WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, ".stock-map__list")))
        time.sleep(1)
        
        modal_soup = BeautifulSoup(driver.page_source, 'html.parser')
        rows = modal_soup.select(".stock-map__list_row:not(.stock-map__list_row--header)")
        
        for row in rows:
            cells = row.select(".stock-map__list_row_cell")
            if len(cells) >= 2:
                address = cells[0].text.strip()
                stock_str = cells[1].text.strip()
                stock = int(re.sub(r'\D', '', stock_str)) if re.search(r'\d', stock_str) else 0
                
                store_type = get_store_type(address)
                
                results.append({
                    "Номер": 0,
                    "Сеть": retail_name,
                    "Тип магазина": store_type,
                    "Адрес Торговой точки": address,
                    "Бренд": brand,
                    "Название продукта": name,
                    "Цена": current_price,
                    "Цена по акции": promo_price,
                    "Фото товара": photo_url,
                    "Ссылка на страницу": url,
                    "Рейтинг": rating,
                    "Объем": None,
                    "Вес": weight,
                    "Остаток": stock,
                    "GTIN": product_id
                })
                has_stock_data = True

    except (TimeoutException, NoSuchElementException):
        pass 

    if not has_stock_data:
        results.append({
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Супермаркет",
            "Адрес Торговой точки": "",
            "Бренд": brand,
            "Название продукта": name,
            "Цена": current_price,
            "Цена по акции": promo_price,
            "Фото товара": photo_url,
            "Ссылка на страницу": url,
            "Рейтинг": rating,
            "Объем": None,
            "Вес": weight,
            "Остаток": 0,
            "GTIN": product_id
        })

    return results