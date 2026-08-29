import time
import random
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys

MAX_PRODUCTS_PER_QUERY = 100


def smart_sleep(driver, fallback=1.5):
    min_d = getattr(driver, "custom_min_delay", fallback)
    max_d = getattr(driver, "custom_max_delay", fallback + 1.0)
    time.sleep(random.uniform(min_d, max_d))


def clean_price(price_val):
    if price_val is None:
        return 0.0
    if isinstance(price_val, (int, float)):
        return float(price_val)
    cleaned = re.sub(r"[^\d.,]", "", str(price_val).strip()).replace(",", ".")
    parts = cleaned.split(".")
    if len(parts) > 2:
        cleaned = "".join(parts[:-1]) + "." + parts[-1]
    try:
        return float(cleaned)
    except (ValueError, TypeError):
        return 0.0


def check_and_bypass_waf(driver, shop_name):
    try:
        age_btns = driver.find_elements(By.XPATH, "//button[contains(., '18') or contains(., 'Да, мне есть') or contains(., 'Да, мне исполнилось')]")
        for btn in age_btns:
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.5)

        cookie_btns = driver.find_elements(By.XPATH, "//button[contains(@class, 'cookie') or contains(., 'Принять') or contains(., 'Согласен')]")
        for btn in cookie_btns:
            if btn.is_displayed():
                driver.execute_script("arguments[0].click();", btn)
                time.sleep(0.5)
        return True
    except Exception:
        return True


def set_city(driver, city_name, shop_name):
    try:
        driver.get("https://luding.ru/")
        smart_sleep(driver, 1.5)
        check_and_bypass_waf(driver, shop_name)

        geo_triggers = driver.find_elements(By.CSS_SELECTOR, ".selector__text--geo")
        if not geo_triggers:
            geo_triggers = driver.find_elements(By.XPATH, "//span[contains(@class, 'selector__text')]")

        if not geo_triggers:
            print(f"[{shop_name}] Ошибка 500. Не найден селектор города")
            return 500

        driver.execute_script("arguments[0].click();", geo_triggers[0])
        smart_sleep(driver, 1.0)

        city_items = driver.find_elements(By.CSS_SELECTOR, ".selector__expander-link")
        if not city_items:
            city_items = driver.find_elements(By.XPATH, "//ul[contains(@class, 'selector__expander')]//a")

        target_link = None
        target_name_lower = city_name.strip().lower()

        for item in city_items:
            c_text = item.get_attribute("textContent").strip().lower()
            if target_name_lower == c_text or target_name_lower in c_text:
                target_link = item
                break

        if target_link:
            driver.execute_script("arguments[0].click();", target_link)
            smart_sleep(driver, 2.0)
            check_and_bypass_waf(driver, shop_name)
            print(f"[{shop_name}] Установлен город: {city_name}")
            return 200
        else:
            print(f"[{shop_name}] Ошибка 999. Город {city_name} не найден на сайте")
            return 999

    except Exception as e:
        print(f"[{shop_name}] Ошибка 500 при установке города {city_name}: {e}")
        return 500


def get_product_links(driver, query, shop_name):
    collected_links = []
    page_num = 1

    print(f"[{shop_name}] Сбор данных по запросу: {query}")
    driver.get("https://luding.ru/")
    smart_sleep(driver, 1.5)
    check_and_bypass_waf(driver, shop_name)

    try:
        search_input = WebDriverWait(driver, 5).until(
            EC.presence_of_element_located((By.XPATH, "//input[contains(@class, 'search__input')]"))
        )
        search_input.clear()
        search_input.send_keys(query)
        smart_sleep(driver, 0.5)

        
        search_btns = driver.find_elements(By.CSS_SELECTOR, "button.search-button.search__button")
        if not search_btns:
            search_btns = driver.find_elements(By.XPATH, "//button[contains(text(), 'Найти') or contains(@class, 'search__button')]")
        
        if search_btns:
            driver.execute_script("arguments[0].click();", search_btns[0])
        else:
            search_input.send_keys(Keys.ENTER) 

    except Exception:
        print(f"[{shop_name}] Не удалось найти строку поиска или кнопку")
        return []

    while len(collected_links) < MAX_PRODUCTS_PER_QUERY:
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".card-component-wrapper"))
            )
            smart_sleep(driver, 1.0)
            check_and_bypass_waf(driver, shop_name)

            cards = driver.find_elements(By.CSS_SELECTOR, ".card-component-wrapper")
            if not cards:
                break

            current_page_links = []
            for card in cards:
                try:
                    link_tags = card.find_elements(By.CSS_SELECTOR, ".card-component__name")
                    if not link_tags:
                        link_tags = card.find_elements(By.XPATH, ".//a[contains(@class, 'link-absolute') or contains(@href, '/collection/item/')]")

                    if link_tags:
                        href = link_tags[0].get_attribute("href")
                        if href:
                            if not href.startswith("http"):
                                href = f"https://luding.ru{href}"
                            if href not in collected_links and href not in current_page_links:
                                current_page_links.append(href)
                except Exception:
                    continue

            if not current_page_links:
                break

            for lk in current_page_links:
                if lk not in collected_links:
                    collected_links.append(lk)
                if len(collected_links) >= MAX_PRODUCTS_PER_QUERY:
                    break

            next_page_btns = driver.find_elements(By.XPATH, "//a[contains(@class, 'pagination__link') and contains(text(), 'След')]")
            if not next_page_btns or len(collected_links) >= MAX_PRODUCTS_PER_QUERY:
                break
            
            driver.execute_script("arguments[0].click();", next_page_btns[0])
            smart_sleep(driver, 2.0)
            page_num += 1

        except Exception as e:
            print(f"[{shop_name}] Ошибка при сборе ссылок (страница {page_num}): {e}")
            break

    return collected_links


def parse_product(driver, product_url, retail_name, city_name, shop_name):
    parsed_items = []
    try:
        driver.get(product_url)
        smart_sleep(driver, 1.5)
        check_and_bypass_waf(driver, shop_name)

        title_elems = driver.find_elements(By.TAG_NAME, "h1")
        if not title_elems:
            title_elems = driver.find_elements(By.CSS_SELECTOR, ".rdd-only-sticky__title")
        product_name = title_elems[0].text.strip() if title_elems else ""

        brand_text = ""
        brand_elems = driver.find_elements(By.CSS_SELECTOR, ".rdd-brands__name")
        if not brand_elems:
            brand_elems = driver.find_elements(By.XPATH, "//a[contains(@href, '/collection/brands/')]//span")
        if brand_elems:
            brand_text = brand_elems[0].text.strip()

        sku_elems = driver.find_elements(By.CSS_SELECTOR, ".rdd-product-code__value")
        if not sku_elems:
            sku_elems = driver.find_elements(By.XPATH, "//*[contains(text(), 'Код товара')]/following-sibling::*")
        gtin_text = ""
        if sku_elems:
            raw_sku = sku_elems[0].text.strip()
            sku_match = re.search(r"\d+", raw_sku)
            gtin_text = sku_match.group(0) if sku_match else raw_sku

        volume_text = ""
        vol_elems = driver.find_elements(By.CSS_SELECTOR, ".rdd-volumes__link--active")
        if not vol_elems:
            vol_elems = driver.find_elements(By.XPATH, "//div[contains(@class, 'rdd-volumes')]//a[contains(@class, 'active')]")
        if vol_elems:
            volume_text = vol_elems[0].text.strip()

        weight_text = ""
        vol_fallback, weight_fallback = extract_volume_weight(product_name)
        if not volume_text:
            volume_text = vol_fallback
        if not weight_text:
            weight_text = weight_fallback

        photo_elems = driver.find_elements(By.CSS_SELECTOR, ".detail-image__slider-img img")
        if not photo_elems:
            photo_elems = driver.find_elements(By.CSS_SELECTOR, ".rdd-only-sticky__img")
        photo_url = ""
        if photo_elems:
            photo_url = photo_elems[0].get_attribute("src") or photo_elems[0].get_attribute("data-src") or ""
            if photo_url and not photo_url.startswith("http"):
                photo_url = f"https://luding.ru{photo_url}"

        main_base_price = 0.0
        main_promo_price = None
        promo_elems = driver.find_elements(By.CSS_SELECTOR, ".rdd-price__discount")
        base_elems = driver.find_elements(By.CSS_SELECTOR, ".rdd-price__main")

        if promo_elems and base_elems:
            main_promo_price = clean_price(promo_elems[0].text)
            main_base_price = clean_price(base_elems[0].text)
        elif base_elems:
            main_base_price = clean_price(base_elems[0].text)
        elif promo_elems:
            main_base_price = clean_price(promo_elems[0].text)

        
        shops_parsed = []
        where_buy_btns = driver.find_elements(By.XPATH, "//button[@data-detail-where-buy-bound='1' or contains(text(), 'Где купить')]")
        if not where_buy_btns:
            where_buy_btns = driver.find_elements(By.XPATH, "//button[contains(@class, 'rdd-where-buy-button')]")
        
        if where_buy_btns:
            try:
                driver.execute_script("arguments[0].click();", where_buy_btns[0])
                
                WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, ".rdd-shops__item"))
                )
                smart_sleep(driver, 1.0) 

                shop_rows = driver.find_elements(By.CSS_SELECTOR, ".rdd-shops__item")
                for row in shop_rows:
                    addr_elems = row.find_elements(By.CSS_SELECTOR, ".rdd-shops-item__name")
                    if not addr_elems:
                        continue
                    full_addr = addr_elems[0].text.strip()

                    status_elems = row.find_elements(By.CSS_SELECTOR, ".rdd-status-value")
                    status_text = status_elems[0].text.strip().lower() if status_elems else ""
                    stock_val = 1 if "наличи" in status_text else 0

                    row_prices = row.find_elements(By.CSS_SELECTOR, ".rdd-shops__price")
                    r_base = main_base_price
                    r_promo = main_promo_price
                    
                    if len(row_prices) == 2:
                        promo_elem = row.find_elements(By.CSS_SELECTOR, ".rdd-shops__price--discount")
                        if promo_elem:
                            r_promo = clean_price(promo_elem[0].text)
                            for p in row_prices:
                                if "discount" not in p.get_attribute("class"):
                                    r_base = clean_price(p.text)
                    elif len(row_prices) == 1:
                        r_base = clean_price(row_prices[0].text)
                        r_promo = None

                    shops_parsed.append({
                        "address": f"{city_name} ({full_addr})",
                        "stock": stock_val,
                        "price_base": r_base,
                        "price_promo": r_promo
                    })
            except Exception:
                pass

        if not shops_parsed:
            shops_parsed.append({
                "address": f"{city_name} (Основной склад)",
                "stock": 1,
                "price_base": main_base_price,
                "price_promo": main_promo_price
            })

        for sp in shops_parsed:
            parsed_items.append({
                "Номер": 0,
                "Сеть": retail_name,
                "Тип магазина": "Магазин",
                "Адрес Торговой точки": sp["address"],
                "Бренд": brand_text,
                "Название продукта": product_name,
                "Цена": sp["price_base"],
                "Цена по акции": sp["price_promo"],
                "Фото товара": photo_url,
                "Ссылка на страницу": product_url,
                "Рейтинг": None,
                "Объем": volume_text,
                "Вес": weight_text,
                "Остаток": sp["stock"],
                "GTIN": gtin_text
            })

    except Exception as e:
        print(f"[{shop_name}] Ошибка парсинга товара {product_url}: {e}")

    return parsed_items


def extract_volume_weight(text):
    weight_str, volume_str = "", ""
    txt = str(text).lower()
    vol_match = re.search(r"(\d+[.,]?\d*)\s*(мл|л)\b", txt)
    if vol_match:
        volume_str = f"{vol_match.group(1)} {vol_match.group(2)}"
    w_match = re.search(r"(\d+[.,]?\d*)\s*(г|кг)\b", txt)
    if w_match:
        weight_str = f"{w_match.group(1)} {w_match.group(2)}"
    return volume_str, weight_str