# -*- coding: utf-8 -*-
import re
import time

import requests

from parsers_core.categories import city_in
from parsers_core.debug_dump import dump_debug as _dump
from parsers_core.normalize import norm_measure, split_name_measure, split_regular_promo
from parsers_core.rows import make_row
from parsers_core.settings import smart_sleep as _core_sleep

API_URL = "https://api.yarcheplus.ru/api/graphql"
HOME_URL = "https://yarcheplus.ru/"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

KNOWN_CITIES = {
    "асино", "ачинск", "балашиха", "барнаул", "белово", "бердск", "бийск",
    "брянск", "видное", "владимир", "внуковское", "воронеж", "воскресенск",
    "долгопрудный", "домодедово", "екатеринбург", "жуковский", "зеленоград",
    "иваново", "искитим", "калуга", "кемерово", "ковров", "коломна",
    "королёв", "королев", "красногорск", "красноярск", "курск",
    "ленинск-кузнецкий", "липецк", "луховицы", "люберцы", "междуреченск",
    "мисайлово", "москва", "московский", "муром", "мытищи",
    "нижний новгород", "новоалтайск", "новокузнецк", "новомосковск",
    "новосибирск", "ногинск", "обнинск", "обь", "одинцово", "омск",
    "орехово-зуево", "осинники", "пермь", "подольск", "прокопьевск",
    "пушкино", "раменское", "реутов", "рязань", "северск",
    "сергиев посад", "серпухов", "тверь", "томск", "троицк", "тула",
    "тюмень", "фрязино", "химки", "челябинск", "черепаново", "чехов",
    "щёлково", "щелково", "электросталь", "юрга", "ярославль",
}

LAST_HTTP_STATUS = None


def is_served_city(city):
    """Города доставки Ярче!."""
    return city_in(city, KNOWN_CITIES)


def smart_sleep():
    _core_sleep(section="YARCHE")


def _request(session, method, url, **kw):
    global LAST_HTTP_STATUS
    kw.setdefault("timeout", 20)

    delay = 5
    for attempt in range(4):
        r = session.request(method, url, **kw)
        LAST_HTTP_STATUS = r.status_code
        if r.status_code != 429:
            break
        if attempt < 3:
            time.sleep(delay)
            delay *= 2

    if r.status_code == 401:
        from parsers_core.exceptions import AuthLost
        raise AuthLost(f"Ярче!: сессия не принята (401) на {url}")
    if r.status_code == 429:
        from parsers_core.exceptions import RateLimited
        raise RateLimited(f"Ярче!: ограничение частоты запросов (429) на {url}")
    if r.status_code in (403, 404):
        raise RuntimeError(f"Ошибка {r.status_code}")
    return r


def bootstrap_token(session):
    r = _request(session, "GET", HOME_URL, headers={
        "User-Agent": UA,
        "Accept-Language": "ru-RU,ru;q=0.9",
    })
    if r.status_code == 500:
        raise RuntimeError("Ошибка 500")
    m = re.search(r'"auth":\{[^}]*?"token":"([0-9a-f-]+)"', r.text)
    if not m:
        raise RuntimeError("Не удалось получить сессионный token со страницы")
    return m.group(1)


SEARCH_QUERY = """
  query ($search: String!, $page: PageInput) {
    search (search: $search, page: $page) {
      products {
        id
        code
        name
        price
        previousPrice
        isAvailable
        rating
        numberOfRatings
        brand
        weightUnit
        volumeUnit
        categories { name }
        image { id }
      }
      page { total limit page }
    }
  }
"""


def dump_debug(debug_dir, label, text):
    _dump(debug_dir, label, text, ext=".json")


def search_products(session, token, query_text, page_limit=48, max_pages=20, debug_dir=None):
    global LAST_HTTP_STATUS
    products = []
    page_num = 1
    while page_num <= max_pages:
        payload = {
            "query": SEARCH_QUERY,
            "variables": {
                "search": query_text,
                "page": {"page": page_num, "limit": page_limit},
            },
        }
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/plain, */*",
            "token": token,
            "Origin": "https://yarcheplus.ru",
            "Referer": "https://yarcheplus.ru/",
            "User-Agent": UA,
        }
        r = _request(session, "POST", API_URL, json=payload, headers=headers)
        dump_debug(debug_dir, f"{query_text}_page{page_num}", r.text)
        if r.status_code == 500:
            break
        data = r.json()
        if data.get("errors"):
            break
        result = (data.get("data") or {}).get("search") or {}
        batch = result.get("products") or []
        products.extend(batch)
        print(f"[Ярче!] Страница {page_num}: найдено товаров {len(batch)}")

        page_info = result.get("page") or {}
        total = page_info.get("total") or 0
        if not batch or len(products) >= total or len(batch) < page_limit:
            break
        page_num += 1
        smart_sleep()
    return products


def _matches_brand(product, brands):
    brand = (product.get("brand") or "").strip().lower()
    if not brand:
        return False
    return any(b.strip().lower() in brand or brand in b.strip().lower() for b in brands)


def filter_by_brand(products, brands):
    return [p for p in products if _matches_brand(p, brands)]


def photo_url(image_id, size="600x600"):
    if not image_id:
        return ""
    s = str(int(image_id)).zfill(5)
    return f"https://api.yarcheplus.ru/thumbnail/{size}/{s[:2]}/{s[2:]}/{image_id}.webp"


def to_row(product, shop_name, city):
    regular, promo = split_regular_promo(product.get("price"), product.get("previousPrice"))
    categories = product.get("categories") or []

    name, name_vol, name_wt = split_name_measure(product.get("name"))
    api_vol, api_vol_as_wt = norm_measure(product.get("volumeUnit"))
    _, api_wt = norm_measure(product.get("weightUnit"))

    return make_row(
        shop_name, city, name, regular,
        store_type="Доставка", brand=product.get("brand"), promo_price=promo,
        photo=photo_url((product.get("image") or {}).get("id")),
        url=f"https://yarcheplus.ru/product/{product.get('code')}-{product.get('id')}",
        rating=product.get("rating"),
        volume=api_vol or name_vol, weight=api_wt or api_vol_as_wt or name_wt,
        stock=bool(product.get("isAvailable")),
        category=categories[-1]["name"] if categories else "",
    )
