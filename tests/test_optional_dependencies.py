"""A util function needing a library ib_async does not install says how to
install it."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from ib_async import util


@pytest.mark.parametrize(
    ("call", "install"),
    [
        (lambda: util.pandasDf([]), "pip install pandas"),
        (lambda: util.barplot([]), "pip install matplotlib"),
        (lambda: util.useQt("PyQt6"), "pip install PyQt6"),
    ],
)
def test_a_missing_library_is_named_with_how_to_install_it(
    monkeypatch: pytest.MonkeyPatch, call: Callable[[], object], install: str
) -> None:
    def missing(name: str) -> None:
        raise ImportError(name)

    monkeypatch.setattr(util, "import_module", missing)
    with pytest.raises(
        ImportError, match=f"which ib_async does not install: {install}$"
    ):
        call()
