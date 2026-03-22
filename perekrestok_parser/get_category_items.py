from perekrestok_parser.requests_to_site import get_category_data
from perekrestok_parser.requests_to_site import set_jwt_token
import time
import random


def get_items_ids(category_id: int, shop_id: int) -> list:
    """
    Get items ids by category
    :param category_id: id of category.
    :param shop_id: id of shop.
    :return: list of items ids.
    """
    for retry in range(10):
        items_data = get_category_data(category_id, shop_id)
        if not items_data or not isinstance(items_data, dict):
            print("Данные не получены. Повторное соединение.")
            time.sleep(random.uniform(5, 10))
            set_jwt_token(value=None)
            continue
        content = items_data.get("content")
        if not content or not isinstance(content, dict):
            print("Токен не получен. Повторное соединение.")
            time.sleep(random.uniform(5, 10))
            set_jwt_token(value=None)
            continue
        items = content.get("items") or []
        items_ids = []
        for item in items:
            if not isinstance(item, dict):
                continue
            products = item.get("products") or []
            for dct in products:
                if not isinstance(dct, dict):
                    continue
                item_master_data = dct.get("masterData") or {}
                plu = item_master_data.get("plu")
                if plu:
                    items_ids.append(plu)
        return items_ids
    return []
