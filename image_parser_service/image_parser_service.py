# -*- coding: utf-8 -*-
import sys
import os
from pathlib import Path

sys.path.insert(0, os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")))

import config
from parsers_core.utils import update_retail_points
from . import image_parser_utils
from . import flyer_pdf_utils
from .image_parser_utils import (
    collect_images,
    detect_format,
    ocr_image,
    extract_price,
    extract_measure,
    extract_brand,
    extract_name,
    SUPPORTED_FORMATS,
)

RETAIL = "Скан изображений"
LAST_HTTP_STATUS = None
DEBUG_DIR = os.path.join(os.path.dirname(__file__), "debug_dump")


def get_all_data(source=None, shop_name=None, city=None):
    source = source or getattr(config, "image_source", "images_input")
    shop_name = shop_name or getattr(config, "image_shop_name", RETAIL)
    city = city if city is not None else getattr(config, "image_city", "")
    known_brands = getattr(config, "image_known_brands", [])
    debug_mode = getattr(config, "debug_mode", False)
    debug_dir = DEBUG_DIR if debug_mode else None

    all_data = []
    _error = None

    try:
        paths = collect_images(source)
        if not paths:
            print(f"[{shop_name}] Источник '{source}' не содержит файлов jpg/png/pdf.")
            return all_data

        print(f"[{shop_name}] Найдено файлов: {len(paths)}")
        total = len(paths)
        for i, path in enumerate(paths, 1):
            name_only = os.path.basename(path)

            if name_only.lower().endswith(".pdf"):
                try:
                    items = flyer_pdf_utils.parse_flyer_pdf(path, debug_dir=debug_dir)
                except Exception as e:
                    print(f"[{shop_name}] Ошибка разбора {name_only}: {e}")
                    continue
                print(f"[{shop_name}] {name_only}: найдено позиций {len(items)}")
                for item in items:
                    if item["old_price"]:
                        regular, promo = item["old_price"], item["price"]
                    else:
                        regular, promo = item["price"], 0
                    all_data.append({
                        "Сеть": shop_name,
                        "Тип магазина": "Листовка",
                        "Адрес Торговой точки": city,
                        "Бренд": item["brand"],
                        "Название продукта": item["name"],
                        "Цена": float(regular),
                        "Фото товара": "",
                        "Ссылка на страницу": "",
                        "Объем": item["volume"],
                        "Вес": item["weight"],
                        "Остаток": "1",
                        "Категория": "",
                        "Цена по акции": float(promo),
                        "Рейтинг": 0.0,
                        "Артикул": item["sku"],
                    })
                if i % 5 == 0 or i == total:
                    print(f"[{shop_name}] Обработано файлов: {i} из {total}")
                continue

            fmt = detect_format(path)
            if fmt not in SUPPORTED_FORMATS:
                print(f"[{shop_name}] Пропущен {name_only} — формат "
                      f"{fmt or 'неизвестен'} не поддерживается.")
                continue

            try:
                text = ocr_image(path)
            except Exception as e:
                print(f"[{shop_name}] Ошибка распознавания {name_only}: {e}")
                continue

            if debug_dir:
                os.makedirs(debug_dir, exist_ok=True)
                with open(os.path.join(debug_dir, f"{name_only}.txt"), "w", encoding="utf-8") as f:
                    f.write(text)

            price = extract_price(text)
            if price is None:
                print(f"[{shop_name}] {name_only} ({fmt}): цена не распознана, пропуск.")
                continue

            product_name = extract_name(text)
            if not product_name:
                print(f"[{shop_name}] {name_only} ({fmt}): название не распознано, пропуск.")
                continue

            volume, weight = extract_measure(text)
            brand = extract_brand(text, known_brands)

            all_data.append({
                "Сеть": shop_name,
                "Тип магазина": "Скан",
                "Адрес Торговой точки": city,
                "Бренд": brand,
                "Название продукта": product_name,
                "Цена": float(price),
                "Фото товара": Path(path).resolve().as_uri(),
                "Ссылка на страницу": "",
                "Объем": volume,
                "Вес": weight,
                "Остаток": "1",
                "Категория": "",
                "Цена по акции": 0,
                "Рейтинг": 0.0,
                "Артикул": "",
            })

            if i % 5 == 0 or i == total:
                print(f"[{shop_name}] Обработано файлов: {i} из {total}")

        try:
            update_retail_points(shop_name, city, 1)
        except Exception:
            pass

    except Exception as e:
        _error = e
        print(f"[{shop_name}] Критическая ошибка работы сервиса: {e}")

    for idx, row in enumerate(all_data, 1):
        row["Номер"] = idx

    if _error is not None:
        raise _error
    return all_data


def main(source=None, shop_name=None, city=None):
    return get_all_data(source=source, shop_name=shop_name, city=city)


def run_and_export(source=None, shop_name=None, city=None, output_path=None):
    from datetime import datetime
    from parsers_core.utils import write_excel

    rows = main(source=source, shop_name=shop_name, city=city)
    if not output_path:
        out_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "output")
        os.makedirs(out_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_path = os.path.join(out_dir, f"image_scan_{timestamp}.xlsx")
    write_excel(rows, output_path)
    return output_path, rows


if __name__ == "__main__":
    path, rows = run_and_export()
    print(f"rows: {len(rows)}")
    print(f"file: {path}")
