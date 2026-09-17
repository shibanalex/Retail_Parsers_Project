# -*- coding: utf-8 -*-
import configparser
import os
import random
import re
import time

import requests

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
    name = (city or "").strip().lower()
    return any(name in known or known in name for known in KNOWN_CITIES)


def _read_delays(section="YARCHE"):
    cfg_path = os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "parsers_core", "share_parsers.cfg")
    min_delay, max_delay = 1.0, 3.0
    if os.path.exists(cfg_path):
        cp = configparser.ConfigParser()
        try:
            cp.read(cfg_path, encoding="utf-8")
            if cp.has_section("BROWSER"):
                min_delay = cp.getfloat("BROWSER", "min_delay", fallback=min_delay)
                max_delay = cp.getfloat("BROWSER", "max_delay", fallback=max_delay)
            if cp.has_section(section):
                min_delay = cp.getfloat(section, "min_delay", fallback=min_delay)
                max_delay = cp.getfloat(section, "max_delay", fallback=max_delay)
        except Exception:
            pass
    return min_delay, max_delay


def smart_sleep():
    lo, hi = _read_delays()
    time.sleep(random.uniform(lo, hi))


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
    if not debug_dir:
        return
    os.makedirs(debug_dir, exist_ok=True)
    path = os.path.join(debug_dir, f"{label}.json")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text or "")
    except Exception:
        pass


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


_VOL_RE = re.compile(r'(\d+[.,]?\d*)\s*(мл|л|кг|г)(?![а-яёa-z])', re.IGNORECASE)


def norm_measure(v):
    v = (v or "").replace(",", ".").strip()
    unit = v.split()[-1].lower() if v else ""
    if unit in ("л", "мл"):
        return v, ""
    if unit in ("г", "кг"):
        return "", v
    return "", ""


def split_name_measure(name):
    name = name or ""
    m = _VOL_RE.search(name)
    if not m:
        return re.sub(r'\s{2,}', ' ', name).strip(" ,;"), "", ""
    value = m.group(1).replace(",", ".")
    unit = m.group(2).lower()
    clean = (name[:m.start()] + " " + name[m.end():])
    clean = re.sub(r'\s{2,}', ' ', clean).strip(" ,;")
    if unit in ("л", "мл"):
        return clean, f"{value} {unit}", ""
    return clean, "", f"{value} {unit}"


def photo_url(image_id, size="600x600"):
    if not image_id:
        return ""
    s = str(int(image_id)).zfill(5)
    return f"https://api.yarcheplus.ru/thumbnail/{size}/{s[:2]}/{s[2:]}/{image_id}.webp"


def to_row(product, shop_name, city):
    price = product.get("price")
    previous = product.get("previousPrice")
    if previous is not None and price is not None and previous > price:
        regular_price, promo_price = previous, price
    else:
        regular_price, promo_price = price, None

    if regular_price is None:
        return None

    categories = product.get("categories") or []
    category = categories[-1]["name"] if categories else ""

    brand = product.get("brand") or ""

    clean_name, name_vol, name_wt = split_name_measure(product.get("name") or "")
    api_vol, api_vol_as_wt = norm_measure(product.get("volumeUnit"))
    _, api_wt = norm_measure(product.get("weightUnit"))
    volume = api_vol or name_vol
    weight = api_wt or api_vol_as_wt or name_wt

    return {
        "Сеть": shop_name,
        "Тип магазина": "Доставка",
        "Адрес Торговой точки": city,
        "Бренд": brand,
        "Название продукта": clean_name,
        "Цена": float(regular_price),
        "Фото товара": photo_url((product.get("image") or {}).get("id")),
        "Ссылка на страницу": f"https://yarcheplus.ru/product/{product.get('code')}-{product.get('id')}",
        "Объем": volume,
        "Вес": weight,
        "Остаток": "1" if product.get("isAvailable") else "0",
        "Категория": category,
        "Цена по акции": float(promo_price) if promo_price is not None else 0,
        "Рейтинг": float(product.get("rating") or 0),
    }
