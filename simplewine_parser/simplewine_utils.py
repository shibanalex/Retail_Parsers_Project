import time
import re
from bs4 import BeautifulSoup
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException

def check_and_bypass_waf(driver):
    try:
        age_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[.//span[contains(text(), 'Подтверждаю')]] | //button[contains(text(), 'Подтверждаю')] | //button[contains(translate(text(), 'ПОДТВЕРДИТЬ', 'подтвердить'), 'подтвердить')]"))
        )
        driver.execute_script("arguments[0].click();", age_btn)
        time.sleep(1)
    except TimeoutException:
        pass
    return True

def set_city(driver, city_name):
    driver.get("https://simplewine.ru/")
    check_and_bypass_waf(driver)
    
    try:
        city_btn = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "//header//div[contains(@class, 'city')]//button | //header//button[contains(@class, 'location')] | /html/body/div[1]/div/div/header/div/div/div[1]/div/div/div/ul[2]/li[1]/div/button"))
        )
        
        driver.execute_script("arguments[0].click();", city_btn)
        time.sleep(1)
        
        target_city_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, f"//li[contains(text(), '{city_name}')] | //div[contains(@class, 'modal')]//li[contains(., '{city_name}')]"))
        )
        driver.execute_script("arguments[0].click();", target_city_btn)
        time.sleep(2)
        return True
    except Exception:
        return False

def get_product_links(driver, query):
    links = set()
    try:
        search_input = WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.XPATH, "/html/body/div[1]/div/div/header/div/div/div[2]/div/div[2]/form/label/input | //input[@type='search']"))
        )
        search_input.clear()
        search_input.send_keys(query)
        
        search_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div/div/header/div/div/div[2]/div/div[2]/form/label/div/button/span | //button[@type='submit']"))
        )
        driver.execute_script("arguments[0].click();", search_btn)
        time.sleep(3)
        
        cards_found = False
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CLASS_NAME, "snippet"))
            )
            cards_found = True
        except TimeoutException:
            pass
            
        if not cards_found:
            try:
                search_input_404 = WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.XPATH, "/html/body/div[1]/header/div/div[2]/div[2]/form/div/input"))
                )
                search_input_404.clear()
                search_input_404.send_keys(query)
                search_input_404.send_keys(Keys.ENTER)
                time.sleep(3)
                
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.CLASS_NAME, "snippet"))
                )
            except Exception:
                pass
        
        retries = 0       
        max_retries = 4   
        
        while True:
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            product_cards = soup.find_all('article', class_=lambda x: x and 'snippet' in x)
            
            links_count_before = len(links)
            
            for card in product_cards:
                status = card.find('div', class_='snippet-status')
                if status and 'нет в наличии' in status.text.lower():
                    continue
                    
                a_tag = card.find('a', class_='snippet-name')
                if a_tag and 'href' in a_tag.attrs:
                    href = a_tag['href']
                    if not href.startswith('http'):
                        href = f"https://simplewine.ru{href}"
                    links.add(href)
                    
            if len(links) > links_count_before:
                retries = 0
            else:
                retries += 1
                
            if retries >= max_retries:
                break
                
            try:
                cards_elements = driver.find_elements(By.CSS_SELECTOR, "article.snippet")
                if cards_elements:
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", cards_elements[-1])
                else:
                    driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            except Exception:
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                
            time.sleep(2) 
            
    except Exception:
        pass
        
    return list(links)

def clean_price(price_str):
    if not price_str: return 0.0
    cleaned = re.sub(r'[^\d.,]', '', str(price_str).replace(',', '.'))
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
        product_name = h1_tag.text.strip() if h1_tag else ""

        photo_url = ""
        try:
            img_elem = driver.find_element(By.XPATH, "/html/body/div[1]/div/div/main/div[1]/div[2]/div[2]/div/div[1]/div[1]/div/div/div[2]/div/div[1]/div[1]/div/div/picture/img | //img[@itemprop='image']")
            photo_url = img_elem.get_attribute("src")
        except Exception:
            pass

        if not photo_url:
            img_tag = soup.find('img', itemprop='image')
            if img_tag and 'src' in img_tag.attrs:
                photo_url = img_tag['src']

        if photo_url and not photo_url.startswith('http'):
            photo_url = "https://static.simplewine.ru" + photo_url

        p_main_text = ""
        try:
            p_main_elem = driver.find_element(By.XPATH, "/html/body/div[1]/div/div/main/div[1]/div[2]/div[2]/div/div[1]/div[2]/div[2]/div[1]/div[2]/span | /html/body/div[1]/div/div/main/div[1]/div[2]/div[2]/div/div[1]/div[2]/div[2]/div[2]/div[2]/div/div/span")
            p_main_text = p_main_elem.text
        except Exception:
            pass

        p_promo_text = ""
        try:
            p_promo_elem = driver.find_element(By.XPATH, "/html/body/div[1]/div/div/main/div[1]/div[2]/div[2]/div/div[1]/div[2]/div[2]/div[1]/div[2]/div/div/span")
            p_promo_text = p_promo_elem.text
        except Exception:
            pass

        price_base = clean_price(p_main_text)
        price_promo = clean_price(p_promo_text) if p_promo_text else None

        if price_base == 0.0:
            price_meta = soup.find('meta', itemprop='price')
            if price_meta:
                price_base = clean_price(price_meta.get('content', ''))

        if price_base == 0.0 and price_promo:
            price_base = price_promo
            price_promo = None

        try:
            volume = driver.find_element(By.XPATH, "/html/body/div[1]/div/div/main/div[1]/div[2]/div[2]/div/div[1]/div[2]/div[1]/div[2]/div[1]/div[3]/a/span").text
        except Exception:
            volume = ""

        try:
            brand = driver.find_element(By.XPATH, "/html/body/div[1]/div/div/main/div[1]/div[2]/div[2]/div/div[1]/div[2]/div[1]/div[2]/div[1]/div[5]/a/span").text
        except Exception:
            brand = ""

        gtin = ""
        try:
            sku_meta = soup.find('meta', itemprop='sku')
            if sku_meta:
                gtin = sku_meta.get('content', '')
        except Exception:
            pass

        try:
            avail_btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.XPATH, "/html/body/div[1]/div/div/main/div[1]/div[2]/div[2]/div/div[1]/div[2]/div[2]/div[1]/div[4]/div/div[1]/span/button | //button[contains(text(), 'Наличие')]"))
            )
            driver.execute_script("arguments[0].click();", avail_btn)
            time.sleep(2)
            
            try:
                list_view_btn = driver.find_element(By.XPATH, "//button[contains(text(), 'Списком')] | //div[contains(text(), 'Списком')]")
                driver.execute_script("arguments[0].click();", list_view_btn)
                time.sleep(2)
            except Exception:
                pass
                
        except Exception:
            pass

        address_texts =[]
        try:
            addr_elements = driver.find_elements(By.XPATH, "//span[contains(@class, 'ihsuk')] | //div[@role='button']//span[contains(text(), 'г.')]")
            for elem in addr_elements:
                txt = elem.text.strip()
                if txt and txt not in address_texts:
                    address_texts.append(txt)
        except Exception:
            pass

        if not address_texts:
            soup_shops = BeautifulSoup(driver.page_source, 'html.parser')
            addresses = soup_shops.find_all('span', class_='ihsuk')
            for addr in addresses:
                txt = addr.text.strip()
                if txt and txt not in address_texts:
                    address_texts.append(txt)
        
        for address_text in address_texts:
            results.append({
                "Номер": 0,
                "Сеть": retail_name,
                "Тип магазина": "Магазин",
                "Адрес Торговой точки": address_text,
                "Бренд": brand,
                "Название продукта": product_name,
                "Цена": price_base,
                "Цена по акции": price_promo,
                "Фото товара": photo_url,
                "Ссылка на страницу": product_url,
                "Рейтинг": None,
                "Объем": volume,
                "Вес": "",
                "Остаток": 1,
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

    except Exception:
        pass
        
    return results