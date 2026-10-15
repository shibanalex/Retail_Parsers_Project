# -*- coding: utf-8 -*-
import os

from parsers_core.dp_browser import DPWrapper


def get_browser(parser_cfg_name=""):
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return DPWrapper(base_dir, "ozon_dp_profile", parser_cfg_name, extra_args=("--disable-infobars",))
