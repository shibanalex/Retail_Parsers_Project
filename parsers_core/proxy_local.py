import os
import shutil
import socket
import subprocess
import time
from contextlib import contextmanager
from urllib.parse import urlsplit


PROXY_SERVER_JS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "proxy-server.js")


def _pick_free_port() -> int:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def _parse_proxy_url(proxy_url: str | None) -> dict | None:
    proxy_url = (proxy_url or "").strip()
    if not proxy_url:
        return None
    if "://" not in proxy_url:
        proxy_url = "http://" + proxy_url
    parsed = urlsplit(proxy_url)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return None
    scheme = (parsed.scheme or "http").lower()
    return {
        "scheme": scheme,
        "host": host,
        "port": int(port),
        "username": parsed.username,
        "password": parsed.password,
    }


def _wait_for_port(port: int, timeout_s: float = 5.0) -> bool:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.settimeout(0.3)
            sock.connect(("127.0.0.1", port))
            return True
        except Exception:
            time.sleep(0.1)
        finally:
            sock.close()
    return False


@contextmanager
def local_proxy_for(proxy_url: str | None):
    info = _parse_proxy_url(proxy_url)
    if not info:
        yield proxy_url, None
        return

    if not (info.get("username") and info.get("password")):
        yield proxy_url, None
        return

    local_port = _pick_free_port()

    node_bin = shutil.which("node")
    if not node_bin:
        raise RuntimeError(
            "Node.js не найден в PATH. Установите Node.js: https://nodejs.org/ "
            "Или укажите путь через переменную окружения NODE_BIN."
        )

    cmd = [os.getenv("NODE_BIN", node_bin), PROXY_SERVER_JS]
    if info["scheme"] in {"socks5", "socks5h"}:
        cmd.append("socks5")
    cmd.extend(
        [
            info["host"],
            str(info["port"]),
            info["username"],
            info["password"],
            str(local_port),
        ]
    )

    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    try:
        if not _wait_for_port(local_port, timeout_s=5.0):
            raise RuntimeError("Local proxy did not start in time")
        local_proxy = f"http://127.0.0.1:{local_port}"
        yield local_proxy, proc
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=3)
            except Exception:
                proc.kill()
