"""OptionComputation arithmetic keeps a value IBKR did not compute unknown.

A greek, volatility or price IBKR did not compute is None. ``a + b``,
``a - b`` and ``a * n`` (spread greeks such as ``longGreeks - shortGreeks``)
give None for a field when a leg's field is None, so an unknown leg never
reads as zero and two unknown legs never read as delta neutral.
"""

from __future__ import annotations

import operator
from collections.abc import Callable

import pytest
from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async._pb import TickOptionComputation_pb2
from ib_async._server_versions import MAX_CLIENT_VER
from ib_async.decoder import Decoder
from ib_async.objects import OptionComputation
from ib_async.util import getLoop
from tests._property import examples
from tests._sim import SimulatedTws

FIELDS = ["impliedVol", "delta", "optPrice", "gamma", "vega", "theta"]

LONG = OptionComputation(0, 0.2, 0.6, 5.0, 0.1, 0.02, 0.3, -0.05, 700.0)
SHORT = OptionComputation(0, 0.25, 0.4, 3.0, 0.1, 0.03, 0.2, -0.04, 700.0)
NOT_COMPUTED = OptionComputation(0, undPrice=700.0)
ZEROS = OptionComputation(0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 700.0)


def values(c: OptionComputation) -> list[float | None]:
    return [getattr(c, name) for name in FIELDS]


def test_computed_legs_combine_as_before() -> None:
    spread = LONG - SHORT
    assert spread.delta == pytest.approx(0.2)
    assert spread.optPrice == pytest.approx(2.0)
    assert (LONG + SHORT).gamma == pytest.approx(0.05)
    assert (LONG * 100).delta == pytest.approx(60.0)
    left = OptionComputation(1, 0.2, 0.6, 5.0, 0.1, 0.02, 0.3, -0.05, 701.0)
    for result in (left - SHORT, left + SHORT, left * 100):
        assert result.undPrice == 701.0
        assert result.pvDividend is None and result.tickAttrib == 0


def test_an_unknown_leg_makes_every_field_unknown() -> None:
    for spread in (LONG - NOT_COMPUTED, NOT_COMPUTED - LONG, LONG + NOT_COMPUTED):
        assert values(spread) == [None] * len(FIELDS)


def test_unknown_legs_differ_from_real_zeros() -> None:
    assert (NOT_COMPUTED + NOT_COMPUTED).delta is None
    assert (ZEROS + ZEROS).delta == 0.0
    assert (NOT_COMPUTED * 100).delta is None
    assert (ZEROS * 100).delta == 0.0


def test_one_unknown_field_leaves_the_others() -> None:
    partial = OptionComputation(0, None, 0.4, 3.0, None, 0.03, None, None, 700.0)
    spread = LONG - partial
    assert (spread.impliedVol, spread.vega, spread.theta) == (None, None, None)
    assert spread.delta == pytest.approx(0.2)
    assert spread.gamma == pytest.approx(-0.01)


computations = st.builds(
    OptionComputation,
    tickAttrib=st.just(0),
    **{name: st.one_of(st.none(), st.floats(-10, 10)) for name in FIELDS},
)


@given(a=computations, b=computations, op=st.sampled_from(["+", "-"]))
@examples()
def test_a_leg_field_is_unknown_exactly_when_either_is(
    a: OptionComputation, b: OptionComputation, op: str
) -> None:
    func: Callable[[float, float], float] = operator.add if op == "+" else operator.sub
    combined = a + b if op == "+" else a - b
    for name in FIELDS:
        x, y = getattr(a, name), getattr(b, name)
        expected = None if x is None or y is None else func(x, y)
        assert getattr(combined, name) == expected, name


@given(a=computations, n=st.floats(-100, 100))
@examples()
def test_a_scaled_field_is_unknown_exactly_when_it_was(
    a: OptionComputation, n: float
) -> None:
    scaled = a * n
    for name in FIELDS:
        x = getattr(a, name)
        assert getattr(scaled, name) == (None if x is None else x * n), name


def modelGreeks(
    tws: SimulatedTws, conId: int, delta: float | None
) -> OptionComputation:
    """The model greeks a ticker gets from a protobuf tick, with delta left
    out (IBKR did not compute it) when ``delta`` is None."""
    ticker = tws.ib.reqMktData(
        ibi.Option("SPY", "20261218", 500, "C", "SMART", conId=conId)
    )
    reqId = tws.asks[-1].reqId
    tws.run()
    proto = TickOptionComputation_pb2.TickOptionComputation(
        reqId=reqId, tickType=13, tickAttrib=0, impliedVol=0.2, optPrice=5.0
    )
    if delta is not None:
        proto.delta = delta
    Decoder(tws.wrapper, MAX_CLIENT_VER)._protoTickOptionComputation(proto)
    assert ticker.modelGreeks is not None
    return ticker.modelGreeks


def test_a_spread_with_a_leg_ibkr_did_not_compute_has_no_delta() -> None:
    tws = SimulatedTws(getLoop())
    long = modelGreeks(tws, 1, 0.6)
    short = modelGreeks(tws, 2, None)

    spread = long - short

    assert short.delta is None and spread.delta is None
    assert spread.optPrice == pytest.approx(0.0)
