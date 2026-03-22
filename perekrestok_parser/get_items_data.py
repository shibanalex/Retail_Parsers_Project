import os
from parsers_core.utils import update_retail_points, write_excel, write_json
from perekrestok_parser.requests_to_site import (
    _close_driver,
    get_city,
    get_city_http,
    get_item_data,
    get_search_items_http,
    get_search_request,
    set_jwt_token,
)
from perekrestok_parser.get_category_items import get_items_ids
from perekrestok_parser.urls import json_path
from tqdm import tqdm
from perekrestok_parser.settings import cats, shops, retail_name
from datetime import datetime
from config import cities, brand, search_req
import time
import random

retail = "Перекресток"


def safe_join(value, sep=", "):
    """Безопасное объединение поддерживает None, строки и списки."""
    if not value:
        return ""
    if isinstance(value, (list, tuple, set)):
        return sep.join(str(v) for v in value if v)
    return str(value)


def check_search_match(item_data, sr):
    """Проверяет, все ли слова из поискового запроса содержатся в названии товара."""
    sr_split = sr.split()
    item_title = item_data.get("content", {}).get("title") or item_data.get("title") or ""
    result_check = []
    for elem in sr_split:
        if elem.lower() in item_title.lower():
            result_check.append(True)
        else:
            result_check.append(False)
    return all(result_check)


def parse_json_data(item_data, retail=retail_name):
    """Разбор JSON-данных о товаре и формирование итогового словаря."""
    if not item_data or not isinstance(item_data, dict):
        return None

    def parse_features(features, field_name: str):
        for feature in features or []:
            if not isinstance(feature, dict):
                continue
            feature_title = feature.get("title")
            if feature_title == field_name:
                for dct in feature.get("items") or []:
                    if isinstance(dct, dict) and dct.get("title") == "Бренд":
                        return dct.get("displayValues")
        return None

    def parse_photos(photos):
        photos_urls = []
        for photo in photos or []:
            if not isinstance(photo, dict):
                continue
            photo_url = photo.get("cropUrlTemplate")
            if photo_url:
                photo_url = photo_url.replace("%s", "1600x1600-fit")
                photos_urls.append(photo_url)
        return photos_urls

    def parse_url():
        content = item_data.get("content") or {}
        cat_primary = content.get("catalogPrimaryCategory") or {}
        cat_id = cat_primary.get("id")
        if not cat_id:
            primary_cat = content.get("primaryCategory") or {}
            cat_id = primary_cat.get("id")
        master_data = content.get("masterData") or {}
        item_slug = master_data.get("slug")
        item_plu = master_data.get("plu")
        return f"https://www.perekrestok.ru/cat/{cat_id}/p/{item_slug}-{item_plu}"

    result_dct = {
        "Номер": None,
        "Сеть": retail,
        "Тип магазина": None,
        "Адрес Торговой точки": None,
        "Бренд": None,
        "Название продукта": None,
        "Цена": None,
        "Цена по акции": None,
        "Фото товара": None,
        "Ссылка на страницу": None,
        "Рейтинг": None,
        "Объем": None,
        "Вес": None,
        "Остаток": None,
    }

    content = item_data.get("content") or {}
    master_data = content.get("masterData") or {}
    item_features = content.get("features")
    item_photos = content.get("images")
    item_weight = master_data.get("weight")
    item_volume = master_data.get("volume")
    item_title = content.get("title")
    item_brand = parse_features(item_features, "Информация")
    price_tag = item_data.get("priceTag") or {}
    item_price = price_tag.get("grossPrice")
    item_photos = parse_photos(item_photos)
    item_url = parse_url()
    item_rating = content.get("rating")
    item_stock = content.get("balanceStock")
    if item_stock:
        item_stock = int(item_stock / 100)
    result_dct["Название продукта"] = item_title
    result_dct["Бренд"] = safe_join(item_brand)
    result_dct["Фото товара"] = safe_join(item_photos)
    result_dct["Ссылка на страницу"] = item_url
    result_dct["Вес"] = item_weight
    result_dct["Объем"] = item_volume
    result_dct["Рейтинг"] = item_rating / 100 if item_rating else None
    result_dct["Остаток"] = item_stock
    if item_price:
        result_dct["Цена"] = item_price / 100
        content_price_tag = content.get("priceTag") or {}
        discount_price = content_price_tag.get("price")
        result_dct["Цена по акции"] = discount_price / 100 if discount_price else None
    else:
        content_price_tag = content.get("priceTag") or {}
        item_price = content_price_tag.get("price")
        result_dct["Цена"] = item_price / 100 if item_price else None

    return result_dct


def parse_search_item_data(item_data, retail=retail_name):
    """Разбор данных товара из ответа search/all."""
    if not item_data or not isinstance(item_data, dict):
        return None

    master_data = item_data.get("masterData") or {}
    item_title = item_data.get("title")
    item_rating = item_data.get("rating")
    price_tag = item_data.get("priceTag") or {}
    item_image = item_data.get("image") or {}

    cat_id = None
    for key in ("catalogPrimaryCategory", "primaryCategory", "category"):
        value = item_data.get(key) or {}
        cat_id = value.get("id")
        if cat_id:
            break

    item_slug = master_data.get("slug")
    item_plu = master_data.get("plu")
    item_url = None
    if cat_id and item_slug and item_plu:
        item_url = f"https://www.perekrestok.ru/cat/{cat_id}/p/{item_slug}-{item_plu}"

    photo_url = None
    crop = item_image.get("cropUrlTemplate")
    if crop:
        photo_url = crop.replace("%s", "1600x1600-fit")

    result_dct = {
        "Номер": None,
        "Сеть": retail,
        "Тип магазина": None,
        "Адрес Торговой точки": None,
        "Бренд": None,
        "Название продукта": item_title,
        "Цена": None,
        "Цена по акции": None,
        "Фото товара": safe_join(photo_url),
        "Ссылка на страницу": item_url,
        "Рейтинг": item_rating / 100 if item_rating else None,
        "Объем": master_data.get("volume"),
        "Вес": master_data.get("weight"),
        "Остаток": None,
    }

    gross_price = price_tag.get("grossPrice")
    price = price_tag.get("price")
    if gross_price:
        result_dct["Цена"] = gross_price / 100
        if price and price != gross_price:
            result_dct["Цена по акции"] = price / 100
    elif price:
        result_dct["Цена"] = price / 100

    return result_dct


def get_items_data_by_category(category_id: int, shop_id: int) -> list:
    """Получает данные товаров по категории."""
    items_ids = get_items_ids(category_id, shop_id)
    items_data_by_category = [get_item_data(item_id) for item_id in tqdm(items_ids)]
    return items_data_by_category


def get_all_items_data(categories: dict = cats, shops: dict = shops) -> None:
    """
    Получает все товары по магазинам и категориям.
    """
    for shop_id, shop_name in shops.items():
        print(f"Парсим {retail_name} — {shop_name}")
        for category_id, category_name in categories.items():
            print(f"Парсим категорию {category_name}")
            items_data_by_category = get_items_data_by_category(
                category_id=category_id, shop_id=shop_id
            )
            write_json(
                items_data_by_category,
                f"{json_path}{category_name}_{shop_id}_{shop_name}.json",
            )
    return None


def parse_search_json(search_json):
    """Извлекает ID товаров из ответа поиска."""
    product_ids = []
    if not search_json or not isinstance(search_json, dict):
        return product_ids
    content = search_json.get("content") or {}
    products_data = content.get("items") or []
    for product in products_data:
        if not isinstance(product, dict):
            continue
        master_data = product.get("masterData") or {}
        product_id = master_data.get("plu")
        if product_id:
            product_ids.append(product_id)
    return product_ids


def filter_by_brand(brand, parsed_items):
    """Фильтрует товары по бренду (поддерживает частичные совпадения)."""
    filtered_items = []
    brand = brand.lower().strip()
    for item in parsed_items:
        item_brand = (item.get("Бренд") or "").lower()
        if brand in item_brand:
            filtered_items.append(item)
    return filtered_items


def get_search_legacy(search_req=search_req, cities=cities, brand=brand):
    """
    Основная функция поиска и парсинга товаров по запросу (driver-based).
    Гибридный режим: Город ищем через HTTP, товары собираем через Driver.
    """

    def get_json_data_w_pagination(sr, shop_id, max_retries=15):
        page = 1
        for retry in range(max_retries):
            first_req = get_search_request(search_req=sr, shop_id=shop_id, page=page)
            all_search_data = [first_req]
            try:
                next_page = first_req.get("content", {}).get("paginator", {}).get("nextPageExists")
            except AttributeError:
                print("Токен не получен. Повторное соединение.")
                time.sleep(random.uniform(5, 10))
                set_jwt_token(value=None)
                continue
            while next_page:
                page += 1
                json_data = get_search_request(search_req=sr, shop_id=shop_id, page=page)
                all_search_data.append(json_data)
                next_page = json_data.get("content", {}).get("paginator", {}).get("nextPageExists")
            return all_search_data
        return None

    all_parsed_data = []
    search_pattern = search_req or brand
    stats = {
        "Обработано городов": set(),
        "Итого магазинов": 0,
        "Количество поисковых запросов": len(search_pattern),
        "Список поисковых запросов": search_pattern,
    }

    for city in cities:
        stats["Обработано городов"].add(city)

        cities_data = get_city_http(city_pattern=city)


        if not cities_data:
            print(f"HTTP поиск города '{city}' не дал результатов, пробую Selenium...")
            cities_data = get_city(city_pattern=city)

        if not cities_data:
            print(f"❌ Не удалось найти данные для города: {city}. Пропускаем.")
            set_jwt_token(value=None)
            continue

        for shop_id, shop_address in cities_data:
            stats["Итого магазинов"] += 1
            print(f"Парсим №{stats.get('Итого магазинов')} {retail_name} {shop_address}")
            for sr in search_pattern:
                search_data = []
                parsed_data_lst = []
                search_json = get_json_data_w_pagination(sr, shop_id=shop_id)
                if not search_json:
                    set_jwt_token(value=None)
                    continue
                for item in search_json:
                    if not item:
                        continue
                    product_ids = parse_search_json(item)
                    for product_num, product_id in enumerate(product_ids, 1):
                        item_data = get_item_data(product_id)
                        if not item_data:
                            continue
                        if check_search_match(item_data, sr):
                            search_data.append(item_data)
                            parsed_data = parse_json_data(item_data)
                            if not parsed_data:
                                continue
                            parsed_data["Номер"] = product_num
                            parsed_data["Адрес Торговой точки"] = shop_address
                            parsed_data_lst.append(parsed_data)
                            if brand and brand is not search_pattern:
                                parsed_data_lst = filter_by_brand(brand, parsed_data_lst)
                all_parsed_data.extend(parsed_data_lst)
        count_stores = len(cities_data)
        update_retail_points(retail, city, count_stores)
    _close_driver()
    return all_parsed_data


def get_search_http(search_req=search_req, cities=cities, brand=brand):
    """Основная функция поиска и парсинга товаров по запросу (HTTP + Selenium token)."""
    all_parsed_data = []
    search_pattern = search_req or brand
    stats = {
        "Обработано городов": set(),
        "Итого магазинов": 0,
        "Количество поисковых запросов": len(search_pattern),
        "Список поисковых запросов": search_pattern,
    }

    for city in cities:
        stats["Обработано городов"].add(city)
        cities_data = get_city_http(city_pattern=city)
        if not cities_data:
            print("HTTP-режим: данные города не получены, пробую legacy-режим.")
            cities_data = get_city(city_pattern=city)
        if not cities_data:
            print("Токен/данные города не получены. Повторное подключение.")
            continue
        for shop_id, shop_address in cities_data:
            stats["Итого магазинов"] += 1
            print(f"Парсим №{stats.get('Итого магазинов')} {retail_name} {shop_address}")
            for sr in search_pattern:
                parsed_data_lst = []
                items = get_search_items_http(sr, shop_id=shop_id)
                if not items:
                    continue
                for product_num, item in enumerate(items, 1):
                    if check_search_match(item, sr):
                        parsed_data = parse_search_item_data(item)
                        if not parsed_data:
                            continue
                        parsed_data["Номер"] = product_num
                        parsed_data["Адрес Торговой точки"] = shop_address
                        parsed_data_lst.append(parsed_data)
                        if brand and brand is not search_pattern:
                            parsed_data_lst = filter_by_brand(brand, parsed_data_lst)
                all_parsed_data.extend(parsed_data_lst)
        count_stores = len(cities_data)
        update_retail_points(retail, city, count_stores)
    _close_driver()
    return all_parsed_data


def get_search(search_req=search_req, cities=cities, brand=brand):
    """Основная функция поиска и парсинга товаров по запросу."""
    use_http = os.getenv("PEREKRESTOK_HTTP_SEARCH", "0").lower() in ("1", "true", "yes")
    if use_http:
        return get_search_http(search_req=search_req, cities=cities, brand=brand)
    return get_search_legacy(search_req=search_req, cities=cities, brand=brand)


if __name__ == "__main__":
    get_search()