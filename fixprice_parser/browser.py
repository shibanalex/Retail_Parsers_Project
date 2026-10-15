# -*- coding: utf-8 -*-
from parsers_core.katoteka import open_browser


def get_browser(parser_cfg_name="KATOTEKA"):
    return open_browser(parser_cfg_name)
