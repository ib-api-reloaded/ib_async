"""``scripts/check_marimo.py`` finds cell parameters no cell defines."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def checker():
    path = ROOT / "scripts" / "check_marimo.py"
    spec = importlib.util.spec_from_file_location("check_marimo", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve their module through sys.modules
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


NOTEBOOK = """\
import marimo

app = marimo.App()

with app.setup:
    import marimo as mo

    from ib_async import IB, util

    PORT = 7497


@app.cell
async def _():
    ib = IB()
    await ib.connectAsync("127.0.0.1", PORT)
    return (ib,)


@app.cell
async def _(ib):
    bars = await ib.reqHistoricalDataAsync(None, "", "1 D", "1 hour", "TRADES", True)
    return (bars,)


@app.cell
def _(BARS_PARAMETER):
    mo.md(str(util.df(BARS_PARAMETER)))
    return
"""


def write(tmp_path: Path, source: str) -> Path:
    path = tmp_path / "notebook.py"
    path.write_text(source)
    return path


def test_a_consistent_notebook_has_no_problems(checker, tmp_path):
    path = write(tmp_path, NOTEBOOK.replace("BARS_PARAMETER", "bars"))
    assert checker.problems(path) == []


def test_a_parameter_no_cell_returns(checker, tmp_path):
    path = write(tmp_path, NOTEBOOK.replace("BARS_PARAMETER", "barz"))
    [problem] = checker.problems(path)
    assert "'barz'" in problem
    assert "no cell returns" in problem


def test_a_variable_returned_by_two_cells(checker, tmp_path):
    source = NOTEBOOK.replace("BARS_PARAMETER", "bars").replace(
        "return (bars,)", "return (bars, ib)"
    )
    [problem] = checker.problems(write(tmp_path, source))
    assert "'ib' is also returned" in problem


def test_the_examples_notebooks_are_consistent(checker):
    notebooks = sorted((ROOT / "examples" / "notebooks").glob("*.py"))
    assert notebooks
    assert [p for path in notebooks for p in checker.problems(path)] == []


def test_main_exit_code(checker, tmp_path, capsys):
    good = write(tmp_path, NOTEBOOK.replace("BARS_PARAMETER", "bars"))
    assert checker.main([str(good)]) == 0
    bad = write(tmp_path, NOTEBOOK.replace("BARS_PARAMETER", "barz"))
    assert checker.main([str(bad)]) == 1
    assert "'barz'" in capsys.readouterr().out
