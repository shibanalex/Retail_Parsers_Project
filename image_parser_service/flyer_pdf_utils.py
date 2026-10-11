# -*- coding: utf-8 -*-
import re

import pypdf
import pypdfium2 as pdfium

from . import image_parser_utils

MIN_TEXT_LEN = 30

_SKU_LINE_RE = re.compile(r'^[\d/]{3,}$')
_OLDPRICE_RE = re.compile(r'^(\d{3,})\s*(\d{1,2})%$')
_VOL_RE = re.compile(r'(\d+[.,]?\d*)\s*(мл|л|кг|г)(?![а-яёa-z])', re.IGNORECASE)
_FOOTNOTE_LINE_RE = re.compile(
    r'^\*|^\d+\*?$|^\d{3,}\s+\d+\+\d+$|^(ЦЕНА|ШТ\.?|одновременно\.?)\b',
    re.IGNORECASE,
)


def _is_footnote_line(line):
    return bool(_FOOTNOTE_LINE_RE.match(line))


_JUNK_NAME_RE = re.compile(r'^\d|ЦЕНА\s+(ОТ|ЗА)\s+\d|^ШТ\.', re.IGNORECASE)


def _is_junk_name(name):
    return bool(_JUNK_NAME_RE.search(name))


def _looks_like_brand(seg):
    seg = seg.strip()
    if len(seg) < 3 or not seg[0].isupper():
        return False
    if seg.isupper() and len(seg) <= 5:
        return False
    return True


def _extract_measure(text):
    m = _VOL_RE.search(text)
    if not m:
        return "", ""
    value = m.group(1).replace(",", ".")
    unit = m.group(2).lower()
    if unit in ("л", "мл"):
        return f"{value} {unit}", ""
    return "", f"{value} {unit}"


def parse_flyer_page(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    items = []
    name_buf = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        if _SKU_LINE_RE.match(line):
            sku = line
            rub = lines[i + 1] if i + 1 < n and lines[i + 1].isdigit() else None
            kop = None
            if rub is not None and i + 2 < n and lines[i + 2].isdigit() and len(lines[i + 2]) <= 2:
                kop = lines[i + 2]
            consumed = 3 if kop is not None else (2 if rub is not None else 1)

            old_price = None
            discount = None
            if kop is not None and i + 3 < n:
                m = _OLDPRICE_RE.match(lines[i + 3])
                if m:
                    digits = m.group(1)
                    old_price = float(f"{digits[:-2]}.{digits[-2:]}")
                    discount = m.group(2)
                    consumed += 1

            full_name = " ".join(name_buf).strip()
            full_name = re.sub(r'^\d{3,}\s*\d{1,2}%\s*', '', full_name)
            name_buf = []

            clean_name = re.sub(r'\s{2,}', ' ', full_name).strip(" ,;")
            if rub is not None and len(clean_name) >= 3 and not _is_junk_name(clean_name):
                parts = [p.strip() for p in full_name.split(",")]
                brand = ""
                if len(parts) >= 3 and _looks_like_brand(parts[-2]):
                    brand = parts[-2]
                volume, weight = _extract_measure(full_name)
                items.append({
                    "name": clean_name,
                    "brand": brand,
                    "sku": sku,
                    "price": float(f"{rub}.{kop or '00'}"),
                    "old_price": old_price,
                    "discount": discount,
                    "volume": volume,
                    "weight": weight,
                })
            i += consumed
        else:
            if not _is_footnote_line(line):
                name_buf.append(line)
            i += 1
    return items


def _parse_scanned_page(doc, page_index, debug_dir=None):
    page = doc[page_index]
    bitmap = page.render(scale=2.0)
    img = bitmap.to_pil()
    processed = image_parser_utils.preprocess(img)
    cfg = image_parser_utils._OCR_CFG
    if cfg is None:
        return []
    import pytesseract
    text = pytesseract.image_to_string(processed, lang=cfg["lang"])
    if debug_dir:
        import os
        os.makedirs(debug_dir, exist_ok=True)
        with open(os.path.join(debug_dir, f"pdf_page{page_index + 1}_ocr.txt"), "w", encoding="utf-8") as f:
            f.write(text)
    price = image_parser_utils.extract_price(text)
    name = image_parser_utils.extract_name(text)
    if price is None or not name:
        return []
    volume, weight = _extract_measure(text)
    return [{
        "name": name, "brand": "", "sku": "", "price": price,
        "old_price": None, "discount": None, "volume": volume, "weight": weight,
    }]


def parse_flyer_pdf(path, debug_dir=None):
    reader = pypdf.PdfReader(path)
    doc = pdfium.PdfDocument(path)
    items = []
    for i, page in enumerate(reader.pages):
        text = page.extract_text() or ""
        if len(text.strip()) >= MIN_TEXT_LEN:
            page_items = parse_flyer_page(text)
        else:
            page_items = _parse_scanned_page(doc, i, debug_dir=debug_dir)
        items.extend(page_items)
    return items
