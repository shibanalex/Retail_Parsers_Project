import time
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from magazinoff_pkg.collector import run_collection

SITE_URL = "https://magazinnoff.ru/"


def main(shop_name=None):
    from parsers_core.names import retail_name
    shop_name = shop_name or retail_name(SITE_URL)
    try:
        all_data = run_collection(shop_name)
        return all_data
    except Exception as e:
        print(f"[{shop_name}] Критическая ошибка: {e}")
        return []

if __name__ == "__main__":
    main()