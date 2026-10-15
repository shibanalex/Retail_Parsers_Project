# -*- coding: utf-8 -*-
import os


def dump_debug(debug_dir, label, text, ext=".html"):
    """Сырой ответ в файл, только при debug_mode."""
    if not debug_dir:
        return
    os.makedirs(debug_dir, exist_ok=True)
    try:
        with open(os.path.join(debug_dir, f"{label}{ext}"), "w", encoding="utf-8") as f:
            f.write(text or "")
    except OSError:
        pass
