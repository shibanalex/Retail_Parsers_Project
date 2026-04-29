import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import cities, search_req, parsers
from parsers_core.utils import update_retail_points
from .browser import get_browser
from .simplewine_utils import set_city, get_product_links, parse_product

RETAIL_NAME = parsers.get("https://simplewine.ru/", "SimpleWine")

def get_all_data():
    driver = get_browser()
    all_data = []

    try:
        actual_city_name = cities[0] if cities else "Москва"
        set_city(driver, actual_city_name)
        points_count = 1

        for query in search_req:
            product_links = get_product_links(driver, query)

            for link_data in product_links:
                product_data_list = parse_product(driver, link_data, RETAIL_NAME, actual_city_name)
                all_data.extend(product_data_list)

        if all_data:
            update_retail_points(RETAIL_NAME, actual_city_name, points_count)

    except Exception:
        pass
    finally:
        driver.quit()

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    return all_data

def main():
    return get_all_data()

if __name__ == "__main__":
    main()