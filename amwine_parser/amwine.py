import sys
import os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from config import cities, search_req, parsers
from parsers_core.utils import update_retail_points
from .browser import get_browser
from .amwine_utils import select_shop, get_product_links, parse_product

RETAIL_NAME = parsers.get("https://amwine.ru/", "Ароматный Мир")

def get_all_data():
    """
    Main pipeline entrypoint. Iterates over all accessible shops in a given city,
    performs search queries, extracts links, and parses detailed product info.
    """
    driver = get_browser()
    all_data = []

    try:
        actual_city_name = cities[0] if cities else "Москва"
        
        visited_addresses = set()
        shop_counter = 1

        while True:
            address = select_shop(driver, actual_city_name, visited_addresses)
            
            if not address:
                break
                
            visited_addresses.add(address)

            for query in search_req:
                product_links = get_product_links(driver, query)
                
                for link in product_links:
                    product_data_list = parse_product(driver, link, RETAIL_NAME, actual_city_name, address)
                    all_data.extend(product_data_list)
            
            shop_counter += 1

        if all_data:
            update_retail_points(RETAIL_NAME, actual_city_name, shop_counter - 1)

    except Exception as e:
        print(f"Critical execution error in Amwine parser: {e}")
    finally:
        driver.quit()

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    return all_data

def main():
    return get_all_data()

if __name__ == "__main__":
    main()