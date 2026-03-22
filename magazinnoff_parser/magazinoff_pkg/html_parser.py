import re
from bs4 import BeautifulSoup

BASE_URL = "https://www.magazinnoff.ru"

def transliterate_city(city_name):
    symbols = {
        'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
        'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
        'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
        'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'shch',
        'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        ' ': '-', '-': '-'
    }
    result = ''.join(symbols.get(c, c) for c in city_name.lower())
    return re.sub(r'-+', '-', result).strip('-')

def parse_stores(html, city_name, target_names=None):
    soup = BeautifulSoup(html, "lxml")
    found_stores = {}

    for a in soup.find_all("a", href=True):
        href = a.get("href", "")
        if href.startswith("/magazin/"):
            parts = href.split("/")
            if len(parts) >= 3:
                store_slug = parts[2]
                if store_slug in ["search", "map"]: continue

                name_tag = a.find("h3")
                raw_name = name_tag.text.strip() if name_tag else store_slug.capitalize()

                clean_name = re.sub(r'(?i)^акции\s+', '', raw_name)
                clean_name = re.sub(rf'(?i)\s+в\s+{re.escape(city_name)}', '', clean_name)
                clean_name = re.sub(rf'(?i)\s+{re.escape(city_name)}$', '', clean_name).strip()

                if target_names:
                    matched = False
                    for target in target_names:
                        if target.lower() in clean_name.lower() or target.lower() in raw_name.lower():
                            found_stores[store_slug] = target
                            matched = True
                            break
                    if not matched:
                        continue
                else:
                    found_stores[store_slug] = clean_name

    return found_stores

def parse_search_results(html, store_name):
    soup = BeautifulSoup(html, "lxml")
    items = []

    if "Ничего не найдено" in soup.text:
        return []

    cards = soup.find_all("div", class_="strip")
    if not cards:
        cards = soup.find_all("div", class_="item")

    for s in cards:
        try:
            t_tag = s.find("div", class_="item_title")
            name = t_tag.find("h3").text.strip() if t_tag and t_tag.find("h3") else "Unknown"

            price = None
            p_span = s.find("span", style=lambda x: x and "16px" in x)
            if not p_span:
                p_text = s.find(string=re.compile(r"\d+[\.,]\d{2}"))
                if p_text: p_span = p_text.parent

            if p_span:
                clean_price = re.sub(r"[^\d.,]", "", p_span.text).replace(",", ".")
                if clean_price: price = float(clean_price)

            l_tag = s.find("a", class_="strip_info")
            link = BASE_URL + l_tag.get("href") if l_tag else None

            img_tag = s.find("img")
            img = None
            if img_tag:
                img = img_tag.get("data-src") or img_tag.get("src")
                if img and not img.startswith("http"): img = BASE_URL + img

            items.append({
                "name": name, "price": price, "store": store_name,
                "link": link, "img": img
            })
        except:
            continue
    return items

def parse_product_details(html, name_fallback):
    soup = BeautifulSoup(html, "lxml")
    specs = {}

    container = soup.find("div", attrs={"itemprop": "description"})
    if container:
        cols = container.find_all("div", class_="col-6")
        for i in range(0, len(cols) - 1, 2):
            k = cols[i].get_text(strip=True).lower().rstrip(":")
            v = cols[i + 1].get_text(strip=True)
            specs[k] = v

    brand = specs.get("бренд") or specs.get("производитель") or specs.get("торговая марка")
    weight = specs.get("вес") or specs.get("масса") or specs.get("масса нетто")
    volume = specs.get("объем") or specs.get("объём") or specs.get("емкость")

    exact_price = None
    price_tag = soup.find(attrs={"itemprop": "price"})
    if price_tag and price_tag.has_attr('content'):
        try:
            exact_price = float(price_tag['content'])
        except:
            pass

    if not weight and not volume:
        finds = re.findall(r"(\d+(?:[.,]\d+)?\s*(?:г|кг|мл|л|шт))", name_fallback.lower())
        if finds:
            ext = finds[-1]
            if any(x in ext for x in ["мл", "л"]):
                volume = ext
            else:
                weight = ext

    category = None
    breadcrumbs_div = soup.find("div", class_="breadcrumbs")
    if breadcrumbs_div:
        name_spans = breadcrumbs_div.find_all("span", attrs={"itemprop": "name"})
        if name_spans and len(name_spans) >= 2:
            category = name_spans[-2].get_text(strip=True)

    return brand, weight, volume, exact_price, category