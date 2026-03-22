from parsers_core.utils import update_retail_points
import json
import time
import random
import os
from pyaterochka_parser.settings import retail
from parsers_core.captcha_bypass import bypass_pyaterochka_antibot
from config import (
    search_req,
    brand,
    cities,
    proxy,
)
from pyaterochka_parser.pyaterochka_config import (
    pyaterochka_headless,
    pyaterochka_startup_timeout_s,
)
from pyaterochka_parser.stealth_session import driver_get_json, pyaterochka_driver, pyaterochka_requests_session, _init_uc_driver


# Maximum number of driver recreation attempts per single store before giving up on it
_MAX_SESSION_RECOVERIES = 2


_QUICK_MODE = os.getenv("PYATEROCHKA_QUICK", "").strip() in {"1", "true", "yes"}
_SLEEP_MIN, _SLEEP_MAX = ((0.05, 0.15) if _QUICK_MODE else (0.9, 2.0))
_RETRY_SLEEP_MIN, _RETRY_SLEEP_MAX = ((1.0, 2.0) if _QUICK_MODE else (10.0, 20.0))

# Глобальный индекс текущего прокси для ротации
_proxy_index = 0

def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


_HEADLESS = _env_flag("PYATEROCHKA_HEADLESS", bool(pyaterochka_headless))
_STARTUP_TIMEOUT_S = float(
    os.getenv("PYATEROCHKA_STARTUP_TIMEOUT_S", str(pyaterochka_startup_timeout_s))
)
_BACKEND = (os.getenv("PYATEROCHKA_BACKEND") or "driver").strip().lower()


def _sleep():
    time.sleep(random.uniform(_SLEEP_MIN, _SLEEP_MAX))


def _is_session_dead(exc: Exception) -> bool:
    """Check if an exception indicates the browser session has died."""
    # Selenium's InvalidSessionIdException
    try:
        from selenium.common.exceptions import InvalidSessionIdException
        if isinstance(exc, InvalidSessionIdException):
            return True
    except ImportError:
        pass

    # Also check the error message for common session-dead indicators,
    # because some WebDriverException subtypes carry the message too.
    msg = str(exc).lower()
    dead_markers = (
        "invalid session id",
        "session deleted",
        "unable to receive message from renderer",
        "browser has closed",
        "no such window",
        "target window already closed",
        "chrome not reachable",
        "disconnected",
    )
    return any(marker in msg for marker in dead_markers)


def _recreate_driver(old_driver, proxy_url, old_proxy_proc=None, old_proxy_ctx=None):
    """Quit the dead driver (best-effort) and create a fresh one.

    Uses ``local_proxy_for`` to set up the local proxy bridge, exactly as the
    original ``pyaterochka_driver`` context manager does.

    Returns ``(new_driver, local_proxy_proc, proxy_ctx)`` — the caller **must**
    keep both ``local_proxy_proc`` and ``proxy_ctx`` alive for the lifetime of
    the driver.  When the driver is no longer needed, clean up by calling
    ``proxy_ctx.__exit__(None, None, None)`` (or terminate the process manually).
    """
    # Try to quit the old driver so Chrome process doesn't linger
    try:
        old_driver.quit()
    except Exception:
        pass

    # Clean up the old proxy context manager (terminates the process in its finally block)
    if old_proxy_ctx is not None:
        try:
            old_proxy_ctx.__exit__(None, None, None)
        except Exception:
            pass
    elif old_proxy_proc is not None:
        # Fallback: terminate the process directly if no context was passed
        try:
            old_proxy_proc.terminate()
            old_proxy_proc.wait(timeout=3)
        except Exception:
            try:
                old_proxy_proc.kill()
            except Exception:
                pass

    print("Пересоздаём браузер (сессия умерла)...")

    # Start a fresh local proxy bridge (handles auth) just like pyaterochka_driver does.
    proxy_ctx = local_proxy_for(proxy_url)
    local_url, proxy_proc = proxy_ctx.__enter__()

    try:
        new_driver = _init_uc_driver(
            headless=_HEADLESS,
            locale="ru-RU",
            proxy=local_url,
        )
    except Exception:
        # If driver creation fails, clean up the proxy process
        try:
            proxy_ctx.__exit__(None, None, None)
        except Exception:
            pass
        raise

    try:
        new_driver.set_page_load_timeout(30)
    except Exception:
        pass
    try:
        new_driver.set_script_timeout(30)
    except Exception:
        pass

    # Navigate to the site so cookies / antibot context is established
    try:
        new_driver.get("https://5ka.ru/")
        bypass_pyaterochka_antibot(new_driver, timeout=30)
    except Exception:
        pass
        
    print("Браузер пересоздан, продолжаем парсинг.")
    return new_driver, proxy_proc, proxy_ctx


def _get_json(transport, url: str, params: dict, timeout_s: float = 15.0) -> dict:
    if _BACKEND == "requests":
        resp = transport.get(url, params=params, timeout=timeout_s)
        # Проверка HTTP статуса
        if resp.status_code in (403, 429, 502, 503):
            raise RuntimeError(f"HTTP {resp.status_code} Forbidden/Blocked for {resp.url}")
        try:
            data = resp.json()
            # Проверка что ответ - словарь или список, а не число/строка
            if isinstance(data, (int, float, str, bool)):
                raise RuntimeError(f"Unexpected response type {type(data).__name__}: {data}")
            return data
        except json.JSONDecodeError as e:
            head = (resp.text or "")[:300].replace("\n", "\\n")
            raise RuntimeError(f"Non-JSON response for {resp.url}: {head}") from e
    return driver_get_json(transport, url, params=params, timeout_s=timeout_s)


def get_city_center(driver, city_name, timeout_s: float = 15.0):
    tup = ["Россия", city_name, ""]
    geocode = ", ".join(tup)
    try:
        page_json = _get_json(
            driver,
            "https://5ka.ru/api/maps/geocode/",
            {"geocode": geocode},
            timeout_s=timeout_s,
        )
    except Exception as e:
        print(f"Ошибка геокодирования для {city_name}: {e}")
        return dict()

    if not isinstance(page_json, dict):
        return dict()

    try:
        response = page_json.get("response") or {}
        geo_collection = response.get("GeoObjectCollection") or {}
        feature_members = geo_collection.get("featureMember") or []
        if not feature_members:
            print(f"Не найдены координаты для города {city_name}")
            return dict()
        geo_object = feature_members[0].get("GeoObject") or {}
        point = geo_object.get("Point") or {}
        center_point = point.get("pos")
    except (IndexError, KeyError, TypeError) as e:
        print(f"Ошибка парсинга координат для {city_name}: {e}")
        return dict()

    return (
        {city_name: tuple(map(float, center_point.split()))} if center_point else dict()
    )


def search_in_grid(
    driver,
    city_name,
    center_lon,
    center_lat,
    grid_size=0.2,
    points=10,
    grid_num=1,
    timeout_s: float = 15.0,
):
    found_stores = []
    checked_sap_codes = set()

    lon_step = grid_size / (points - 1) if points > 1 else 0
    lat_step = grid_size / (points - 1) if points > 1 else 0

    start_lon = center_lon - grid_size / 2
    start_lat = center_lat - grid_size / 2

    total_points = points * points
    processed = 0

    # Track consecutive errors for early termination
    consecutive_errors = 0
    proxy_count = len(proxy) if proxy else 1
    # Stop grid if a full proxy-round of consecutive requests all fail
    error_threshold = proxy_count

    print(f"Сетка #{grid_num}: размер {grid_size}, точки {points}x{points}")

    grid_stopped_early = False
    for i in range(points):
        if grid_stopped_early:
            break
        for j in range(points):
            lon = start_lon + i * lon_step
            lat = start_lat + j * lat_step
            processed += 1

            try:
                stores_data = _get_json(
                    driver,
                    "https://5d.5ka.ru/api/orders/v1/orders/stores/",
                    {"lon": lon, "lat": lat},
                    timeout_s=timeout_s,
                )

                # Successful response — reset consecutive error counter
                consecutive_errors = 0

                if (
                        isinstance(stores_data, dict)
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
                consecutive_errors += 1

                print(f" " * 100, end="\r")
                print(f"Ошибка: {e}")

                if consecutive_errors >= error_threshold:
                    print(f"\nСлишком много ошибок подряд в сетке #{grid_num} "
                          f"({consecutive_errors} подряд). "
                          f"Прекращаем поиск магазинов в этой сетке.")
                    grid_stopped_early = True
                    break

            _sleep()

    return found_stores


def search_multiple_grids(driver, city_name, center_lon, center_lat):
    all_stores = []
    checked_sap_codes = set()

    grid_configs = [(0.04, 4)] if _QUICK_MODE else [(0.25, 12), (0.15, 10), (0.08, 8), (0.04, 6)]

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
            _sleep()

    return all_stores


def get_search_orig(city_name, query, max_retries=10):
    return get_search(city_name=city_name, query=[query], max_retries=max_retries)


def _get_next_proxy():
    """Получить следующий прокси из списка с ротацией."""
    global _proxy_index
    if not proxy or not isinstance(proxy, list):
        return None
    proxy_url = proxy[_proxy_index % len(proxy)]
    _proxy_index += 1
    return proxy_url


def _rotate_proxy():
    """Принудительно переключить на следующий прокси."""
    global _proxy_index
    if proxy and isinstance(proxy, list):
        _proxy_index += 1
        return proxy[_proxy_index % len(proxy)]
    return None


def get_search(city_name, query, max_retries=None):
    global _proxy_index
    proxy_url = _get_next_proxy()

    last_error = None

    if max_retries is None:
        max_retries = len(proxy) * 2 if proxy else 1
    try:
        max_retries = int(os.getenv("PYATEROCHKA_MAX_RETRIES", str(max_retries)))
    except ValueError:
        pass

    proxy_count = len(proxy) if proxy else 1
    for retry in range(max_retries):
        if retry > 0:
            # Skip sleep on the last proxy of each full round (no point waiting
            # if we just finished cycling all proxies and they were all blocked)
            is_round_boundary = (retry % proxy_count == 0)
            is_last_retry = (retry == max_retries - 1)
            if not (is_round_boundary or is_last_retry):
                backoff_time = 5
                print(f"Ожидание {backoff_time}с перед повторной попыткой {retry + 1}/{max_retries}...")
                time.sleep(backoff_time)
            else:
                print(f"Повторная попытка {retry + 1}/{max_retries} (без ожидания — смена раунда прокси)...")

        try:
            if _BACKEND == "requests":
                transport_cm = pyaterochka_requests_session(
                    locale="ru-RU",
                    proxy=proxy_url,
                    startup_timeout_s=_STARTUP_TIMEOUT_S,
                    cookie_headless=False,
                )
            else:
                transport_cm = pyaterochka_driver(
                    headless=_HEADLESS,
                    locale="ru-RU",
                    proxy=proxy_url,
                    startup_timeout_s=_STARTUP_TIMEOUT_S,
                )

            with transport_cm as driver:
                # Use active_driver so we can swap it if the session dies.
                # The context manager will still try to quit() the original
                # driver in its finally block, which is fine (already dead/quit).
                active_driver = driver
                _extra_driver = None  # tracks a recreated driver for cleanup
                _extra_proxy_proc = None  # tracks the local proxy process for a recreated driver
                _extra_proxy_ctx = None  # tracks the proxy context manager to prevent GC

                all_stores = dict()

                city_center = get_city_center(driver=active_driver, city_name=city_name)

                for city, (lon, lat) in city_center.items():
                    print(f"\n{'=' * 60}")
                    print(f"ГОРОД: {city}")
                    print(f"Центр города: {lon}, {lat}")
                    city_stores = search_multiple_grids(active_driver, city, lon, lat)
                    all_stores[city] = city_stores
                    print(f"\nИТОГ в {city}: {len(city_stores)} магазинов")
                    _sleep()

                sap_codes = get_sap_codes(all_stores, city_name=city_name)

                all_data = []
                session_recoveries = 0

                for indx, sap_code in enumerate(sap_codes, 1):
                    print(f"Парсим №{indx} {retail} {sap_code.get('address')}")
                    for q in query:
                        time.sleep(random.uniform(0.2, 0.6) if _QUICK_MODE else random.uniform(1, 2.2))
                        try:
                            json_response = _get_json(
                                active_driver,
                                f"https://5d.5ka.ru/api/catalog/v3/stores/{sap_code.get('sap_code')}/search",
                                {
                                    "mode": "delivery",
                                    "include_restrict": "true",
                                    "q": q,
                                    "limit": 499,
                                },
                                timeout_s=15.0,
                            )
                        except Exception as e:
                            if _is_session_dead(e) and session_recoveries < _MAX_SESSION_RECOVERIES:
                                print(f"Сессия браузера умерла: {e}")
                                try:
                                    active_driver, _extra_proxy_proc, _extra_proxy_ctx = _recreate_driver(
                                        active_driver, proxy_url, _extra_proxy_proc, _extra_proxy_ctx,
                                    )
                                    _extra_driver = active_driver
                                    session_recoveries += 1
                                except Exception as re_err:
                                    print(f"Не удалось пересоздать браузер: {re_err}")
                                    json_response = None
                                    continue
                                # Retry this query with the new driver
                                try:
                                    json_response = _get_json(
                                        active_driver,
                                        f"https://5d.5ka.ru/api/catalog/v3/stores/{sap_code.get('sap_code')}/search",
                                        {
                                            "mode": "delivery",
                                            "include_restrict": "true",
                                            "q": q,
                                            "limit": 499,
                                        },
                                        timeout_s=15.0,
                                    )
                                except Exception as retry_err:
                                    print(f"Ошибка при запросе товаров (после пересоздания): {retry_err}")
                                    json_response = None
                            else:
                                print(f"Ошибка при запросе товаров: {e}")
                                json_response = None
                        json_data = []
                        if isinstance(json_response, dict):
                            json_data = json_response.get("products") or []

                        for product in json_data:
                            product["store_address"] = sap_code.get("address")

                        all_data.extend(json_data)

                # Clean up any extra driver we created outside the context manager
                if _extra_driver is not None:
                    try:
                        _extra_driver.quit()
                    except Exception:
                        pass
                if _extra_proxy_ctx is not None:
                    try:
                        _extra_proxy_ctx.__exit__(None, None, None)
                    except Exception:
                        pass
                elif _extra_proxy_proc is not None:
                    try:
                        _extra_proxy_proc.terminate()
                        _extra_proxy_proc.wait(timeout=3)
                    except Exception:
                        try:
                            _extra_proxy_proc.kill()
                        except Exception:
                            pass

                time.sleep(1)
                return all_data

        except Exception as e:
            last_error = e
            if "Forbidden" in str(e) or "Non-JSON response" in str(e) or "антибот" in str(e):
                proxy_url = _rotate_proxy()
                print(f"Получен Forbidden/Non-JSON, переключаюсь на прокси: {proxy_url}")
                # Удаляем кэш кук для старого прокси чтобы получить свежие
                try:
                    from .stealth_session import _cookie_bundle_path
                    old_bundle = _cookie_bundle_path(proxy_url)
                    if old_bundle.exists():
                        old_bundle.unlink()
                        print("Кэш кук очищен.")
                except Exception:
                    pass
            continue

    print(f"\nВсе прокси заблокированы для парсера Пятёрочка. Парсинг остановлен.")
    print(f"(Сделано {max_retries} попыток — 2 полных раунда по {proxy_count} прокси)")
    if last_error is not None:
        print(f"Последняя ошибка: {type(last_error).__name__}: {last_error}")
    return None


def filter_brand(items, brand):
    filtered_items = []
    if not items or not brand:
        return filtered_items
    for b in brand:
        try:
            f = [
                item for item in items
                if item.get("Название продукта") and b.lower() in item.get("Название продукта").lower()
            ]
            filtered_items.extend(f)
        except Exception as e:
            print(f"Ошибка фильтрации бренда {b}: {e}")
    return filtered_items


def get_sap_codes(stores, city_name):
    city_stores = stores.get(city_name) or []
    return [
        {"sap_code": store.get("sap_code"), "address": store.get("address")}
        for store in city_stores
        if isinstance(store, dict) and store.get("sap_code")
    ]


def parse_items(items):
    all_items = []
    if not items or not isinstance(items, list):
        return all_items

    for indx, item in enumerate(items, 1):
        if not isinstance(item, dict):
            continue
        try:
            result_dct = dict()
            result_dct["Номер"] = indx
            result_dct["Сеть"] = retail
            result_dct["Тип магазина"] = None
            result_dct["Адрес Торговой точки"] = item.get("store_address")
            result_dct["Бренд"] = None
            result_dct["Название продукта"] = item.get("name")

            prices = item.get("prices") or {}
            result_dct["Цена"] = float(prices.get("regular")) if prices.get("regular") else None
            result_dct["Цена по акции"] = float(prices.get("discount")) if prices.get("discount") else None

            image_links = item.get("image_links") or {}
            normal_images = image_links.get("normal") or []
            result_dct["Фото товара"] = ", ".join(normal_images) if normal_images else None

            result_dct["Ссылка на страницу"] = None

            rating = item.get("rating") or {}
            result_dct["Рейтинг"] = rating.get("rating_average")

            result_dct["Объем"] = None
            prop_clar = item.get("property_clarification")
            result_dct["Вес"] = (
                prop_clar.split()[0]
                if prop_clar and len(prop_clar.split()) < 3
                else None
            )
            result_dct["Остаток"] = int(float(item.get("stock_limit"))) if item.get("stock_limit") else -1
            all_items.append(result_dct)
        except Exception as e:
            print(f"Ошибка парсинга товара #{indx}: {e}")
            continue
    return all_items


def get_all_data_orig(cities=cities, search_req=search_req, brand=brand):
    full_items_data = []
    search_pattern = search_req
    if brand and not search_req:
        search_pattern = brand
    for city in cities:
        for sr in search_pattern:
            search_data = get_search(city_name=city, query=sr)
            parsed_items = parse_items(search_data)

            if brand and brand is not search_pattern:
                parsed_items = filter_brand(items=parsed_items, brand=brand)
            full_items_data.extend(parsed_items)
    return full_items_data


def get_all_data(cities_list=None, search_list=None, brand_list=None):

    import sys
    import os

    current_dir = os.path.dirname(os.path.abspath(__file__))
    parent_dir = os.path.dirname(current_dir)
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)

    try:
        import config
    except ImportError as e:
        print(f"❌ Критическая ошибка: Парсер Пятерочки не смог найти файл config.py! ({e})")
        return []

    cities_to_parse = cities_list if cities_list is not None else getattr(config, 'cities', [])
    search_patterns = search_list if search_list is not None else getattr(config, 'search_req', [])
    brands_to_filter = brand_list if brand_list is not None else getattr(config, 'brand', [])

    if not cities_to_parse or not search_patterns:
        print("⚠️ Пятерочка: Не заданы города (cities) или товары (search_req) в config.py.")
        return []

    full_items_data = []

    for city in cities_to_parse:
        print(f"Парсим Пятерочка {city}")

        # Передаем паттерны в функцию поиска
        search_data = get_search(city_name=city, query=search_patterns)

        if not search_data:
            continue

        parsed_items = parse_items(search_data)

        if brands_to_filter and brands_to_filter != search_patterns:
            parsed_items = filter_brand(items=parsed_items, brand=brands_to_filter)

        full_items_data.extend(parsed_items)

        try:
            from parsers_core.utils import update_retail_points  # Или откуда у вас эта функция
            unique_addresses = set(
                item.get("Адрес Торговой точки") for item in parsed_items if item.get("Адрес Торговой точки"))
            count_stores = len(unique_addresses)
            update_retail_points("Пятерочка", city, count_stores)
        except Exception as e:
            print(f"⚠️ Ошибка статистики: {e}")

    return full_items_data
