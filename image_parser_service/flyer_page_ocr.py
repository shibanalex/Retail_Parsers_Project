# -*- coding: utf-8 -*-
"""Разбор страницы листовки-картинки: ценник ищем по цвету плашки, название — рядом с ней."""
import re

import cv2
import numpy as np
import pytesseract

from . import image_parser_utils

DIGITS_WL = "-c tessedit_char_whitelist=0123456789"
_CYR_WORD_RE = re.compile(r"[А-Яа-яЁё]{3,}")
_TEXT_RE = re.compile(r"[A-Za-zА-Яа-яЁё]{2,}|\d\s*(г|кг|мл|л|шт)(?![а-яё])", re.IGNORECASE)
_JUNK_RE = re.compile(r"цена\s+по\s+карте\*?|наше(го)?\s+производств[оа]|супер\s+цена", re.IGNORECASE)
_DISCOUNT_HSV = ((150, 60, 120), (179, 255, 255))


class FlyerProfile:
    """Как выглядит ценник сети: цвета плашки (HSV) и где название — над ней или под ней."""

    def __init__(self, badge_hsv, name_side="below", min_fill=0.6, close=5, lang=None, drop_upper=False,
                 refine=False, dark_text=False):
        self.badge_hsv = badge_hsv
        self.name_side = name_side
        self.min_fill = min_fill
        # Чем крупнее цифры на плашке, тем больше ядро, чтобы закрыть дыры от них
        self.close = close
        # Если в названиях нет латиницы, «rus» не путает «г» с «r» и «Молоко» с «Monoko»
        self.lang = lang
        # Строки капслоком — надписи-плашки («НАШЕ ПРОИЗВОДСТВО»), а не названия
        self.drop_upper = drop_upper
        # Перечитывать каждую подпись отдельно (дольше, но фото рядом не портят текст)
        self.refine = refine
        self.dark_text = dark_text


def _lang(profile=None):
    cfg = image_parser_utils._OCR_CFG
    if cfg is None:
        raise RuntimeError("Tesseract не настроен — запусти: python -m image_parser_service.ocr_setup")
    return profile.lang if profile is not None and profile.lang else cfg["lang"]


def _text_scale(img):
    """Мелкие листовки (900 px) увеличиваем, крупные (PDF 2400 px) оставляем как есть."""
    return min(3.0, max(1.0, 2700.0 / img.shape[1]))


def find_badges(img, profile):
    H, W = img.shape[:2]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    boxes = []
    for lo, hi in profile.badge_hsv:
        mask = cv2.inRange(hsv, np.array(lo), np.array(hi))
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((profile.close, profile.close), np.uint8))
        # Срезаем тонкие контуры упаковок, которые склеиваются с плашкой
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((9, 9), np.uint8))
        cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        for c in cnts:
            x, y, w, h = cv2.boundingRect(c)
            if w < W * 0.06 or h < 30 or w > W * 0.6:
                continue
            if cv2.contourArea(c) / float(w * h) < profile.min_fill:
                continue
            boxes.append((x, y, w, h))
    return sorted(boxes, key=lambda b: (b[1] // 40, b[0]))


def _ink_components(crop):
    lab = cv2.cvtColor(crop, cv2.COLOR_BGR2LAB).astype(np.int16)
    bg = np.median(lab.reshape(-1, 3), axis=0)
    ink = (np.sqrt(((lab - bg) ** 2).sum(axis=2)) > 60).astype(np.uint8) * 255
    n, labels, stats, _ = cv2.connectedComponentsWithStats(ink, 8)
    ch, cw = ink.shape
    comps = []
    for i in range(1, n):
        x, y, w, h, area = stats[i]
        if area < 30 or h < ch * 0.06:
            continue
        # Края вырезки — это соседние плашки (скидка) и рамки, а не цифры
        if x <= 1 or y <= 1 or x + w >= cw - 1 or y + h >= ch - 1:
            continue
        comps.append((x, y, w, h, i))
    return labels, comps


def _ocr_glyphs(labels, group):
    x0 = min(c[0] for c in group)
    y0 = min(c[1] for c in group)
    x1 = max(c[0] + c[2] for c in group)
    y1 = max(c[1] + c[3] for c in group)
    sub = np.zeros((y1 - y0, x1 - x0), np.uint8)
    for x, y, w, h, lbl in group:
        sub[y - y0:y - y0 + h, x - x0:x - x0 + w] |= (labels[y:y + h, x:x + w] == lbl).astype(np.uint8) * 255
    sub = cv2.copyMakeBorder(255 - sub, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
    # Один режим Tesseract иногда читает «99» как «00»: берём самый частый ответ нескольких прогонов
    votes = {}
    for target, psm in ((90, 7), (60, 7), (90, 8)):
        scale = target / sub.shape[0]
        inter = cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA
        big = cv2.resize(sub, None, fx=scale, fy=scale, interpolation=inter)
        txt = pytesseract.image_to_string(big, config=f"--psm {psm} {DIGITS_WL}").strip()
        if txt.isdigit():
            votes[txt] = votes.get(txt, 0) + 1
    return max(votes, key=votes.get) if votes else ""


def _chain(seed, comps, min_h):
    """Глифы одной строки цены: похожая высота, та же строка, идут подряд."""
    mid = seed[1] + seed[3] * 0.5
    row = sorted((c for c in comps if c[3] >= min_h and c[1] < mid < c[1] + c[3]), key=lambda c: c[0])
    i = row.index(seed)
    group = [seed]
    gap = seed[3] * 0.6
    for c in row[i + 1:]:
        if c[0] - (group[-1][0] + group[-1][2]) > gap:
            break
        group.append(c)
    for c in reversed(row[:i]):
        if group[0][0] - (c[0] + c[2]) > gap:
            break
        group.insert(0, c)
    return group


def _superscript(base, comps, base_h):
    """Копейки: мелкие глифы сразу справа от рублей, верх на уровне их верха (звёздочки и сноски — мимо)."""
    right = max(c[0] + c[2] for c in base)
    top = min(c[1] for c in base)
    cands = sorted((c for c in comps if c not in base and base_h * 0.25 <= c[3] < base_h * 0.75
                    and c[0] >= right - 5 and abs(c[1] - top) <= base_h * 0.35), key=lambda c: c[0])
    group = []
    edge = right
    for c in cands:
        if c[0] - edge > base_h * 0.6:
            break
        group.append(c)
        edge = c[0] + c[2]
    return group


def _to_price(rub, kop):
    if not rub.isdigit() or len(rub) > 5:
        return None
    if len(kop) != 2 or not kop.isdigit():
        kop = "00"
    value = float(f"{int(rub)}.{kop}")
    return value if value > 0 else None


def read_badge(img, box):
    """Цена с плашки: крупные рубли + мелкие копейки справа сверху. Ниже — старая цена, если есть."""
    x, y, w, h = box
    scale = min(3.0, max(1.0, 220.0 / h))
    crop = cv2.resize(img[y:y + h, x:x + w], None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    labels, comps = _ink_components(crop)
    if not comps:
        return None, None
    seed = max(comps, key=lambda c: c[3])
    rub = _chain(seed, comps, seed[3] * 0.7)
    rub_bottom = max(c[1] + c[3] for c in rub)
    kop = _superscript(rub, comps, seed[3])
    price = _to_price(_ocr_glyphs(labels, rub), _ocr_glyphs(labels, kop) if kop else "")

    old = None
    below = [c for c in comps if c[1] + c[3] / 2 > rub_bottom and seed[3] * 0.25 <= c[3] < seed[3] * 0.8]
    if below:
        old_seed = max(below, key=lambda c: c[3])
        old_rub = _chain(old_seed, below, old_seed[3] * 0.7)
        old_kop = _superscript(old_rub, comps, old_seed[3])
        old = _to_price(_ocr_glyphs(labels, old_rub), _ocr_glyphs(labels, old_kop) if old_kop else "")
        if old is not None and price is not None and not (price < old < price * 4):
            old = None
    return price, old


def read_discount(img, box):
    """Процент с розовой плашки скидки у правого нижнего угла ценника («-24%»)."""
    x, y, w, h = box
    H, W = img.shape[:2]
    x0, y0 = max(0, x + w // 3), max(0, y + h // 2)
    x1, y1 = min(W, x + w + w // 2), min(H, y + h + h // 2)
    area = img[y0:y1, x0:x1]
    if area.size == 0:
        return None
    hsv = cv2.cvtColor(area, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, np.array(_DISCOUNT_HSV[0]), np.array(_DISCOUNT_HSV[1]))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
    cnts, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    cnts = [c for c in cnts if cv2.contourArea(c) > (h * h) * 0.05]
    if not cnts:
        return None
    bx, by, bw, bh = cv2.boundingRect(max(cnts, key=cv2.contourArea))
    sub = area[by:by + bh, bx:bx + bw]
    scale = min(4.0, max(1.0, 120.0 / bh))
    sub = cv2.resize(sub, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    labels, comps = _ink_components(sub)
    if not comps:
        return None
    seed = max(comps, key=lambda c: c[3])
    txt = _ocr_glyphs(labels, _chain(seed, comps, seed[3] * 0.7))
    if txt.isdigit() and 1 <= int(txt) <= 90:
        return int(txt)
    return None


def _check_old(price, old, discount):
    """Зачёркивающая линия портит цифры старой цены: сверяем её со скидкой с соседней плашки."""
    if old is None or discount is None or price is None:
        return old
    expected = price / (1 - discount / 100.0)
    return old if abs(old - expected) / expected < 0.06 else None


def _rows(badges):
    rows = []
    for box in sorted(badges, key=lambda b: b[1] + b[3] / 2):
        cy = box[1] + box[3] / 2
        if rows and abs(cy - rows[-1][0]) < box[3] * 0.6:
            rows[-1][1].append(box)
        else:
            rows.append([cy, [box]])
    return [r[1] for r in rows]


def _text_layer(part, profile=None):
    """Серое изображение для OCR. dark_text: оставляем только почти чёрный текст, цветные упаковки уходят."""
    if profile is not None and profile.dark_text:
        hsv = cv2.cvtColor(part, cv2.COLOR_BGR2HSV)
        dark = (hsv[:, :, 2] < 120) & (hsv[:, :, 1] < 150)
        return np.where(dark, 0, 255).astype(np.uint8)
    return cv2.cvtColor(part, cv2.COLOR_BGR2GRAY)


def _segments(img, y0, y1, profile=None):
    """Строки текста полосы, разрезанные по большим пробелам: колонки листовки не склеиваются."""
    if y1 - y0 < 10:
        return []
    k = _text_scale(img)
    band = _text_layer(img[y0:y1], profile)
    if k > 1:
        band = cv2.resize(band, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    d = pytesseract.image_to_data(band, lang=_lang(profile), config="--psm 6", output_type=pytesseract.Output.DICT)
    lines = {}
    for i, word in enumerate(d["text"]):
        word = word.strip()
        if not word or float(d["conf"][i]) < 30:
            continue
        key = (d["block_num"][i], d["par_num"][i], d["line_num"][i])
        lines.setdefault(key, []).append((d["left"][i] / k, d["top"][i] / k + y0,
                                          d["width"][i] / k, d["height"][i] / k, word))
    out = []
    for words in lines.values():
        words.sort()
        cur = [words[0]]
        for w in words[1:]:
            prev = cur[-1]
            if w[0] - (prev[0] + prev[2]) > max(prev[3], w[3]) * 2.5:
                out.append(cur)
                cur = [w]
            else:
                cur.append(w)
        out.append(cur)
    return [(min(w[0] for w in seg), max(w[0] + w[2] for w in seg), min(w[1] for w in seg),
             " ".join(w[4] for w in seg), max(w[1] + w[3] for w in seg)) for seg in out]


def _ocr_block(img, box, profile=None):
    """Перечитываем подпись по её точной рамке: на полосе целиком мешают соседние фото."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = box
    pad = int(6 * max(1.0, W / 900.0))
    crop = img[max(0, int(y0) - pad):min(H, int(y1) + pad), max(0, int(x0) - pad):min(W, int(x1) + pad)]
    if crop.size == 0:
        return ""
    gray = _text_layer(crop, profile)
    k = _text_scale(img)
    if k > 1:
        gray = cv2.resize(gray, None, fx=k, fy=k, interpolation=cv2.INTER_CUBIC)
    text = pytesseract.image_to_string(gray, lang=_lang(profile), config="--psm 6")
    return " ".join(line.strip() for line in text.splitlines() if _CYR_WORD_RE.search(line) or re.search(r"\d", line))


def _is_upper_label(text):
    letters = [ch for ch in text if ch.isalpha()]
    return len(letters) >= 4 and sum(ch.isupper() for ch in letters) / len(letters) > 0.8


_DIGIT_LOOKALIKE = str.maketrans({"З": "3", "з": "3", "Э": "9", "э": "9", "О": "0", "о": "0", "Б": "6", "l": "1", "I": "1"})
_MEASURE_TOKEN_RE = re.compile(r"(?<![А-Яа-яЁёA-Za-z])([\dЗзЭэОоБlI][\dЗзЭэОоБlI,.]*)\s*(мл|мп|г|кг|л|шт)(?![а-яё])", re.IGNORECASE)


def _fix_measure(m):
    """В объёме OCR путает цифры с буквами: «ЭООмл» — это 900 мл, «З0Ог» — 300 г."""
    num = m.group(1).translate(_DIGIT_LOOKALIKE)
    if not re.search(r"\d", m.group(1)) and len(num) < 2:
        return m.group(0)
    unit = m.group(2).lower().replace("мп", "мл")
    return f"{num}{unit}"


def _clean_name(parts):
    text = _JUNK_RE.sub(" ", " ".join(parts))
    text = re.sub(r"(\d)\s*r\b", r"\1г", text)
    text = _MEASURE_TOKEN_RE.sub(_fix_measure, text)
    text = re.sub(r"^[^A-Za-zА-Яа-яЁё0-9«]+", "", text)
    return re.sub(r"\s{2,}", " ", text).strip(" ,.;:-*|_—=<>")


def assign_names(img, badges, side, profile=None):
    """Каждый сегмент текста отдаём ближайшей по горизонтали плашке своего ряда."""
    H, W = img.shape[:2]
    tol = 12 * max(1.0, W / 900.0)
    rows = _rows(badges)
    names = {}
    for i, row in enumerate(rows):
        top = min(b[1] for b in row)
        bottom = max(b[1] + b[3] for b in row)
        h = max(b[3] for b in row)
        if side == "below":
            nxt = min(b[1] for b in rows[i + 1]) if i + 1 < len(rows) else H
            y0, y1 = bottom, min(nxt, bottom + 3 * h)
        else:
            y0 = max(b[1] + b[3] for b in rows[i - 1]) if i > 0 else 0
            y1 = top
        # Под ценником только текст названия; над ним — ещё и надписи с упаковок на фото
        text_re = _TEXT_RE if side == "below" else _CYR_WORD_RE
        drop_upper = profile is not None and profile.drop_upper
        segs = [s for s in sorted(_segments(img, int(y0), int(y1), profile), key=lambda s: s[2])
                if text_re.search(s[3]) and not (drop_upper and _is_upper_label(s[3]))]
        # Строки одной подписи выровнены по краю: собираем их в блок и отдаём плашке целиком
        edge = 1 if side == "above" else 0
        blocks = []
        for seg in segs:
            for block in blocks:
                last = block[-1]
                if abs(last[edge] - seg[edge]) <= tol and 0 < seg[2] - last[2] <= h:
                    block.append(seg)
                    break
            else:
                blocks.append([seg])
        parts = {b: [] for b in row}
        for block in blocks:
            x0, x1 = block[0][0], block[0][1]
            refine = profile is not None and profile.refine
            if side == "above":
                dist = {b: abs((b[0] + b[2]) - x1) for b in row}
            else:
                dist = {b: abs((b[0] + b[2] / 2) - (x0 + x1) / 2) for b in row}
            owner = min(dist, key=dist.get)
            # Далеко от всех плашек — это подпись товара, чей ценник не нашёлся
            if dist[owner] > owner[2] * 1.2:
                continue
            if refine:
                bbox = (min(s[0] for s in block), block[0][2], max(s[1] for s in block), max(s[4] for s in block))
                text = _ocr_block(img, bbox, profile)
                if _CYR_WORD_RE.search(text):
                    parts[owner].append(text)
                    continue
            parts[owner].extend(s[3] for s in block)
        for b in row:
            names[b] = _clean_name(parts[b])
    return names


def parse_flyer_image(path, profile):
    img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return []
    badges = find_badges(img, profile)
    names = assign_names(img, badges, profile.name_side, profile)
    items = []
    for box in badges:
        price, old = read_badge(img, box)
        if old is not None:
            old = _check_old(price, old, read_discount(img, box))
        name = names.get(box, "")
        if price is None or len(name) < 3:
            continue
        items.append({"name": name, "price": price, "old_price": old, "box": box})
    return items


def parse_flyer_images(paths, profile, workers=None):
    """Страницы разбираются в потоках. Распознаёт отдельный процесс tesseract, поэтому потоки
    грузят все ядра, а новых процессов Python (и перезапуска главного скрипта в них) нет."""
    import os
    from concurrent.futures import ThreadPoolExecutor

    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    if workers == 1 or len(paths) < 2:
        return [parse_flyer_image(p, profile) for p in paths]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(lambda p: parse_flyer_image(p, profile), paths))
