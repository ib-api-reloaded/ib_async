"""util.useQt runs Qt's event loop with each library's own exec name."""

from __future__ import annotations

from types import SimpleNamespace
from typing import ClassVar

import pytest

from ib_async import util


class FakeEventLoop:
    calls: ClassVar[list[str]] = []

    def exec(self):
        FakeEventLoop.calls.append("exec")

    def exec_(self):
        FakeEventLoop.calls.append("exec_")

    def quit(self):
        pass


class FakeTimer:
    def __init__(self):
        self.timeout = SimpleNamespace(connect=lambda slot: None)

    def start(self, msec):
        pass

    def stop(self):
        pass


class FakeApp:
    @staticmethod
    def instance():
        return SimpleNamespace(processEvents=lambda: None)


@pytest.mark.parametrize(
    ("qtLib", "called"),
    [("PyQt5", "exec_"), ("PySide2", "exec_"), ("PyQt6", "exec"), ("PySide6", "exec")],
)
def test_qt6_libraries_use_exec(monkeypatch, qtLib, called):
    modules = {
        f"{qtLib}.QtCore": SimpleNamespace(QEventLoop=FakeEventLoop, QTimer=FakeTimer),
        f"{qtLib}.QtWidgets": SimpleNamespace(QApplication=FakeApp),
    }
    monkeypatch.setattr(util, "import_module", modules.__getitem__)
    FakeEventLoop.calls = []
    util.useQt(qtLib, period=3600)
    assert FakeEventLoop.calls == [called]


def test_use_qt_without_qt_says_how_to_get_it(monkeypatch):
    def missing(name: str) -> None:
        raise ImportError(name)

    monkeypatch.setattr(util, "import_module", missing)
    with pytest.raises(ImportError, match="requires PySide6.*: pip install PySide6"):
        util.useQt("PySide6")
