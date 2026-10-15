"""Internal protobuf integration layer.

Hand-written converters that translate IBKR protobuf messages to and
from our existing domain dataclasses (``Contract``, ``Order``,
``Trade``, etc.). Stays internal; nothing here is part of the public
``ib_async`` API surface.

The converter modules import the generated ``ib_async._pb`` bindings,
so they load on first use rather than with ``import ib_async``. The
client and decoder import this package once (as ``_converters``) and
reach a converter as ``_converters.<module>.<function>``; each module is
imported the first time it is accessed (PEP 562). ``import ib_async``
therefore stays fast and works where the bindings have not been
generated (documentation builds, tooling).
"""

from __future__ import annotations

from importlib import import_module
from types import ModuleType
from typing import TYPE_CHECKING

__all__ = [
    "accounts",
    "contracts",
    "historical",
    "market_data",
    "news",
    "orders",
    "rest",
    "safe",
    "scanner",
]

_MODULES = frozenset(__all__)

if TYPE_CHECKING:
    from . import (
        accounts,
        contracts,
        historical,
        market_data,
        news,
        orders,
        rest,
        safe,
        scanner,
    )


def __getattr__(name: str) -> ModuleType:
    if name in _MODULES:
        # import_module also binds the submodule on this package, so later
        # accesses are plain attribute lookups that never reach here.
        return import_module(f"{__name__}.{name}")
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
