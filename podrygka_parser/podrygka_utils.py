import time
import random
import re
import urllib.parse
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

def smart_sleep(driver, fallback=2.0):
    if hasattr(driver, 'custom_min_delay') and hasattr(driver, 'custom_max_delay'):
        time.sleep(random.uniform(driver.custom_min_delay, driver.custom_max_delay))
    else:
        time.sleep(fallback)

def check_and_bypass_waf(driver, shop_name):
    try:
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.TAG_NAME, "header"))
        )
    except TimeoutException:
        pass

    try:
        cookie_btn = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(translate(text(), 'ПРИНЯТЬ', 'принять'), 'принять') or contains(@class, 'cookie')]"))
        )
        driver.execute_script("arguments[0].click();", cookie_btn)
        time.sleep(0.5)
    except TimeoutException:
        pass
        
    try:
        city_confirm_btn = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.XPATH, "//*[contains(translate(text(), 'ВЕРНО', 'верно'), 'верно') or contains(text(), 'Да, ') or contains(text(), 'Выбрать другой')]"))
        )
        driver.execute_script("arguments[0].click();", city_confirm_btn)
        time.sleep(0.5)
    except TimeoutException:
        pass

    return True

def set_city(driver, city_name, shop_name):
    try:
        driver.get("https://www.podrygka.ru/")
        smart_sleep(driver, 2.0)
    except Exception as e:
        print(f"[{shop_name}] Ошибка 404. Не удалось загрузить главную страницу.")
        return 404

    check_and_bypass_waf(driver, shop_name)

    try:
        city_trigger = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//*[@data-header-user-navigate] | //a[contains(@class, 'header-navigate')]"))
        )
        
        current_city = driver.execute_script("return arguments[0].innerText;", city_trigger).strip()
        
        if city_name.lower() in current_city.lower():
            return 200

        driver.execute_script("arguments[0].click();", city_trigger)
        smart_sleep(driver, 1.5)
        
        try:
            city_option = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, f"//a[contains(@class, 'popup-sm__link') and contains(text(), '{city_name}')]"))
            )
            driver.execute_script("arguments[0].click();", city_option)
            smart_sleep(driver, 2.0)
            return 200
        except TimeoutException:
            return 999

    except TimeoutException:
        print(f"[{shop_name}] Ошибка 403. Элементы выбора города не найдены.")
        return 403
    except Exception as e:
        print(f"[{shop_name}] Ошибка 500 при выборе города.")
        return 500

def get_product_links(driver, query, shop_name):
    links = set()
    try:
        driver.get("https://www.podrygka.ru/")
        smart_sleep(driver, 2.5)
        
        check_and_bypass_waf(driver, shop_name)
        
        try:
            search_inputs = WebDriverWait(driver, 5).until(
                EC.presence_of_all_elements_located((By.XPATH, "//input[@id='search' or @name='search' or @type='search']"))
            )
            
            visible_input = None
            for inp in search_inputs:
                if inp.is_displayed():
                    visible_input = inp
                    break
                    
            if not visible_input:
                visible_input = search_inputs[0]

            driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", visible_input)
            driver.execute_script("arguments[0].focus(); arguments[0].value = '';", visible_input)
            
            visible_input.send_keys(" ")
            visible_input.send_keys(Keys.BACKSPACE)
            smart_sleep(driver, 0.5)
            
            visible_input.send_keys(query)
            smart_sleep(driver, 1.5)
            visible_input.send_keys(Keys.ENTER)
            smart_sleep(driver, 4.0)
            
        except TimeoutException:
            encoded_query = urllib.parse.quote(query)
            driver.get(f"https://www.podrygka.ru/search/?q={encoded_query}")
            smart_sleep(driver, 4.0)
        
        retries = 0       
        max_retries = 3   
        
        while True:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            product_cards = soup.find_all('div', attrs={"data-product-id": True})
            
            links_count_before = len(links)
            
            for card in product_cards:
                a_tag = card.find('a', href=True)
                if a_tag:
                    href = a_tag['href']
                    if not href.startswith('http'):
                        href = f"https://www.podrygka.ru{href}"
                    links.add(href)
                    
            if len(links) > links_count_before:
                retries = 0
            else:
                retries += 1
                
            if retries >= max_retries:
                break
                
            try:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                pass
                
            smart_sleep(driver, 2.0)
            
        print(f"[{shop_name}] Найдено уникальных ссылок: {len(links)}")
        
    except Exception as e:
        print(f"[{shop_name}] Ошибка при поиске '{query}'.")
        
    return list(links)

def clean_price(price_str):
    if not price_str: return 0.0
    cleaned = re.sub(r'[^\d.,]', '', price_str.replace(',', '.'))
    try:
        return float(cleaned)
    except:
        return 0.0

def parse_product(driver, product_url, retail_name, city_name, shop_name):
    results = []
    try:
        driver.get(product_url)
        smart_sleep(driver, 2.0)
        
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        h1_tag = soup.find('h1')
        product_name = h1_tag.text.strip() if h1_tag else "Неизвестный товар"
        
        photo_url = ""
        img_tag = soup.find('img', class_=lambda c: c and 'gallery-img' in c)
        if img_tag and 'src' in img_tag.attrs:
            photo_url = img_tag['src']
            if not photo_url.startswith('http'):
                photo_url = "https://www.podrygka.ru" + photo_url
            
        price_base = 0.0
        price_promo = None
        
        curr_price_tag = soup.find('span', class_=lambda c: c and 'current-price' in c)
        old_price_tag = soup.find('div', class_=lambda c: c and 'old-price-wrapper' in c)
        
        if curr_price_tag and old_price_tag:
            price_promo = clean_price(curr_price_tag.text)
            price_base = clean_price(old_price_tag.text)
        elif curr_price_tag:
            price_base = clean_price(curr_price_tag.text)

        brand = ""
        brand_tag = soup.find('div', class_='product-detail__brand')
        if brand_tag:
            b_img = brand_tag.find('img')
            if b_img and b_img.get('alt'):
                brand = b_img.get('alt').strip()

        volume = ""
        weight = ""
        gtin = ""
        
        specs_block = soup.find('div', class_='block-weight-info')
        if specs_block:
            for li in specs_block.find_all('li'):
                text_low = li.text.lower()
                if 'объем' in text_low or 'объём' in text_low:
                    volume = text_low.split(':')[-1].strip()
                elif 'вес' in text_low:
                    weight = text_low.split(':')[-1].strip()
                elif 'артикул' in text_low:
                    gtin_span = li.find(id='articltrading')
                    if gtin_span:
                        gtin = gtin_span.text.strip()

        stock_int = 0
        cart_btn = soup.find('button', title=re.compile(r'корзин', re.I))
        if cart_btn and 'disabled' not in cart_btn.attrs:
            stock_int = 1

        try:
            avail_btn = WebDriverWait(driver, 3).until(
                EC.presence_of_element_located((By.XPATH, "//div[contains(translate(text(), 'НАЛИЧИЕ', 'наличие'), 'наличие в магазин')] | //a[contains(@href, 'availability')]"))
            )
            driver.execute_script("arguments[0].click();", avail_btn)
            smart_sleep(driver, 1.5)
            
            soup_shops = BeautifulSoup(driver.page_source, 'html.parser')
            shop_items = soup_shops.find_all('div', class_=lambda c: c and ('shop-item' in c or 'store-item' in c))
            
            for shop in shop_items:
                addr_tag = shop.find(class_=lambda c: c and 'address' in c)
                qty_tag = shop.find(class_=lambda c: c and ('qty' in c or 'status' in c))
                
                address = addr_tag.text.strip() if addr_tag else ""
                qty_text = qty_tag.text.strip().lower() if qty_tag else ""
                
                quantity = 1
                if 'нет' in qty_text or '0' in qty_text:
                    quantity = 0
                elif qty_match := re.search(r'\d+', qty_text):
                    quantity = int(qty_match.group())
                
                if address:
                    results.append({
                        "Номер": 0,
                        "Сеть": retail_name,
                        "Тип магазина": "Магазин",
                        "Адрес Торговой точки": f"{city_name}, {address}",
                        "Бренд": brand,
                        "Название продукта": product_name,
                        "Цена": price_base,
                        "Цена по акции": price_promo,
                        "Фото товара": photo_url,
                        "Ссылка на страницу": product_url,
                        "Рейтинг": None,
                        "Объем": volume,
                        "Вес": weight,
                        "Остаток": quantity,
                        "GTIN": gtin
                    })
        except TimeoutException:
            pass

        if not results:
            results.append({
                "Номер": 0,
                "Сеть": retail_name,
                "Тип магазина": "Магазин",
                "Адрес Торговой точки": city_name,
                "Бренд": brand,
                "Название продукта": product_name,
                "Цена": price_base,
                "Цена по акции": price_promo,
                "Фото товара": photo_url,
                "Ссылка на страницу": product_url,
                "Рейтинг": None,
                "Объем": volume,
                "Вес": weight,
                "Остаток": stock_int,
                "GTIN": gtin
            })

    except Exception as e:
        print(f"[{shop_name}] Ошибка при парсинге карточки.")
        
    return results