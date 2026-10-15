# -*- coding: utf-8 -*-
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from parsers_core import katoteka

TILES_HTML = """
<p class="period">Период действия:<br><span class="dates">30 сентября – 13 октября 2026</span></p>
<div class="product"><div class="titleProd">ШОКОЛАД АЛЁНКА, МОЛОЧНЫЙ, 75 Г</div>
<div class="imageProd"><img src="/1images/catalogs/mar/1/w/0004.jpg?1" alt=""></div>
<div class="priceProd"><span class="priceNew"><span class="rubNew">79</span><span class="kopNew">99</span></span>
<span class="priceOld"><span class="rubOld">90</span><span class="kopOld">99</span></span></div></div>
<div class="product"><div class="titleProd">Бокал, Plast team, 360 мл</div>
<div class="imageProd"><img src="../1images/catalogs/fix/1/w/0004.jpeg?1" alt=""></div>
<div class="priceProd"><span class="priceNew"><span class="rubNew">55</span><span class="kopNew">00</span></span></div></div>
<div class="product"><div class="titleProd">Без цены</div></div>
<img src="../1images/catalogs/mon/cat1/1/01.jpg?5"><img src="/1images/catalogs/mon/0.jpg?1">
<a href="https://katoteka.ru/mon/sve/">Свердловская</a><a href="https://katoteka.ru/mon/nvs/">Новосибирская</a>
"""


def test_product_tiles():
    items = katoteka.product_tiles(TILES_HTML)
    assert [(i["name"], i["price"], i["old_price"]) for i in items] == [
        ("ШОКОЛАД АЛЁНКА, МОЛОЧНЫЙ, 75 Г", 79.99, 90.99),
        ("Бокал, Plast team, 360 мл", 55.0, None),
    ]
    assert items[1]["photo"] == "https://katoteka.ru/1images/catalogs/fix/1/w/0004.jpeg?1"


def test_page_helpers():
    assert katoteka.period(TILES_HTML) == "30 сентября – 13 октября 2026"
    assert katoteka.catalog_images(TILES_HTML, "mon") == ["https://katoteka.ru/1images/catalogs/mon/cat1/1/01.jpg?5"]
    assert katoteka.region_codes(TILES_HTML, "mon") == {"sve", "nvs"}


@pytest.mark.parametrize("city,code", [
    ("Екатеринбург", "sve"), ("Новосибирск", "nvs"), ("г. Сургут", "khm"), ("Москва", "mow"),
    ("Санкт-Петербург", "spe"), ("Барнаул", "alt"), ("Ульяновск", None), ("", None),
])
def test_city_region(city, code):
    assert katoteka.city_region(city) == code


def test_match_queries():
    assert katoteka.match_queries("ШОКОЛАД АЛЁНКА, МОЛОЧНЫЙ", ["шоколад"])
    assert katoteka.match_queries("Кефир ВКУСНЯЕВ 3.2%", ["Кефир"])
    assert katoteka.match_queries("Корм для кошек Шеба", ["корм для кошек"])
    assert not katoteka.match_queries("Корм для собак", ["корм для кошек"])
    assert not katoteka.match_queries("Молоко", ["Кефир"])


def _ocr_ready():
    try:
        from image_parser_service import image_parser_utils
        return image_parser_utils._OCR_CFG is not None
    except Exception:
        return False


def _font(size, bold=False):
    from PIL import ImageFont
    for name in (("arialbd.ttf",) if bold else ()) + ("arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    pytest.skip("нет TTF-шрифта с кириллицей")


@pytest.mark.skipif(not _ocr_ready(), reason="Tesseract не настроен")
def test_flyer_page_ocr(tmp_path):
    from PIL import Image, ImageDraw
    from image_parser_service.flyer_page_ocr import FlyerProfile, parse_flyer_image

    img = Image.new("RGB", (900, 460), (250, 245, 215))
    d = ImageDraw.Draw(img)
    for x0, rub, name, measure in ((170, "129", "Сыр плавленый сливочный", "200 г"),
                                   (630, "349", "Килька черноморская", "240 г")):
        d.rounded_rectangle((x0, 240, x0 + 250, 312), radius=36, fill=(255, 230, 51))
        d.text((x0 + 40, 246), rub, font=_font(58, bold=True), fill=(0, 0, 0))
        d.text((x0 + 40 + d.textlength(rub, font=_font(58, bold=True)) + 6, 250), "99",
               font=_font(26, bold=True), fill=(0, 0, 0))
        d.text((x0 - 150, 340), name, font=_font(22), fill=(0, 0, 0))
        d.text((x0 - 150, 368), measure, font=_font(22), fill=(0, 0, 0))
    path = tmp_path / "page.jpg"
    img.save(path, quality=95)

    profile = FlyerProfile([((24, 185, 240), (30, 225, 255))], name_side="below", close=21)
    items = sorted(parse_flyer_image(str(path), profile), key=lambda i: i["box"][0])
    assert [i["price"] for i in items] == [129.99, 349.99]
    assert "Сыр" in items[0]["name"] and "200" in items[0]["name"]
    assert "Килька" in items[1]["name"]


@pytest.mark.parametrize("raw,clean", [
    ("Кефир Нашей дойки 2,5% ЭООМл", "Кефир Нашей дойки 2,5% 900мл"),
    ("Сметана Большая кружка 15% ЗООг", "Сметана Большая кружка 15% 300г"),
    ("Яйцо куриное С1 Роскар 1Ошт", "Яйцо куриное С1 Роскар 10шт"),
    ("— Молоко Рогачев 3,2% 1л", "Молоко Рогачев 3,2% 1л"),
    ("Бургер 190r цена по карте*", "Бургер 190г"),
])
def test_clean_flyer_name(raw, clean):
    from image_parser_service.flyer_page_ocr import _clean_name
    assert _clean_name([raw]) == clean


def test_upper_labels_are_not_names():
    from image_parser_service.flyer_page_ocr import _is_upper_label
    assert _is_upper_label("НАШЕ ПРОИЗВОДСТВО")
    assert _is_upper_label("ВРЕМЯ ОБЕДА")
    assert not _is_upper_label("Молоко Северная долина 2,5%")
