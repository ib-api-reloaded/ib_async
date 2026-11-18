"""qualifyDetails: the qualification rule as a public seam."""

from __future__ import annotations

from ib_async.contract import Contract, ContractDetails
from ib_async.ib import qualifyDetails


def _details(secType: str, conId: int, exchange: str = "") -> ContractDetails:
    return ContractDetails(
        contract=Contract(
            secType=secType, conId=conId, exchange=exchange,
            localSymbol=f"L{conId}"))


def test_single_reply_wins_and_fills_in_place() -> None:
    requested = Contract(secType="STK", symbol="SPY")
    pick = qualifyDetails(requested, [_details("STK", 756733, "ARCA")])
    assert pick is not None and pick.contract is not None
    assert pick.contract.conId == 756733
    assert requested.conId == 756733
    assert requested.exchange == "ARCA"
    assert requested.localSymbol == "L756733"


def test_smart_request_stays_smart() -> None:
    requested = Contract(secType="STK", symbol="SPY", exchange="SMART")
    pick = qualifyDetails(requested, [_details("STK", 756733, "ARCA")])
    assert pick is not None
    assert requested.exchange == "SMART"


def test_many_replies_disambiguate_by_requested_sec_type() -> None:
    requested = Contract(secType="FOP", symbol="ES", exchange="CME")
    pick = qualifyDetails(
        requested,
        [_details("EC", 1, "CME"), _details("FOP", 2, "CME")])
    assert pick is not None and pick.contract is not None
    assert pick.contract.secType == "FOP"
    assert requested.conId == 2


def test_many_replies_without_sec_type_is_unknown() -> None:
    requested = Contract(symbol="SPY")
    pick = qualifyDetails(requested, [_details("STK", 1), _details("STK", 2)])
    assert pick is None


def test_many_replies_no_unique_match_is_unknown() -> None:
    requested = Contract(secType="FOP", symbol="ES")
    pick = qualifyDetails(
        requested, [_details("FOP", 1), _details("FOP", 2)])
    assert pick is None


def test_no_replies_is_unknown() -> None:
    assert qualifyDetails(Contract(symbol="SPY"), []) is None


def test_reply_without_contract_is_unknown_not_asserted() -> None:
    requested = Contract(secType="STK", symbol="SPY")
    pick = qualifyDetails(requested, [ContractDetails()])
    assert pick is None
