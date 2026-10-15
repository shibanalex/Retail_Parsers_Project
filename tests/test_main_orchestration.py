# -*- coding: utf-8 -*-
import importlib
import os
import sys

import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

FAKES = {
    "https://ok.test/": "tests.fake_parsers.fake_ok",
    "https://slow.test/": "tests.fake_parsers.fake_slow",
    "https://fail.test/": "tests.fake_parsers.fake_fail",
    "https://empty.test/": "tests.fake_parsers.fake_empty",
}


@pytest.fixture
def main_mod(tmp_path, monkeypatch):
    import main
    funcs = {url: importlib.import_module(mod) for url, mod in FAKES.items()}
    monkeypatch.setattr(main, "parsers", {**{u: u for u in FAKES}, "https://nofunc.test/": "Нет"})
    monkeypatch.setattr(main, "parsers_funcs", funcs)
    monkeypatch.setattr(main, "OUTPUT_DIR", str(tmp_path / "out"))
    monkeypatch.setattr(main, "LOG_DIR", str(tmp_path / "log"))
    monkeypatch.setattr(main, "table_name", "test_run")
    os.makedirs(main.OUTPUT_DIR, exist_ok=True)
    return main


def test_start_collects_and_logs(main_mod):
    main_mod.start()
    files = [f for f in os.listdir(main_mod.OUTPUT_DIR) if f.endswith(".xlsx")]
    assert len(files) == 1, files
    df = pd.read_excel(os.path.join(main_mod.OUTPUT_DIR, files[0]))
    log_dir = main_mod.LOG_DIR
    log_text = open(os.path.join(log_dir, os.listdir(log_dir)[0]), encoding="utf-8").read()

    assert len(df) == 4
    assert sorted(df["Сеть"].unique()) == ["ФейкМедл", "ФейкОК"]
    assert "Ошибка 403" in log_text and "https://fail.test/" in log_text
    assert "https://empty.test/: ⚠️ Нет данных" in log_text
    assert "https://nofunc.test/: ❌ Нет функции парсера" in log_text
