import os
import re
import shutil
import platform
import zipfile
import subprocess
from pathlib import Path
from urllib.parse import urlsplit, urlparse


def _shared_get_cache_dir(name: str, env_override_key: str = None) -> Path:
    """Создает и возвращает путь к папке кэша."""
    if env_override_key:
        env_path = os.getenv(env_override_key)
        if env_path:
            p = Path(env_path)
            p.mkdir(parents=True, exist_ok=True)
            return p

    base_dir = Path(os.getcwd()) / ".cache" / name
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir


def _shared_get_chrome_binary() -> str | None:
    """Пытается найти путь к исполняемому файлу Chrome."""
    env_bin = os.getenv("CHROME_BINARY_PATH")
    if env_bin and os.path.exists(env_bin):
        return env_bin

    system = platform.system()
    if system == "Windows":
        paths = [
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            os.path.join(os.getenv("LOCALAPPDATA", ""), r"Google\Chrome\Application\chrome.exe"),
            os.path.join(os.getenv("PROGRAMFILES", ""), r"Google\Chrome\Application\chrome.exe"),
            os.path.join(os.getenv("PROGRAMFILES(X86)", ""), r"Google\Chrome\Application\chrome.exe"),
        ]
        for p in paths:
            if os.path.exists(p):
                return p
    elif system == "Linux":
        for p in ["google-chrome", "google-chrome-stable", "chromium", "chromium-browser"]:
            path = shutil.which(p)
            if path:
                return path
    elif system == "Darwin":
        p = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        if os.path.exists(p):
            return p
    return None


def _shared_detect_chrome_version_main(binary_path: str | None, env_override_key: str = None) -> int | None:
    """Определяет мажорную версию Chrome."""
    if env_override_key:
        val = os.getenv(env_override_key)
        if val and val.isdigit():
            return int(val)

    if not binary_path:
        return 120

    try:
        if platform.system() == "Windows":
            cmd = f'(Get-Item "{binary_path}").VersionInfo.ProductVersion'
            result = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True)
            output = result.stdout.strip()
            match = re.search(r"(\d+)\.", output)
            if match:
                return int(match.group(1))
        else:
            result = subprocess.run([binary_path, "--version"], capture_output=True, text=True)
            output = result.stdout.strip()
            match = re.search(r"(\d+)\.", output)
            if match:
                return int(match.group(1))
    except Exception:
        pass

    return 120


def _shared_is_forbidden_ban(html: str) -> bool:
    if not html:
        return False
    lowered = html.lower()
    return (
            "403 forbidden" in lowered
            or "access denied" in lowered
            or "mq-start-page" in lowered
            or "cloudflare" in lowered
    )


def _shared_parse_proxy(proxy_str: str | None) -> dict | None:
    """
    Умный парсер прокси. Понимает форматы:
    - http://ip:port
    - http://user:pass@ip:port
    - ip:port
    - ip:port:user:pass (формат из текстовых файлов)
    """
    if not proxy_str:
        return None

    proxy_str = proxy_str.strip()

    try:
        if "://" not in proxy_str and proxy_str.count(":") == 3:
            parts = proxy_str.split(":")
            return {
                "scheme": "http",
                "host": parts[0],
                "port": int(parts[1]),
                "username": parts[2],
                "password": parts[3]
            }

        if "://" not in proxy_str:
            proxy_str = "http://" + proxy_str

        parsed = urlsplit(proxy_str)

        return {
            "scheme": parsed.scheme,
            "host": parsed.hostname,
            "port": parsed.port,
            "username": parsed.username,
            "password": parsed.password
        }
    except Exception:
        return None


def _shared_ensure_proxy_auth_extension(proxy_info: dict, cache_dir: Path, ext_name: str) -> Path:
    """Создает Chrome Extension для авторизации."""
    ext_dir = cache_dir / ext_name

    if ext_dir.exists():
        try:
            shutil.rmtree(ext_dir)
        except:
            pass

    ext_dir.mkdir(parents=True, exist_ok=True)

    manifest_json = """
    {
        "version": "1.0.0",
        "manifest_version": 2,
        "name": "Chrome Proxy Auth",
        "permissions": [
            "proxy",
            "tabs",
            "unlimitedStorage",
            "storage",
            "<all_urls>",
            "webRequest",
            "webRequestBlocking"
        ],
        "background": {
            "scripts": ["background.js"]
        },
        "minimum_chrome_version":"22.0.0"
    }
    """

    background_js = """
    var config = {
            mode: "fixed_servers",
            rules: {
              singleProxy: {
                scheme: "%s",
                host: "%s",
                port: parseInt(%s)
              },
              bypassList: ["localhost"]
            }
          };

    chrome.proxy.settings.set({value: config, scope: "regular"}, function() {});

    function callbackFn(details) {
        return {
            authCredentials: {
                username: "%s",
                password: "%s"
            }
        };
    }

    chrome.webRequest.onAuthRequired.addListener(
                callbackFn,
                {urls: ["<all_urls>"]},
                ['blocking']
    );
    """ % (
        proxy_info.get('scheme', 'http'),
        proxy_info.get('host'),
        proxy_info.get('port'),
        proxy_info.get('username') or "",
        proxy_info.get('password') or ""
    )

    (ext_dir / "manifest.json").write_text(manifest_json, encoding="utf-8")
    (ext_dir / "background.js").write_text(background_js, encoding="utf-8")

    return ext_dir


class LocalProxyContext:
    def __init__(self, proxy):
        self.proxy = proxy

    def __enter__(self):
        return self.proxy, None

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def local_proxy_for(proxy):
    return LocalProxyContext(proxy)