# -*- coding: utf-8 -*-
import configparser
import os
import random
import re
import time

import requests
from bs4 import BeautifulSoup

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
    name = (city or "").strip().lower()
    return any(name in known or known in name for known in KNOWN_CITIES)


def _read_delays(section="WINESTYLE"):
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


def dump_debug(debug_dir, label, text):
    if not debug_dir:
        return
    os.makedirs(debug_dir, exist_ok=True)
    path = os.path.join(debug_dir, f"{label}.html")
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(text or "")
    except Exception:
        pass


_VOL_RE = re.compile(r'(\d+[.,]?\d*)\s*(мл|л|кг|г)(?![а-яёa-z])', re.IGNORECASE)


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


def _to_float(text):
    if not text:
        return None
    cleaned = text.replace("\xa0", "").replace(" ", "").replace("₽", "").strip()
    cleaned = cleaned.replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


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
    regular = product.get("regular_price")
    if regular is None:
        return None
    promo = product.get("promo_price")
    clean_name, volume, weight = split_name_measure(product.get("name") or "")
    return {
        "Сеть": shop_name,
        "Тип магазина": "Магазин",
        "Адрес Торговой точки": city,
        "Бренд": product.get("brand") or "",
        "Название продукта": clean_name,
        "Цена": float(regular),
        "Фото товара": product.get("photo") or "",
        "Ссылка на страницу": product.get("url") or "",
        "Объем": volume,
        "Вес": weight,
        "Остаток": "1",
        "Категория": "",
        "Цена по акции": float(promo) if promo is not None else 0.0,
        "Рейтинг": float(product.get("rating") or 0),
    }
