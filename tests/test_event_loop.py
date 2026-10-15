"""util.getLoop: the loop of the calling thread, on every Python version."""

from __future__ import annotations

import asyncio
import subprocess
import sys
import textwrap
import threading
from unittest.mock import MagicMock

import pytest
from eventkit.util import get_event_loop

import ib_async as ibi
from ib_async import util


@pytest.fixture
def noThreadLoop():
    """Run with no event loop set for the main thread; restore after."""
    previous = util.getLoop()
    asyncio.set_event_loop(None)
    yield
    current = util.getLoop()
    asyncio.set_event_loop(previous)
    if current is not previous:
        current.close()


def test_getLoop_is_eventkits_loop_for_the_thread(noThreadLoop):
    assert util.getLoop() is get_event_loop()


def test_running_loop_wins():
    async def inner():
        return util.getLoop() is asyncio.get_running_loop()

    loop = asyncio.new_event_loop()
    try:
        assert loop.run_until_complete(inner())
    finally:
        loop.close()


def test_loop_set_for_the_thread_is_used(noThreadLoop):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    assert util.getLoop() is loop


def test_closed_loop_is_replaced(noThreadLoop):
    closed = asyncio.new_event_loop()
    asyncio.set_event_loop(closed)
    closed.close()
    loop = util.getLoop()
    assert loop is not closed and not loop.is_closed()
    assert util.getLoop() is loop


def test_each_thread_gets_its_own_loop():
    main = util.getLoop()
    seen = {}

    def worker():
        seen["loop"] = util.getLoop()
        seen["again"] = util.getLoop()
        asyncio.set_event_loop(None)
        seen["loop"].close()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert seen["loop"] is not main
    assert seen["again"] is seen["loop"]


def test_watchdog_start_without_a_loop_set():
    """Watchdog.start is a sync method; on Python 3.14 a bare
    ``ensure_future`` raises when the thread has no loop set."""
    seen = {}

    def worker():
        ib = MagicMock()
        ib.isConnected.return_value = False
        watchdog = ibi.Watchdog(controller=MagicMock(), ib=ib)
        task = watchdog.start()
        seen["same loop"] = task.get_loop() is util.getLoop()
        task.cancel()
        loop = util.getLoop()
        loop.run_until_complete(asyncio.gather(task, return_exceptions=True))
        asyncio.set_event_loop(None)
        loop.close()

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join()
    assert seen["same loop"]


def test_no_deprecation_warning_importing_and_getting_a_loop():
    """A fresh interpreter's main thread with no loop set is where Python
    3.12 - 3.13 warn and 3.14 refuses to create a loop implicitly."""
    snippet = textwrap.dedent(
        """
        import asyncio
        import ib_async
        from ib_async import util

        loop = util.getLoop()
        assert asyncio.get_event_loop() is loop
        util.run(asyncio.sleep(0))
        loop.close()
        """
    )
    result = subprocess.run(
        [sys.executable, "-W", "error::DeprecationWarning", "-c", snippet],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_startLoop_allows_sync_calls_inside_a_running_loop():
    """What a notebook cell does: a synchronous ib_async call while the
    loop is already running, including a timeout inside the nested run
    (Python 3.14 needs the current-task fix to allow it)."""
    snippet = textwrap.dedent(
        """
        import asyncio
        from ib_async import util

        util.startLoop()


        async def cell():
            return util.run(asyncio.wait_for(asyncio.sleep(0.01, result=42), 1))


        assert asyncio.run(cell()) == 42
        """
    )
    result = subprocess.run(
        [sys.executable, "-W", "error::DeprecationWarning", "-c", snippet],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
