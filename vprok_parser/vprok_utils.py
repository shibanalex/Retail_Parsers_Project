# -*- coding: utf-8 -*-
import json
import re

from bs4 import BeautifulSoup

from parsers_core.debug_dump import dump_debug
from parsers_core.normalize import split_name_measure, split_regular_promo
from parsers_core.rows import make_row

BASE_URL = "https://www.vprok.ru"
LAST_HTTP_STATUS = None


def capture_status(driver):
    """Настоящий HTTP-код страницы из лога сети браузера."""
    global LAST_HTTP_STATUS
    try:
        logs = driver.get_log("performance")
    except Exception:
        return
    status = None
    for entry in logs:
        try:
            msg = json.loads(entry["message"])["message"]
        except Exception:
            continue
        if msg.get("method") != "Network.responseReceived":
            continue
        params = msg.get("params", {})
        if params.get("type") != "Document":
            continue
        response = params.get("response", {})
        if BASE_URL in (response.get("url") or ""):
            status = response.get("status")
    if status is not None:
        LAST_HTTP_STATUS = status

KNOWN_CITIES = {
    "москва", "зеленоград", "троицк", "щербинка", "апрелевка", "балашиха",
    "видное", "воскресенск", "дзержинский", "долгопрудный", "домодедово",
    "дубна", "жуковский", "ивантеевка", "истра", "кашира", "климовск",
    "клин", "коломна", "королёв", "королев", "котельники", "красноармейск",
    "красногорск", "лобня", "лосино-петровский", "луховицы", "лыткарино",
    "люберцы", "можайск", "мытищи", "наро-фоминск", "ногинск", "одинцово",
    "орехово-зуево", "подольск", "протвино", "пушкино", "раменское",
    "реутов", "сергиев посад", "серпухов", "солнечногорск", "ступино",
    "фрязино", "химки", "черноголовка", "чехов", "шатура", "щёлково",
    "щелково", "электросталь", "электроугли", "санкт-петербург", "петербург",
    "спб", "колпино", "пушкин", "сестрорецк", "петергоф", "кронштадт",
    "всеволожск", "выборг", "гатчина", "кириши", "кировск", "коммунар",
    "кудрово", "мурино", "отрадное", "сертолово", "сосновый бор", "тосно",
}


def is_served_city(city):
    name = (city or "").strip().lower()
    return any(name in known or known in name for known in KNOWN_CITIES)


_BRAND_RE = re.compile(r'\{"name":"Торговая марка"[^}]*"value":"([^"]+)"')


def extract_brand(html):
    m = _BRAND_RE.search(html or "")
    return m.group(1) if m else ""


def check_page(html):
    global LAST_HTTP_STATUS
    text = html or ""
    if "похожи на автоматические" in text or "Ошибка #" in text:
        code = LAST_HTTP_STATUS if LAST_HTTP_STATUS in (403, 404, 429, 500) else 403
        LAST_HTTP_STATUS = code
        raise RuntimeError(f"Ошибка {code}")


def _class_has(tag, needle):
    cls = tag.get("class") or []
    return any(needle in c for c in cls)


def _class_token(needle):
    return lambda c: c and needle in c


def _direct_text(tag):
    for c in tag.contents:
        if isinstance(c, str):
            return c
    return ""


def _extract_price(span):
    if span is None:
        return None
    rubles = _direct_text(span).strip()
    if not rubles.isdigit():
        return None
    frac_span = span.find(lambda t: t.name == "span" and _class_has(t, "Price_fraction"))
    frac_digits = ""
    if frac_span is not None:
        frac_digits = re.sub(r"[^\d]", "", _direct_text(frac_span))
    if frac_digits:
        return float(f"{rubles}.{frac_digits}")
    return float(rubles)


def _extract_id(href):
    m = re.search(r"--(\d+)", href or "")
    return m.group(1) if m else None


def parse_search_page(html):
    soup = BeautifulSoup(html, "html.parser")
    products = []
    for article in soup.find_all("article", class_=_class_token("UiProductTileMain_root")):
        link = article.find("a", class_=_class_token("longName"))
        if not link or not link.get("href"):
            continue
        pid = _extract_id(link["href"])
        if not pid:
            continue
        name = link.get("title") or link.get_text(strip=True)

        discount_span = article.find("span", class_=_class_token("Price_role_discount"))
        old_span = article.find("span", class_=_class_token("Price_role_old"))
        regular_span = article.find("span", class_=_class_token("Price_role_regular"))

        current_price = _extract_price(discount_span) if discount_span else _extract_price(regular_span)
        old_price = _extract_price(old_span) if old_span else None
        if current_price is None:
            continue

        rating = 0.0
        rating_link = article.find("a", class_=_class_token("UiProductButtonRating_rating"))
        if rating_link and rating_link.get("title"):
            m = re.search(r"[\d.,]+", rating_link["title"])
            if m:
                try:
                    rating = float(m.group().replace(",", "."))
                except ValueError:
                    rating = 0.0

        img = article.find("img")
        photo = img.get("src") or "" if img else ""

        products.append({
            "id": pid,
            "name": name,
            "url": BASE_URL + link["href"].split("?")[0],
            "photo": photo,
            "price": current_price,
            "old_price": old_price,
            "rating": rating,
        })
    return products


def to_row(product, shop_name, city):
    regular, promo = split_regular_promo(product.get("price"), product.get("old_price"))
    name, volume, weight = split_name_measure(product.get("name"))
    return make_row(
        shop_name, city, name, regular,
        store_type="Доставка", brand=product.get("brand"), promo_price=promo,
        photo=product.get("photo"), url=product.get("url"), rating=product.get("rating"),
        volume=volume, weight=weight, stock="1",
    )
