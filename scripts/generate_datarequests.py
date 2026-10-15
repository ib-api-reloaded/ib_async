"""Generate the data request value types from the catalog.

``ib_async/datarequests/catalog.py`` is the single source of truth for the
values historical and real-time data requests take. This writes, from it,
``ib_async/datarequests/generated.py``: one ``StrEnum`` per family, and
one ``Literal`` per request parameter that accepts the parameter's values
as plain strings and as the enum's members.

``--check`` writes nothing and exits 1 if the file is out of date.

Usage::

    uv run python scripts/generate_datarequests.py [--check]
"""

from __future__ import annotations

import sys

import generating

from ib_async.datarequests.catalog import FAMILIES, PARAMETERS, Family, Parameter

MODULE = generating.ROOT / "ib_async" / "datarequests" / "generated.py"


def enumSource(family: Family) -> str:
    members = "".join(f"    {name} = {value!r}\n" for name, value in family.members)
    return f'\n\nclass {family.name}(StrEnum):\n    """{family.doc}"""\n\n{members}'


def aliasSource(parameter: Parameter) -> str:
    """The parameter's values as strings, its other spellings, then the
    same values as enum members."""
    names = {value: name for name, value in parameter.family.members}
    unknown = [v for v in parameter.values if v not in names]
    if unknown:
        raise SystemExit(f"{parameter.name}: not in {parameter.family.name}: {unknown}")
    strings = [repr(v) for v in (*parameter.values, *parameter.spellings)]
    members = [f"{parameter.family.name}.{names[v]}" for v in parameter.values]
    return (
        f"\n\n#: {parameter.doc}\n"
        f"{parameter.name} = Literal[{', '.join(strings + members)}]\n"
    )


def module() -> str:
    names = [f.name for f in FAMILIES] + [p.name for p in PARAMETERS]
    header = (
        '"""The values historical and real-time data requests take, '
        "generated from\n``catalog.py`` by ``scripts/generate_datarequests.py``. "
        'Do not edit: change\nthe catalog and regenerate."""\n\n'
        "from __future__ import annotations\n\nfrom enum import StrEnum\nfrom typing import Literal\n\n"
        "__all__ = [" + ", ".join(repr(n) for n in sorted(names)) + "]\n"
    )
    source = (
        header
        + "".join(enumSource(f) for f in FAMILIES)
        + "".join(aliasSource(p) for p in PARAMETERS)
    )
    return generating.formatted(source, MODULE)


def main(argv: list[str] | None = None) -> int:
    return generating.main(
        __doc__.split("\n\n")[0],
        "generate_datarequests.py",
        lambda: {MODULE: module()},
        argv,
    )


if __name__ == "__main__":
    sys.exit(main())
