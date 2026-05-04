import time
import re
import urllib.parse
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

def check_and_bypass_waf(driver):
    """Обход проверки возраста"""
    try:
        age_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div/div[2]/div/div[2]/div[3]/button[1] | //button[contains(translate(text(), 'ДА', 'да'), 'да') or contains(text(), '18')]"))
        )
        age_btn.click()
        time.sleep(1)
        print("Плашка 18+ закрыта.")
    except TimeoutException:
        pass
    return True

def dismiss_city_popup(driver):
    """Закрывает плашку Да, верно"""
    try:
        confirm_btn = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(@class, 'dbtn') and (contains(., 'Да, верно') or contains(., 'Верно'))]"))
        )
        driver.execute_script("arguments[0].click();", confirm_btn)
        time.sleep(1)
    except:
        pass

def set_city(driver, city_name):
    driver.get("https://winestreet.ru/robots.txt")
    driver.delete_all_cookies()
    
    driver.get("https://winestreet.ru/")
    check_and_bypass_waf(driver)
    
    dismiss_city_popup(driver)
    
    try:
        city_header_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "/html/body/div[1]/div/div[1]/div/div[1]/div/div/div[1]/div"))
        )
        current_city = city_header_btn.text.strip()
        
        if city_name.lower() in current_city.lower():
            print(f"Город уже установлен корректно: {current_city}")
            return True
            
        driver.execute_script("arguments[0].click();", city_header_btn)
        time.sleep(1)
        
        target_city_xpath = f"//div[contains(@class, 'listRegions--item')]//a[contains(text(), '{city_name}')]"
        target_city_btn = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, target_city_xpath))
        )
        
        driver.execute_script("arguments[0].click();", target_city_btn)
        time.sleep(3)
        print(f"Город изменен на: {city_name}")
        return True
    except Exception as e:
        print(f"Ошибка при выборе города: {e}")
        return False

def get_product_links(driver, query):
    """Сбор ссылок с динамической пагинацией"""
    links = set()
    print(f"Начинаем поиск для '{query}'...")
    
    try:
        encoded_query = urllib.parse.quote(query)
        max_pages = 1
        current_page = 1
        
        while current_page <= max_pages:
            search_url = f"https://winestreet.ru/catalog/search/?filter.text={encoded_query}&page={current_page}"
            print(f" Парсим выдачу, страница: {current_page} из {max_pages}")
            
            driver.get(search_url)
            time.sleep(2)
            
            dismiss_city_popup(driver)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            
            if current_page == 1:
                pagination = soup.find_all('li', class_='page-item')
                if pagination and len(pagination) >= 2:
                    for item in reversed(pagination):
                        txt = item.get_text().strip()
                        if txt.isdigit():
                            max_pages = int(txt)
                            print(f"✅ Найдено страниц в пагинации: {max_pages}")
                            break

            product_cards = soup.find_all('div', class_='cardProduct')
            if not product_cards:
                break
                
            found_on_page = 0
            for card in product_cards:
                price_block = card.find('div', class_=lambda c: c and 'cardProduct--price' in c)
                if price_block and "нет в наличии" in price_block.get_text().lower():
                    continue
                
                a_tag = card.find('a', class_=lambda c: c and 'cardProduct--title' in c)
                if not a_tag:
                    a_tag = card.find('a', href=True)
                
                if a_tag and 'href' in a_tag.attrs:
                    href = a_tag['href']
                    if not href.startswith('http'):
                        href = f"https://winestreet.ru{href}"
                    
                    if href not in links:
                        links.add(href)
                        found_on_page += 1
            
            print(f"   Добавлено ссылок со стр {current_page}: {found_on_page}")
            current_page += 1
                
        print(f"ИТОГО уникальных ссылок 'В наличии': {len(links)}")
    except Exception as e:
        print(f"Ошибка при сборе ссылок: {e}")
        
    return list(links)

def clean_price(price_str):
    if not price_str: return 0.0
    cleaned = re.sub(r'[^\d.,]', '', price_str.replace(',', '.'))
    try:
        return float(cleaned)
    except:
        return 0.0

def extract_volume(name_str):
    match = re.search(r'(\d+[.,]?\d*)\s*(л|ml|мл|l|cl)', name_str, re.IGNORECASE)
    if match:
        return match.group(0).strip()
    return ""

def parse_product(driver, product_url, retail_name, city_name):
    """Сбор данных внутри карточки"""
    results = []
    try:
        driver.get(product_url)
        time.sleep(1.5)
        
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        name_tag = soup.find('h1', attrs={"itemprop": "name"})
        if not name_tag: name_tag = soup.find('h1')
        product_name = name_tag.get_text(separator=" ").strip() if name_tag else "Неизвестный товар"
        product_name = product_name.replace('\xa0', ' ')
        
        art_tag = soup.find(attrs={"itemprop": "productID"})
        gtin = art_tag.text.strip() if art_tag else ""
        

        img_tag = soup.find('img', attrs={"itemprop": "contentUrl"})
        photo_url = img_tag['src'] if img_tag and 'src' in img_tag.attrs else ""
        if photo_url and not photo_url.startswith('http'):
            photo_url = "https://static.winestreet.ru" + photo_url
            

        price_base = 0.0
        price_promo = None
        old_price_tag = soup.find('div', class_=lambda c: c and 'priceOld' in c)
        current_price_tag = soup.find(attrs={"itemprop": "price"})
        
        if old_price_tag and current_price_tag:
            price_base = clean_price(old_price_tag.text)
            price_promo = clean_price(current_price_tag.get('content') or current_price_tag.text)
        elif current_price_tag:
            price_base = clean_price(current_price_tag.get('content') or current_price_tag.text)
            

        brand = ""
        attrs_blocks = soup.find_all('div', class_='productAttributes--item')
        for block in attrs_blocks:
            header = block.find('strong', class_='productAttributes--header')
            if header and 'бренд' in header.text.lower():
                val_tag = block.find('span', class_='productAttributes--values')
                brand = val_tag.text.strip() if val_tag else ""
                break
                
        volume = extract_volume(product_name)


        try:
            dismiss_city_popup(driver)
            
            store_btn_xpath = "//a[contains(@href, '#stocks')] | //div[contains(@class, 'cardProduct--availability')]//a"
            store_btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.XPATH, store_btn_xpath))
            )
            driver.execute_script("arguments[0].click();", store_btn)
            time.sleep(3)
        except:
            pass

        soup_shops = BeautifulSoup(driver.page_source, 'html.parser')
        shop_cards = soup_shops.find_all('div', class_='goodsStock')
        
        for shop in shop_cards:
            addr_div = shop.find('div', class_='goodsStock--address')
            if addr_div:
                address = addr_div.get_text(separator=" ").strip().replace('\xa0', ' ')
                results.append({
                    "Номер": 0, "Сеть": retail_name, "Тип магазина": "Магазин",
                    "Адрес Торговой точки": address, "Бренд": brand,
                    "Название продукта": product_name, "Цена": price_base, "Цена по акции": price_promo,
                    "Фото товара": photo_url, "Ссылка на страницу": product_url,
                    "Рейтинг": None, "Объем": volume, "Вес": "", "Остаток": 1, "GTIN": gtin
                })
                
        if not results:
             results.append({
                "Номер": 0, "Сеть": retail_name, "Тип магазина": "Магазин",
                "Адрес Торговой точки": "Нет в наличии / Не указано",
                "Бренд": brand, "Название продукта": product_name,
                "Цена": price_base, "Цена по акции": price_promo,
                "Фото товара": photo_url, "Ссылка на страницу": product_url,
                "Рейтинг": None, "Объем": volume, "Вес": "", "Остаток": 0, "GTIN": gtin
            })

    except Exception as e:
        print(f"Ошибка при парсинге карточки {product_url}: {e}")
        
    return results