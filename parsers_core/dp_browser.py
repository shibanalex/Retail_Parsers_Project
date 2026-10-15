# -*- coding: utf-8 -*-
import os

from .settings import parser_settings, parse_window_size

BASE_ARGS = ("--no-sandbox", "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled")


def get_dp_page(base_dir, profile_name="", parser_cfg_name="", extra_args=None, use_cfg_size=True):
    """Браузер DrissionPage (ozon, samokat, utkonos, megamarket). Всегда с окном."""
    from DrissionPage import ChromiumOptions, ChromiumPage

    settings = parser_settings(parser_cfg_name)
    co = ChromiumOptions()
    if profile_name:
        profile_dir = os.path.join(base_dir, profile_name)
        os.makedirs(profile_dir, exist_ok=True)
        co.set_user_data_path(profile_dir)
    co.headless(False)
    for arg in BASE_ARGS + tuple(extra_args or ()):
        co.set_argument(arg)
    mode, size = parse_window_size(settings["browser_size"]) if use_cfg_size else ("default", (1920, 1080))
    if mode != "explicit":
        size = (1920, 1080)
    co.set_argument(f"--window-size={size[0]},{size[1]}")

    page = ChromiumPage(co)
    page.custom_min_delay = settings["min_delay"]
    page.custom_max_delay = settings["max_delay"]
    return page


class DPWrapper:
    def __init__(self, base_dir, profile_name, parser_cfg_name="", extra_args=None):
        self.page = get_dp_page(base_dir, profile_name, parser_cfg_name, extra_args)
        self.custom_min_delay = self.page.custom_min_delay
        self.custom_max_delay = self.page.custom_max_delay

    def quit(self):
        self.page.quit()
