"""Check that every marimo notebook cell only asks for variables that exist.

A marimo cell receives the variables it uses from other cells as its
parameters (``def _(ib, bars): ...``), and a cell makes its variables
available by returning them (``return (bars,)``). A parameter that no
cell returns is an error marimo reports only when the notebook runs,
which for the examples means connected to TWS. ``marimo check`` does not
catch it, and ruff cannot, since to ruff a parameter is always defined.

This reads each notebook without running it and reports:

* a cell parameter that no other cell returns and the setup cell does
  not define;
* a variable returned by more than one cell (marimo refuses to run).

Usage::

    uv run python scripts/check_marimo.py examples/notebooks/*.py
"""

from __future__ import annotations

import argparse
import ast
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class Cell:
    line: int
    parameters: tuple[str, ...]
    returns: tuple[str, ...]


def _isCell(decorator: ast.expr) -> bool:
    """``@app.cell`` or ``@app.cell(...)``."""
    target = decorator.func if isinstance(decorator, ast.Call) else decorator
    return (
        isinstance(target, ast.Attribute)
        and target.attr == "cell"
        and isinstance(target.value, ast.Name)
        and target.value.id == "app"
    )


def _returned(function: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, ...]:
    """Names in the cell's final ``return`` (a name or a tuple of names)."""
    last = function.body[-1] if function.body else None
    if not isinstance(last, ast.Return) or last.value is None:
        return ()
    value = last.value
    elements = value.elts if isinstance(value, ast.Tuple) else [value]
    return tuple(e.id for e in elements if isinstance(e, ast.Name))


def _setupNames(statement: ast.With) -> set[str]:
    """Names the ``with app.setup:`` block binds (imports and assignments)."""
    names: set[str] = set()
    for node in ast.walk(statement):
        if isinstance(node, ast.Import | ast.ImportFrom):
            names.update(
                (alias.asname or alias.name).split(".")[0] for alias in node.names
            )
        elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        elif isinstance(node, ast.FunctionDef | ast.ClassDef):
            names.add(node.name)
    return names


def _isSetup(statement: ast.With) -> bool:
    return any(
        isinstance(item.context_expr, ast.Attribute)
        and item.context_expr.attr == "setup"
        for item in statement.items
    )


def problems(path: Path) -> list[str]:
    """Every problem found in the notebook at ``path``, as messages."""
    module = ast.parse(path.read_text(), filename=str(path))
    setup: set[str] = set()
    cells: list[Cell] = []
    for statement in module.body:
        if isinstance(statement, ast.With) and _isSetup(statement):
            setup |= _setupNames(statement)
        elif isinstance(statement, ast.FunctionDef | ast.AsyncFunctionDef) and any(
            _isCell(d) for d in statement.decorator_list
        ):
            parameters = tuple(a.arg for a in statement.args.args)
            cells.append(Cell(statement.lineno, parameters, _returned(statement)))

    found: list[str] = []
    definedBy: dict[str, int] = {}
    for cell in cells:
        for name in cell.returns:
            if name in definedBy:
                found.append(
                    f"{path}:{cell.line}: {name!r} is also returned by the cell "
                    f"at line {definedBy[name]}"
                )
            definedBy.setdefault(name, cell.line)
    for cell in cells:
        for name in cell.parameters:
            if name not in definedBy and name not in setup:
                found.append(
                    f"{path}:{cell.line}: the cell asks for {name!r}, which no "
                    "cell returns and the setup cell does not define"
                )
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("notebooks", nargs="+", type=Path)
    args = parser.parse_args(argv)
    found = [message for path in args.notebooks for message in problems(path)]
    for message in found:
        print(message)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
