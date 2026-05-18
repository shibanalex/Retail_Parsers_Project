import time
import sys
import os

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from cataloged_pkg.crawler import run_collection

def main(shop_name="Cataloged"):
    try:
        all_data = run_collection(shop_name)
        return all_data
    except Exception as e:
        print(f"[{shop_name}] Критическая ошибка: {e}")
        return []

if __name__ == "__main__":
    main()