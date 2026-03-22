from .utils import update_retail_points
import json
import os
import shutil
import time
import urllib
import random
from .settings import retail
from config import search_req, brand, cities
from shared.browser_utils import detect_chrome_version_main as _detect_ver

# Global driver instance
_driver = None


def _get_chrome_binary():
    """Find Chrome/Chromium binary cross-platform."""
    env_binary = os.environ.get("CHROME_BINARY")
    if env_binary and os.path.isfile(env_binary):
        return env_binary
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        path = shutil.which(name)
        if path:
            return path
    return None


def _init_driver(headless=False):
    """Initialize undetected-chromedriver."""
    try:
        import undetected_chromedriver as uc
    except ImportError:
        print("undetected-chromedriver не установлен. Установи: pip install undetected-chromedriver")
        return None

    options = uc.ChromeOptions()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--lang=ru-RU")

    chrome_binary = _get_chrome_binary()
    if chrome_binary:
        options.binary_location = chrome_binary

    _ver = _detect_ver(chrome_binary, env_override_key="PYATEROCHKA_CHROME_VERSION_MAIN")
    _uc_kw = dict(options=options, headless=headless, use_subprocess=True)
    if _ver:
        _uc_kw["version_main"] = _ver
    driver = uc.Chrome(**_uc_kw)
    driver.set_page_load_timeout(30)
    return driver


def _get_driver():
    """Get or create driver instance."""
    global _driver
    if _driver is None:
        headless = os.environ.get("PYATEROCHKA_HEADLESS", "false").lower() in ("true", "1", "yes")
        _driver = _init_driver(headless=headless)
    return _driver


def _close_driver():
    """Close driver instance."""
    global _driver
    if _driver:
        try:
            _driver.quit()
        except:
            pass
        _driver = None


def _fetch_json(driver, url):
    """Fetch JSON from URL using driver."""
    try:
        driver.get(url)
        time.sleep(random.uniform(0.3, 0.7))
        # Get page source and parse JSON
        page_source = driver.page_source
        # The JSON is typically wrapped in <pre> tags or just raw in body
        if "<pre>" in page_source:
            import re
            match = re.search(r'<pre[^>]*>(.*?)</pre>', page_source, re.DOTALL)
            if match:
                return json.loads(match.group(1))
        # Try parsing the body content directly
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(page_source, "lxml")
        body = soup.find("body")
        if body:
            text = body.get_text().strip()
            if text.startswith("{") or text.startswith("["):
                return json.loads(text)
        return None
    except Exception as e:
        return None


def get_city_center(driver, city_name):
    tup = ["Россия", city_name, ""]
    string = urllib.parse.quote(", ".join(tup))
    url = f"https://5ka.ru/api/maps/geocode/?geocode={string}"

    page_json = _fetch_json(driver, url)
    if not page_json:
        return dict()

    center_point = (
        page_json.get("response", {})
        .get("GeoObjectCollection", {})
        .get("featureMember", [])[0]
        .get("GeoObject", {})
        .get("Point", {})
        .get("pos")
    )
    return (
        {city_name: tuple(map(float, center_point.split()))} if center_point else dict()
    )


def search_in_grid(driver, city_name, center_lon, center_lat, grid_size=0.2, points=10, grid_num=1):
    found_stores = []
    checked_sap_codes = set()

    lon_step = grid_size / (points - 1) if points > 1 else 0
    lat_step = grid_size / (points - 1) if points > 1 else 0

    start_lon = center_lon - grid_size / 2
    start_lat = center_lat - grid_size / 2

    total_points = points * points
    processed = 0

    print(f"Сетка #{grid_num}: размер {grid_size}, точки {points}x{points}")

    for i in range(points):
        for j in range(points):
            lon = start_lon + i * lon_step
            lat = start_lat + j * lat_step
            processed += 1

            try:
                url = f"https://5d.5ka.ru/api/orders/v1/orders/stores/?lon={lon}&lat={lat}"
                stores_data = _fetch_json(driver, url)

                if (
                        stores_data
                        and len(stores_data) > 0
                        and stores_data.get("shop_address") is not None
                ):

                    store = stores_data
                    sap_code = store.get("sap_code")

                    if sap_code and sap_code not in checked_sap_codes:
                        checked_sap_codes.add(sap_code)
                        store_info = {
                            "address": store.get("shop_address", "N/A"),
                            "city": store.get("store_city", "N/A"),
                            "sap_code": sap_code,
                            "has_delivery": store.get("has_delivery", False),
                            "coordinates": (lon, lat),
                            "grid_point": (i, j),
                        }
                        found_stores.append(store_info)

                        print(f" " * 100, end="\r")
                        print(f"Найден магазин #{len(found_stores)}: {store_info['address']}")

                    else:
                        pass
                else:
                    pass

            except Exception as e:
                print(f" " * 100, end="\r")
                print(f"Ошибка: {e}")

            time.sleep(random.uniform(0.7, 2))

    return found_stores


def search_multiple_grids(driver, city_name, center_lon, center_lat):
    all_stores = []
    checked_sap_codes = set()

    grid_configs = [
        (0.25, 12),
        (0.15, 10),
        (0.08, 8),
        (0.04, 6),
    ]

    for grid_num, (grid_size, points) in enumerate(grid_configs, 1):
        found_in_grid = search_in_grid(
            driver, city_name, center_lon, center_lat, grid_size, points, grid_num
        )

        new_stores = []
        for store in found_in_grid:
            sap_code = store.get("sap_code")
            if sap_code and sap_code not in checked_sap_codes:
                checked_sap_codes.add(sap_code)
                new_stores.append(store)

        all_stores.extend(new_stores)
        print(f" " * 100, end="\r")  # Очищаем строку
        print(f"В этой сетке найдено {len(new_stores)} новых магазинов")
        print()

        if grid_num < len(grid_configs):
            time.sleep(random.uniform(0.7, 1.5))

    return all_stores


def get_search(city_name, query, max_retries=10):
    driver = _get_driver()
    if not driver:
        return None

    for retry in range(max_retries):
        try:
            # First visit main site to establish session
            driver.get("https://5ka.ru")
            time.sleep(random.uniform(2, 4))

            # Wait for page to load
            from selenium.webdriver.support.ui import WebDriverWait
            from selenium.webdriver.support import expected_conditions as EC
            from selenium.webdriver.common.by import By

            try:
                WebDriverWait(driver, 10).until(
                    EC.presence_of_element_located((By.TAG_NAME, "body"))
                )
            except:
                pass

            time.sleep(random.uniform(1, 2))

            all_stores = dict()

            city_center = get_city_center(driver=driver, city_name=city_name)

            for city, (lon, lat) in city_center.items():
                print(f"\n{'=' * 60}")
                print(f"ГОРОД: {city}")
                print(f"Центр города: {lon}, {lat}")
                city_stores = search_multiple_grids(driver, city, lon, lat)
                all_stores[city] = city_stores
                print(f"\nИТОГ в {city}: {len(city_stores)} магазинов")
                time.sleep(random.uniform(0.7, 2))

            sap_codes = get_sap_codes(all_stores, city_name=city_name)

            all_data = []

            for indx, sap_code in enumerate(sap_codes, 1):
                print(f"Парсим №{indx} {retail} {sap_code.get('address')}")
                for q in query:
                    time.sleep(random.uniform(1, 2.2))
                    url = (
                        f"https://5d.5ka.ru/api/catalog/v3/stores/"
                        f"{sap_code.get('sap_code')}/search"
                        f"?mode=delivery&include_restrict=true&q={q}&limit=499"
                    )

                    json_response = _fetch_json(driver, url)
                    json_data = json_response.get("products") if json_response else []

                    for product in json_data:
                        product["store_address"] = sap_code.get("address")

                    all_data.extend(json_data)

            return all_data

        except Exception as e:
            print(f"Ошибка: {e}, повтор {retry + 1}/{max_retries}")
            time.sleep(random.uniform(10, 20))
            continue

    print("Попытки подключения исчерпаны. Сервер недоступен.")
    _close_driver()
    return None


def filter_brand(items, brand):
    filtered_items = []
    for b in brand:
        try:
            f = [item for item in items if b.lower() in item.get("Название продукта").lower()]
            filtered_items.extend(f)
        except Exception as e:
            pass
    return filtered_items


def get_sap_codes(stores, city_name):
    return [
        {"sap_code": store.get("sap_code"), "address": store.get("address")}
        for store in stores.get(city_name)
    ]


def parse_items(items):
    all_items = []
    for indx, item in enumerate(items, 1):
        result_dct = dict()
        result_dct["Номер"] = indx
        result_dct["Сеть"] = retail
        result_dct["Тип магазина"] = None
        result_dct["Адрес Торговой точки"] = item.get("store_address")
        result_dct["Бренд"] = None
        result_dct["Название продукта"] = item.get("name")
        result_dct["Цена"] = float(item.get("prices").get("regular")) if item.get("prices", {}).get("regular") else None
        result_dct["Цена по акции"] = float(item.get("prices").get("discount")) if item.get("prices", {}).get(
            "discount") else None
        result_dct["Фото товара"] = ", ".join(item.get("image_links").get("normal")) if item.get(
            "image_links") else None
        result_dct["Ссылка на страницу"] = None
        result_dct["Рейтинг"] = item.get("rating").get("rating_average") if item.get("rating") else None
        result_dct["Объем"] = None
        result_dct["Вес"] = (
            item.get("property_clarification").split()[0]
            if item.get("property_clarification") and len(item.get("property_clarification").split()) < 3
            else None
        )
        result_dct["Остаток"] = int(float(item.get("stock_limit"))) if item.get("stock_limit") else -1
        all_items.append(result_dct)
    return all_items


def get_all_data(cities=cities, search_req=search_req, brand=brand):
    full_items_data = []
    search_pattern = search_req

    if brand and not search_req:
        search_pattern = brand

    for city in cities:
        print(f"Парсим {retail} {city}")
        search_data = get_search(city_name=city, query=search_pattern)

        if not search_data:
            continue

        parsed_items = parse_items(search_data)

        if brand and brand is not search_pattern:
            parsed_items = filter_brand(items=parsed_items, brand=brand)
        full_items_data.extend(parsed_items)

        # === СТАНДАРТ КОЛИЧЕСТВА ТТ ===
        try:
            unique_addresses = set()
            for item in parsed_items:
                address = item.get("Адрес Торговой точки")
                if address:
                    unique_addresses.add(address)
            count_stores = len(unique_addresses)
        except Exception as e:
            count_stores = 0

        update_retail_points(
            retail,
            city,
            count_stores
        )

    # Close driver when done
    _close_driver()

    return full_items_data
