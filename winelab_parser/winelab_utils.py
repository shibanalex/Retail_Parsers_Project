# -*- coding: utf-8 -*-
import configparser
import json
import os
import random
import re
import time
from urllib.parse import urlparse, parse_qs, urlencode

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.winelab.ru"
LAST_HTTP_STATUS = None

ALCOHOL_KEYWORDS = {
    "вино", "винн", "виски", "водка", "коньяк", "бренди", "ром", "джин",
    "текила", "пиво", "сидр", "шампанск", "игрист", "ликер", "ликёр",
    "вермут", "абсент", "портвейн", "херес", "саке", "мескаль", "глинтвейн",
    "каберне", "мерло", "шардоне", "совиньон", "рислинг", "пино",
    "мускат", "санджовезе", "темпранильо", "мальбек", "шираз", "сира",
    "зинфандель", "неббиоло", "грюнер", "просекко", "кава", "граппа",
    "перно", "чинзано", "мартини", "джек дэниэлс", "абсолют",
}


def is_alcohol_query(query):
    q = (query or "").strip().lower()
    return any(k in q for k in ALCOHOL_KEYWORDS)

KNOWN_CITIES = {
    "москва", "зеленоград", "балашиха", "видное", "долгопрудный", "домодедово",
    "жуковский", "истра", "королёв", "королев", "красногорск", "коломна",
    "люберцы", "мытищи", "ногинск", "одинцово", "орехово-зуево", "подольск",
    "пушкино", "раменское", "реутов", "сергиев посад", "серпухов", "химки",
    "чехов", "щёлково", "щелково", "электросталь", "санкт-петербург", "петербург",
    "спб", "гатчина", "всеволожск", "выборг", "краснодар", "сочи", "новороссийск",
    "анапа", "геленджик", "армавир", "ростов-на-дону", "ростов", "таганрог",
    "батайск", "волгодонск", "шахты", "воронеж", "липецк", "тамбов", "белгород",
    "старый оскол", "курск", "орёл", "орел", "брянск", "калуга", "обнинск",
    "тула", "рязань", "владимир", "иваново", "кострома", "ярославль", "тверь",
    "смоленск", "великий новгород", "псков", "нижний новгород", "дзержинск",
    "арзамас", "казань", "набережные челны", "нижнекамск", "чебоксары",
    "новочебоксарск", "йошкар-ола", "саранск", "ульяновск", "пенза", "самара",
    "тольятти", "сызрань", "саратов", "энгельс", "балаково", "оренбург", "орск",
    "уфа", "стерлитамак", "октябрьский", "пермь", "березники", "ижевск",
    "сарапул", "киров", "екатеринбург", "нижний тагил", "каменск-уральский",
    "первоуральск", "челябинск", "магнитогорск", "миасс", "златоуст",
    "курган", "тюмень", "тобольск", "сургут", "нижневартовск", "нефтеюганск",
    "ханты-мансийск", "новый уренгой", "ноябрьск", "омск", "новосибирск",
    "бердск", "томск", "северск", "кемерово", "новокузнецк", "прокопьевск",
    "барнаул", "бийск", "рубцовск", "красноярск", "ачинск", "норильск",
    "абакан", "кызыл", "иркутск", "ангарск", "братск", "улан-удэ", "чита",
    "якутск", "благовещенск", "хабаровск", "комсомольск-на-амуре",
    "владивосток", "находка", "уссурийск", "артём", "артем",
    "южно-сахалинск", "петропавловск-камчатский", "магадан", "калининград",
    "мурманск", "североморск", "апатиты", "архангельск", "северодвинск",
    "вологда", "череповец", "петрозаводск", "сыктывкар", "ухта",
    "астрахань", "элиста", "ставрополь", "пятигорск", "кисловодск",
    "невинномысск", "нальчик", "владикавказ", "махачкала", "грозный",
    "симферополь", "севастополь", "ялта", "керчь", "евпатория",
}


def is_served_city(city):
    name = (city or "").strip().lower()
    return any(name in known or known in name for known in KNOWN_CITIES)


def _read_delays(section="WINELAB"):
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
        raise AuthLost(f"ВинЛаб: сессия не принята (401) на {url}")
    if r.status_code == 429:
        from parsers_core.exceptions import RateLimited
        raise RateLimited(f"ВинЛаб: ограничение частоты запросов (429) на {url}")
    if r.status_code == 403:
        raise RuntimeError(f"Ошибка {r.status_code}")
    if r.status_code == 404 and "schema.org/Product" not in r.text:
        raise RuntimeError(f"Ошибка {r.status_code}")
    return r


def _next_url(current_url, next_page_url):
    npu_qs = parse_qs(urlparse(next_page_url).query)
    cur = urlparse(current_url)
    qs = parse_qs(cur.query)
    qs.update(npu_qs)
    flat = {k: v[0] for k, v in qs.items()}
    return f"{cur.scheme}://{cur.netloc}{cur.path}?{urlencode(flat)}"


def _parse_old_price(card):
    el = card.select_one(".product-price--old")
    if not el:
        return None
    text = el.get_text().replace("\xa0", "").replace(" ", "").replace("₽", "").strip()
    try:
        return float(text)
    except ValueError:
        return None


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


def search_products(session, query_text, max_pages=10, debug_dir=None):
    products = []
    url = f"{BASE_URL}/search?text={query_text}"
    page_num = 1
    while url and page_num <= max_pages:
        r = _request(session, "GET", url)
        dump_debug(debug_dir, f"{query_text}_page{page_num}", r.text)
        if r.status_code == 500:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select(".productcard[itemtype='https://schema.org/Product']")
        for card in cards:
            pid = card.get("data-id")
            if not pid:
                continue
            link = card.select_one(".productcard__title")
            href = link.get("href") if link else None
            products.append({
                "id": pid,
                "name": card.get("data-name") or "",
                "price": card.get("data-price"),
                "old_price": _parse_old_price(card),
                "category": card.get("data-category") or "",
                "url": BASE_URL + href if href else "",
            })

        container = soup.select_one(".productcards")
        has_next = bool(container and container.get("data-hasnextpage") == "true")
        next_page_url = container.get("data-nextpageurl") if container else None
        if not has_next or not next_page_url:
            break
        url = _next_url(url, next_page_url)
        page_num += 1
        smart_sleep()
    return products


def _extract_ld_json(html):
    m = re.search(r'application/ld\+json["\']>\s*(\{.*?\})\s*</script>', html or "", re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except ValueError:
        return None


def bootstrap_session_and_driver():
    from .browser import solve_challenge
    driver, cookies, ua = solve_challenge(keep_open=True)
    session = requests.Session()
    for k, v in cookies.items():
        session.cookies.set(k, v, domain="www.winelab.ru")
    session.headers.update({
        "User-Agent": ua,
        "Accept-Language": "ru-RU,ru;q=0.9",
    })
    return session, driver


def is_blocked_page(html):
    text = html or ""
    return "stage.winelab.ru" in text or "qrator" in text.lower()


def fetch_product_detail_browser(driver, url):
    from .browser import _wait_ready
    driver.get(url)
    _wait_ready(driver)
    time.sleep(1)
    html = driver.page_source
    if is_blocked_page(html):
        return "blocked"
    return _extract_ld_json(html)


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


def to_row(card, detail, shop_name, city):
    detail = detail or {}
    offers = detail.get("offers") or {}

    try:
        current_price = float(offers.get("price"))
    except (TypeError, ValueError):
        try:
            current_price = float(card.get("price"))
        except (TypeError, ValueError):
            return None

    old_price = card.get("old_price")
    if old_price is not None and old_price > current_price:
        regular_price, promo_price = old_price, current_price
    else:
        regular_price, promo_price = current_price, 0

    raw_name = detail.get("name") or card.get("name") or ""
    name, volume, weight = split_name_measure(raw_name)

    brand = detail.get("brand") or ""
    if isinstance(brand, dict):
        brand = brand.get("name", "")

    rating_info = detail.get("aggregateRating") or {}
    try:
        review_count = int(rating_info.get("reviewCount") or 0)
    except (TypeError, ValueError):
        review_count = 0
    try:
        rating = float(rating_info.get("ratingValue") or 0)
    except (TypeError, ValueError):
        rating = 0.0

    availability = offers.get("availability") or ""
    in_stock = availability.endswith("InStock")

    return {
        "Сеть": shop_name,
        "Тип магазина": "Магазин",
        "Адрес Торговой точки": city,
        "Бренд": brand,
        "Название продукта": name,
        "Цена": float(regular_price),
        "Фото товара": detail.get("image") or "",
        "Ссылка на страницу": card.get("url") or offers.get("url") or "",
        "Объем": volume,
        "Вес": weight,
        "Остаток": "1" if in_stock else "0",
        "Категория": card.get("category") or "",
        "Цена по акции": float(promo_price),
        "Рейтинг": rating if review_count else 0.0,
    }
