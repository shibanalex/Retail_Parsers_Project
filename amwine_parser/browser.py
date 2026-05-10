import os
import re
import shutil
import subprocess
import undetected_chromedriver as uc


def _get_chrome_major_version() -> int | None:
    """
    Читает major-версию Chrome из бинарного файла (не из реестра Windows).
    Реестр может содержать устаревшую запись о незавершённом обновлении —
    именно это заставляет UC скачивать chromedriver неправильной версии.
    """
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]
    for path in chrome_paths:
        if not os.path.exists(path):
            continue
        try:
            result = subprocess.run(
                f'powershell -NoProfile -Command '
                f'"(Get-Item \'{path}\').VersionInfo.FileVersion"',
                capture_output=True, text=True, shell=True, timeout=10
            )
            ver = result.stdout.strip()
            m = re.match(r"(\d+)", ver)
            if m:
                major = int(m.group(1))
                print(f"[WineStreet] 🌐 Chrome major (из файла): {major}")
                return major
        except Exception:
            pass
    return None


def get_browser():
    options = uc.ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-notifications")
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')

    base_dir = os.path.dirname(os.path.abspath(__file__))
    profile_dir = os.path.join(base_dir, "profile")
    options.add_argument(f"--user-data-dir={profile_dir}")

    # Вариант 2: указываем UC системный chromedriver напрямую.
    # Это предотвращает загрузку UC собственного драйвера по версии из реестра
    # (реестр может показывать 148 при фактическом Chrome 147).
    system_driver = shutil.which("chromedriver")
    chrome_major  = _get_chrome_major_version()

    if system_driver:
        print(f"[WineStreet] 🛠️ Используем системный chromedriver: {system_driver}")
    else:
        print("[WineStreet] ⚠️ chromedriver не найден в PATH — UC будет скачивать сам")

    try:
        driver = uc.Chrome(
            options=options,
            driver_executable_path=system_driver,   # системный драйвер, а не UC-кэш
            version_main=chrome_major,               # страховка: major из файла chrome.exe
        )
    except Exception:
        # Fallback: без явного пути, UC определяет сам
        driver = uc.Chrome(options=options, version_main=chrome_major)

    driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
        "source": """
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            window.navigator.chrome = { runtime: {} };
            Object.defineProperty(navigator, 'languages', { get: () => ['ru-RU', 'ru', 'en-US', 'en'] });
            Object.defineProperty(navigator, 'plugins',   { get: () => [1, 2, 3] });
        """
    })

    return driver
