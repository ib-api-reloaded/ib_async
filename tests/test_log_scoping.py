"""``logToFile`` / ``logToConsole`` must configure only the ``ib_async``
logger, never the root logger.

A library that attaches handlers to the root logger captures every log
record in the process — its own plus the application's and every other
third-party library's — which is the "ib_async logging is too aggressive"
complaint. Scoping the handlers to the ``ib_async`` namespace fixes that:
every ib_async module logs under ``ib_async.*``, so a handler on the
``ib_async`` logger still catches all library output while leaving
unrelated records alone. Propagation stays enabled, so an application that
configures the root logger keeps receiving ib_async records too.

These tests pin the scope, the third-party isolation, the idempotent
repeat-call behaviour, and the optional format override.
"""

import logging
import sys

import pytest

import ib_async as ibi


@pytest.fixture(autouse=True)
def _isolate_logging():
    """Snapshot and restore the level and handler set of both the root and
    ``ib_async`` loggers so a test that calls logToFile / logToConsole does
    not leak handlers or level mutations into the rest of the session."""
    loggers = (logging.getLogger(), logging.getLogger("ib_async"))
    saved = {lg: (lg.level, list(lg.handlers)) for lg in loggers}
    try:
        yield
    finally:
        for lg, (level, handlers) in saved.items():
            lg.setLevel(level)
            for h in list(lg.handlers):
                if h not in handlers:
                    lg.removeHandler(h)
                    if isinstance(h, logging.FileHandler):
                        h.close()
            for h in handlers:
                if h not in lg.handlers:
                    lg.addHandler(h)


def _added(logger, before):
    return [h for h in logger.handlers if h not in before]


# ---- logToFile ------------------------------------------------------------


def test_logToFile_attaches_to_ib_async_not_root(tmp_path):
    path = tmp_path / "ib.log"
    root = logging.getLogger()
    ib = logging.getLogger("ib_async")
    root_before = list(root.handlers)
    ib_before = list(ib.handlers)

    ibi.util.logToFile(path)

    added = _added(ib, ib_before)
    assert list(root.handlers) == root_before  # root left untouched
    assert len(added) == 1
    assert isinstance(added[0], logging.FileHandler)
    assert ib.level == logging.INFO


def test_logToFile_writes_only_ib_async_records(tmp_path):
    path = tmp_path / "ib.log"
    ib = logging.getLogger("ib_async")
    ib_before = list(ib.handlers)

    ibi.util.logToFile(path, level=logging.INFO)
    (handler,) = _added(ib, ib_before)

    logging.getLogger("ib_async.sub").info("ib-async-record")
    third = logging.getLogger("third_party")
    third.setLevel(logging.INFO)
    third.info("third-party-record")
    handler.flush()

    contents = path.read_text()
    assert "ib-async-record" in contents
    assert "third-party-record" not in contents


def test_logToFile_is_idempotent_for_same_path(tmp_path):
    path = tmp_path / "ib.log"
    ib = logging.getLogger("ib_async")

    ibi.util.logToFile(path)
    count = len(ib.handlers)
    ibi.util.logToFile(path)  # same path again

    assert len(ib.handlers) == count  # no duplicate handler stacked


def test_logToFile_honours_custom_format(tmp_path):
    path = tmp_path / "ib.log"
    ib = logging.getLogger("ib_async")
    ib_before = list(ib.handlers)

    ibi.util.logToFile(path, fmt="CUSTOMFMT %(message)s")
    (handler,) = _added(ib, ib_before)
    logging.getLogger("ib_async.sub").info("hello")
    handler.flush()

    assert "CUSTOMFMT hello" in path.read_text()


# ---- logToConsole ---------------------------------------------------------


def test_logToConsole_attaches_to_ib_async_not_root():
    root = logging.getLogger()
    ib = logging.getLogger("ib_async")
    root_before = list(root.handlers)
    ib_before = list(ib.handlers)

    ibi.util.logToConsole(level=logging.DEBUG)

    added = _added(ib, ib_before)
    assert list(root.handlers) == root_before
    assert len(added) == 1
    assert isinstance(added[0], logging.StreamHandler)
    assert added[0].stream is sys.stderr
    assert ib.level == logging.DEBUG  # level applied to the ib_async logger


def test_logToConsole_is_idempotent():
    ib = logging.getLogger("ib_async")

    ibi.util.logToConsole()
    count = len(ib.handlers)
    ibi.util.logToConsole()

    assert len(ib.handlers) == count


def test_logToConsole_skips_when_root_already_has_stderr_handler():
    """When root already has a stderr handler (e.g. the app called
    ``logging.basicConfig()``), logToConsole must not add a duplicate to
    ib_async: records propagate up to root, so the existing handler already
    prints them and a second would double-print."""
    root = logging.getLogger()
    ib = logging.getLogger("ib_async")
    ib_before = list(ib.handlers)

    root.addHandler(logging.StreamHandler())  # defaults to sys.stderr

    ibi.util.logToConsole()

    assert _added(ib, ib_before) == []  # nothing added to ib_async
    assert ib.level == logging.INFO  # level still applied
