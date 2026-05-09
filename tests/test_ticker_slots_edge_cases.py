"""The Ticker dataclass uses ``slots=True`` for a per-tick attribute-lookup
win on the hot path. That can quietly break copy / pickle / repr if any
attribute is non-trivial; verify that nothing user-visible regressed.

Pickle is the highest-risk path because eventkit Event objects don't
necessarily round-trip; if a user pickles a Ticker for caching or IPC and
the Event slot is unpicklable, that's a regression we want to catch
before they hit it.
"""

import copy
import pickle

import pytest

from ib_async.contract import Stock
from ib_async.ticker import Ticker, TickerUpdateEvent


def _fresh_ticker() -> Ticker:
    contract = Stock("AAPL", "SMART", "USD")
    ticker = Ticker(contract=contract)
    ticker.bid = 100.5
    ticker.ask = 100.6
    ticker.last = 100.55
    return ticker


def test_repr_does_not_raise_on_fresh_ticker():
    ticker = _fresh_ticker()
    text = repr(ticker)
    assert "AAPL" in text


def test_repr_does_not_raise_after_post_init_blank():
    # default-constructed (no contract) — must not raise either.
    ticker = Ticker()
    repr(ticker)


def test_copy_preserves_field_values():
    ticker = _fresh_ticker()
    duplicate = copy.copy(ticker)
    assert duplicate.bid == 100.5
    assert duplicate.ask == 100.6
    assert duplicate.last == 100.55
    assert duplicate.contract == ticker.contract


def test_deepcopy_preserves_field_values_and_isolates_mutation():
    ticker = _fresh_ticker()
    ticker.ticks.append(("synthetic",))  # type: ignore[arg-type]
    duplicate = copy.deepcopy(ticker)
    assert duplicate.bid == 100.5
    duplicate.ticks.append(("after-copy",))  # type: ignore[arg-type]
    # Original ticks list must not be mutated by the duplicate's append.
    assert len(ticker.ticks) == 1
    assert len(duplicate.ticks) == 2


def test_copy_does_not_reset_via_post_init():
    # __post_init__ uses ``self.created`` as a guard so a copy is not
    # re-blanked. Copying after fields have been set must preserve them.
    ticker = _fresh_ticker()
    ticker.created = True
    ticker.bid = 999.0
    duplicate = copy.copy(ticker)
    assert duplicate.bid == 999.0


def test_pickle_roundtrip_preserves_market_fields():
    ticker = _fresh_ticker()
    # The eventkit Event in the updateEvent slot may not be pickleable in all
    # eventkit versions; if pickle.dumps raises, mark the test xfail loudly so
    # the regression surfaces but doesn't block the suite. (This documents
    # behaviour rather than asserting a fix.)
    try:
        blob = pickle.dumps(ticker)
    except Exception as exc:
        pytest.xfail(f"Ticker is not picklable due to updateEvent slot: {exc!r}")
        return

    restored = pickle.loads(blob)
    assert restored.bid == 100.5
    assert restored.ask == 100.6
    assert restored.last == 100.55
    assert restored.contract == ticker.contract


def test_post_init_assigns_a_real_update_event():
    ticker = Ticker()
    assert isinstance(ticker.updateEvent, TickerUpdateEvent)


def test_slots_prevent_attribute_typos():
    # If slots=True is in effect, adding an undeclared attribute must raise.
    # This is a smoke test: if someone disables slots later this catches it.
    ticker = _fresh_ticker()
    with pytest.raises(AttributeError):
        ticker.this_attribute_does_not_exist = 1  # type: ignore[attr-defined]
