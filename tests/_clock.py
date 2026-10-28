"""A virtual clock for an event loop, so a test makes time limits pass
without waiting on real time."""

from __future__ import annotations

import asyncio

import pytest


class VirtualClock:
    """The loop's time, moved only by :meth:`advance`. Timers (time limits,
    call_later) fire on the loop's next steps once the time passes them."""

    def __init__(self, start: float) -> None:
        self.now = start

    def time(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def installClock(
    loop: asyncio.AbstractEventLoop, monkeypatch: pytest.MonkeyPatch
) -> VirtualClock:
    """Run ``loop`` on a virtual clock until the test ends."""
    clock = VirtualClock(loop.time())
    monkeypatch.setattr(loop, "time", clock.time)
    return clock
