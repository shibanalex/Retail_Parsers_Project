# -*- coding: utf-8 -*-
import os
import time

from parsers_core.uc_browser import get_browser as _get_browser, wait_for, wait_ready

BASE = "https://www.winelab.ru"


def get_browser(parser_cfg_name="WINELAB"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return _get_browser(base_dir, "", parser_cfg_name)


def _confirm_age(driver):
    driver.execute_script("var b = document.getElementById('age-confirm-modal-btn'); if (b) { b.click(); }")
    time.sleep(1)


def solve_challenge(search_text="вино", keep_open=False):
    """Проходит Qrator и окно 18+, прогревает карточку товара. Возвращает cookies и UA."""
    driver = get_browser()
    try:
        driver.get(f"{BASE}/")
        wait_ready(driver)
        time.sleep(1.5)
        _confirm_age(driver)

        driver.get(f"{BASE}/search?text={search_text}")
        wait_ready(driver)
        wait_for(driver, ".productcard__title, #age-confirm-modal-btn", 10)
        _confirm_age(driver)

        product_href = driver.execute_script(
            "var a = document.querySelector('.productcard__title'); return a ? a.getAttribute('href') : null;")
        if product_href:
            driver.get(f"{BASE}{product_href}")
            wait_ready(driver)
            time.sleep(1)
            _confirm_age(driver)

        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        ua = driver.execute_script("return navigator.userAgent")
    except Exception:
        driver.quit()
        raise
    if keep_open:
        return driver, cookies, ua
    driver.quit()
    return cookies, ua
