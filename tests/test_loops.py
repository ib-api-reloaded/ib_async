"""tests/_loops.py: which loop each test gets, and the check that fails a
test that drops a failure nobody read.

Each test runs pytest in a subprocess on the test file below, with the
plugin and the loop scope under test.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REFCOUNTED = sys.implementation.name == "cpython"

TESTS = """
import asyncio

from ib_async.util import getLoop

# The loops themselves, not their ids: an id is unique only while its
# object lives, and a closed loop's id can be reused by the next one.
loops = []


def test_sync_first():
    loops.append(getLoop())


async def test_async():
    loops.append(asyncio.get_running_loop())


def test_sync_second():
    loops.append(getLoop())


def test_loops():
    distinct = len({id(loop) for loop in loops})
    print(f"LOOPS distinct={distinct} of={len(loops)}")


def test_drops_a_failure():
    loop = getLoop()
    future = loop.create_future()
    future.set_exception(ConnectionError("dropped by a sync test"))
    # Only the pending callback holds it.
    loop.call_soon(id, future)


async def test_async_drops_a_failure():
    future = asyncio.get_running_loop().create_future()
    future.set_exception(ConnectionError("dropped by an async test"))


def test_reads_its_failure():
    loop = getLoop()
    future = loop.create_future()
    future.set_exception(ConnectionError("read"))
    loop.call_soon(id, future)
    assert isinstance(future.exception(), ConnectionError)


async def test_leaves_a_task_pending():
    asyncio.ensure_future(asyncio.sleep(3600))


def test_closes_the_thread_loop():
    getLoop().close()
"""


@dataclass(frozen=True, slots=True)
class Run:
    returncode: int
    output: str

    def outcomes(self, name: str) -> set[str]:
        """The outcomes pytest listed for test ``name`` with -rA. A test
        whose call passed and whose teardown failed is listed as both
        PASSED and ERROR."""
        listed = rf"^(PASSED|FAILED|ERROR) [^\n]*::{name}\b"
        found = set(re.findall(listed, self.output, re.MULTILINE))
        assert found, self.output
        return found


def run(tmp: Path, testScope: str, fixtureScope: str | None = None) -> Run:
    (tmp / "test_inner.py").write_text(TESTS)
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "tests._loops",
        "-p",
        "no:cacheprovider",
        "-o",
        "asyncio_mode=auto",
        "-o",
        f"asyncio_default_test_loop_scope={testScope}",
        "-o",
        f"asyncio_default_fixture_loop_scope={fixtureScope or testScope}",
        "-s",
        "-rA",
        "test_inner.py",
    ]
    # Only what this run is given: no arguments or plugins from the outer run.
    env = {**os.environ, "PYTHONPATH": str(ROOT)}
    for name in ("PYTHONASYNCIODEBUG", "PYTEST_ADDOPTS", "PYTEST_PLUGINS"):
        env.pop(name, None)
    done = subprocess.run(
        command, cwd=tmp, env=env, capture_output=True, text=True, check=False
    )
    return Run(done.returncode, done.stdout + done.stderr)


@pytest.fixture(scope="module")
def isolated(tmp_path_factory: pytest.TempPathFactory) -> Run:
    return run(tmp_path_factory.mktemp("isolated"), "function")


@pytest.fixture(scope="module")
def shared(tmp_path_factory: pytest.TempPathFactory) -> Run:
    return run(tmp_path_factory.mktemp("shared"), "session")


def test_isolated_tests_each_get_a_loop_of_their_own(isolated: Run) -> None:
    assert "LOOPS distinct=3 of=3" in isolated.output, isolated.output


def test_shared_tests_all_run_on_one_loop(shared: Run) -> None:
    assert "LOOPS distinct=1 of=3" in shared.output, shared.output


@pytest.mark.parametrize("mode", ["isolated", "shared"])
def test_a_test_that_drops_a_failure_fails(
    mode: str, request: pytest.FixtureRequest
) -> None:
    result: Run = request.getfixturevalue(mode)
    assert result.returncode == 1, result.output
    assert "exception(s) nobody retrieved" in result.output
    assert "dropped by a sync test" in result.output
    assert "dropped by an async test" in result.output
    if REFCOUNTED:
        # Freed in the test that dropped it, so reported there.
        assert "ERROR" in result.outcomes("test_drops_a_failure")
        assert "ERROR" in result.outcomes("test_async_drops_a_failure")
    assert result.outcomes("test_reads_its_failure") == {"PASSED"}
    assert result.outcomes("test_sync_second") == {"PASSED"}


def test_a_task_left_pending_on_the_shared_loop_fails(
    isolated: Run, shared: Run
) -> None:
    # An isolated test's loop is closed after it, with its tasks cancelled.
    assert isolated.outcomes("test_leaves_a_task_pending") == {"PASSED"}
    assert "ERROR" in shared.outcomes("test_leaves_a_task_pending")
    assert "left 1 task(s) pending on the shared loop" in shared.output


def test_closing_the_shared_loop_fails_the_test(isolated: Run, shared: Run) -> None:
    assert isolated.outcomes("test_closes_the_thread_loop") == {"PASSED"}
    assert "ERROR" in shared.outcomes("test_closes_the_thread_loop")
    assert "the test closed the shared event loop" in shared.output


def test_a_shared_loop_needs_session_fixtures(tmp_path: Path) -> None:
    result = run(tmp_path, "session", fixtureScope="function")
    assert result.returncode == pytest.ExitCode.USAGE_ERROR, result.output
    assert "asyncio_default_fixture_loop_scope=session" in result.output
