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
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "header"))
        )
    except TimeoutException:
        pass

    try:
        cookie_btn = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(translate(text(), 'ПОНЯТНО', 'понятно'), 'понятно') or contains(text(), 'Принять')]"))
        )
        driver.execute_script("arguments[0].click();", cookie_btn)
        time.sleep(0.5)
    except TimeoutException:
        pass

    try:
        city_confirm_btn = WebDriverWait(driver, 3).until(
            EC.presence_of_element_located((By.XPATH, "//button[contains(text(), 'Да, верно') or contains(text(), 'Всё верно')]"))
        )
        driver.execute_script("arguments[0].click();", city_confirm_btn)
        time.sleep(0.5)
    except TimeoutException:
        pass

    return True

def set_city(driver, city_name, shop_name):
    try:
        driver.get("https://www.r-ulybka.ru/")
        smart_sleep(driver, 2.0)
    except Exception as e:
        print(f"[{shop_name}] Ошибка 404. Не удалось загрузить главную страницу.")
        return 404

    check_and_bypass_waf(driver, shop_name)

    try:
        city_trigger = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "/html/body/div[3]/header/div[2]/div[1]/div/div[1]/div/span | //header//div[contains(@class, 'MuiStack-root')]//span[contains(@class, 'MuiTypography-root') and not(contains(text(), 'Войти')) and not(contains(text(), 'Корзина'))]"))
        )
        
        current_city = driver.execute_script("return arguments[0].innerText;", city_trigger).strip()
        
        if city_name.lower() in current_city.lower():
            return 200

        driver.execute_script("arguments[0].click();", city_trigger)
        smart_sleep(driver, 1.5)
        
        try:
            city_option = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.XPATH, f"//div[contains(@class, 'MuiGrid-item')]//span[contains(text(), '{city_name}')]"))
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
        encoded_query = urllib.parse.quote(query)
        page = 1
        max_pages = 10 
        
        while page <= max_pages:
            search_url = f"https://www.r-ulybka.ru/search/?q={encoded_query}&page={page}"
            driver.get(search_url)
            smart_sleep(driver, 3.0)
            
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            product_cards = soup.find_all('a', href=re.compile(r'/catalog/goods/.*-\d+/$'))
            
            links_count_before = len(links)
            
            for card in product_cards:
                href = card['href']
                if not href.startswith('http'):
                    href = f"https://www.r-ulybka.ru{href}"
                links.add(href)
                
            if len(links) == links_count_before:
                break
                
            page += 1
            
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
        img_tag = soup.find('img', fetchpriority="high") or soup.find('img', alt=product_name)
        if img_tag and 'src' in img_tag.attrs:
            photo_url = img_tag['src']
            if not photo_url.startswith('http') and not photo_url.startswith('data:'):
                photo_url = "https://www.r-ulybka.ru" + photo_url
            
        price_base = 0.0
        price_promo = None
        
        price_tags = soup.find_all(class_=re.compile(r'MuiTypography-(h1|h2)'))
        prices = []
        for tag in price_tags:
            text = tag.get_text(separator=' ', strip=True)
            if '₽' in text:
                p = clean_price(text)
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
        rating = None
        
        dts = soup.find_all('dt')
        for dt in dts:
            label = dt.text.lower()
            dd = dt.find_next_sibling('dd')
            if not dd: continue
            val = dd.text.strip()
            
            if 'бренд' in label:
                brand = val
            elif 'фасовка' in label or 'объем' in label:
                if 'мл' in val.lower():
                    volume = val
                else:
                    weight = val
            elif 'вес' in label:
                weight = val

        art_span = soup.find(string=re.compile(r'Арт\.'))
        if art_span:
            parent = art_span.parent.parent if art_span.parent else None
            if parent:
                gtin_match = re.search(r'\d+', parent.text)
                if gtin_match:
                    gtin = gtin_match.group()

        rating_svg = soup.find('svg', attrs={'aria-hidden': 'true'}) 
        if rating_svg:
            rating_container = soup.find(attrs={'aria-label': re.compile(r'Stars', re.I)})
            if rating_container and rating_container.previous_sibling:
                try:
                    rating = float(rating_container.previous_sibling.text.strip())
                except:
                    pass

        stock_int = 1
        if soup.find(string=re.compile(r'Нет в наличии', re.I)):
            stock_int = 0

        results.append({
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Магазин",
            "Адрес Торговой точки": f"{city_name}, Доставка / Самовывоз",
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
        print(f"[{shop_name}] Ошибка при парсинге карточки.")
        
    return results