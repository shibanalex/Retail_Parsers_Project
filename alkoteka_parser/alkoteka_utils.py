import time
import re
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException

def check_and_bypass_waf(driver):
    try:
        age_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(translate(text(), 'ЕСТЬ', 'есть'), 'есть') or contains(text(), '18')]"))
        )
        age_btn.click()
        time.sleep(1)
        print("Плашка 18+ закрыта.")
    except TimeoutException:
        pass
    return True

def set_city(driver, city_name):
    driver.get("https://alkoteka.com/")
    check_and_bypass_waf(driver)
    
    try:
        city_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(@class, 'header__locality')]"))
        )
        current_city = city_btn.text.strip()
        
        if city_name.lower() in current_city.lower():
            print(f"Город уже установлен: {city_name}")
            return True
            
        driver.execute_script("arguments[0].click();", city_btn)
        
        WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CLASS_NAME, "modal-locality__list"))
        )
        
        target_city_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, f"//button[contains(@class, 'modal-locality__list-item') and contains(text(), '{city_name}')]"))
        )
        driver.execute_script("arguments[0].click();", target_city_btn)
        time.sleep(2)
        print(f"Город изменен на: {city_name}")
        return True
    except Exception as e:
        print(f"Ошибка при выборе города: {e}")
        return False

def get_product_links(driver, query):
    links = set()
    try:
        search_trigger = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, "//div[contains(text(), 'Искать товары')]"))
        )
        driver.execute_script("arguments[0].click();", search_trigger)
        time.sleep(1)
        
        search_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//input[@type='search' or @type='text']"))
        )
        search_input.clear()
        search_input.send_keys(query)
        search_input.send_keys(Keys.ENTER)
        
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "card-product"))
        )
        
        print(f"Начинаем листать список для '{query}'...")
        
        retries = 0       
        max_retries = 4   
        
        while True:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            product_cards = soup.find_all('div', class_='card-product')
            
            links_count_before = len(links)
            
            for card in product_cards:
                if 'card-product--empty' in card.get('class',[]):
                    continue
                    
                a_tag = card.find('a')
                if a_tag and 'href' in a_tag.attrs:
                    href = a_tag['href']
                    if not href.startswith('http'):
                        href = f"https://alkoteka.com{href}"
                    links.add(href)
                    
            if len(links) > links_count_before:
                retries = 0
            else:
                retries += 1
                
            if retries >= max_retries:
                print("Достигнут конец списка товаров.")
                break
                
            try:
                cards_elements = driver.find_elements(By.CLASS_NAME, "card-product")
                if cards_elements:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cards_elements[-1])
                else:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                
            time.sleep(2) 
            
        print(f"ИТОГО найдено уникальных ссылок в наличии для '{query}': {len(links)}")
        
    except Exception as e:
        print(f"Ошибка при поиске '{query}': {e}")
        
    return list(links)

def clean_price(price_str):
    if not price_str: return 0.0
    cleaned = re.sub(r'[^\d.,]', '', price_str.replace(',', '.'))
    try:
        return float(cleaned)
    except:
        return 0.0

def parse_product(driver, product_url, retail_name, city_name):
    results =[]
    try:
        driver.get(product_url)
        
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "h1"))
        )
        time.sleep(1)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        h1_tag = soup.find('h1')
        product_name = h1_tag.text.strip() if h1_tag else "Неизвестный товар"
        
        img_tag = soup.find('img', alt='hero')
        photo_url = img_tag['src'] if img_tag and 'src' in img_tag.attrs else ""
        if photo_url and not photo_url.startswith('http'):
            photo_url = "https://web.alkoteka.com" + photo_url
            
        price_base = 0.0
        price_promo = None
        price_container = soup.find('p', class_=lambda c: c and 'button-count__title' in c)
        
        if price_container:
            span = price_container.find('span')
            if span:
                price_base_str = span.text
                span.extract()
                price_promo_str = price_container.text
                
                price_base = clean_price(price_base_str)
                price_promo = clean_price(price_promo_str)
            else:
                price_base = clean_price(price_container.text)

        brand = ""
        volume = ""
        specs = soup.find_all('div', class_='specifications-card')
        for spec in specs:
            label = spec.find('span')
            if label:
                label_text = label.text.strip().lower()
                val_tag = spec.find('p', class_='text--body')
                val_text = val_tag.text.strip() if val_tag else ""
                
                if 'бренд' in label_text:
                    brand = val_text
                elif 'объем' in label_text or 'объём' in label_text:
                    volume = val_text

        gtin = ""
        header_tag = soup.find('div', class_='product-card__header')
        if header_tag:
            for p in header_tag.find_all('p'):
                if 'Артикул' in p.text:
                    gtin = p.text.replace('Артикул:', '').strip()
                    break

        try:
            list_view_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "//p[contains(text(), 'Списком')]"))
            )
            driver.execute_script("arguments[0].click();", list_view_btn)
            
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "card-map"))
            )
            time.sleep(1)
        except TimeoutException:
            print(f"Магазины списком не найдены для: {product_name}")

        soup_shops = BeautifulSoup(driver.page_source, 'html.parser')
        shop_cards = soup_shops.find_all('div', class_='card-map')
        
        for shop in shop_cards:
            addr_tag = shop.find('p', class_='card-map__address-title')
            qty_tag = shop.find('p', class_='card-map__quantity')
            
            address = addr_tag.text.strip() if addr_tag else ""
            qty_text = qty_tag.text.strip() if qty_tag else "0"
            
            qty_match = re.search(r'\d+', qty_text)
            quantity = int(qty_match.group()) if qty_match else 0
            
            if address:
                results.append({
                    "Номер": 0,
                    "Сеть": retail_name,
                    "Тип магазина": "Магазин",
                    "Адрес Торговой точки": city_name + " " + address,
                    "Бренд": brand,
                    "Название продукта": product_name,
                    "Цена": price_base,
                    "Цена по акции": price_promo,
                    "Фото товара": photo_url,
                    "Ссылка на страницу": product_url,
                    "Рейтинг": None,
                    "Объем": volume,
                    "Вес": "",
                    "Остаток": quantity,
                    "GTIN": gtin
                })
                
        if not results:
             results.append({
                "Номер": 0,
                "Сеть": retail_name,
                "Тип магазина": "Магазин",
                "Адрес Торговой точки": "Нет в наличии / Не указано",
                "Бренд": brand,
                "Название продукта": product_name,
                "Цена": price_base,
                "Цена по акции": price_promo,
                "Фото товара": photo_url,
                "Ссылка на страницу": product_url,
                "Рейтинг": None,
                "Объем": volume,
                "Вес": "",
                "Остаток": 0,
                "GTIN": gtin
            })

    except Exception as e:
        print(f"Ошибка при парсинге карточки {product_url}: {e}")
        
    return results