"""Property tests for contract equality, hashing and market data identity.

- Equal contracts have equal hashes.
- A contract equals itself and its recreation.
- A continuous future never equals the front month that shares its conId.
- Spreads are distinguished by their legs, not by IBKR's shared combo
  conId.
- A contract has a market data identity exactly when it is hashable.
"""

from __future__ import annotations

import dataclasses

from hypothesis import given
from hypothesis import strategies as st

import ib_async as ibi
from ib_async._subscriptions import SubscriptionRegistry
from tests._property import examples

symbols = st.sampled_from(["A", "B", "ES", "SPY"])
exchanges = st.sampled_from(["", "SMART", "CME", "ISLAND"])
legs = st.lists(
    st.builds(
        ibi.ComboLeg,
        conId=st.sampled_from([10, 11, 20, 21]),
        ratio=st.integers(1, 3),
        action=st.sampled_from(["BUY", "SELL"]),
        exchange=exchanges,
    ),
    min_size=1,
    max_size=4,
)


@st.composite
def contracts(draw: st.DrawFn) -> ibi.Contract:
    secType = draw(st.sampled_from(["STK", "OPT", "FUT", "CONTFUT", "BAG", "CASH"]))
    conId = draw(st.sampled_from([0, 10, 11, 20, 28812380]))
    return ibi.Contract(
        secType=secType,
        conId=conId,
        symbol=draw(symbols),
        exchange=draw(exchanges),
        currency=draw(st.sampled_from(["USD", "EUR"])),
        lastTradeDateOrContractMonth=draw(st.sampled_from(["", "202612"])),
        comboLegs=draw(legs) if secType == "BAG" else [],
    )


def identity(contract: ibi.Contract) -> int | None:
    return SubscriptionRegistry._market_data_identity(contract)


@given(contract=contracts())
@examples()
def test_contract_equals_itself_and_recreation(contract):
    assert contract == dataclasses.replace(contract)
    again = ibi.Contract.recreate(contract)
    assert again == contract and contract == again
    assert type(again) is type(ibi.Contract.create(secType=contract.secType))
    if contract.isHashable():
        assert hash(again) == hash(contract)


@given(a=contracts(), b=contracts())
@examples()
def test_equal_contracts_have_equal_hash_and_identity(a, b):
    if a == b:
        assert b == a
        assert a.isHashable() == b.isHashable()
        if a.isHashable():
            assert hash(a) == hash(b)
            assert identity(a) == identity(b)


@given(contract=contracts(), other=symbols, conId=st.sampled_from([0, 10, 99]))
@examples()
def test_contract_identity_by_sec_type(contract, other, conId):
    """Check which fields identify each kind of contract.

    A qualified contract is identified by its conId, so a different symbol
    with the same conId is the same contract. A spread compares on every
    field, but its market data identity comes from its legs. A spread with
    the same legs and another conId, such as a user's bag and IBKR's copy
    of it, has the same hash and shares the stream. A continuous future
    never equals the front month with the same conId."""
    renamed = dataclasses.replace(contract, symbol=other)
    renumbered = dataclasses.replace(contract, conId=conId)
    if contract.secType == "BAG":
        assert (renamed == contract) == (other == contract.symbol)
        assert (renumbered == contract) == (conId == contract.conId)
        assert hash(renumbered) == hash(contract)
        assert identity(renumbered) == identity(contract)
    elif contract.isHashable():
        assert renamed == contract
        assert hash(renamed) == hash(contract)
        assert (renumbered == contract) == (conId == contract.conId)
    else:
        assert (renamed == contract) == (other == contract.symbol)
    if contract.secType in ("FUT", "CONTFUT") and contract.conId:
        twin = dataclasses.replace(
            contract, secType="CONTFUT" if contract.secType == "FUT" else "FUT"
        )
        assert twin != contract
        assert hash(twin) == -hash(contract)


@given(contract=contracts())
@examples()
def test_market_data_identity_exists_only_for_hashable_contracts(contract):
    key = identity(contract)
    assert (key is None) == (not contract.isHashable())
    if key is not None:
        assert key == hash(contract)
