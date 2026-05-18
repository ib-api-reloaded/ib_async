import pytest

import ib_async as ibi

# Live: requires a running TWS / IB Gateway on 127.0.0.1:7497.
# Skipped by default. Opt in with ``pytest -m live``.
pytestmark = [pytest.mark.asyncio, pytest.mark.live]


async def test_request_error_raised(ib):
    contract = ibi.Forex("EURUSD")
    order = ibi.MarketOrder("BUY", 100)
    orderState = await ib.whatIfOrderAsync(contract, order)
    assert orderState.commission > 0

    ib.RaiseRequestErrors = True
    badContract = ibi.Stock("XXX")
    with pytest.raises(ibi.RequestError) as exc_info:
        await ib.whatIfOrderAsync(badContract, order)
    assert exc_info.value.code == 321


async def test_account_summary(ib):
    summary = await ib.accountSummaryAsync()
    assert summary
    assert all(isinstance(value, ibi.AccountValue) for value in summary)
