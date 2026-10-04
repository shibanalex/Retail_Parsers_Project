# -*- coding: utf-8 -*-
import os
import re

import pytesseract
from PIL import Image, ImageFilter, ImageOps

from . import ocr_setup

SUPPORTED_FORMATS = {"JPEG", "PNG"}

_OCR_CFG = ocr_setup.resolve(require_rus=False)
if _OCR_CFG:
    pytesseract.pytesseract.tesseract_cmd = _OCR_CFG["cmd"]
    os.environ["TESSDATA_PREFIX"] = _OCR_CFG["tessdata"]


def collect_images(source):
    if isinstance(source, (list, tuple)):
        return [str(p) for p in source]
    if os.path.isdir(source):
        paths = []
        for name in sorted(os.listdir(source)):
            ext = os.path.splitext(name)[1].lower()
            if ext in (".jpg", ".jpeg", ".png"):
                paths.append(os.path.join(source, name))
        return paths
    if os.path.isfile(source):
        return [source]
    return []


def detect_format(path):
    try:
        with Image.open(path) as img:
            return img.format
    except Exception:
        return None


def preprocess(img):
    img = img.convert("L")
    img = ImageOps.autocontrast(img)
    if img.width < 900:
        scale = 1800 / img.width
        img = img.resize((int(img.width * scale), int(img.height * scale)), Image.LANCZOS)
    return img.filter(ImageFilter.SHARPEN)


def ocr_image(path):
    if _OCR_CFG is None:
        raise RuntimeError("Tesseract не настроен — запусти: python -m image_parser_service.ocr_setup")
    with Image.open(path) as img:
        processed = preprocess(img)
        return pytesseract.image_to_string(processed, lang=_OCR_CFG["lang"])


_PRICE_TAGGED_RE = re.compile(r'(\d[\d\s]{0,7}[.,]\d{2})\s*(?:₽|руб|р\.)', re.IGNORECASE)
_PRICE_BARE_RE = re.compile(r'\b(\d[\d\s]{0,7}[.,]\d{2})\b')


def extract_price(text):
    m = _PRICE_TAGGED_RE.search(text)
    if not m:
        m = _PRICE_BARE_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace(" ", "").replace(",", ".")
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


_VOL_RE = re.compile(r'(\d+[.,]?\d*)\s*(мл|л|кг|г)(?![а-яёa-z])', re.IGNORECASE)
_OCR_UNIT_FIX_RE = re.compile(r'(?<=\d)\s*[nlNL](?![а-яёa-zA-Z])')


def extract_measure(text):
    text = _OCR_UNIT_FIX_RE.sub(' л', text)
    m = _VOL_RE.search(text)
    if not m:
        return "", ""
    value = m.group(1).replace(",", ".")
    unit = m.group(2).lower()
    if unit in ("л", "мл"):
        return f"{value} {unit}", ""
    return "", f"{value} {unit}"


def extract_brand(text, known_brands):
    lowered = text.lower()
    for brand in known_brands:
        cleaned = brand.strip()
        if cleaned and cleaned.lower() in lowered:
            return cleaned
    return ""


def extract_name(text):
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    candidates = []
    for line in lines:
        stripped = _PRICE_TAGGED_RE.sub("", line)
        stripped = _PRICE_BARE_RE.sub("", stripped)
        stripped = stripped.replace("₽", "").strip(" .,:;-")
        if len(stripped) >= 3 and not stripped.replace(" ", "").isdigit():
            candidates.append(stripped)
    if not candidates:
        return ""
    candidates.sort(key=len, reverse=True)
    return re.sub(r'\s{2,}', ' ', candidates[0])
