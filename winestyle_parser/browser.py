# -*- coding: utf-8 -*-
import os
import time

from parsers_core.uc_browser import get_browser as _get_browser, wait_for, wait_ready

BASE = "https://winestyle.ru"


def get_browser(parser_cfg_name="WINESTYLE"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return _get_browser(base_dir, "", parser_cfg_name)


def _confirm_age(driver):
    driver.execute_script(
        "var b = Array.from(document.querySelectorAll('button'))"
        ".find(function(x){return (x.textContent||'').trim() === 'Подтверждаю';});"
        "if (b) { b.click(); }"
    )
    time.sleep(1)


def solve_challenge(search_text="вино"):
    """Проходит Qrator и окно 18+. Возвращает cookies и UA для requests."""
    driver = get_browser()
    try:
        driver.get(f"{BASE}/")
        wait_ready(driver)
        time.sleep(1.5)
        _confirm_age(driver)
        driver.get(f"{BASE}/search/?text={search_text}")
        wait_ready(driver)
        wait_for(driver, ".m-product-item, button", 10)
        _confirm_age(driver)
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        ua = driver.execute_script("return navigator.userAgent")
    finally:
        driver.quit()
    return cookies, ua
