import json
import os
import re
import requests
import logging

try:
    from curl_cffi import requests as cffi_requests
except Exception:
    cffi_requests = None
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from pathlib import Path
from urllib.parse import unquote
import time
import random

from perekrestok_parser.urls import site_url, city_url, product_url, category_items_url
from perekrestok_parser.shared_utils import (
    _shared_get_chrome_binary,
    _shared_detect_chrome_version_main,
    _shared_is_forbidden_ban,
    _shared_parse_proxy,
    _shared_get_cache_dir,
    _shared_ensure_proxy_auth_extension,
    local_proxy_for
)

# Настройка логирования для подавления шума от библиотек
logging.getLogger('urllib3').setLevel(logging.ERROR)
logging.getLogger('selenium').setLevel(logging.ERROR)

jwt_token = None
_token_proxy = None
_driver = None
_driver_proxy = None
_driver_proxy_cm = None
_blocked_proxies: set[str] = set()
_http_session = None
_http_session_proxy = None
_http_session_warmed = False

_chrome_version_cache: int | None = None


def _get_chrome_version() -> int | None:
    global _chrome_version_cache
    if _chrome_version_cache is not None:
        return _chrome_version_cache

    chrome_binary = _shared_get_chrome_binary()
    version = _shared_detect_chrome_version_main(
        chrome_binary,
        env_override_key="PEREKRESTOK_CHROME_VERSION_MAIN"
    )
    _chrome_version_cache = version
    return _chrome_version_cache


def _get_user_agent() -> str:
    version = _get_chrome_version()
    return (
        f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version}.0.0.0 Safari/537.36"
    )


class ProxyBlockedError(RuntimeError):
    pass


try:
    _RETRIES_PER_PROXY = int(os.getenv("PEREKRESTOK_RETRIES_PER_PROXY", "3"))
except ValueError:
    _RETRIES_PER_PROXY = 3


def _extract_access_token_from_session_cookie(session_cookie_value: str) -> str | None:
    try:
        session_data_decode = unquote(session_cookie_value)
        session_token_data = json.loads(session_data_decode)
        return session_token_data.get("accessToken")
    except Exception:
        return None


def _normalize_proxy(proxy: str | None) -> str | None:
    proxy = (proxy or "").strip()
    if not proxy:
        return None
    if "://" not in proxy:
        proxy = "http://" + proxy
    return proxy


def _get_proxy_pool() -> list[str]:
    try:
        from config import proxy as config_proxy
    except Exception:
        return []

    if isinstance(config_proxy, (list, tuple)):
        proxies = [_normalize_proxy(p) for p in config_proxy]
    elif isinstance(config_proxy, str):
        proxies = [_normalize_proxy(config_proxy)]
    else:
        proxies = []

    return [p for p in proxies if p]


def _iter_proxy_retries(max_retries: int, retries_per_proxy: int | None = None):
    proxies = _get_proxy_pool()
    per_proxy = retries_per_proxy or _RETRIES_PER_PROXY
    if proxies:
        for proxy in proxies:
            if proxy in _blocked_proxies:
                continue
            for _ in range(per_proxy):
                if proxy in _blocked_proxies:
                    break
                yield proxy
        return
    total = max_retries if max_retries and max_retries > 0 else per_proxy
    for _ in range(total):
        yield None


def _mark_proxy_blocked(proxy: str | None):
    if proxy:
        _blocked_proxies.add(proxy)


def _find_chrome_binary():
    return _shared_get_chrome_binary()


def _is_headless() -> bool:
    return os.environ.get("PEREKRESTOK_HEADLESS", "false").lower() in ("true", "1", "yes")


def _close_driver():
    global _driver, _driver_proxy, _driver_proxy_cm
    if _driver:
        try:
            _driver.quit()
        except Exception:
            pass
    if _driver_proxy_cm:
        try:
            _driver_proxy_cm.__exit__(None, None, None)
        except Exception:
            pass
    _driver = None
    _driver_proxy = None
    _driver_proxy_cm = None


def _reset_http_session(clear_cookies: bool = False):
    global _http_session, _http_session_proxy, _http_session_warmed
    _http_session = None
    _http_session_proxy = None
    _http_session_warmed = False
    if clear_cookies:
        try:
            path = _cookies_file_path()
            if path.exists():
                path.unlink()
        except Exception:
            pass


def _build_selenium_options(proxy_url: str | None) -> Options:
    options = Options()
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--start-maximized")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU,ru")
    options.add_argument(f"--user-agent={_get_user_agent()}")

    options.add_argument("--disable-gpu")
    options.add_argument("--disable-software-rasterizer")
    options.add_argument("--ignore-certificate-errors")
    options.add_argument("--ignore-ssl-errors")

    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)

    chrome_binary = _find_chrome_binary()
    if chrome_binary:
        options.binary_location = chrome_binary

    if proxy_url:
        options.add_argument(f"--proxy-server={proxy_url}")
    return options


def _get_token_and_cookies_selenium(proxy: str | None, wait_s: float = 5.0) -> tuple[str, dict]:
    cached = _load_cookies_from_file()
    if cached:
        return cached

    proxy_cm = local_proxy_for(proxy)
    proxy_url, _proc = proxy_cm.__enter__()
    label = f"token_{_sanitize_label(proxy_url or 'direct')}"

    try:
        # Пытаемся получить драйвер, обрабатывая ошибки uc
        driver = _get_or_create_driver(proxy, main_url="about:blank")

        try:
            driver.get(site_url)
            time.sleep(wait_s)

            # Скрываем webdriver
            try:
                driver.execute_script(
                    "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
                )
            except Exception:
                pass

            deadline = time.time() + _get_page_wait_s()
            token = None
            cookies = []
            while time.time() < deadline:
                state = _wait_for_content_or_captcha(
                    driver, max(2.0, deadline - time.time())
                )
                if state == "forbidden":
                    raise ProxyBlockedError("Forbidden ban detected")
                if state == "captcha":
                    if not _solve_captcha_if_present(driver, label):
                        manual_deadline = time.time() + 120
                        while time.time() < manual_deadline:
                            if _page_loaded_without_captcha(driver):
                                break
                            time.sleep(1)
                        else:
                            # Если не решили капчу, но токен все-таки появился - выходим
                            if _extract_access_token_from_driver(driver):
                                break
                            raise RuntimeError("Captcha manual solve timeout")

                    if _wait_for_content_or_captcha(driver, max(2.0, deadline - time.time())) != "content":
                        # Проверяем токен даже если контент не загрузился полностью
                        token = _extract_access_token_from_driver(driver)
                        if token:
                            break
                        continue

                elif state == "content":
                    if _wait_for_content_or_captcha(driver, max(2.0, deadline - time.time())) != "content":
                        continue
                elif state == "timeout":
                    break

                token = _extract_access_token_from_driver(driver) or _wait_for_token(
                    driver, _get_token_wait_s()
                )
                if token:
                    break
            cookies = driver.get_cookies()
        finally:
            try:
                # В отличие от одноразового запуска, мы используем глобальный драйвер,
                # поэтому здесь его закрывать не обязательно, если хотим переиспользовать.
                # Но для надежности в текущей логике - закрываем, если это не глобальный.
                pass
            except Exception:
                pass
    finally:
        try:
            proxy_cm.__exit__(None, None, None)
        except Exception:
            pass

    if not token:
        _clear_cookies_cache()
        raise RuntimeError("Token not found in browser cookies")

    cookie_map = {}
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        if name and value is not None:
            cookie_map[name] = value

    _save_cookies_to_file(token, cookie_map)
    return token, cookie_map


def _build_http_session(token: str, cookies: dict, proxy: str | None):
    session = cffi_requests.Session() if cffi_requests else requests.Session()
    session.headers.update(
        {
            "accept": "application/json, text/plain, */*",
            "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "auth": f"Bearer {token}",
            "cache-control": "no-cache",
            "origin": site_url.rstrip("/"),
            "pragma": "no-cache",
            "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-fetch-dest": "empty",
            "sec-fetch-mode": "cors",
            "sec-fetch-site": "same-origin",
            "user-agent": _get_user_agent(),
        }
    )
    if cookies:
        session.cookies.update(cookies)
    if proxy:
        proxy = _normalize_proxy(proxy)
    if proxy:
        session.proxies = {"http": proxy, "https": proxy}
    return session


def _ensure_http_session(max_retries: int = 3) -> requests.Session | None:
    global _http_session, _http_session_proxy, _http_session_warmed
    if _http_session:
        return _http_session

    cached = _load_cookies_from_file()
    if cached:
        token, cookies = cached
        proxy = None
        if not os.getenv("PEREKRESTOK_HTTP_NO_PROXY", "0").lower() in ("1", "true", "yes"):
            proxies = _get_proxy_pool()
            proxy = proxies[0] if proxies else None
        session = _build_http_session(token, cookies, proxy)
        if _test_http_session(session):
            _http_session = session
            _http_session_proxy = proxy
            _http_session_warmed = False
            return session
        else:
            try:
                _cookies_file_path().unlink(missing_ok=True)
            except Exception:
                pass

    if os.getenv("PEREKRESTOK_HTTP_NO_PROXY", "0").lower() in ("1", "true", "yes"):
        proxy_iter = [None]
    else:
        proxy_iter = _iter_proxy_retries(max_retries)
    for proxy in proxy_iter:
        try:
            token, cookies = _get_token_and_cookies_selenium(proxy)
            session = _build_http_session(token, cookies, proxy)
            _http_session = session
            _http_session_proxy = proxy
            _http_session_warmed = False
            return session
        except Exception as e:
            print(f"Ошибка создания сессии (proxy={proxy}): {e}")
            _reset_http_session()
            _mark_proxy_blocked(proxy)
            time.sleep(2)
            continue
    _clear_cookies_cache()
    return None


def reset_http_session():
    _reset_http_session()


def _http_json_or_raise(resp: requests.Response, url: str) -> dict:
    status = resp.status_code
    text = resp.text or ""
    if status in {401, 403, 429} or _looks_blocked_html(text):
        raise ProxyBlockedError(f"Blocked response for {url} (status {status})")
    content_type = (resp.headers.get("content-type") or "").lower()
    if "application/json" not in content_type:
        raise RuntimeError(f"Non-JSON response for {url}: {text[:200]}")
    return resp.json()


def _http_request_kwargs(session):
    kwargs = {"timeout": 20}
    if session.__class__.__module__.startswith("curl_cffi"):
        kwargs["impersonate"] = "chrome120"
    return kwargs


def _http_get_json(session, url: str, params: dict | None = None) -> dict:
    resp = session.get(url, params=params, **_http_request_kwargs(session))
    return _http_json_or_raise(resp, resp.url)


def _http_put_json(session, url: str, json_body: dict | None = None) -> dict:
    resp = session.put(url, json=json_body or {}, **_http_request_kwargs(session))
    return _http_json_or_raise(resp, resp.url)


def _test_http_session(session) -> bool:
    try:
        resp = session.get(
            f"{site_url}api/customer/1.4.1.0/geocoder/suggests",
            params={"search": "Москва"},
            **_http_request_kwargs(session),
        )
        if resp.status_code in {401, 403, 429}:
            return False
        if _looks_blocked_html(resp.text or ""):
            return False
        return resp.status_code == 200
    except Exception:
        return False


def _warmup_http(session) -> None:
    global _http_session_warmed
    if _http_session_warmed:
        return
    try:
        session.get(site_url, **_http_request_kwargs(session))
        time.sleep(0.5)
    except Exception:
        pass
    _http_session_warmed = True


def get_location_http(city_pattern: str, max_retries: int = 5):
    for _ in range(max_retries):
        session = _ensure_http_session(max_retries=1)
        if not session:
            time.sleep(2)
            continue
        try:
            _warmup_http(session)
            data = _http_get_json(
                session,
                f"{site_url}api/customer/1.4.1.0/geocoder/suggests",
                params={"search": city_pattern},
            )
            items = data.get("content", {}).get("items", [])
            if not items:
                _reset_http_session()
                return None
            location = items[0].get("location", {}).get("coordinates")
            return location
        except ProxyBlockedError:
            _reset_http_session(clear_cookies=True)
            time.sleep(2)
            continue
        except Exception:
            _reset_http_session(clear_cookies=True)
            time.sleep(2)
            continue
    return None


def get_city_http(city_pattern: str, max_retries: int = 5):
    for _ in range(max_retries):
        session = _ensure_http_session(max_retries=1)
        if not session:
            time.sleep(2)
            continue
        try:
            location = get_location_http(city_pattern, max_retries=1)
            if not location or len(location) < 2:
                _reset_http_session()
                time.sleep(2)
                continue
            data = _http_get_json(
                session,
                f"{site_url}api/customer/1.4.1.0/shop",
                params={
                    "orderBy": "distance",
                    "orderDirection": "asc",
                    "lat": location[1],
                    "lng": location[0],
                    "page": 1,
                    "perPage": 100,
                },
            )
            shops_ids = []
            cities_data = data.get("content", {}).get("items", {})
            for city in cities_data:
                city_name = city.get("city", {}).get("name")
                if city_name == city_pattern:
                    shops_ids.append((city.get("id"), city.get("address")))
            if not shops_ids:
                _reset_http_session()
            return shops_ids
        except ProxyBlockedError:
            _reset_http_session()
            time.sleep(2)
            continue
        except Exception:
            _reset_http_session()
            time.sleep(2)
            continue
    return None


def set_pickup_http(shop_id: int, max_retries: int = 3):
    for _ in range(max_retries):
        session = _ensure_http_session(max_retries=1)
        if not session:
            time.sleep(2)
            continue
        try:
            _http_put_json(session, f"{city_url}{shop_id}", json_body={})
            return True
        except ProxyBlockedError:
            _reset_http_session()
            time.sleep(2)
            continue
        except Exception:
            _reset_http_session()
            time.sleep(2)
            continue
    return False


def get_search_items_http(search_req: str, shop_id: int, max_retries: int = 5) -> list:
    for _ in range(max_retries):
        session = _ensure_http_session(max_retries=1)
        if not session:
            time.sleep(2)
            continue
        try:
            if shop_id:
                set_pickup_http(shop_id, max_retries=1)
            data = _http_get_json(
                session,
                f"{site_url}api/customer/1.4.1.0/catalog/search/all",
                params={"textQuery": search_req, "entityTypes[]": ["product", "category"]},
            )
            if data.get("error") or data.get("content") is None:
                _reset_http_session()
                time.sleep(2)
                continue
            content = data.get("content") or {}
            products = content.get("products") or content.get("items") or []
            if not isinstance(products, list):
                return []
            return [p for p in products if isinstance(p, dict)]
        except ProxyBlockedError:
            _reset_http_session()
            time.sleep(2)
            continue
        except Exception:
            _reset_http_session()
            time.sleep(2)
            continue
    return []


def _get_or_create_driver(proxy: str | None, main_url: str = site_url):
    global _driver, _driver_proxy, _driver_proxy_cm
    if _driver and _driver_proxy == proxy:
        return _driver

    _close_driver()

    try:
        import undetected_chromedriver as uc
        use_uc = True
    except Exception:
        use_uc = False

    chrome_binary = _find_chrome_binary()

    def prepare_proxy_args(opts, p_info):
        """Правильно форматирует прокси для Chrome."""
        if not p_info:
            return

        scheme = p_info.get('scheme', 'http').lower()
        host = p_info.get('host')
        port = p_info.get('port')

        if scheme in ('http', 'https'):
            p_str = f"{host}:{port}"
        # Для SOCKS схема обязательна
        elif 'socks' in scheme:
            p_str = f"{scheme}://{host}:{port}"
        else:
            # Fallback
            p_str = f"{host}:{port}"

        opts.add_argument(f"--proxy-server={p_str}")


        if scheme not in {"socks5"} and p_info.get("username"):
            ext_dir = _ensure_proxy_auth_extension(p_info)
            opts.add_argument(f"--load-extension={str(ext_dir)}")


    if use_uc:
        options = uc.ChromeOptions()
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-gpu")

        if chrome_binary:
            options.binary_location = chrome_binary

        proxy_cm = local_proxy_for(proxy)
        proxy_url, _proc = proxy_cm.__enter__()
        _driver_proxy_cm = proxy_cm

        proxy_info = _shared_parse_proxy(proxy_url)
        if proxy_info:
            prepare_proxy_args(options, proxy_info)

        _ver = _shared_detect_chrome_version_main(chrome_binary, env_override_key="PEREKRESTOK_CHROME_VERSION_MAIN")

        try:
            uc_kwargs = dict(
                options=options,
                headless=_is_headless(),
                use_subprocess=True,
            )
            if _ver:
                uc_kwargs["version_main"] = _ver

            driver = uc.Chrome(**uc_kwargs)
            driver.set_page_load_timeout(30)
            _driver = driver
            _driver_proxy = proxy
            return driver
        except Exception as e:
            print(f"Ошибка UC: {e}. Переключаюсь на обычный Selenium.")
            if _driver_proxy_cm:
                try:
                    _driver_proxy_cm.__exit__(None, None, None)
                except:
                    pass

    # 2. Fallback: Обычный Selenium
    options = _build_selenium_options(None)  # Прокси добавим вручную ниже

    proxy_cm = local_proxy_for(proxy)
    proxy_url, _proc = proxy_cm.__enter__()
    _driver_proxy_cm = proxy_cm

    proxy_info = _shared_parse_proxy(proxy_url)
    if proxy_info:
        prepare_proxy_args(options, proxy_info)

    if _is_headless():
        options.add_argument("--headless=new")

    driver = webdriver.Chrome(options=options)
    driver.set_page_load_timeout(30)

    try:
        driver.get(main_url)
        _startup_html = driver.page_source or ""
    except Exception:
        _startup_html = ""

    if _shared_is_forbidden_ban(_startup_html):
        try:
            driver.quit()
        except:
            pass
        raise ProxyBlockedError("Forbidden ban detected")

    _driver = driver
    _driver_proxy = proxy
    return driver


def _extract_access_token_from_driver(driver) -> str | None:
    session_cookie_value = None
    try:
        cookies = driver.get_cookies()
    except Exception:
        cookies = []
    for c in cookies or []:
        if c.get("name") == "session":
            session_cookie_value = c.get("value")
            break
    if session_cookie_value:
        token = _extract_access_token_from_session_cookie(session_cookie_value)
        if token:
            return token
    for c in cookies or []:
        token = _extract_access_token_from_session_cookie(c.get("value", ""))
        if token:
            return token
        token = _extract_access_token_from_text(c.get("value", ""))
        if token:
            return token

    try:
        local_items = driver.execute_script("return Object.entries(window.localStorage);")
    except Exception:
        local_items = []
    token = _extract_access_token_from_storage_items(local_items)
    if token:
        return token

    try:
        session_items = driver.execute_script("return Object.entries(window.sessionStorage);")
    except Exception:
        session_items = []
    token = _extract_access_token_from_storage_items(session_items)
    if token:
        return token

    try:
        return _extract_access_token_from_text(driver.page_source)
    except Exception:
        return None


def _driver_fetch_text(
        driver,
        url: str,
        *,
        method: str = "GET",
        headers: dict | None = None,
        json_data: dict | None = None,
        timeout_s: float = 20.0,
) -> tuple[int, str]:
    payload = json.dumps(json_data) if json_data is not None else None
    hdrs = dict(headers or {})
    blocked_headers = {
        "host",
        "origin",
        "referer",
        "user-agent",
        "connection",
        "content-length",
        "accept-encoding",
        "cookie",
    }
    for key in list(hdrs.keys()):
        lowered = key.lower()
        if lowered in blocked_headers or lowered.startswith("sec-"):
            hdrs.pop(key, None)
    if json_data is not None and not any(k.lower() == "content-type" for k in hdrs):
        hdrs["content-type"] = "application/json"
    script = r"""
const url = arguments[0];
const method = arguments[1];
const headers = arguments[2];
const body = arguments[3];
const timeoutMs = arguments[4];
const done = arguments[arguments.length - 1];

const options = { method, headers, credentials: "include" };
if (body !== null) {
  options.body = body;
}

const timer = setTimeout(() => done({ ok: false, error: "timeout" }), timeoutMs);

fetch(url, options)
  .then(async (r) => {
    const t = await r.text();
    clearTimeout(timer);
    done({ ok: true, status: r.status, text: t });
  })
  .catch((e) => {
    clearTimeout(timer);
    done({ ok: false, error: String(e) });
  });
"""

    result = driver.execute_async_script(script, url, method, hdrs, payload, int(timeout_s * 1000))
    if not isinstance(result, dict) or not result.get("ok"):
        raise RuntimeError(f"fetch failed for {url}: {result}")
    return int(result.get("status", 0) or 0), str(result.get("text", "") or "")


def _get_captcha_api_key() -> str:
    key = (os.getenv("APIKEY_2CAPTCHA") or os.getenv("RUCAPTCHA_KEY") or "").strip()
    if key:
        return key
    try:
        from config import APIKEY_2CAPTCHA as config_key
    except Exception:
        config_key = ""
    if not config_key:
        try:
            from config import RUCAPTCHA_KEY as config_key
        except Exception:
            config_key = ""
    return str(config_key or "").strip()


def _get_captcha_max_tries() -> int:
    try:
        value = int(os.getenv("PEREKRESTOK_CAPTCHA_MAX_TRIES", "5"))
    except ValueError:
        value = 5
    return max(0, value)


def _get_captcha_wait_s() -> float:
    try:
        value = float(os.getenv("PEREKRESTOK_CAPTCHA_WAIT_S", "6"))
    except ValueError:
        value = 6.0
    return max(0.5, value)


def _get_token_wait_s() -> float:
    return 20.0


def _get_page_wait_s() -> float:
    return 60.0


def _get_captcha_refresh_enabled() -> bool:
    return os.getenv("PEREKRESTOK_CAPTCHA_REFRESH", "0").lower() in ("1", "true", "yes")


def _sanitize_label(label: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "_", label or "captcha")
    return cleaned[:80] or "captcha"


def _captcha_cache_dir() -> Path:
    cache_dir = _get_cache_dir() / "captcha"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


def _detect_captcha_kind(html: str) -> str:
    lowered = (html or "").lower()

    # Checkbox check first
    if "challenge-platform" in lowered or "cf-turnstile" in lowered or "verify you are human" in lowered:
        return "checkbox"

    if "разверните картинку" in lowered or "sp_rotated_captcha" in lowered:
        return "captcha-rotate"
    if "get_image.php" in lowered and "captcha" in lowered:
        return "captcha-rotate"
    if "<title>forbidden</title>" in lowered or "<h1>forbidden</h1>" in lowered:
        return "forbidden"
    if "servicepipe" in lowered or "exhkqyad" in lowered:
        return "captcha"
    if "captcha_root" in lowered or "captcha-holder" in lowered or "captcha-control" in lowered:
        return "captcha"
    if html.lstrip().startswith("{"):
        return "json"
    return "other"


def _save_captcha_image(driver: webdriver.Chrome, label: str) -> str | None:
    selectors = [
        "img[src*='rotate']",
        "img[src*='captcha']",
        "img[class*='captcha']",
        ".sp_rotated_captcha img",
        "[class*='captcha'] img",
        "#captcha_root img",
        "img",
    ]
    safe_label = _sanitize_label(label)
    for selector in selectors:
        try:
            elements = driver.find_elements(By.CSS_SELECTOR, selector)
        except Exception:
            continue
        for idx, el in enumerate(elements):
            src = (el.get_attribute("src") or "").lower()
            cls = (el.get_attribute("class") or "").lower()
            if selector == "img" and "captcha" not in src and "rotate" not in src and "captcha" not in cls:
                continue
            path = _captcha_cache_dir() / f"captcha_{safe_label}_{int(time.time())}_{idx}.png"
            try:
                el.screenshot(str(path))
            except Exception:
                continue
            return str(path)

    container_selectors = [".sp_rotated_captcha", "#captcha_root", "[class*='captcha']"]
    for sel in container_selectors:
        try:
            container = driver.find_element(By.CSS_SELECTOR, sel)
            path = _captcha_cache_dir() / f"captcha_{safe_label}_{int(time.time())}_container.png"
            container.screenshot(str(path))
            return str(path)
        except Exception:
            continue
    return None


def _wait_for_token(driver: webdriver.Chrome, max_wait_s: float | None = None) -> str | None:
    wait_s = max_wait_s if max_wait_s is not None else _get_token_wait_s()
    deadline = time.time() + max(0.5, wait_s)
    while time.time() < deadline:
        token = _extract_access_token_from_driver(driver)
        if token:
            return token
        time.sleep(0.5)
    return None


def _wait_page_ready(driver: webdriver.Chrome, max_wait_s: float | None = None) -> bool:
    wait_s = max_wait_s if max_wait_s is not None else _get_captcha_wait_s()
    deadline = time.time() + max(0.5, wait_s)
    while time.time() < deadline:
        try:
            if driver.execute_script("return document.readyState") == "complete":
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


def _page_loaded_without_captcha(driver: webdriver.Chrome) -> bool:
    if _has_rotate_captcha(driver):
        return False
    try:
        ready = driver.execute_script("return document.readyState") == "complete"
    except Exception:
        ready = False
    if not ready:
        return False
    try:
        has_structure = driver.execute_script(
            "return !!(document.querySelector('header') || document.querySelector('main') || "
            "document.querySelector('footer') || document.querySelector('nav'));"
        )
    except Exception:
        has_structure = False
    if has_structure:
        return True
    try:
        text_len = int(
            driver.execute_script(
                "return (document.body && (document.body.innerText || '') || '').length;"
            )
        )
    except Exception:
        text_len = 0
    if text_len > 500:
        return True
    try:
        html = driver.page_source or ""
    except Exception:
        html = ""
    if _detect_captcha_kind(html) in {"captcha", "captcha-rotate", "forbidden", "checkbox"}:
        return False
    return text_len > 200


def _wait_for_content_or_captcha(driver: webdriver.Chrome, max_wait_s: float | None = None) -> str:
    wait_s = max_wait_s if max_wait_s is not None else _get_page_wait_s()
    deadline = time.time() + max(2.0, wait_s)
    while time.time() < deadline:
        try:
            html = driver.page_source or ""
        except Exception:
            html = ""
        if _shared_is_forbidden_ban(html):
            return "forbidden"
        kind = _detect_captcha_kind(html)
        if kind in {"captcha", "captcha-rotate", "forbidden", "checkbox"} or _has_rotate_captcha(driver):
            return "captcha"
        if _page_loaded_without_captcha(driver):
            return "content"
        time.sleep(0.5)
    return "timeout"


def _has_rotate_captcha(driver: webdriver.Chrome) -> bool:
    selectors = [
        ".captcha-control-button",
        ".captcha-control-track",
        "img[src*='rotate']",
        "img[src*='captcha']",
        "img[class*='captcha']",
    ]
    for selector in selectors:
        try:
            if driver.find_elements(By.CSS_SELECTOR, selector):
                return True
        except Exception:
            continue
    return False


def _solve_checkbox_captcha(driver: webdriver.Chrome) -> bool:
    """
    Нажатие на чекбокс капчи.
    """
    try:
        wait = WebDriverWait(driver, 10)

        try:
            label = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "label[for='is-robot']")))

            action = ActionChains(driver)
            action.move_to_element(label)
            action.pause(random.uniform(0.3, 0.8))
            action.click()
            action.perform()
            return True
        except Exception:
            driver.execute_script("document.getElementById('is-robot').click();")

            time.sleep(2)
            is_checked = driver.execute_script("return document.getElementById('is-robot').checked;")
            return is_checked

    except Exception as e:
        print(f"Ошибка при обработке чекбокса: {e}")

    return False

def _solve_rotate_captcha(driver: webdriver.Chrome, label: str, max_attempts: int) -> bool:
    api_key = _get_captcha_api_key()
    if not api_key:
        print("[captcha] API-ключ не задан. Автоматическое решение rotate-капчи невозможно.")
        return False

    for attempt in range(1, max_attempts + 1):
        if attempt > 1:
            if not _wait_for_captcha_image(driver, max_wait=10.0):
                try:
                    driver.refresh()
                    time.sleep(3)
                    _wait_for_captcha_image(driver, max_wait=10.0)
                except Exception:
                    pass

        path = _save_captcha_image(driver, label)
        if not path:
            try:
                driver.refresh()
                time.sleep(3)
            except Exception:
                pass
            continue

        angle, raw = solve_rotate_captcha_from_file(path)
        if angle is None:
            continue

        _move_captcha_control(driver, angle)
        time.sleep(3)

        state = _wait_for_content_or_captcha(driver, 10.0)
        if state == "forbidden":
            raise ProxyBlockedError("Forbidden ban detected")
        if state == "content":
            return True
        if _wait_for_token(driver, 5.0):
            return True
        if state == "captcha":
            time.sleep(1)
            continue
        if _wait_captcha_clear(driver):
            return True
    return False


def _wait_for_captcha_image(driver: webdriver.Chrome, max_wait: float = 10.0) -> bool:
    deadline = time.time() + max_wait
    while time.time() < deadline:
        try:
            imgs = driver.find_elements(By.CSS_SELECTOR, "img")
            for img in imgs:
                src = (img.get_attribute("src") or "").lower()
                if "rotate" in src or "captcha" in src:
                    if img.size.get("width", 0) > 50:
                        return True
        except Exception:
            pass
        for sel in (".sp_rotated_captcha img", "[class*='captcha'] img", "#captcha_root img"):
            try:
                if driver.find_elements(By.CSS_SELECTOR, sel):
                    return True
            except Exception:
                continue
        time.sleep(0.5)
    return False


def _parse_angle_from_value(val) -> int | None:
    if isinstance(val, (int, float)):
        return int(val)
    if not isinstance(val, str):
        return None
    val = val.strip()
    if not val:
        return None
    if val.isdigit():
        return int(val)
    try:
        return int(float(val))
    except ValueError:
        pass
    if ":" in val:
        part = val.split(":")[-1].strip()
        try:
            return int(float(part))
        except ValueError:
            pass
    m = re.search(r"(\d+\.?\d*)", val)
    if m:
        return int(float(m.group(1)))
    return None


def solve_rotate_captcha_from_file(path: str) -> tuple[int | None, dict | str | None]:
    if not path or not os.path.exists(path):
        return None, None
    api_key = _get_captcha_api_key()
    if not api_key:
        return None, None
    try:
        from twocaptcha import TwoCaptcha
    except Exception:
        return None, None
    solver = TwoCaptcha(api_key)
    try:
        result = solver.rotate(path)
    except Exception:
        return None, None

    angle = None
    if isinstance(result, dict):
        for key in ("code", "rotate", "angle", "request", "text"):
            val = result.get(key)
            angle = _parse_angle_from_value(val)
            if angle is not None:
                break
    else:
        angle = _parse_angle_from_value(result)
    return angle, result


def _compute_slider_delta(driver: webdriver.Chrome, button, angle: int, max_angle: int = 360) -> int:
    script = """
        const btn = arguments[0];
        const preferred = document.querySelector('.captcha-control-track');
        let track = preferred;
        if (!track) {
            let el = btn;
            for (let i = 0; i < 6 && el; i++) {
                const parent = el.parentElement;
                if (!parent) break;
                const r = parent.getBoundingClientRect();
                const br = btn.getBoundingClientRect();
                if (r.width >= br.width * 2 && r.height >= br.height * 0.6) { track = parent; break; }
                el = parent;
            }
        }
        if (!track) return null;
        const tr = track.getBoundingClientRect();
        const br = btn.getBoundingClientRect();
        return {trackLeft: tr.left, trackWidth: tr.width, btnLeft: br.left, btnWidth: br.width};
    """
    info = driver.execute_script(script, button)
    if not info:
        return angle
    travel = int(info["trackWidth"] - info["btnWidth"])
    if travel <= 0:
        return 0
    target = int(round(travel * angle / max_angle))
    target = max(0, min(target, travel))
    current = int(round(info["btnLeft"] - info["trackLeft"]))
    return target - current


def _move_captcha_control(driver: webdriver.Chrome, angle: int, max_angle: int = 360) -> None:
    button_selectors = [
        ".captcha-control-button",
        "[class*='captcha-control'] button",
        "[class*='captcha'] [class*='button']",
        "[class*='slider'] [class*='button']",
    ]
    el = None
    for sel in button_selectors:
        try:
            el = driver.find_element(By.CSS_SELECTOR, sel)
            if el:
                break
        except Exception:
            continue
    if not el:
        return
    try:
        offset_x = _compute_slider_delta(driver, el, angle, max_angle=max_angle)
        ActionChains(driver).click_and_hold(el).move_by_offset(offset_x, 0).release().perform()
    except Exception:
        pass


def _wait_captcha_clear(driver: webdriver.Chrome, max_wait_s: float | None = None) -> bool:
    wait_s = max_wait_s if max_wait_s is not None else _get_captcha_wait_s()
    deadline = time.time() + max(0.5, wait_s)
    while time.time() < deadline:
        if _extract_access_token_from_driver(driver):
            return True
        html = driver.page_source or ""
        kind = _detect_captcha_kind(html)
        if kind not in {"captcha", "captcha-rotate", "forbidden", "checkbox"}:
            return True
        time.sleep(0.5)
    return False


def _solve_captcha_if_present(driver: webdriver.Chrome, label: str, max_attempts: int | None = None) -> bool:
    """
    Проверка наличия и решение капчи.
    """
    attempts = _get_captcha_max_tries() if max_attempts is None else max(0, max_attempts)
    if attempts <= 0:
        return True

    for attempt in range(1, attempts + 1):
        html = driver.page_source or ""
        kind = _detect_captcha_kind(html)

        # 1. Если обнаружен чекбокс (Cloudflare или простая форма)
        if kind == "checkbox" or driver.find_elements(By.ID, "is-robot"):
            if _solve_checkbox_captcha(driver):
                time.sleep(5)
                if _page_loaded_without_captcha(driver):
                    return True

        # 2. Если обнаружена Rotate-капча (повороты)
        if kind == "captcha-rotate":
            return _solve_rotate_captcha(driver, label, attempts)

        # 3. Общая логика для блокировок и неопознанных капч
        if kind in {"captcha", "forbidden"}:
            if _extract_access_token_from_driver(driver):
                return True
            if _has_rotate_captcha(driver):
                return _solve_rotate_captcha(driver, label, attempts)

            # Попытка нажать на чекбокс как на последний шанс
            if _solve_checkbox_captcha(driver):
                time.sleep(5)
                if _extract_access_token_from_driver(driver):
                    return True

            if _wait_for_token(driver):
                return True
            return False

        if _has_rotate_captcha(driver):
            return _solve_rotate_captcha(driver, label, attempts)

        return True
    return False


def _trigger_and_solve_captcha(driver: webdriver.Chrome, label: str, url: str = site_url) -> bool:
    try:
        driver.get(url)
        time.sleep(2)
    except Exception:
        pass
    return _solve_captcha_if_present(driver, label)


def _looks_blocked_html(text: str) -> bool:
    lowered = (text or "").lower()
    if not lowered:
        return False
    blocked_markers = (
        "captcha_root",
        "captcha-holder",
        "captcha-control",
        "sp_rotated_captcha",
        "servicepipe",
        "get_image.php",
        "мы хотим убедиться",
        "access denied",
        "/exhkqyad",
        "challenge-platform",
        "cf-turnstile"
    )
    return any(marker in lowered for marker in blocked_markers)


def _raise_if_blocked(status: int, text: str, url: str):
    if status in {401, 403, 429} or _looks_blocked_html(text):
        raise ProxyBlockedError(f"Blocked response for {url} (status {status})")


def _driver_fetch_json(
        driver,
        url: str,
        *,
        method: str = "GET",
        headers: dict | None = None,
        json_data: dict | None = None,
        timeout_s: float = 20.0,
        captcha_retries: int | None = None,
        captcha_label: str | None = None,
) -> dict:
    retries = _get_captcha_max_tries() if captcha_retries is None else max(0, captcha_retries)
    label = captcha_label or "fetch"
    for attempt in range(retries + 1):
        status, text = _driver_fetch_text(
            driver, url, method=method, headers=headers, json_data=json_data, timeout_s=timeout_s
        )
        blocked = status in {401, 403, 429} or _looks_blocked_html(text)
        if blocked:
            kind = _detect_captcha_kind(text)
            if kind in {"captcha-rotate", "captcha", "checkbox"} and attempt < retries:
                if _trigger_and_solve_captcha(driver, label):
                    continue
            _raise_if_blocked(status, text, url)
        if status != 200:
            raise RuntimeError(f"HTTP {status} for {url}")
        try:
            return json.loads(text)
        except Exception as e:
            if _looks_blocked_html(text):
                kind = _detect_captcha_kind(text)
                if kind in {"captcha-rotate", "captcha", "checkbox"} and attempt < retries:
                    if _trigger_and_solve_captcha(driver, label):
                        continue
                raise ProxyBlockedError(f"Blocked response for {url} (non-JSON)") from e
            head = (text or "")[:300].replace("\n", "\\n")
            raise RuntimeError(f"Non-JSON response for {url}: {head}") from e
    raise ProxyBlockedError(f"Blocked response for {url} (captcha retries exhausted)")


def _driver_fetch_text_checked(
        driver,
        url: str,
        *,
        method: str = "GET",
        headers: dict | None = None,
        json_data: dict | None = None,
        timeout_s: float = 20.0,
        captcha_retries: int | None = None,
        captcha_label: str | None = None,
) -> tuple[int, str]:
    retries = _get_captcha_max_tries() if captcha_retries is None else max(0, captcha_retries)
    label = captcha_label or "fetch"
    for attempt in range(retries + 1):
        status, text = _driver_fetch_text(
            driver, url, method=method, headers=headers, json_data=json_data, timeout_s=timeout_s
        )
        blocked = status in {401, 403, 429} or _looks_blocked_html(text)
        if blocked:
            kind = _detect_captcha_kind(text)
            if kind in {"captcha-rotate", "captcha", "checkbox"} and attempt < retries:
                if _trigger_and_solve_captcha(driver, label):
                    continue
            _raise_if_blocked(status, text, url)
        return status, text
    raise ProxyBlockedError(f"Blocked response for {url} (captcha retries exhausted)")


def _ensure_token_for_proxy(main_url: str, proxy: str | None, max_retries: int = 1):
    global jwt_token, _token_proxy
    if _token_proxy != proxy:
        jwt_token = None
        _token_proxy = None
    driver = _get_or_create_driver(proxy, main_url=main_url)
    label = f"token_driver_{_sanitize_label(proxy or 'direct')}"
    if not _solve_captcha_if_present(driver, label):
        return None
    if jwt_token is None:
        token = _extract_access_token_from_driver(driver)
        if token:
            jwt_token = token
            _token_proxy = proxy
        else:
            get_jwt_token(main_url, max_retries=max_retries, proxy=proxy)
    if jwt_token is None or _token_proxy != proxy:
        return None
    return driver


def _ensure_proxy_auth_extension(proxy_info: dict) -> Path:
    return _shared_ensure_proxy_auth_extension(
        proxy_info, _get_cache_dir(), ext_name="Perekrestok Proxy Auth"
    )


def _get_cache_dir() -> Path:
    cache_dir = _shared_get_cache_dir(
        "perekrestok_parser", env_override_key="PEREKRESTOK_CACHE_DIR"
    )
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir


_COOKIES_MAX_AGE_S = 1800  # 30 minutes


def _cookies_file_path() -> Path:
    return _get_cache_dir() / "cookies.json"


def _save_cookies_to_file(token: str, cookies: dict) -> None:
    data = {"token": token, "cookies": cookies, "ts": time.time()}
    try:
        _cookies_file_path().write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        print(f"Не удалось сохранить куки: {e}")


def _load_cookies_from_file() -> tuple[str, dict] | None:
    path = _cookies_file_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    ts = data.get("ts", 0)
    if time.time() - ts > _COOKIES_MAX_AGE_S:
        return None
    token = data.get("token")
    cookies = data.get("cookies")
    if not token or not isinstance(cookies, dict):
        return None
    return token, cookies


def _clear_cookies_cache() -> None:
    try:
        path = _cookies_file_path()
        if path.exists():
            path.unlink()
    except Exception as e:
        print(f"Не удалось очистить кэш куков: {e}")


def _extract_access_token_from_storage_items(storage_items) -> str | None:
    for key, value in storage_items or []:
        if not value:
            continue
        token = _extract_access_token_from_session_cookie(value)
        if token:
            return token
        try:
            data = json.loads(value)
            if isinstance(data, dict) and data.get("accessToken"):
                return data.get("accessToken")
        except Exception:
            pass
        match = re.search(r'"accessToken"\s*:\s*"([^"]+)"', value)
        if match:
            return match.group(1)
    return None


def _extract_access_token_from_text(text: str) -> str | None:
    if not text:
        return None
    match = re.search(r'"accessToken"\s*:\s*"([^"]+)"', text)
    if match:
        return match.group(1)
    return None


def get_jwt_token(url: str, max_retries: int = 3, proxy: str | None = None) -> None:
    """
    Get JWT token
    :param url: main site url
    :param max_retries: max number of retries
    :return: JWT token in global var
    """
    if proxy is None:
        proxy_iter = _iter_proxy_retries(max_retries)
    else:
        attempts = max_retries if max_retries and max_retries > 0 else 1
        proxy_iter = [proxy] * attempts
    try:
        wait_s = float(os.getenv("PEREKRESTOK_TOKEN_WAIT_S", "15"))
    except ValueError:
        wait_s = 15.0
    for proxy_item in proxy_iter:
        try:
            driver = _get_or_create_driver(proxy_item, main_url=url)
            try:
                driver.get(url)
            except Exception:
                pass
            if not _solve_captcha_if_present(driver, f"jwt_{_sanitize_label(proxy_item or 'direct')}"):
                time.sleep(5)
                continue
            access_token = None
            deadline = time.time() + wait_s
            while time.time() < deadline and not access_token:
                access_token = _extract_access_token_from_driver(driver)
                if access_token:
                    break
                time.sleep(0.5)
            global jwt_token, _token_proxy
            jwt_token = access_token
            _token_proxy = proxy_item if access_token else None
            if not jwt_token:
                time.sleep(5)
                continue
            return None
        except Exception:
            time.sleep(5)
            continue
    jwt_token = None
    _token_proxy = None
    return None


def set_jwt_token(value):
    global jwt_token, _token_proxy
    jwt_token = value
    if value is None:
        _token_proxy = None


def get_category_data(
        category_id: int,
        shop_id: int,
        main_url: str = site_url,
        city_change_url: str = city_url,
        url: str = category_items_url,
        max_retries: int = 10,
) -> dict | None:
    """
    Get category data
    :param category_id: id of category
    :param shop_id: id of shop
    :param main_url: main site url
    :param city_change_url: url for city change
    :param url: product url
    :param max_retries: max number of retries
    :return: Items data by category
    """
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "auth": "",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": main_url,
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        'user-agent': _get_user_agent(),
    }
    json_data = {
        "filter": {
            "category": category_id,
            "onlyWithProductReviews": False,
        },
        "withBestProductReviews": False,
    }
    for proxy in _iter_proxy_retries(max_retries):
        try:
            driver = _ensure_token_for_proxy(main_url, proxy, max_retries=1)
            if not driver:
                time.sleep(5)
                continue
            headers["auth"] = f"Bearer {jwt_token}"
            time.sleep(random.uniform(0.7, 1.2))
            status, text = _driver_fetch_text_checked(
                driver,
                f"{city_change_url}{shop_id}",
                method="PUT",
                headers=headers,
                json_data={},
                captcha_label="pickup",
            )
            if status != 200:
                raise RuntimeError(f"HTTP {status} for {city_change_url}{shop_id}")
            return _driver_fetch_json(
                driver,
                url,
                method="POST",
                headers=headers,
                json_data=json_data,
            )
        except ProxyBlockedError as e:
            set_jwt_token(None)
            _mark_proxy_blocked(proxy)
            time.sleep(5)
            continue
        except Exception as e:
            set_jwt_token(None)
            time.sleep(5)
            continue
    return None


def get_item_data(
        item_id: str,
        url: str = product_url,
        main_url: str = site_url,
        max_retries: int = 10,
) -> dict | None:
    """
    Get item data
    :param item_id: item id
    :param url: item url
    :param main_url: main url of site
    :param max_retries: max number of retries
    :return:
    """
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "auth": "",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": main_url,
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        'user-agent': _get_user_agent(),
    }
    for proxy in _iter_proxy_retries(max_retries):
        try:
            time.sleep(random.uniform(0.5, 0.8))
            driver = _ensure_token_for_proxy(main_url, proxy, max_retries=1)
            if not driver:
                time.sleep(5)
                continue
            headers["auth"] = f"Bearer {jwt_token}"
            return _driver_fetch_json(
                driver,
                f"{url}plu{item_id}",
                method="GET",
                headers=headers,
            )
        except ProxyBlockedError as e:
            set_jwt_token(None)
            _mark_proxy_blocked(proxy)
            time.sleep(5)
            continue
        except Exception as e:
            set_jwt_token(None)
            time.sleep(5)
            continue
    return None


def get_search_data(
        search_req, shop_id, main_url: str = site_url, city_change_url: str = city_url, max_retries: int = 10,
):
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "auth": "",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": main_url,
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        'user-agent': _get_user_agent(),
    }
    for proxy in _iter_proxy_retries(max_retries):
        try:
            driver = _ensure_token_for_proxy(main_url, proxy, max_retries=1)
            if not driver:
                time.sleep(5)
                continue
            headers["auth"] = f"Bearer {jwt_token}"
            status, text = _driver_fetch_text_checked(
                driver,
                f"{city_change_url}{shop_id}",
                method="PUT",
                headers=headers,
                json_data={},
                captcha_label="pickup",
            )
            if status != 200:
                raise RuntimeError(f"HTTP {status} for {city_change_url}{shop_id}")
            return _driver_fetch_json(
                driver,
                f"https://www.perekrestok.ru/api/customer/1.4.1.0/catalog/search/all?textQuery={search_req}&entityTypes[]=product&entityTypes[]=category",
                method="GET",
                headers=headers,
            )
        except ProxyBlockedError as e:
            set_jwt_token(None)
            _mark_proxy_blocked(proxy)
            time.sleep(5)
            continue
        except Exception as e:
            set_jwt_token(None)
            time.sleep(5)
            continue
    return None


def get_location(city_pattern, main_url: str = site_url, max_retries: int = 10, proxy: str | None = None):
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "auth": "",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": main_url,
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        'user-agent': _get_user_agent(),
    }
    if proxy is None:
        proxy_iter = _iter_proxy_retries(max_retries)
    else:
        attempts = max_retries if max_retries and max_retries > 0 else 1
        proxy_iter = [proxy] * attempts
    for proxy_item in proxy_iter:
        try:
            driver = _ensure_token_for_proxy(main_url, proxy_item, max_retries=1)
            if not driver:
                time.sleep(5)
                continue
            headers["auth"] = f"Bearer {jwt_token}"
            r_json = _driver_fetch_json(
                driver,
                f"https://www.perekrestok.ru/api/customer/1.4.1.0/geocoder/suggests?search={city_pattern}",
                method="GET",
                headers=headers,
            )
            items = r_json.get("content", {}).get("items", [])
            if not items:
                return None
            r_data = items[0]
            location = r_data.get("location", {}).get("coordinates")
            return location
        except ProxyBlockedError as e:
            set_jwt_token(None)
            _mark_proxy_blocked(proxy_item)
            time.sleep(5)
            continue
        except Exception as e:
            set_jwt_token(None)
            time.sleep(5)
            continue
    return None


def get_city(city_pattern, main_url: str = site_url, max_retries: int = 10):
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "auth": "",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": main_url,
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua": '"Not)A;Brand";v="8", "Chromium";v="138", "Google Chrome";v="138"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        'user-agent': _get_user_agent(),
    }
    for proxy in _iter_proxy_retries(max_retries):
        try:
            driver = _ensure_token_for_proxy(main_url, proxy, max_retries=1)
            if not driver:
                time.sleep(5)
                continue
            location = get_location(city_pattern, main_url, max_retries=1, proxy=proxy)
            if not location or len(location) < 2:
                time.sleep(5)
                continue
            headers["auth"] = f"Bearer {jwt_token}"
            c_json = _driver_fetch_json(
                driver,
                f"https://www.perekrestok.ru/api/customer/1.4.1.0/shop?orderBy=distance&orderDirection=asc&lat={location[1]}&lng={location[0]}&page=1&perPage=100",
                method="GET",
                headers=headers,
            )
            shops_ids = []
            cities_data = c_json.get("content", {}).get("items", {})
            for city in cities_data:
                city_name = city.get("city", {}).get("name")
                if city_name == city_pattern:
                    shops_ids.append((city.get("id"), city.get("address")))
            return shops_ids
        except ProxyBlockedError as e:
            set_jwt_token(None)
            _mark_proxy_blocked(proxy)
            time.sleep(5)
            continue
        except Exception as e:
            set_jwt_token(None)
            time.sleep(5)
            continue
    return None


def get_search_request(search_req, page, shop_id, main_url: str = site_url, city_change_url: str = city_url,
                       max_retries: int = 10):
    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        "auth": "",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "origin": main_url,
        "pragma": "no-cache",
        "priority": "u=1, i",
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
        'user-agent': _get_user_agent(),
    }
    json_data = {
        "filter": {
            "textQuery": search_req,
        },
        "page": page,
        "perPage": 48,
        "withBestProductReviews": False,
    }
    for proxy in _iter_proxy_retries(max_retries):
        try:
            driver = _ensure_token_for_proxy(main_url, proxy, max_retries=1)
            if not driver:
                time.sleep(5)
                continue
            headers["auth"] = f"Bearer {jwt_token}"
            status, text = _driver_fetch_text_checked(
                driver,
                f"{city_change_url}{shop_id}",
                method="PUT",
                headers=headers,
                json_data={},
                captcha_label="pickup",
            )
            if status != 200:
                raise RuntimeError(f"HTTP {status} for {city_change_url}{shop_id}")
            return _driver_fetch_json(
                driver,
                "https://www.perekrestok.ru/api/customer/1.4.1.0/catalog/product/feed",
                method="POST",
                headers=headers,
                json_data=json_data,
            )
        except ProxyBlockedError as e:
            set_jwt_token(None)
            _mark_proxy_blocked(proxy)
            time.sleep(5)
            continue
        except Exception as e:
            set_jwt_token(None)
            time.sleep(5)
            continue
    return None