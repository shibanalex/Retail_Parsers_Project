# -*- coding: utf-8 -*-
ROW_KEYS = (
    "Сеть", "Тип магазина", "Адрес Торговой точки", "Бренд", "Название продукта",
    "Цена", "Цена по акции", "Фото товара", "Ссылка на страницу", "Рейтинг",
    "Объем", "Вес", "Остаток", "Категория",
)

FORBIDDEN_SUFFIXES = ("_source", "_timestamp")


def make_row(retail, address, name, price, *, store_type="", brand="", promo_price=0.0,
             photo="", url="", rating=0.0, volume="", weight="", stock="1",
             category="", extra=None):
    """Строка результата по ТЗ. Без цены или названия — None, такие строки пропускаем."""
    if price is None:
        return None
    try:
        price = float(price)
    except (TypeError, ValueError):
        return None
    if price <= 0 or not (name or "").strip():
        return None
    try:
        promo = float(promo_price or 0)
    except (TypeError, ValueError):
        promo = 0.0
    try:
        rating_value = float(rating or 0)
    except (TypeError, ValueError):
        rating_value = 0.0
    if isinstance(stock, bool):
        stock = "1" if stock else "0"
    row = {
        "Сеть": retail,
        "Тип магазина": store_type,
        "Адрес Торговой точки": address,
        "Бренд": brand or "",
        "Название продукта": name.strip(),
        "Цена": price,
        "Цена по акции": promo,
        "Фото товара": photo or "",
        "Ссылка на страницу": url or "",
        "Рейтинг": rating_value,
        "Объем": volume or "",
        "Вес": weight or "",
        "Остаток": str(stock) if stock is not None else "",
        "Категория": category or "",
    }
    for key, value in (extra or {}).items():
        if key.startswith("_") or key.endswith(FORBIDDEN_SUFFIXES) or "normalized" in key:
            continue
        row[key] = value
    return row


def number_rows(rows):
    for idx, row in enumerate(rows, 1):
        row["Номер"] = idx
    return rows


def uniform_keys(rows):
    keys = []
    for row in rows:
        for k in row:
            if k not in keys:
                keys.append(k)
    for row in rows:
        for k in keys:
            row.setdefault(k, "")
    return rows
