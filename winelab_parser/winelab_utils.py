# -*- coding: utf-8 -*-
import json
import re
import time
from urllib.parse import urlparse, parse_qs, urlencode

import requests
from bs4 import BeautifulSoup

from parsers_core.categories import city_in, is_alcohol_query
from parsers_core.debug_dump import dump_debug
from parsers_core.normalize import split_name_measure, split_regular_promo, to_price
from parsers_core.rows import make_row
from parsers_core.settings import smart_sleep as _core_sleep

BASE_URL = "https://www.winelab.ru"
LAST_HTTP_STATUS = None

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
    return city_in(city, KNOWN_CITIES)


def smart_sleep():
    _core_sleep(section="WINELAB")


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
    return to_price(el.get_text()) if el else None


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
    """Карточку товара берём только браузером: requests с теми же cookies получает 401."""
    from parsers_core.uc_browser import wait_ready
    driver.get(url)
    wait_ready(driver)
    time.sleep(1)
    html = driver.page_source
    if is_blocked_page(html):
        return "blocked"
    return _extract_ld_json(html)


def to_row(card, detail, shop_name, city):
    detail = detail or {}
    offers = detail.get("offers") or {}

    current_price = to_price(offers.get("price")) or to_price(card.get("price"))
    if current_price is None:
        return None
    regular_price, promo_price = split_regular_promo(current_price, card.get("old_price"))

    name, volume, weight = split_name_measure(detail.get("name") or card.get("name"))

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

    in_stock = (offers.get("availability") or "").endswith("InStock")

    return make_row(
        shop_name, city, name, regular_price,
        store_type="Магазин", brand=brand, promo_price=promo_price,
        photo=detail.get("image"), url=card.get("url") or offers.get("url"),
        rating=rating if review_count else 0.0, volume=volume, weight=weight,
        stock=in_stock, category=card.get("category"),
    )
