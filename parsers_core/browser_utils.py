from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from hashlib import sha256
from pathlib import Path
from typing import Optional
from urllib.parse import urlsplit

import platformdirs


def get_cache_dir(app_name: str, env_override_key: Optional[str] = None) -> Path:
    if env_override_key:
        override = os.getenv(env_override_key)
        if override:
            return Path(override).expanduser().resolve()

    return Path(platformdirs.user_cache_dir(app_name, appauthor=False))


def get_chrome_binary(env_override_key: Optional[str] = None) -> Optional[str]:
    if env_override_key:
        override = os.getenv(env_override_key)
        if override:
            return override

    override = os.getenv("CHROME_BINARY")
    if override and os.path.isfile(override):
        return override

    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        path = shutil.which(name)
        if path:
            return path

    if sys.platform == "darwin":
        mac_paths = [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
            os.path.expanduser(
                "~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            ),
        ]
        for p in mac_paths:
            if os.path.isfile(p):
                return p

    elif sys.platform == "win32":
        win_dirs = [
            os.environ.get("PROGRAMFILES", r"C:\Program Files"),
            os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        win_suffixes = [
            r"Google\Chrome\Application\chrome.exe",
            r"Chromium\Application\chrome.exe",
        ]
        for d in win_dirs:
            if not d:
                continue
            for suffix in win_suffixes:
                p = os.path.join(d, suffix)
                if os.path.isfile(p):
                    return p

    return None


def prepare_writable_chromedriver(
    cache_dir: Path,
    env_override_key: Optional[str] = None,
) -> Optional[str]:
    if env_override_key:
        override = os.getenv(env_override_key)
    else:
        override = None
    src = override or shutil.which("chromedriver")
    if not src:
        return None

    uc_dir = cache_dir / "uc"
    uc_dir.mkdir(parents=True, exist_ok=True)

    ext = ".exe" if os.name == "nt" else ""
    dst = uc_dir / f"chromedriver{ext}"

    try:
        shutil.copy2(src, dst)
        if os.name != "nt":
            dst.chmod(0o755)
    except Exception:
        return None

    return str(dst)


def parse_proxy(proxy: Optional[str]) -> Optional[dict]:
    proxy = (proxy or "").strip()
    if not proxy:
        return None

    if "://" not in proxy:
        proxy = "http://" + proxy

    parsed = urlsplit(proxy)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return None

    scheme = (parsed.scheme or "http").lower()
    if scheme in {"http", "https"}:
        scheme = "http"
    if scheme in {"socks5", "socks5h"}:
        scheme = "socks5"

    return {
        "scheme": scheme,
        "host": host,
        "port": int(port),
        "username": parsed.username,
        "password": parsed.password,
    }


def ensure_proxy_auth_extension(
    proxy_info: dict,
    cache_dir: Path,
    ext_name: str = "Proxy Auth",
) -> Path:
    digest = sha256(
        f"{proxy_info.get('scheme')}|{proxy_info.get('host')}|{proxy_info.get('port')}|"
        f"{proxy_info.get('username')}|{proxy_info.get('password')}".encode("utf-8")
    ).hexdigest()[:16]

    ext_dir = cache_dir / "proxy_auth_ext" / digest
    ext_dir.mkdir(parents=True, exist_ok=True)

    username = proxy_info.get("username") or ""
    password = proxy_info.get("password") or ""
    host = proxy_info["host"]
    port = int(proxy_info["port"])
    scheme = proxy_info.get("scheme") or "http"

    manifest = {
        "name": ext_name,
        "version": "1.0.0",
        "manifest_version": 3,
        "permissions": ["proxy", "storage", "webRequest", "webRequestAuthProvider"],
        "host_permissions": ["<all_urls>"],
        "background": {"service_worker": "background.js"},
        "minimum_chrome_version": "108.0.0",
    }

    (ext_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    background_js = f"""
const config = {{
  mode: "fixed_servers",
  rules: {{
    singleProxy: {{
      scheme: "{scheme}",
      host: "{host}",
      port: {port},
    }},
    bypassList: ["localhost", "127.0.0.1"],
  }},
}};

chrome.proxy.settings.set({{ value: config, scope: "regular" }}, () => {{}});

chrome.webRequest.onAuthRequired.addListener(
  (details) => {{
    return {{
      authCredentials: {{
        username: {json.dumps(username)},
        password: {json.dumps(password)},
      }},
    }};
  }},
  {{ urls: ["<all_urls>"] }},
  ["blocking"]
);
""".lstrip()

    (ext_dir / "background.js").write_text(background_js, encoding="utf-8")

    return ext_dir


def _detect_chrome_version_win(chrome_binary: Optional[str]) -> Optional[int]:
    """Определение версии Chrome на Windows через реестр и file version."""
    # 1) Реестр — самый надёжный способ
    reg_keys = [
        r"HKEY_CURRENT_USER\Software\Google\Chrome\BLBeacon",
        r"HKEY_LOCAL_MACHINE\Software\Google\Chrome\BLBeacon",
        r"HKEY_LOCAL_MACHINE\Software\Wow6432Node\Google\Chrome\BLBeacon",
    ]
    for key in reg_keys:
        try:
            proc = subprocess.run(
                ["reg", "query", key, "/v", "version"],
                capture_output=True, text=True, timeout=5, check=False,
                encoding="utf-8", errors="replace",
            )
            if proc.returncode == 0:
                m = re.search(r"(\d+)\.\d+\.\d+\.\d+", proc.stdout)
                if m:
                    return int(m.group(1))
        except Exception:
            continue

    # 2) File version через PowerShell
    if chrome_binary:
        ps_cmd = (
            f'(Get-Item "{chrome_binary}").VersionInfo.FileVersion'
        )
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=10, check=False,
                encoding="utf-8", errors="replace",
            )
            m = re.search(r"(\d+)\.\d+\.\d+\.\d+", proc.stdout)
            if m:
                return int(m.group(1))
        except Exception:
            pass

    return None


def detect_chrome_version_main(
    chrome_binary: Optional[str],
    env_override_key: Optional[str] = None,
) -> Optional[int]:
    if env_override_key:
        override = os.getenv(env_override_key)
        if override:
            try:
                return int(override)
            except ValueError:
                return None

    # Windows: chrome.exe --version не работает, используем реестр/powershell
    if sys.platform == "win32":
        return _detect_chrome_version_win(chrome_binary)

    if not chrome_binary:
        return None

    try:
        proc = subprocess.run(
            [chrome_binary, "--version"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
            encoding="utf-8",
            errors="replace",
        )
    except Exception:
        return None

    text = (proc.stdout or proc.stderr or "").strip()
    match = re.search(r"\b(\d+)\.", text)
    if not match:
        return None

    try:
        return int(match.group(1))
    except ValueError:
        return None


def is_forbidden_ban(html: str) -> bool:
    """Моментальное определение CDN/Akamai Forbidden-бана по HTML.

    Страница-бан содержит «Forbidden» + «if you are not a bot» или «origin:».
    Такой бан не решается капчей — нужно менять прокси.
    """
    if not html:
        return False
    lowered = html.lower()
    return "forbidden" in lowered and (
        "if you are not a bot" in lowered or "origin:" in lowered
    )
