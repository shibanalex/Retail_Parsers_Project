# -*- coding: utf-8 -*-
import os

from parsers_core.uc_browser import get_browser as _get_browser


def get_browser(parser_cfg_name=""):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return _get_browser(base_dir, "vkusvill_profile", parser_cfg_name)
