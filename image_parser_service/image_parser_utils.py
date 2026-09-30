# -*- coding: utf-8 -*-
import os
import re

import pytesseract
from PIL import Image, ImageFilter, ImageOps

SUPPORTED_FORMATS = {"JPEG", "PNG"}

_TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
]
for _path in _TESSERACT_CANDIDATES:
    if os.path.exists(_path):
        pytesseract.pytesseract.tesseract_cmd = _path
        break


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
    with Image.open(path) as img:
        processed = preprocess(img)
        return pytesseract.image_to_string(processed, lang="rus+eng")


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
