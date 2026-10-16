"""Conventions of the library's source that no linter checks."""

from __future__ import annotations

import ast
from pathlib import Path

import eventkit
import pytest

import ib_async

PACKAGE = Path(__file__).resolve().parent.parent / "ib_async"
MODULES = sorted(p for p in PACKAGE.rglob("*.py") if "_pb" not in p.parts)


@pytest.mark.parametrize(
    "path", MODULES, ids=lambda p: str(p.relative_to(PACKAGE.parent))
)
def test_no_class_writes_its_own_slots(path: Path) -> None:
    """A class with slots is ``@dataclass(slots=True)``, never one that
    lists ``__slots__`` by hand."""
    tree = ast.parse(path.read_text(), str(path))
    manual = [
        f"{node.name} (line {node.lineno})"
        for node in ast.walk(tree)
        if isinstance(node, ast.ClassDef)
        for statement in node.body
        if isinstance(statement, ast.Assign | ast.AnnAssign)
        and any(
            isinstance(target, ast.Name) and target.id == "__slots__"
            for target in (
                statement.targets
                if isinstance(statement, ast.Assign)
                else [statement.target]
            )
        )
    ]
    assert not manual, f"hand-written __slots__: {', '.join(manual)}"


def test_importing_ib_async_patches_no_class():
    """A class has the methods its body defines: importing ib_async adds
    none to its own classes or to another library's."""
    for name in ("dict", "tuple", "update", "nonDefaults"):
        assert not hasattr(eventkit.Event, name)
        assert not hasattr(ib_async.Contract, name)
        assert not hasattr(ib_async.Order, name)
