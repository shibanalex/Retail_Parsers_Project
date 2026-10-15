# -*- coding: utf-8 -*-
import re

_MEASURE_RE = re.compile(r'(\d+[.,]?\d*)\s*(мл|л|кг|г)(?![а-яёa-z])', re.IGNORECASE)
_SPACES_RE = re.compile(r'\s{2,}')
_LIQUID = ("л", "мл")
_SOLID = ("г", "кг")


def to_price(raw):
    """'1 299,90 ₽' -> 1299.9. Ноль и мусор -> None."""
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw) if raw > 0 else None
    s = str(raw).replace("\xa0", "").replace(" ", "")
    s = re.sub(r'(?i)(руб\.?|р\.|₽|от|за)', "", s)
    s = "".join(ch for ch in s if ch.isdigit() or ch in ",.")
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    elif s.count(",") and s.count("."):
        s = s.replace(",", "")
    try:
        value = float(s)
    except ValueError:
        return None
    return value if value > 0 else None


def clean_text(text):
    return _SPACES_RE.sub(" ", (text or "").replace("\xa0", " ")).strip(" ,;")


def norm_measure(value):
    v = (value or "").replace(",", ".").strip()
    unit = v.split()[-1].lower() if v else ""
    if unit in _LIQUID:
        return v, ""
    if unit in _SOLID:
        return "", v
    return "", ""


def split_name_measure(name):
    """'Вино красное 0,75 л' -> ('Вино красное', '0.75 л', '')."""
    name = name or ""
    m = _MEASURE_RE.search(name)
    if not m:
        return clean_text(name), "", ""
    measure = f"{m.group(1).replace(',', '.')} {m.group(2).lower()}"
    rest = clean_text(re.sub(r"\s*,(\s*,)+", ",", name[:m.start()] + " " + name[m.end():]))
    if m.group(2).lower() in _LIQUID:
        return rest, measure, ""
    return rest, "", measure


def split_regular_promo(current, old):
    """Есть зачёркнутая цена — она идёт в «Цена», текущая в «Цена по акции»."""
    if current is None:
        return None, 0.0
    if old is not None and old > current:
        return float(old), float(current)
    return float(current), 0.0
