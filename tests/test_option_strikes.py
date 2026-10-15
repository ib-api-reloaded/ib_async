"""IB.reqOptionStrikes: the strikes each expiration lists, from contract details."""

import asyncio
import copy
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal

import pytest

import ib_async as ibi
from ib_async import Contract, ContractDetails, Future, OptionStrikes, Stock

ESZ6, ESH7 = 1001, 1002  # the conIds of two ES futures months
FIFTY = Decimal(50)


def option(
    secType: str,
    expiration: str,
    strike: float,
    right: str,
    tradingClass: str,
    multiplier: str = "50",
) -> Contract:
    """A contract as contract details report an ES option (or event contract)."""
    return Contract(
        secType=secType,
        symbol="ES",
        lastTradeDateOrContractMonth=expiration,
        strike=strike,
        right=right,
        multiplier=multiplier,
        exchange="CME",
        currency="USD",
        tradingClass=tradingClass,
    )


# What a December 2026 ES futures option search returns, in no order: the
# quarterly and weekly classes, a call and a put at each strike, options on
# two futures months, and a CME event contract, which is not an option.
DECEMBER = [
    ContractDetails(option("FOP", "20261218", 6005, "C", "ES"), underConId=ESZ6),
    ContractDetails(option("FOP", "20261218", 6000, "P", "ES"), underConId=ESZ6),
    ContractDetails(option("FOP", "20261218", 6000, "C", "ES"), underConId=ESZ6),
    ContractDetails(option("FOP", "20261218", 6000, "C", "EW3"), underConId=ESZ6),
    ContractDetails(option("FOP", "20261207", 5990, "P", "E1A"), underConId=ESZ6),
    ContractDetails(option("FOP", "20261231", 6100, "C", "EW"), underConId=ESH7),
    ContractDetails(option("EC", "20261218", 6000, "P", "ECES", "1"), underConId=ESZ6),
    ContractDetails(None),
]


class RecordedIB(ibi.IB):
    """An IB that answers contract details searches from recorded
    responses, by search month, and keeps the searches it was sent."""

    def __init__(self, responses: Mapping[str, Sequence[ContractDetails]]) -> None:
        super().__init__()
        self.responses = responses
        self.searches: list[Contract] = []

    async def reqContractDetailsAsync(
        self, contract: Contract
    ) -> list[ContractDetails]:
        self.searches.append(contract)
        return list(self.responses.get(contract.lastTradeDateOrContractMonth, ()))


@dataclass(frozen=True, slots=True)
class Lookup:
    """What reqOptionStrikesAsync returned, and the searches it sent."""

    chains: list[OptionStrikes]
    searches: list[Contract]


def lookUp(
    underlying: Contract,
    *months: str,
    responses: Mapping[str, Sequence[ContractDetails]] | None = None,
) -> Lookup:
    """reqOptionStrikesAsync against recorded responses."""
    ib = RecordedIB(responses or {})
    chains = asyncio.run(ib.reqOptionStrikesAsync(underlying, *months))
    return Lookup(chains, ib.searches)


def test_strikes_are_grouped_per_expiration_and_trading_class() -> None:
    es = Future("ES", "202612", "CME", conId=ESZ6, localSymbol="ESZ6")
    chains = lookUp(es, "202612", responses={"202612": DECEMBER}).chains
    assert chains == [
        OptionStrikes("20261207", "E1A", FIFTY, ESZ6, (5990.0,)),
        OptionStrikes("20261218", "ES", FIFTY, ESZ6, (6000.0, 6005.0)),
        OptionStrikes("20261218", "EW3", FIFTY, ESZ6, (6000.0,)),
        OptionStrikes("20261231", "EW", FIFTY, ESH7, (6100.0,)),
    ]


def test_a_future_is_searched_by_symbol_month_and_its_exchange_only() -> None:
    """The conId, localSymbol and trading class of the future would pin
    the search to the future itself; the caller's contract is untouched."""
    es = Future(
        "ES", "202612", "CME", conId=ESZ6, localSymbol="ESZ6", tradingClass="ES"
    )
    before = copy.deepcopy(es)
    searches = lookUp(es, "202612", "202701").searches
    assert [
        (s.secType, s.symbol, s.lastTradeDateOrContractMonth, s.exchange)
        for s in searches
    ] == [("FOP", "ES", "202612", "CME"), ("FOP", "ES", "202701", "CME")]
    for search in searches:
        assert (search.conId, search.localSymbol) == (0, "")
        assert (search.tradingClass, search.multiplier) == ("", "")
    assert es == before


def test_a_stock_is_searched_on_smart() -> None:
    aapl = Stock("AAPL", "NASDAQ", "USD", conId=265598, tradingClass="NMS")
    (search,) = lookUp(aapl, "20261218").searches
    assert (search.secType, search.exchange) == ("OPT", "SMART")
    assert (search.currency, search.tradingClass) == ("USD", "")


def test_each_month_is_searched_once() -> None:
    searches = lookUp(Future("ES", exchange="CME"), "202612", "202612").searches
    assert len(searches) == 1


@pytest.mark.parametrize(
    ("underlying", "months", "message"),
    [
        (ibi.Index("SPX", "CBOE"), ("202612",), "stock or future"),
        (Future("ES"), ("202612",), "the future's exchange"),
        (Future("ES", exchange="CME"), (), "YYYYMM"),
        (Future("ES", exchange="CME"), ("2026-12",), "YYYYMM"),
    ],
)
def test_refusals(underlying: Contract, months: tuple[str, ...], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        lookUp(underlying, *months)
