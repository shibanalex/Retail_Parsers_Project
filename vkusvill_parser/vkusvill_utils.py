import time
import random
import re
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from .vkusvill_config import VKUSVILL_VALID_ADDRESSES

def smart_sleep(driver, fallback=2.0):
    if hasattr(driver, 'custom_min_delay') and hasattr(driver, 'custom_max_delay'):
        time.sleep(random.uniform(driver.custom_min_delay, driver.custom_max_delay))
    else:
        time.sleep(fallback)

def set_city_address(driver, city_name, shop_name):
    safe_address = VKUSVILL_VALID_ADDRESSES.get(city_name, f"{city_name}, улица Ленина, 1")
    
    try:
        addr_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".HeaderATDToggler._address button"))
        )
        driver.execute_script("arguments[0].click();", addr_btn)
        time.sleep(1.5)

        input_area = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "textarea#js-my-addresses-address, input#js-my-addresses-address"))
        )
        input_area.clear()
        input_area.send_keys(safe_address)
        smart_sleep(driver, 3.0) 

        suggestion = WebDriverWait(driver, 7).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#js-my-addresses-suggests-delivery .VV_DMenuContentList button"))
        )
        driver.execute_script("arguments[0].click();", suggestion)
        smart_sleep(driver, 4.0) 

        buttons = driver.find_elements(By.XPATH, "//button[contains(@class, 'VV_Button') and (contains(text(), 'Сохранить') or contains(text(), 'Выбрать'))]")
        for btn in buttons:
            if btn.is_displayed() and "_disabled" not in btn.get_attribute("class"):
                driver.execute_script("arguments[0].click();", btn)
                smart_sleep(driver, 2.0)
                break
        
        driver.refresh()
        smart_sleep(driver, 3.0)
        return True
    except Exception:
        return False

def get_brand(name, brand_list, shop_name):
    name_lower = name.lower()
    if brand_list:
        for b in brand_list:
            if b.lower() in name_lower:
                return b
    known_brands = ["Агуша", "ЭкоНива", "Parmalat", "Село Зеленое", "Простоквашино"]
    for b in known_brands:
        if b.lower() in name_lower: return b
    return shop_name

def filter_dynamic_query(items, query):
    if not items: return []
    query_words = [w.strip(".,!-") for w in query.lower().split()]
    filtered_items = []
    
    for item in items:
        name = str(item.get("Название продукта", "")).lower()
        is_match = True
        for qw in query_words:
            if not qw in name:
                is_match = False; break
        if is_match:
            filtered_items.append(item)
    return filtered_items

def parse_html_to_items(html_source, safe_address, brand_list, shop_name):
    soup = BeautifulSoup(html_source, "html.parser")
    cards = soup.find_all("div", class_="ProductCard")
    parsed_items = []

    for card in cards:
        try:
            name_tag = card.find("a", class_="ProductCard__link")
            if not name_tag: continue
            
            name = name_tag.text.strip().replace('\xa0', ' ')
            url = "https://vkusvill.ru" + name_tag.get("href", "")
            brand = get_brand(name, brand_list, shop_name)

            img_tag = card.find("img", class_="ProductCard__imageImg")
            photo_url = img_tag.get("data-src") or img_tag.get("src") if img_tag else None
            
            price_tag = card.find("span", class_="js-datalayer-catalog-list-price")
            price = None
            if price_tag:
                p_text = re.sub(r'[^\d.]', '', price_tag.text.replace(',', '.'))
                price = float(p_text) if p_text else None
            
            old_price_tag = card.find("span", class_="js-datalayer-catalog-list-price-old")
            old_price = None
            if old_price_tag:
                op_text = re.sub(r'[^\d.]', '', old_price_tag.text.replace(',', '.'))
                old_price = float(op_text) if op_text else None

            weight_tag = card.find("div", class_="ProductCard__weight")
            weight = weight_tag.text.strip() if weight_tag else None

            parsed_items.append({
                "Номер": 0,
                "Сеть": shop_name, 
                "Тип магазина": "Даркстор",
                "Адрес Торговой точки": safe_address, 
                "Бренд": brand,
                "Название продукта": name,
                "Цена": price,
                "Цена по акции": old_price,
                "Фото товара": photo_url,
                "Ссылка на страницу": url,
                "Рейтинг": None,
                "Объем": None,
                "Вес": weight,
                "Остаток": 1,
                "GTIN": card.get("data-id")
            })
        except Exception:
            continue
    return parsed_items