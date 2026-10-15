# -*- coding: utf-8 -*-
import time

import requests
from bs4 import BeautifulSoup

from parsers_core.categories import city_in, is_alcohol_query
from parsers_core.debug_dump import dump_debug
from parsers_core.normalize import split_name_measure, to_price
from parsers_core.rows import make_row
from parsers_core.settings import smart_sleep as _core_sleep

BASE_URL = "https://winestyle.ru"
LAST_HTTP_STATUS = None

CATEGORY_MAP = {
    "вино": "wine",
    "красное вино": "wine",
    "белое вино": "wine",
    "виски": "whisky",
    "виски шотландский": "whisky",
    "бурбон": "whisky",
    "коньяк": "cognac",
    "бренди": "cognac",
    "ром": "rum",
    "джин": "gin",
    "водка": "vodka",
    "текила": "tequila",
    "пиво": "beer",
    "сидр": "cider",
    "шампанское": "champagnes-and-sparkling",
    "игристое": "champagnes-and-sparkling",
    "игристое вино": "champagnes-and-sparkling",
    "ликер": "liqueur",
    "ликёр": "liqueur",
    "вода": "water",
}


def category_slug(query):
    """Поиск сайта отдаёт ~15 позиций без пагинации, поэтому добираем страницей категории."""
    return CATEGORY_MAP.get((query or "").strip().lower())


KNOWN_CITIES = {
    "москва", "зеленоград", "балашиха", "видное", "долгопрудный", "домодедово",
    "жуковский", "истра", "королёв", "королев", "красногорск", "коломна",
    "лобня", "люберцы", "мытищи", "наро-фоминск", "ногинск", "одинцово",
    "орехово-зуево", "подольск", "пушкино", "раменское", "реутов", "сергиев посад",
    "серпухов", "солнечногорск", "щёлково", "щелково", "химки", "чехов",
    "электросталь", "апрелевка", "троицк", "московский", "нахабино", "дедовск",
}


def is_served_city(city):
    """Сеть работает только в Москве и области."""
    return city_in(city, KNOWN_CITIES)


def smart_sleep():
    _core_sleep(section="WINESTYLE")


def bootstrap_session():
    from .browser import solve_challenge
    cookies, ua = solve_challenge()
    session = requests.Session()
    for k, v in cookies.items():
        session.cookies.set(k, v, domain="winestyle.ru")
    session.headers.update({
        "User-Agent": ua,
        "Accept-Language": "ru-RU,ru;q=0.9",
    })
    return session


def fetch(session, url):
    global LAST_HTTP_STATUS

    delay = 5
    for attempt in range(4):
        r = session.get(url, timeout=20)
        LAST_HTTP_STATUS = r.status_code
        if r.status_code != 429:
            break
        if attempt < 3:
            time.sleep(delay)
            delay *= 2

    if r.status_code == 401:
        from parsers_core.exceptions import AuthLost
        raise AuthLost(f"Winestyle: сессия не принята (401) на {url}")
    if r.status_code == 429:
        from parsers_core.exceptions import RateLimited
        raise RateLimited(f"Winestyle: ограничение частоты запросов (429) на {url}")
    if r.status_code == 403:
        raise RuntimeError(f"Ошибка {r.status_code}")
    if r.status_code == 404 and "m-product-item" not in r.text:
        raise RuntimeError("Ошибка 404")
    return r


def _to_float(text):
    return to_price(text)


def _parse_price(card):
    price_block = card.select_one(".m-product-item__price")
    if price_block is None:
        return None, None
    sale = price_block.select_one(".price--sale")
    if sale is not None:
        ps = sale.find_all("p")
        if len(ps) >= 2:
            promo = _to_float(ps[0].get_text())
            regular = _to_float(ps[1].get_text())
            return regular, promo
    p = price_block.select_one("p.price") or price_block.find("p")
    if p is not None:
        return _to_float(p.get_text()), None
    return None, None


def _brand_from_name(name):
    if not name or "," not in name:
        return ""
    head = name.split(",", 1)[0].strip()
    if head.startswith(("\"", "«")):
        return ""
    return head


def _parse_description(card):
    result = {}
    for row in card.select(".m-description tr"):
        label_el = row.find("th")
        value_el = row.select_one(".m-description__value")
        if not label_el or not value_el:
            continue
        label = label_el.get_text(strip=True).rstrip(":")
        result[label] = value_el.get_text(strip=True)
    return result


def parse_cards(html):
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen_urls = set()
    for card in soup.select(".m-product-item"):
        link = card.select_one(".m-product-item__title")
        if not link or not link.get("href"):
            continue
        url = link["href"]
        if not url.startswith("http"):
            url = BASE_URL + url
        if url in seen_urls:
            continue
        seen_urls.add(url)

        name = link.get("aria-label") or link.get_text(strip=True)
        regular_price, promo_price = _parse_price(card)
        if regular_price is None:
            continue

        desc = _parse_description(card)
        brand = desc.get("Бренд", "") or _brand_from_name(name)

        rating = 0.0
        meter = card.select_one('[role="meter"]')
        if meter and meter.get("aria-valuenow"):
            try:
                rating = float(meter["aria-valuenow"].replace(",", "."))
            except ValueError:
                rating = 0.0

        img = card.find("img")
        photo = img.get("src") or "" if img else ""

        products.append({
            "url": url,
            "name": name,
            "brand": brand,
            "regular_price": regular_price,
            "promo_price": promo_price,
            "rating": rating,
            "photo": photo,
        })
    return products


def to_row(product, shop_name, city):
    name, volume, weight = split_name_measure(product.get("name"))
    return make_row(
        shop_name, city, name, product.get("regular_price"),
        store_type="Магазин", brand=product.get("brand"), promo_price=product.get("promo_price"),
        photo=product.get("photo"), url=product.get("url"), rating=product.get("rating"),
        volume=volume, weight=weight, stock="1",
    )
