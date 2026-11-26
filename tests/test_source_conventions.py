"""Conventions of the library's source that no linter checks."""

from __future__ import annotations

import ast
from pathlib import Path

import eventkit
import pytest

import ib_async

PACKAGE = Path(__file__).resolve().parent.parent / "ib_async"
MODULES = sorted([p for p in PACKAGE.rglob("*.py") if "_pb" not in p.parts])
# Every Python file in the repository that is linted: the library, its
# scripts, examples, tests and the docs configuration.
SOURCES = MODULES + sorted(
    [
        p
        for folder in ("scripts", "examples", "tests")
        for p in (PACKAGE.parent / folder).rglob("*.py")
    ]
    + [PACKAGE.parent / "docs" / "conf.py"]
)
# The comment that keeps a generator expression, with the reason after it.
GENERATOR_REASON = "# generator:"


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


@pytest.mark.parametrize(
    "path", SOURCES, ids=lambda p: str(p.relative_to(PACKAGE.parent))
)
def test_finite_data_is_built_with_list_comprehensions(path: Path) -> None:
    """A comprehension that is evaluated whole is a list comprehension, also
    inside ``all``, ``join``, ``tuple`` and the like. ``any`` takes a
    generator, since it stops at the first true item. Any other generator
    expression consumes an unbounded stream, and its line says why with a
    ``# generator:`` comment."""
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    tree = ast.parse(source, str(path))
    anyArgs = {
        id(node.args[0]): node.args[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "any"
        and len(node.args) == 1
    }
    listInAny = [
        f"line {arg.lineno}"
        for arg in anyArgs.values()
        if isinstance(arg, ast.ListComp)
    ]
    unexplained = [
        f"line {node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.GeneratorExp)
        and id(node) not in anyArgs
        and GENERATOR_REASON not in lines[node.lineno - 1]
    ]
    assert not listInAny, f"any() over a list comprehension: {', '.join(listInAny)}"
    assert not unexplained, f"generator expressions: {', '.join(unexplained)}"


@pytest.mark.parametrize(
    "path", SOURCES, ids=lambda p: str(p.relative_to(PACKAGE.parent))
)
def test_no_call_to_next(path: Path) -> None:
    """Nothing calls ``next()``. Code says what it takes instead: an
    unpacking such as ``[only] = items``, a counter, or a loop that stops
    after one item."""
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    calls = [
        f"line {node.lineno}"
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "next"
    ]
    assert not calls, f"next() calls: {', '.join(calls)}"


# Generic types that say nothing without their parameters.
GENERICS = {
    "list", "dict", "set", "frozenset", "tuple", "Awaitable", "Coroutine",
    "Callable", "Iterator", "Iterable", "Sequence", "Mapping", "Future",
}  # fmt: skip


def test_every_public_ib_method_declares_what_it_returns() -> None:
    """Each public method of IB has a return annotation, and none of its
    generic types is bare (``Awaitable`` or ``list`` without parameters)."""
    path = PACKAGE / "ib.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    [ib] = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "IB"]
    unannotated = []
    bare = []
    for node in ib.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        if node.name.startswith("_"):
            continue
        if node.returns is None:
            unannotated.append(f"{node.name} (line {node.lineno})")
            continue
        parameterized = {
            id(n.value) for n in ast.walk(node.returns) if isinstance(n, ast.Subscript)
        }
        if any(
            isinstance(n, ast.Name) and n.id in GENERICS and id(n) not in parameterized
            for n in ast.walk(node.returns)
        ):
            bare.append(f"{node.name} (line {node.lineno})")
    assert not unannotated, f"no return annotation: {', '.join(unannotated)}"
    assert not bare, f"bare generic return types: {', '.join(bare)}"


# Blocking methods whose return type is narrower than their async
# sibling's on purpose.
NARROWER_THAN_ASYNC = {"qualifyContracts"}


def _awaited(returns: ast.expr) -> str:
    """The type an async method's return annotation awaits to."""
    if (
        isinstance(returns, ast.Subscript)
        and isinstance(returns.value, ast.Name)
        and returns.value.id == "Awaitable"
    ):
        return ast.unparse(returns.slice)
    return ast.unparse(returns)


def test_each_blocking_ib_method_returns_what_its_async_sibling_does() -> None:
    """A method that runs ``self._run(self.xAsync(...))`` declares the
    type ``xAsync`` answers."""
    path = PACKAGE / "ib.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    [ib] = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "IB"]
    methods = {
        n.name: n
        for n in ib.body
        if isinstance(n, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    mismatched = []
    for name, method in methods.items():
        sibling = methods.get(f"{name}Async")
        if sibling is None or name in NARROWER_THAN_ASYNC:
            continue
        runs = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "_run"
            for node in ast.walk(method)
        )
        if not runs or method.returns is None or sibling.returns is None:
            continue
        if ast.unparse(method.returns) != _awaited(sibling.returns):
            mismatched.append(
                f"{name} -> {ast.unparse(method.returns)}, "
                f"{name}Async -> {_awaited(sibling.returns)}"
            )
    assert not mismatched, "; ".join(mismatched)


def test_importing_ib_async_patches_no_class():
    """A class has the methods its body defines: importing ib_async adds
    none to the classes it exports or to another library's."""
    classes = [v for v in vars(ib_async).values() if isinstance(v, type)]
    assert eventkit.Event in classes and ib_async.Contract in classes
    for cls in classes:
        for name in ("dict", "tuple", "update", "nonDefaults"):
            assert not hasattr(cls, name), f"{cls.__qualname__}.{name}"
