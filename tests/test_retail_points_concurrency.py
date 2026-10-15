# -*- coding: utf-8 -*-
import multiprocessing as mp
import os
import sys

import openpyxl

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

WORKERS = 8
ROUNDS = 3


def _worker(args):
    filename, idx = args
    from parsers_core.utils import update_retail_points
    ok = 0
    for r in range(ROUNDS):
        if update_retail_points(f"Сеть{idx}", "Москва", r + 1, filename=filename):
            ok += 1
    return ok


def test_parallel_writes_are_not_lost(tmp_path):
    filename = str(tmp_path / "retail_points.xlsx")
    ctx = mp.get_context("spawn")
    with ctx.Pool(WORKERS) as pool:
        results = pool.map(_worker, [(filename, i) for i in range(WORKERS)])

    assert all(r == ROUNDS for r in results), results

    wb = openpyxl.load_workbook(filename)
    ws = wb.active
    rows = [(row[2].value, row[3].value, row[4].value) for row in ws.iter_rows(min_row=2, max_col=5)]
    names = sorted(r[0] for r in rows)
    assert names == sorted(f"Сеть{i}" for i in range(WORKERS)), names
    assert all(r[2] == ROUNDS for r in rows), rows
