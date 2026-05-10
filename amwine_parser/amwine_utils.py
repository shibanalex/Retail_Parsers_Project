import time
import re
import urllib.parse
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.action_chains import ActionChains

def check_and_bypass_waf(driver):
    try:
        age_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, '//button[contains(@class, "modal__button") and contains(., "Подтверждаю")]'))
        )
        driver.execute_script("arguments[0].click();", age_btn)
        time.sleep(1)
    except:
        pass
    
    try:
        cookie = driver.find_element(By.XPATH, '//button[contains(text(), "Согласен") or contains(text(), "Хорошо")]')
        driver.execute_script("arguments[0].click();", cookie)
    except:
        pass
    return True

def select_shop(driver, city_name, visited_addresses):
    driver.get("https://amwine.ru/")
    check_and_bypass_waf(driver)
    
    try:
        addr_caller = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "address-picker__caller"))
        )
        driver.execute_script("arguments[0].click();", addr_caller)
        time.sleep(2)

        change_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "address-picker__balloon-button-get-shops"))
        )
        driver.execute_script("arguments[0].click();", change_btn)
        time.sleep(2)

        ok_btn = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, '//div[contains(@class, "modal__footer")]//button[contains(., "Хорошо")]'))
        )
        driver.execute_script("arguments[0].click();", ok_btn)
        time.sleep(3)

        city_dd = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.CLASS_NAME, "select__button-text"))
        )
        if city_name.lower() not in city_dd.text.lower():
            driver.execute_script("arguments[0].click();", city_dd)
            time.sleep(1.5)
            target_city = WebDriverWait(driver, 10).until(
                EC.element_to_be_clickable((By.XPATH, f'//button[contains(@class, "select__option-button") and contains(., "{city_name}")]'))
            )
            driver.execute_script("arguments[0].click();", target_city)
            time.sleep(5) 

        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.XPATH, '//article[contains(@class, "shop-list-card")]'))
        )
        time.sleep(2)

        last_scrolled_address = ""
        scroll_stuck_counter = 0

        while True:
            shops = driver.find_elements(By.XPATH, '//article[contains(@class, "shop-list-card")]')
            if not shops: 
                return None

            for shop in shops:
                try:
                    addr = shop.find_element(By.CLASS_NAME, "shop-list-card__title").text.strip()
                    if addr not in visited_addresses:
                        select_btn = shop.find_element(By.XPATH, './/button[contains(@class, "shop-list-card__button-select")]')
                        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", select_btn)
                        time.sleep(0.5)
                        driver.execute_script("arguments[0].click();", select_btn)
                        time.sleep(3)
                        return addr
                except:
                    break
            
            try:
                last_shop = shops[-1]
                current_last_addr = last_shop.find_element(By.CLASS_NAME, "shop-list-card__title").text.strip()
                
                driver.execute_script("arguments[0].scrollIntoView({block: 'end'});", last_shop)
                time.sleep(2) 

                if current_last_addr == last_scrolled_address:
                    scroll_stuck_counter += 1
                    if scroll_stuck_counter >= 3:
                        return None
                else:
                    last_scrolled_address = current_last_addr
                    scroll_stuck_counter = 0

            except:
                time.sleep(1) 

    except Exception as e:
        print(f"Error selecting shop: {e}")
        return None

def update_url_page(url, page_num):

    parsed = urllib.parse.urlparse(url)
    query_dict = urllib.parse.parse_qs(parsed.query)
    query_dict['page'] = [str(page_num)]
    new_query = urllib.parse.urlencode(query_dict, doseq=True)
    return urllib.parse.urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, new_query, parsed.fragment))

def scroll_page_smoothly(driver):

    total_height = driver.execute_script("return document.body.scrollHeight")
    for i in range(1, total_height, 600):
        driver.execute_script(f"window.scrollTo(0, {i});")
        time.sleep(0.2)
    time.sleep(1)

def get_product_links(driver, query):

    all_links = set()

    try:
        driver.get("https://amwine.ru/")
        check_and_bypass_waf(driver)
        time.sleep(2)

        header = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "header"))
        )
        ActionChains(driver).move_to_element(header).perform()
        time.sleep(1)

        search_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.NAME, "q"))
        )
        driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", search_input)
        time.sleep(0.5)
        driver.execute_script("arguments[0].focus();", search_input)
        time.sleep(0.5)

        search_input.send_keys(Keys.CONTROL + "a")
        search_input.send_keys(Keys.BACKSPACE)
        time.sleep(0.3)

        ActionChains(driver).move_to_element(search_input).click().send_keys(query).perform()
        time.sleep(1)
        search_input.send_keys(Keys.ENTER)
        time.sleep(5)

        soup = BeautifulSoup(driver.page_source, "html.parser")
        max_page = 1
        
        pagination_items = soup.find_all("li", class_=lambda x: x and "pagination__item" in x)
        for item in pagination_items:
            text = item.text.strip()
            if text.isdigit() and int(text) > max_page:
                max_page = int(text)

        base_url = driver.current_url

        for page in range(1, max_page + 1):
            if page > 1:
                next_page_url = update_url_page(base_url, page)
                driver.get(next_page_url)
                time.sleep(3)
            
            scroll_page_smoothly(driver)
            soup = BeautifulSoup(driver.page_source, "html.parser")
            cards = soup.find_all('div', class_=lambda x: x and 'product-item__content' in x)
            
            for card in cards:
                card_text = card.get_text(separator=' ', strip=True).lower()
                if "закончился" in card_text or "нет в наличии" in card_text:
                    continue
                
                a_tag = card.find('a', class_=lambda x: x and 'product-item__title-link' in x)
                if a_tag and a_tag.get('href'):
                    full_url = urllib.parse.urljoin("https://amwine.ru", a_tag['href'])
                    all_links.add(full_url)

        return list(all_links)

    except Exception as e:
        print(f"Error during search for query '{query}': {e}")
        return []

def parse_product(driver, url, retail_name, city, address):

    try:
        driver.get(url)
        time.sleep(2)
        check_and_bypass_waf(driver)
        
        page_src = driver.page_source.lower()
        if "товар закончился" in page_src or "нет в наличии" in page_src or "осталось 0 шт" in page_src:
            return []

        soup = BeautifulSoup(driver.page_source, 'html.parser')
        
        price_old = soup.find('span', class_=re.compile('price-discount-old'))
        price_curr = soup.find('span', class_=re.compile('price-current'))
        
        def clean_p(txt):
            return float(re.sub(r'[^\d.,]', '', txt.replace(',', '.'))) if txt else 0.0

        p_promo = clean_p(price_curr.text) if price_curr else 0.0
        p_base = clean_p(price_old.text) if price_old else p_promo

        try:
            brand = driver.find_element(By.XPATH, '//li[.//span[contains(text(), "Бренд")]]/a').text.strip()
        except: 
            brand = ""
        
        try:
            volume = driver.find_element(By.XPATH, '//li[.//span[contains(text(), "Объем")]]/span[2]').text.strip()
        except: 
            volume = ""
        
        sku_tag = soup.find('span', class_=re.compile('product-hero__head-item'))
        gtin = re.sub(r'[^\d]', '', sku_tag.text) if sku_tag else ""

        stock = 1
        stock_tag = soup.find(lambda tag: tag.has_attr('class') and any('wherehouse' in c for c in tag['class']))
        if stock_tag:
            nums = re.findall(r'\d+', stock_tag.text)
            if nums:
                stock = int(nums[0])

        img = soup.find('img', class_=re.compile('product-hero-carousel__media-img'))
        photo = img['src'] if img else ""
        if photo and not photo.startswith('http'):
            photo = "https://amwine.ru" + photo

        h1_tag = soup.find('h1')
        product_name = h1_tag.text.strip() if h1_tag else ""

        return [{
            "Номер": 0,
            "Сеть": retail_name,
            "Тип магазина": "Магазин",
            "Адрес Торговой точки": address,
            "Бренд": brand,
            "Название продукта": product_name,
            "Цена": p_base,
            "Цена по акции": p_promo if p_base != p_promo else None,
            "Фото товара": photo,
            "Ссылка на страницу": url,
            "Рейтинг": None,
            "Объем": volume,
            "Вес": "",
            "Остаток": stock,
            "GTIN": gtin
        }]
    except Exception as e:
        print(f"Error parsing product {url}: {e}")
        return []