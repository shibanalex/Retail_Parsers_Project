# -*- coding: utf-8 -*-
import glob
import importlib
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _entry_modules():
    mods = []
    for pkg_dir in sorted(glob.glob(os.path.join(ROOT, "*_parser"))):
        pkg = os.path.basename(pkg_dir)
        for path in sorted(glob.glob(os.path.join(pkg_dir, "*.py"))):
            name = os.path.splitext(os.path.basename(path))[0]
            if name == "__init__":
                continue
            mods.append(f"{pkg}.{name}")
    return mods


@pytest.mark.parametrize("module", _entry_modules())
def test_module_imports(module):
    importlib.import_module(module)


@pytest.mark.parametrize("pkg", sorted(os.path.basename(p) for p in glob.glob(os.path.join(ROOT, "*_parser"))))
def test_browser_has_get_browser(pkg):
    path = os.path.join(ROOT, pkg, "browser.py")
    if not os.path.exists(path):
        pytest.skip("пакет без браузера")
    mod = importlib.import_module(f"{pkg}.browser")
    assert callable(getattr(mod, "get_browser", None))
