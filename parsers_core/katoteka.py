# -*- coding: utf-8 -*-
"""Каталоги сетей с katoteka.ru. Сайт закрыт антиботом: проверку один раз проходит человек
(python -m parsers_core.katoteka), дальше парсеры работают на cookies общего профиля."""
import base64
import os
import re
import time

from bs4 import BeautifulSoup

from .categories import city_in

BASE_URL = "https://katoteka.ru"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = "katoteka_profile"
CHALLENGE_MARK = "похожий цвет"
LAST_HTTP_STATUS = None

# Регионы katoteka -> города и названия, по которым узнаём регион в config.cities
REGIONS = {
    "mow": ("москва", "московская", "зеленоград", "балашиха", "химки", "подольск", "мытищи", "королёв",
            "королев", "люберцы", "красногорск", "одинцово", "домодедово", "щёлково", "щелково", "реутов"),
    "spe": ("санкт-петербург", "петербург", "спб", "ленинградская", "гатчина", "всеволожск", "выборг"),
    "sve": ("екатеринбург", "свердловская", "нижний тагил", "каменск-уральский", "первоуральск",
            "серов", "новоуральск", "асбест", "берёзовский", "березовский", "ревда", "верхняя пышма"),
    "che": ("челябинск", "челябинская", "магнитогорск", "златоуст", "миасс", "копейск", "троицк"),
    "kgn": ("курган", "курганская", "шадринск"),
    "tyu": ("тюмень", "тюменская", "тобольск", "ишим", "ялуторовск"),
    "khm": ("ханты-мансийск", "югра", "ханты-мансийский", "сургут", "нижневартовск", "нефтеюганск",
            "когалым", "нягань", "мегион", "лангепас", "пыть-ях", "урай"),
    "yan": ("салехард", "ямало-ненецкий", "новый уренгой", "ноябрьск", "надым", "муравленко", "губкинский"),
    "per": ("пермь", "пермский", "березники", "соликамск", "чайковский", "кунгур"),
    "ba": ("уфа", "башкортостан", "башкирия", "стерлитамак", "салават", "нефтекамск", "октябрьский"),
    "ta": ("казань", "татарстан", "набережные челны", "нижнекамск", "альметьевск", "зеленодольск"),
    "ud": ("ижевск", "удмуртия", "удмуртская", "сарапул", "воткинск", "глазов"),
    "nvs": ("новосибирск", "новосибирская", "бердск", "искитим", "обь", "куйбышев"),
    "tom": ("томск", "томская", "северск", "асино", "стрежевой"),
    "kem": ("кемерово", "кемеровская", "кузбасс", "новокузнецк", "прокопьевск", "белово", "междуреченск",
            "ленинск-кузнецкий", "киселёвск", "киселевск", "юрга", "анжеро-судженск"),
    "alt": ("барнаул", "алтайский", "бийск", "рубцовск", "новоалтайск", "заринск", "камень-на-оби",
            "белокуриха", "алейск", "славгород"),
    "gor": ("горно-алтайск", "республика алтай"),
    "kya": ("красноярск", "красноярский", "норильск", "ачинск", "канск", "минусинск", "железногорск"),
}

FETCH_JS = """
const done = arguments[arguments.length - 1];
fetch(arguments[0], {credentials: 'include'}).then(r => {
  if (!r.ok) { done('ERR ' + r.status); return; }
  return r.blob().then(b => { const fr = new FileReader(); fr.onload = () => done(fr.result); fr.readAsDataURL(b); });
}).catch(e => done('ERR ' + e));
"""


class ChallengeRequired(RuntimeError):
    pass


def city_region(city):
    for code, names in REGIONS.items():
        if city_in(city, names):
            return code
    return None


def open_browser(parser_cfg_name="KATOTEKA"):
    from .uc_browser import get_browser
    driver = get_browser(ROOT, PROFILE, parser_cfg_name)
    driver.set_script_timeout(60)
    return driver


def load_page(driver, path):
    """Страница katoteka. Проверка вместо страницы — это 403: её проходят руками."""
    global LAST_HTTP_STATUS
    driver.get(BASE_URL + path)
    time.sleep(3)
    html = driver.page_source
    if CHALLENGE_MARK in html:
        LAST_HTTP_STATUS = 403
        raise ChallengeRequired("Ошибка 403: katoteka просит пройти проверку — "
                                "запусти python -m parsers_core.katoteka и нажми нужный цвет")
    if "Страница не найдена" in html or "404 Not Found" in html:
        LAST_HTTP_STATUS = 404
        raise RuntimeError(f"Ошибка 404: {BASE_URL + path}")
    LAST_HTTP_STATUS = 200
    return html


def fetch_file(driver, url):
    """Картинку качаем изнутри браузера: запрос без его cookies антибот считает ошибкой и банит IP."""
    data = driver.execute_async_script(FETCH_JS, url)
    if not data or data.startswith("ERR"):
        return None
    return base64.b64decode(data.split(",", 1)[1])


def region_codes(html, slug):
    return set(re.findall(r'href="https://katoteka\.ru/' + re.escape(slug) + r'/([a-z\-]+)/"', html))


def period(html):
    soup = BeautifulSoup(html, "html.parser")
    node = soup.select_one(".period .dates")
    return node.get_text(" ", strip=True) if node else ""


def catalog_images(html, slug):
    """Страницы листовки текущего каталога (без превью других сетей и обложек-заглушек 0.jpg)."""
    soup = BeautifulSoup(html, "html.parser")
    urls = []
    for img in soup.find_all("img"):
        src = img.get("src") or ""
        if f"catalogs/{slug}/" not in src or re.search(r"/0\.jpe?g", src):
            continue
        url = BASE_URL + "/" + src.lstrip("./").lstrip("/")
        if url not in urls:
            urls.append(url)
    return urls


def _price(node, rub_cls, kop_cls):
    if node is None:
        return None
    rub = node.select_one("." + rub_cls)
    kop = node.select_one("." + kop_cls)
    rub_txt = re.sub(r"\D", "", rub.get_text()) if rub else ""
    kop_txt = re.sub(r"\D", "", kop.get_text()) if kop else "00"
    if not rub_txt:
        return None
    value = float(f"{int(rub_txt)}.{(kop_txt or '00')[:2].ljust(2, '0')}")
    return value if value > 0 else None


def product_tiles(html):
    """Каталоги-плитки (Мария-Ра, Фикс Прайс): название, цена и старая цена лежат в HTML."""
    soup = BeautifulSoup(html, "html.parser")
    items = []
    for prod in soup.select("div.product"):
        title = prod.select_one(".titleProd")
        name = title.get_text(" ", strip=True) if title else ""
        price = _price(prod.select_one(".priceNew"), "rubNew", "kopNew")
        old = _price(prod.select_one(".priceOld"), "rubOld", "kopOld")
        img = prod.select_one(".imageProd img")
        photo = BASE_URL + "/" + img["src"].lstrip("./").lstrip("/") if img and img.get("src") else ""
        if name and price:
            items.append({"name": name, "price": price, "old_price": old, "photo": photo})
    return items


def match_queries(name, queries):
    """Товар подходит, если в названии есть все слова запроса (по началу слова: «кефир» ~ «кефирный»)."""
    low = (name or "").lower().replace("ё", "е")
    for q in queries:
        words = [w for w in re.split(r"\W+", q.lower().replace("ё", "е")) if w]
        if words and all(w[:max(4, len(w) - 2)] in low for w in words):
            return True
    return False


def _flyer_items(driver, html, slug, profile, debug_dir=None, tag=""):
    import tempfile
    from image_parser_service.flyer_page_ocr import parse_flyer_images
    with tempfile.TemporaryDirectory() as tmp:
        pages = []
        for i, url in enumerate(catalog_images(html, slug), 1):
            raw = fetch_file(driver, url)
            if not raw:
                continue
            path = os.path.join(debug_dir or tmp, f"{slug}{tag}_{i:03d}.jpg")
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as f:
                f.write(raw)
            pages.append((url, path))
            time.sleep(0.5)
        results = parse_flyer_images([p for _, p in pages], profile)
    items = []
    for (url, _), page_items in zip(pages, results):
        for it in page_items:
            it["photo"] = url
            items.append(it)
    return items


def save_full_screenshot(driver, path):
    """Скриншот всей страницы для ручной сверки. Снимаем кусками и склеиваем:
    одним кадром страница в 20 000 px роняет Chrome."""
    import io
    from PIL import Image
    try:
        width, height = driver.execute_script(
            "return [document.documentElement.scrollWidth, document.documentElement.scrollHeight]")
        step = 3000
        parts = []
        for y in range(0, height, step):
            clip = {"x": 0, "y": y, "width": width, "height": min(step, height - y), "scale": 1}
            data = driver.execute_cdp_cmd("Page.captureScreenshot",
                                          {"format": "png", "captureBeyondViewport": True, "clip": clip})
            parts.append(Image.open(io.BytesIO(base64.b64decode(data["data"]))).convert("RGB"))
        sheet = Image.new("RGB", (max(p.width for p in parts), sum(p.height for p in parts)), "white")
        top = 0
        for p in parts:
            sheet.paste(p, (0, top))
            top += p.height
        os.makedirs(os.path.dirname(path), exist_ok=True)
        sheet.save(path)
    except Exception as e:
        print(f"Скриншот не сохранён: {e}")


def collect_catalog(shop_name, slug, served=None, regional=False, flyer_profile=None, debug_dir=None,
                    photos=True):
    """Строки по ТЗ из каталога katoteka для городов из config.

    served — коды регионов сети (None — работает везде); regional — у сети свои каталоги по регионам;
    flyer_profile — каталог картинками (OCR), иначе плитки с ценами в HTML;
    photos=False — у сети на katoteka картинки перепутаны с товарами, фото не отдаём.
    """
    import config
    from .exceptions import NoShopsError
    from .normalize import split_name_measure, split_regular_promo
    from .rows import make_row, number_rows
    from .utils import update_retail_points

    cities = getattr(config, "cities", []) or []
    queries = list(getattr(config, "search_req", []) or []) or list(getattr(config, "brand", []) or [])

    all_data, no_shops, by_page = [], [], {}
    driver = open_browser()
    try:
        main_html = load_page(driver, f"/{slug}/")
        if regional:
            served = region_codes(main_html, slug)
        for city in cities:
            region = city_region(city)
            if served is not None and region not in served:
                print(f"[{shop_name}] Ошибка 999. Город '{city}' не обслуживается сетью.")
                no_shops.append(city)
                continue
            path = f"/{slug}/{region}/" if regional else f"/{slug}/"
            if path not in by_page:
                html = main_html if path == f"/{slug}/" else load_page(driver, path)
                print(f"[{shop_name}] Каталог {path}: {period(html) or 'период не указан'}")
                tag = f"_{region}" if regional else ""
                if flyer_profile is not None:
                    by_page[path] = _flyer_items(driver, html, slug, flyer_profile, debug_dir, tag)
                else:
                    by_page[path] = product_tiles(html)
                    if debug_dir:
                        save_full_screenshot(driver, os.path.join(debug_dir, f"{slug}{tag}_page.png"))
                print(f"[{shop_name}] Позиций в каталоге: {len(by_page[path])}")
            items = by_page[path]
            if queries:
                items = [it for it in items if match_queries(it["name"], queries)]
                for q in queries:
                    if not any(match_queries(it["name"], [q]) for it in items):
                        print(f"[{shop_name}] По запросу '{q}' ничего не найдено.")
            for it in items:
                regular, promo = split_regular_promo(it["price"], it.get("old_price"))
                name, volume, weight = split_name_measure(it["name"])
                row = make_row(shop_name, city, name, regular, store_type="Магазин", promo_price=promo,
                               photo=it.get("photo") if photos else "", url=BASE_URL + path, volume=volume, weight=weight,
                               stock="1")
                if row:
                    all_data.append(row)
            try:
                update_retail_points(shop_name, city, 1)
            except Exception:
                pass
    finally:
        driver.quit()

    if not all_data and no_shops and len(no_shops) == len(cities):
        raise NoShopsError(parser_name=shop_name, city=", ".join(no_shops))
    return number_rows(all_data)


def pass_challenge(timeout=600):
    """Открывает katoteka в окне и ждёт, пока человек пройдёт проверку."""
    driver = open_browser()
    try:
        driver.get(BASE_URL + "/mon/")
        deadline = time.time() + timeout
        while time.time() < deadline and CHALLENGE_MARK in driver.page_source:
            time.sleep(2)
        ok = CHALLENGE_MARK not in driver.page_source
        print("Проверка пройдена, cookies сохранены в профиле" if ok else "Проверка не пройдена")
        return ok
    finally:
        driver.quit()


if __name__ == "__main__":
    pass_challenge()
