import ib_async as ibi


def test_tick_option_computation_maps_unset_vega_theta_to_none():
    """
    The -2 "not computed" sentinel must be converted to None, not -2.0.

    IBKR reports -2 for a vega or theta it could not compute. Delta and
    gamma are already mapped to None; vega and theta must be treated the
    same way, otherwise a "not computed" value is handed to the caller as
    if it were a real number.
    """
    ib = ibi.IB()
    wrapper = ib.wrapper

    contract = ibi.Stock("AAPL", "SMART", "USD", conId=265598)
    # tickType 13 -> modelGreeks
    ticker = wrapper.startTicker(1, contract, 13)

    wrapper.tickOptionComputation(
        1,
        13,
        0,
        0.25,  # impliedVol
        0.5,  # delta
        5.0,  # optPrice
        0.0,  # pvDividend
        0.02,  # gamma
        -2.0,  # vega: not computed
        -2.0,  # theta: not computed
        100.0,  # undPrice
    )

    greeks = ticker.modelGreeks

    assert greeks is not None
    assert greeks.vega is None
    assert greeks.theta is None
    # Values the venue did compute must be passed through unchanged
    assert greeks.delta == 0.5
    assert greeks.gamma == 0.02
    assert greeks.undPrice == 100.0
