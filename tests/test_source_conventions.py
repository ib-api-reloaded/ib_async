"""Conventions of the library's source that no linter checks."""

from __future__ import annotations

import ast
from pathlib import Path

import eventkit
import pytest

import ib_async

PACKAGE = Path(__file__).resolve().parent.parent / "ib_async"
MODULES = sorted(p for p in PACKAGE.rglob("*.py") if "_pb" not in p.parts)
# Every Python file in the repository that is linted: the library, its
# scripts, examples and tests.
SOURCES = MODULES + sorted(
    p
    for folder in ("scripts", "examples", "tests")
    for p in (PACKAGE.parent / folder).rglob("*.py")
)


@pytest.mark.parametrize(
    "path", MODULES, ids=lambda p: str(p.relative_to(PACKAGE.parent))
)
def test_no_class_writes_its_own_slots(path: Path) -> None:
    """A class with slots is ``@dataclass(slots=True)``, never one that
    lists ``__slots__`` by hand."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
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


@pytest.mark.parametrize(
    "path", MODULES, ids=lambda p: str(p.relative_to(PACKAGE.parent))
)
def test_no_class_is_changed_after_its_body(path: Path) -> None:
    """A class has what its body defines: no code assigns or ``setattr``s
    an attribute of a class the module defines or of a ``cls``, nor a
    dunder of anything but ``self`` (such as a replaced ``__init__``)."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    patched = []
    for node in ast.walk(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign | ast.AnnAssign):
            targets = [node.target]
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and node.args
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id in classes | {"cls"}
        ):
            patched.append(f"setattr({node.args[0].id}, ...) (line {node.lineno})")
        for target in targets:
            if not (
                isinstance(target, ast.Attribute) and isinstance(target.value, ast.Name)
            ):
                continue
            owner = target.value.id
            dunder = target.attr.startswith("__") and target.attr.endswith("__")
            if owner in classes | {"cls"} or (dunder and owner != "self"):
                patched.append(f"{owner}.{target.attr} (line {node.lineno})")
    assert not patched, f"classes changed after their body: {', '.join(patched)}"


def _runsOnImport(tree: ast.Module) -> list[ast.AST]:
    """The nodes that run when the module is imported: everything outside
    a function or lambda body."""
    found: list[ast.AST] = []
    pending: list[ast.AST] = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.Lambda):
            continue
        found.append(node)
        pending.extend(ast.iter_child_nodes(node))
    return found


@pytest.mark.parametrize(
    "path", MODULES, ids=lambda p: str(p.relative_to(PACKAGE.parent))
)
def test_importing_a_module_sets_no_attribute_of_anything(path: Path) -> None:
    """Code run on import assigns no attribute and calls no ``setattr``,
    on whatever a name holds: a loop over classes (``for obj in ...:
    obj.dict = ...``) or a class imported from elsewhere is patched as
    surely as one the module defines."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    patched = []
    for node in _runsOnImport(tree):
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AugAssign | ast.AnnAssign):
            targets = [node.target]
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
        ):
            patched.append(f"setattr(...) (line {node.lineno})")
        patched += [
            f"{ast.unparse(target)} (line {node.lineno})"
            for target in targets
            if isinstance(target, ast.Attribute)
        ]
    assert not patched, f"attributes set on import: {', '.join(patched)}"


@pytest.mark.parametrize(
    "path", SOURCES, ids=lambda p: str(p.relative_to(PACKAGE.parent))
)
def test_text_files_are_read_and_written_as_utf8(path: Path) -> None:
    """Every read_text, write_text and text-mode open names its encoding.
    Without one, Python uses the locale's code page, which on Windows is
    not UTF-8: a generated file with a non-ASCII character then fails to
    import."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    unnamed = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or any(
            keyword.arg == "encoding" for keyword in node.keywords
        ):
            continue
        func = node.func
        textMethod = isinstance(func, ast.Attribute) and func.attr in (
            "read_text",
            "write_text",
        )
        mode = node.args[1] if len(node.args) > 1 else None
        textOpen = (
            isinstance(func, ast.Name)
            and func.id == "open"
            and not (isinstance(mode, ast.Constant) and "b" in str(mode.value))
        )
        if textMethod or textOpen:
            unnamed.append(f"{ast.unparse(func)} (line {node.lineno})")
    assert not unnamed, f"no encoding named: {', '.join(unnamed)}"


def test_importing_ib_async_patches_no_class():
    """A class has the methods its body defines: importing ib_async adds
    none to the classes it exports or to another library's."""
    classes = [v for v in vars(ib_async).values() if isinstance(v, type)]
    assert eventkit.Event in classes and ib_async.Contract in classes
    for cls in classes:
        for name in ("dict", "tuple", "update", "nonDefaults"):
            assert not hasattr(cls, name), f"{cls.__qualname__}.{name}"
