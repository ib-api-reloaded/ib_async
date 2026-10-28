"""How tests get event loops, and a check that no test drops a failure.

An application runs one event loop for everything. Tests run in one of two
modes, chosen by pytest-asyncio's ``asyncio_default_test_loop_scope``:

* ``function`` (the default, set in pyproject.toml): isolated. Each async
  test runs on a loop of its own from pytest-asyncio. Each sync test gets a
  fresh loop, set as the thread's loop, and closed at its teardown. Nothing
  a test leaves on a loop reaches another test.
* ``session`` (``LOOP=shared`` with a make test target): shared, as in an
  application.
  Sync and async tests run on one loop for the whole session. Callbacks and
  tasks a test leaves on the loop reach the tests after it, so a test that
  leaves a task it started still pending fails.
  ``asyncio_default_fixture_loop_scope`` must then be ``session`` too.

In both modes, asyncio's report that the exception of a future or task was
never retrieved fails the test during which it arrives. An application's
loop reports the same thing as an error, and an interactive one shows it as
a crash. At teardown the test's loop runs its pending callbacks, so a
future that only a pending callback still holds is freed in the test that
dropped it. With reference counting (CPython) that is exact. Without it
(PyPy) a dropped future is freed whenever the garbage collector runs, so
its report can arrive in a later test; a collection at the end of the
session catches what is left.
"""

from __future__ import annotations

import asyncio
import gc
import logging
from collections.abc import Callable, Iterator, Mapping

import pytest

SHARED = "session"
# Loop steps at teardown: enough for a done callback to schedule another
# callback and for that one to run too.
DRAIN_STEPS = 3

_sharedLoop = pytest.StashKey[asyncio.AbstractEventLoop]()


class UnreadFailures(logging.Handler):
    """Collects asyncio's reports of an exception nobody retrieved."""

    def __init__(self) -> None:
        super().__init__(logging.ERROR)
        self.reports: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        message = record.getMessage()
        if "exception was never retrieved" in message:
            self.reports.append(message)

    def take(self) -> list[str]:
        """Return the reports collected so far and start over."""
        reports, self.reports = self.reports, []
        return reports


unread = UnreadFailures()


class SharedLoop:
    """Gives pytest-asyncio the shared loop, so async tests run on the
    loop the sync tests use."""

    def __init__(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def get(self) -> asyncio.AbstractEventLoop:
        return self.loop

    @pytest.hookimpl
    def pytest_asyncio_loop_factories(
        self, config: pytest.Config, item: pytest.Item
    ) -> Mapping[str, Callable[[], asyncio.AbstractEventLoop]]:
        return {"shared": self.get}


def pytest_configure(config: pytest.Config) -> None:
    logging.getLogger("asyncio").addHandler(unread)
    if config.getini("asyncio_default_test_loop_scope") != SHARED:
        return
    if config.getini("asyncio_default_fixture_loop_scope") != SHARED:
        raise pytest.UsageError(
            "a shared loop needs asyncio_default_fixture_loop_scope=session "
            "as well as asyncio_default_test_loop_scope=session"
        )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    config.stash[_sharedLoop] = loop
    config.pluginmanager.register(SharedLoop(loop), "shared-event-loop")


def pytest_unconfigure(config: pytest.Config) -> None:
    logging.getLogger("asyncio").removeHandler(unread)
    loop = config.stash.get(_sharedLoop, None)
    if loop is not None and not loop.is_closed():
        loop.close()


def drain(loop: asyncio.AbstractEventLoop) -> None:
    """Run the callbacks pending on ``loop``."""
    if loop.is_closed() or loop.is_running():
        return
    for _ in range(DRAIN_STEPS):
        loop.run_until_complete(asyncio.sleep(0))


def failure(reports: list[str]) -> str:
    return (
        f"asyncio reported {len(reports)} exception(s) nobody retrieved, "
        "from a future or task dropped by this test or, without reference "
        "counting, by an earlier one. Run with PYTHONASYNCIODEBUG=1 to see "
        "where each was created.\n\n" + "\n\n".join(reports)
    )


@pytest.fixture(autouse=True)
def _loopHygiene(request: pytest.FixtureRequest) -> Iterator[None]:
    shared = request.config.stash.get(_sharedLoop, None)
    isAsync = request.node.get_closest_marker("asyncio") is not None
    own: asyncio.AbstractEventLoop | None = None
    if shared is None and not isAsync:
        own = asyncio.new_event_loop()
        asyncio.set_event_loop(own)
    tasksBefore = asyncio.all_tasks(shared) if shared is not None else set()
    # Reports that arrived between tests belong to an earlier test.
    earlier = unread.take()
    yield
    # pytest-asyncio has already closed an isolated async test's loop, and
    # cancelled the tasks left on it.
    loop = own or shared
    if loop is not None:
        if shared is not None and loop.is_closed():
            pytest.fail("the test closed the shared event loop", pytrace=False)
        drain(loop)
    if own is not None:
        own.close()
        asyncio.set_event_loop(None)
    reports = earlier + unread.take()
    if reports:
        pytest.fail(failure(reports), pytrace=False)
    if shared is not None:
        left = asyncio.all_tasks(shared) - tasksBefore
        if left:
            pytest.fail(
                f"the test left {len(left)} task(s) pending on the shared loop, "
                "where they run on into later tests:\n"
                + "\n".join(repr(task) for task in left),
                pytrace=False,
            )


_leftover = pytest.StashKey[list[str]]()


@pytest.hookimpl(tryfirst=True)
def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    gc.collect()
    reports = unread.take()
    session.config.stash[_leftover] = reports
    if reports:
        session.exitstatus = pytest.ExitCode.TESTS_FAILED


def pytest_terminal_summary(
    terminalreporter: pytest.TerminalReporter, config: pytest.Config
) -> None:
    reports = config.stash.get(_leftover, [])
    if reports:
        terminalreporter.section("exceptions nobody retrieved", red=True)
        terminalreporter.write_line(failure(reports))
