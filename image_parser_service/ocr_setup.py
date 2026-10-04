# -*- coding: utf-8 -*-
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.request

PKG_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_TESSDATA = os.path.join(PKG_DIR, "tessdata")

RUS_URL = "https://github.com/tesseract-ocr/tessdata/raw/main/rus.traineddata"
RUS_SHA256 = "681be2c2bead1bc7bd235df88c44e8e60ae73ae866840c0ad4e3b4c247bd37c2"

WINGET_ID = "UB-Mannheim.TesseractOCR"
TESSERACT_CANDIDATES = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
]


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_tesseract():
    found = shutil.which("tesseract")
    if found:
        return found
    for path in TESSERACT_CANDIDATES:
        if os.path.isfile(path):
            return path
    return None


def install_tesseract():
    if shutil.which("winget") is None:
        return False, "winget не найден — установи Tesseract вручную: https://github.com/UB-Mannheim/tesseract/wiki"
    proc = subprocess.run(
        ["winget", "install", "--id", WINGET_ID, "-e", "--silent",
         "--accept-package-agreements", "--accept-source-agreements"],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if proc.returncode != 0:
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-3:]
        return False, "winget завершился с ошибкой (часто нужен запуск от администратора, UAC): " + " | ".join(tail)
    return True, "Tesseract установлен"


def ensure_rus_traineddata(dest_dir=LOCAL_TESSDATA):
    os.makedirs(dest_dir, exist_ok=True)
    target = os.path.join(dest_dir, "rus.traineddata")
    if os.path.isfile(target) and _sha256(target) == RUS_SHA256:
        return target, "уже есть и проверен"

    fd, tmp = tempfile.mkstemp(suffix=".traineddata")
    os.close(fd)
    try:
        urllib.request.urlretrieve(RUS_URL, tmp)
        digest = _sha256(tmp)
        if digest != RUS_SHA256:
            return None, f"контрольная сумма не совпала ({digest[:12]}…), файл отброшен"
        shutil.move(tmp, target)
        return target, "скачан и проверен"
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _has(tessdata, lang):
    return os.path.isfile(os.path.join(tessdata, f"{lang}.traineddata"))


def ensure_eng_traineddata(dest_dir=LOCAL_TESSDATA):
    os.makedirs(dest_dir, exist_ok=True)
    target = os.path.join(dest_dir, "eng.traineddata")
    if os.path.isfile(target):
        return target, "уже есть"
    exe = find_tesseract()
    if exe is None:
        return None, "нет Tesseract, из которого можно взять eng"
    src = os.path.join(os.path.dirname(exe), "tessdata", "eng.traineddata")
    if not os.path.isfile(src):
        return None, f"eng не найден в {os.path.dirname(src)}"
    shutil.copy2(src, target)
    return target, "скопирован из установки Tesseract"


def resolve(require_rus=True):
    exe = find_tesseract()
    if exe is None:
        return None
    system_tessdata = os.path.join(os.path.dirname(exe), "tessdata")
    for tessdata in (LOCAL_TESSDATA, system_tessdata):
        if _has(tessdata, "rus") and _has(tessdata, "eng"):
            return {"cmd": exe, "tessdata": tessdata, "lang": "rus+eng"}
    if require_rus:
        return None
    for tessdata in (LOCAL_TESSDATA, system_tessdata):
        if _has(tessdata, "eng"):
            return {"cmd": exe, "tessdata": tessdata, "lang": "eng"}
    return None


def ensure_all(install=True):
    report = []
    exe = find_tesseract()
    if exe is None and install:
        ok, msg = install_tesseract()
        report.append(("tesseract", ok, msg))
        exe = find_tesseract()
    elif exe is not None:
        report.append(("tesseract", True, f"найден: {exe}"))
    else:
        report.append(("tesseract", False, "не найден (установка отключена --no-install)"))

    if exe is None:
        return None, report

    path, msg = ensure_rus_traineddata()
    report.append(("rus.traineddata", path is not None, msg))
    if path is None:
        return None, report

    eng_path, eng_msg = ensure_eng_traineddata()
    report.append(("eng.traineddata", eng_path is not None, eng_msg))
    if eng_path is None:
        return None, report

    cfg = resolve()
    if cfg is None:
        report.append(("проверка", False, "конфигурация не собралась"))
        return None, report
    report.append(("проверка", True, f"lang={cfg['lang']} tessdata={cfg['tessdata']}"))
    return cfg, report


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    install = "--no-install" not in argv
    cfg, report = ensure_all(install=install)
    for name, ok, msg in report:
        print(f"[{'OK' if ok else 'ERR'}] {name}: {msg}")
    return 0 if cfg else 1


if __name__ == "__main__":
    sys.exit(main())
