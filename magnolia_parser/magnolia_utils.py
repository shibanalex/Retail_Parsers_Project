# -*- coding: utf-8 -*-
import base64
import io
import os
import time

BASE_URL = "https://shop.mgnl.ru"
BOOKLET_PAGE = BASE_URL + "/sale/katalog-skidok/"
LAST_HTTP_STATUS = None

FETCH_JS = """
const done = arguments[arguments.length - 1];
fetch(arguments[0], {credentials: 'include'}).then(r => {
  if (!r.ok) { done('ERR ' + r.status); return; }
  return r.blob().then(b => { const fr = new FileReader(); fr.onload = () => done(fr.result); fr.readAsDataURL(b); });
}).catch(e => done('ERR ' + e));
"""


def confirm_age(driver):
    """Окно «Мне исполнилось 18 лет» закрывает страницу, пока не нажмёшь кнопку."""
    try:
        for btn in driver.find_elements("css selector", "span.item-adult-appruve"):
            if btn.is_displayed():
                btn.click()
                time.sleep(1)
                return True
    except Exception:
        pass
    return False


def open_booklet(driver):
    """Страница буклета: ссылка на PDF. Буклет PDF в 2,7 раза чётче картинок katoteka."""
    global LAST_HTTP_STATUS
    driver.get(BOOKLET_PAGE)
    time.sleep(5)
    confirm_age(driver)
    if "Страница не найдена" in driver.title:
        LAST_HTTP_STATUS = 404
        raise RuntimeError(f"Ошибка 404: {BOOKLET_PAGE}")
    links = driver.find_elements("css selector", "a.catalog-skidok-href, a[href$='.pdf']")
    if not links:
        LAST_HTTP_STATUS = 404
        raise RuntimeError("Ошибка 404: на странице буклета нет ссылки на PDF")
    LAST_HTTP_STATUS = 200
    return links[0].get_attribute("href")


def download(driver, url):
    """Файл качаем изнутри браузера: сайт отдаёт 403 запросам без его cookies."""
    global LAST_HTTP_STATUS
    driver.set_script_timeout(300)
    data = driver.execute_async_script(FETCH_JS, url)
    if not data or data.startswith("ERR"):
        code = data.split()[1] if data and len(data.split()) > 1 and data.split()[1].isdigit() else "403"
        LAST_HTTP_STATUS = int(code)
        raise RuntimeError(f"Ошибка {code}: не удалось скачать {url}")
    return base64.b64decode(data.split(",", 1)[1])


def booklet_pages(pdf_bytes, out_dir):
    """Страница буклета — одна большая картинка внутри PDF. Берём её как есть, без перерисовки."""
    import pypdf
    reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
    paths = []
    for i, page in enumerate(reader.pages, 1):
        images = list(page.images)
        if not images:
            continue
        biggest = max(images, key=lambda im: im.image.size[0] * im.image.size[1])
        path = os.path.join(out_dir, f"page_{i:03d}.jpg")
        biggest.image.convert("RGB").save(path, quality=95)
        paths.append((i, path))
    return paths
