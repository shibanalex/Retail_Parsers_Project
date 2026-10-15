# -*- coding: utf-8 -*-
import os

from parsers_core.uc_browser import get_browser as _get_browser


def get_browser(parser_cfg_name="VPROK"):
    """С логом сети: из него берётся настоящий HTTP-код страниц."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    driver = _get_browser(base_dir, "", parser_cfg_name,
                          capabilities={"goog:loggingPrefs": {"performance": "ALL"}})
    try:
        driver.execute_cdp_cmd("Network.enable", {})
    except Exception:
        pass
    return driver
