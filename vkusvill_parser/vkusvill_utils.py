import time
import re
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

from .vkusvill_config import VKUSVILL_VALID_ADDRESSES

def set_city_address(driver, city_name):
    """Устанавливает реальный адрес доставки, чтобы разблокировать остатки."""
    safe_address = VKUSVILL_VALID_ADDRESSES.get(city_name, f"{city_name}, улица Ленина, 1")
    print(f"   📍 Начинаем привязку к складу по адресу: {safe_address}")
    
    try:
        addr_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, ".HeaderATDToggler._address button"))
        )
        driver.execute_script("arguments[0].click();", addr_btn)
        time.sleep(2)

        try:
            add_new = driver.find_element(By.CSS_SELECTOR, ".js-my-addresses-add-new-button")
            if add_new.is_displayed():
                driver.execute_script("arguments[0].click();", add_new)
                time.sleep(2)
        except:
            pass

        input_area = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "textarea#js-my-addresses-address, input#js-my-addresses-address"))
        )
        input_area.clear()
        input_area.send_keys(safe_address)
        time.sleep(4) 

        suggestion = WebDriverWait(driver, 7).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#js-my-addresses-suggests-delivery .VV_DMenuContentList button"))
        )
        driver.execute_script("arguments[0].click();", suggestion)
        
        print("   ⏳ Подсказка выбрана. Карта проверяет зону доставки...")
        time.sleep(5) 

        buttons = driver.find_elements(By.XPATH, "//button[contains(@class, 'VV_Button') and (contains(text(), 'Сохранить') or contains(text(), 'Выбрать'))]")
        for btn in buttons:
            if btn.is_displayed() and "_disabled" not in btn.get_attribute("class"):
                driver.execute_script("arguments[0].click();", btn)
                print("   ✅ Нажали 'Сохранить' на карте.")
                time.sleep(3)
                break
        
        try:
            final_select = driver.find_element(By.XPATH, "//div[contains(@class, 'VV23_RWayModal__Footer')]//button[contains(text(), 'Выбрать')]")
            if final_select.is_displayed() and "_disabled" not in final_select.get_attribute("class"):
                driver.execute_script("arguments[0].click();", final_select)
                print("   ✅ Нажали финальное 'Выбрать'.")
                time.sleep(2)
        except:
            pass

        driver.refresh()
        time.sleep(4)

        header_text = driver.find_element(By.CSS_SELECTOR, ".HeaderATDToggler._address").text.replace('\n', ' ')
        if "Выберите способ" in header_text:
            print("   ⚠️ Адрес не применился (остатки будут -1).")
            return False
        else:
            print(f"   🎯 Успех! К складу привязались. В шапке: {header_text.strip()}")
            return True

    except Exception as e:
        print(f"   ⚠️ Ошибка установки адреса: {e}")
        return False


def get_brand(name, brand_list):
    """Умное извлечение бренда из названия товара"""
    name_lower = name.lower()
    if brand_list:
        for b in brand_list:
            if b.lower() in name_lower:
                return b
    known_brands = [
        "Агуша", "ЭкоНива", "Parmalat", "Алексеевское", "Рогачевъ", 
        "Можайский", "Северная Долина", "Село Зеленое", "Свитлогорье",
        "Правильное молоко", "Простоквашино", "Домик в деревне", "Рузское"
    ]
    for b in known_brands:
        if b.lower() in name_lower: return b
    return "ВкусВилл"


def filter_dynamic_query(items, query):
    """Строгий динамический фильтр. Отсекает мусор."""
    if not items: return []
    query_words = [w.strip(".,!-") for w in query.lower().split()]
    filtered_items = []
    global_stop_words = ["сгущен", "коктейль", "мороженое", "десерт", "сырок", "запеканка", "оладьи", "блины", "сырники", "блинчики"]
    
    for item in items:
        name = str(item.get("Название продукта", "")).lower()
        if any(stop_word in name for stop_word in global_stop_words):
            continue
        is_match = True
        for qw in query_words:
            if any(char.isdigit() for char in qw):
                if qw not in name.replace(',', '.'):
                    is_match = False; break
            else:
                pattern = r'(?<![а-яёa-z])' + re.escape(qw) + r'(?![а-яёa-z])'
                if not re.search(pattern, name):
                    is_match = False; break
        
        if is_match:
            filtered_items.append(item)
    return filtered_items


def parse_html_to_items(html_source, city_name, brand_list):
    """Парсит HTML страницу поиска ВкусВилл"""
    soup = BeautifulSoup(html_source, "html.parser")
    cards = soup.find_all("div", class_="ProductCard")
    parsed_items = []

    for card in cards:
        try:
            name_tag = card.find("a", class_="ProductCard__link")
            if not name_tag: continue
            
            name = name_tag.text.strip().replace('\xa0', ' ')
            url = "https://vkusvill.ru" + name_tag.get("href", "")
            brand = get_brand(name, brand_list)

            img_tag = card.find("img", class_="ProductCard__imageImg")
            photo_url = img_tag.get("data-src") or img_tag.get("src") if img_tag else None
            if photo_url and photo_url.startswith("//"): photo_url = "https:" + photo_url

            product_id = card.get("data-id")

            price_tag = card.find("span", class_="js-datalayer-catalog-list-price")
            price = None
            if price_tag:
                p_text = price_tag.text.strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
                price = float(p_text) if p_text.replace('.', '').isdigit() else None
            
            old_price_tag = card.find("span", class_="js-datalayer-catalog-list-price-old")
            old_price = None
            if old_price_tag:
                op_text = old_price_tag.text.strip().replace(' ', '').replace('\xa0', '').replace(',', '.')
                old_price = float(op_text) if op_text.replace('.', '').isdigit() else None

            if old_price == price: old_price = None

            weight_tag = card.find("div", class_="ProductCard__weight")
            weight = weight_tag.text.strip().replace('\xa0', ' ') if weight_tag else None

            # ОСТАТОК
            stock = -1
            q_input = card.find("input", class_="js-delivery__product__q")
            if q_input and q_input.get("data-max"):
                try: stock = int(q_input.get("data-max"))
                except: pass
            
            if stock == -1:
                add_btn = card.find("button", class_="js-delivery__basket--add")
                if add_btn and add_btn.get("data-max"):
                    try: stock = int(add_btn.get("data-max"))
                    except: pass
            
            if stock == -1:
                stock_text = card.find("div", class_="ProductCard__Rest")
                if stock_text:
                    match = re.search(r'\d+', stock_text.text)
                    if match: stock = int(match.group())
                    else: stock = 1
                else: stock = 0

            rating_tag = card.find("div", class_="ProductCard__ratingText")
            rating = None
            if rating_tag:
                r_text = rating_tag.text.strip().replace(',', '.')
                try: rating = float(r_text)
                except: rating = None

            parsed_items.append({
                "Номер": 0,
                "Сеть": city_name, 
                "Тип магазина": "Магазин/Дарксторы",
                "Адрес Торговой точки": "", 
                "Бренд": brand,
                "Название продукта": name,
                "Цена": price,
                "Цена по акции": old_price,
                "Фото товара": photo_url,
                "Ссылка на страницу": url,
                "Рейтинг": rating,
                "Объем": None,
                "Вес": weight,
                "Остаток": stock,
                "GTIN": product_id
            })
        except Exception:
            continue

    return parsed_items