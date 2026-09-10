# -*- coding: utf-8 -*-
import configparser
import os
import time

import undetected_chromedriver as uc


def _apply_window(options, section="WINESTYLE"):
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "parsers_core", "share_parsers.cfg")
    size = "0"
    if os.path.exists(cfg_path):
        cp = configparser.ConfigParser()
        try:
            cp.read(cfg_path, encoding="utf-8")
            if cp.has_section("BROWSER"):
                size = cp.get("BROWSER", "browser_size", fallback=size)
            if cp.has_section(section):
                size = cp.get(section, "browser_size", fallback=size)
        except Exception:
            pass
    size = (size or "0").strip().lower().replace("х", "x").replace(",", "x").replace("*", "x")
    if size == "-1":
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    elif size == "0" or "x" not in size:
        options.add_argument("--window-size=1920,1080")
    else:
        w, h = size.split("x")[:2]
        options.add_argument(f"--window-size={w},{h}")


def _confirm_age(driver):
    driver.execute_script(
        "var btns = Array.from(document.querySelectorAll('button'));"
        "var b = btns.find(function(x){return (x.textContent||'').trim() === 'Подтверждаю';});"
        "if (b) { b.click(); }"
    )
    time.sleep(1)


def solve_challenge(search_text="вино"):
    options = uc.ChromeOptions()
    _apply_window(options)
    driver = uc.Chrome(options=options)
    try:
        driver.get("https://winestyle.ru/")
        time.sleep(4)
        _confirm_age(driver)
        time.sleep(1)
        driver.get(f"https://winestyle.ru/search/?text={search_text}")
        time.sleep(5)
        _confirm_age(driver)
        cookies = {c["name"]: c["value"] for c in driver.get_cookies()}
        ua = driver.execute_script("return navigator.userAgent")
    finally:
        driver.quit()
    return cookies, ua
