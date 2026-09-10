# -*- coding: utf-8 -*-
import configparser
import os

import undetected_chromedriver as uc


def get_browser(parser_cfg_name="VPROK"):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(os.path.dirname(base_dir), "parsers_core", "share_parsers.cfg")

    min_delay, max_delay = 1.0, 3.0
    size = "0"
    if os.path.exists(cfg_path):
        cp = configparser.ConfigParser()
        try:
            cp.read(cfg_path, encoding="utf-8")
            if cp.has_section("BROWSER"):
                min_delay = cp.getfloat("BROWSER", "min_delay", fallback=min_delay)
                max_delay = cp.getfloat("BROWSER", "max_delay", fallback=max_delay)
                size = cp.get("BROWSER", "browser_size", fallback=size)
            if parser_cfg_name and cp.has_section(parser_cfg_name):
                min_delay = cp.getfloat(parser_cfg_name, "min_delay", fallback=min_delay)
                max_delay = cp.getfloat(parser_cfg_name, "max_delay", fallback=max_delay)
                size = cp.get(parser_cfg_name, "browser_size", fallback=size)
        except Exception:
            pass

    options = uc.ChromeOptions()
    size = (size or "0").strip().lower().replace("х", "x").replace(",", "x").replace("*", "x")
    if size == "-1":
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1920,1080")
    elif size == "0" or "x" not in size:
        options.add_argument("--window-size=1920,1080")
    else:
        w, h = size.split("x")[:2]
        options.add_argument(f"--window-size={w},{h}")

    driver = uc.Chrome(options=options)
    driver.custom_min_delay = min_delay
    driver.custom_max_delay = max_delay
    return driver
