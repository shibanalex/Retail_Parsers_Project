import time
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

def bypass_cataloged_antibot(driver, timeout=30):
    """
    Механизм обхода для Cataloged:
    Автоматически ищет и нажимает кнопку 'Я не робот' и ждет загрузки контента.
    """
    try:
        WebDriverWait(driver, 10).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(3)
        
        src = driver.page_source
        
        if "Я не робот" in src or "Loading..." in src or "adblock-blocker" in src:
            try:
                buttons = driver.find_elements(By.XPATH, "//div[contains(text(), 'Я не робот')]")
                for btn in buttons:
                    if btn.is_displayed():
                        print("   ! Обнаружен антибот Cataloged. Выполняю клик...")
                        driver.execute_script("arguments[0].click();", btn)
                        time.sleep(2)
                        break
            except Exception as e:
                print(f"   ⚠️ Ошибка при клике на капчу: {e}")

            WebDriverWait(driver, timeout).until(
                lambda d: "Loading..." not in d.page_source and 
                          ("rec__item" in d.page_source or "promo__item" in d.page_source)
            )
            time.sleep(1.5)
            
    except Exception:
        pass 


def bypass_cloudflare_humanity(driver, timeout=30):
    """
    Механизм обхода для Magazinnoff (Cloudflare / DDoS-Guard):
    Ждет исчезновения заглушек "Just a moment" / "Checking your browser".
    """
    try:
        WebDriverWait(driver, timeout).until(
            lambda d: "Just a moment" not in d.title and 
                      "Checking your browser" not in d.page_source
        )
        
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='/magazin/'], footer"))
        )
        time.sleep(1)
        return True
    except Exception:
        print("   Не удалось пройти проверку Cloudflare / загрузить страницу.")
        return False
    

def bypass_pyaterochka_antibot(driver, timeout=45):
    """
    Механизм обхода капчи для пятерочки
    """
    try:
        # Ждем первоначальную загрузку страницы
        WebDriverWait(driver, 5).until(lambda d: d.execute_script('return document.readyState') == 'complete')
        time.sleep(2)
        
        page_source = driver.page_source.lower()
        title = driver.title.lower()

        # Проверяем наличие признаков капчи в заголовке и исходном коде страницы
        if "робот" in page_source or "just a moment" in title or "cloudflare" in page_source or "challenge" in page_source:
            print("   ! Пятерочка: Обнаружена капча. Выполняю автоматический обход...")

            try:
                buttons = driver.find_elements(By.XPATH, "//*[contains(translate(text(), 'РОБОТ', 'робот'), 'не робот')]")
                for btn in buttons:
                    if btn.is_displayed():
                        driver.execute_script("arguments[0].click();", btn)
                        print("   ! Клик по кнопке 'Я не робот'")
                        time.sleep(3)
                        break
            except Exception:
                pass

            try:
                iframes = driver.find_elements(By.TAG_NAME, "iframe")
                for iframe in iframes:
                    src = iframe.get_attribute("src")
                    if src and "challenge" in src.lower():
                        driver.switch_to.frame(iframe)
                        checkboxes = driver.find_elements(By.CSS_SELECTOR, ".mark, input[type='checkbox'], #cf-chl-widget-u3f9m")
                        if checkboxes:
                            driver.execute_script("arguments[0].click();", checkboxes[0])
                            print("   🖱️ Клик по чекбоксу Cloudflare")
                            time.sleep(3)
                        driver.switch_to.default_content()
            except Exception:
                driver.switch_to.default_content()

            WebDriverWait(driver, timeout).until(
                lambda d: "just a moment" not in d.title.lower() and 
                          "проверка" not in d.page_source.lower()
            )
            time.sleep(2)
            print("   Защита пройдена.")
            return True
        else:

            return True

    except Exception as e:
        print(f"   ⚠️ Ошибка или таймаут при обходе защиты Пятерочки (идем дальше): {e}")
        return False