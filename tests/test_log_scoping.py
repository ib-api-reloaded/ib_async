"""logToFile and logToConsole must attach their handlers to the
``ib_async`` logger rather than to root, so an application's other log
records (or library logs from unrelated packages) are not silently teed
into the ib_async-configured destinations.

The ib_insync v0.9.67 changelog entry (``docs/changelog.rst:437``,
ib_insync issue #361) referenced this concern but only addressed the
level-pollution side. Handler attachment was left on root, which these
tests pin down.
"""

import logging
import sys

import pytest

import ib_async as ibi


@pytest.fixture(autouse=True)
def _restore_logger_levels():
    """Snapshot and restore the root and ib_async logger levels so a test
    that calls logToFile/logToConsole (both of which setLevel) does not leak
    its level mutation into the rest of the session."""
    root = logging.getLogger()
    ib_logger = logging.getLogger("ib_async")
    root_level = root.level
    ib_level = ib_logger.level
    try:
        yield
    finally:
        root.setLevel(root_level)
        ib_logger.setLevel(ib_level)


def test_logToFile_attaches_handler_to_ib_async_only(tmp_path):
    """The FileHandler should land on the ib_async logger and not on
    root, so records from unrelated loggers are not written to the file."""
    path = tmp_path / "ib.log"
    root = logging.getLogger()
    ib_logger = logging.getLogger("ib_async")
    root_before = list(root.handlers)
    ib_before = list(ib_logger.handlers)

    ibi.util.logToFile(path)
    added = [h for h in ib_logger.handlers if h not in ib_before]
    try:
        assert list(root.handlers) == root_before
        assert len(added) == 1
        assert isinstance(added[0], logging.FileHandler)

        logging.getLogger("ib_async.test").info("ib-async-record")
        third = logging.getLogger("third_party")
        third.setLevel(logging.INFO)
        third.info("third-party-record")
        for h in added:
            h.flush()

        contents = path.read_text()
        assert "ib-async-record" in contents
        assert "third-party-record" not in contents
    finally:
        for h in added:
            ib_logger.removeHandler(h)
            h.close()


def test_logToFile_skips_duplicate_handler_on_repeat_call(tmp_path):
    """A second call to logToFile with the same path must not add a
    duplicate file handler to the ib_async logger."""
    path = tmp_path / "ib.log"
    ib_logger = logging.getLogger("ib_async")
    ib_before = list(ib_logger.handlers)
    added: list[logging.Handler] = []
    try:
        ibi.util.logToFile(path)
        added = [h for h in ib_logger.handlers if h not in ib_before]
        first_count = len(ib_logger.handlers)

        ibi.util.logToFile(path)
        assert len(ib_logger.handlers) == first_count
    finally:
        for h in added:
            ib_logger.removeHandler(h)
            h.close()


def test_logToConsole_attaches_handler_to_ib_async_only():
    """The StreamHandler should land on the ib_async logger and not on
    root."""
    root = logging.getLogger()
    ib_logger = logging.getLogger("ib_async")
    root_before = list(root.handlers)
    ib_before = list(ib_logger.handlers)

    ibi.util.logToConsole()
    added = [h for h in ib_logger.handlers if h not in ib_before]
    try:
        assert list(root.handlers) == root_before
        assert len(added) == 1
        assert isinstance(added[0], logging.StreamHandler)
        assert added[0].stream is sys.stderr
    finally:
        for h in added:
            ib_logger.removeHandler(h)


def test_logToConsole_skips_duplicate_handler_on_repeat_call():
    """A second call to logToConsole must not add a duplicate stderr
    handler to the ib_async logger."""
    ib_logger = logging.getLogger("ib_async")
    ib_before = list(ib_logger.handlers)
    added: list[logging.Handler] = []
    try:
        ibi.util.logToConsole()
        added = [h for h in ib_logger.handlers if h not in ib_before]
        first_count = len(ib_logger.handlers)

        ibi.util.logToConsole()
        assert len(ib_logger.handlers) == first_count
    finally:
        for h in added:
            ib_logger.removeHandler(h)


def test_logToConsole_skips_when_root_already_has_stderr_handler():
    """When root already has a stderr handler, logToConsole must not add
    a duplicate to ib_async (records propagate up to root, so the existing
    handler will already print them)."""
    root = logging.getLogger()
    ib_logger = logging.getLogger("ib_async")
    root_before = list(root.handlers)
    ib_before = list(ib_logger.handlers)

    user_handler = logging.StreamHandler()  # defaults to sys.stderr
    root.addHandler(user_handler)
    try:
        ibi.util.logToConsole()
        ib_added = [h for h in ib_logger.handlers if h not in ib_before]
        assert ib_added == []
        assert list(root.handlers) == root_before + [user_handler]
    finally:
        root.removeHandler(user_handler)
