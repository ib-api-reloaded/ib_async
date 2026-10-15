.. This page is generated from ib_async/ordertypes/catalog.py by
   scripts/generate_ordertypes.py. Do not edit it.

.. _ordertypes:

Order types
===========

Each order type is a function that returns an ``Order`` with the fields IBKR expects for it. Its parameters are the values that order type needs; any other ``Order`` field (``tif``, ``outsideRth``, ``account``, ``cashQty``, ``includeOvernight``, ...) is a keyword argument. A missing required value, two of a pair where one is needed, or overriding a field the type sets itself raises ``OrderTypeError``.

``ib_async.ordertypes.specOf(order)`` names the order type of any ``Order``; ``ib_async.ordertypes.checkOrder(contract, order)`` lists what IBKR says against an order for a contract, such as a product it is not listed for; given the contract's ``ContractDetails`` instead, also an order type its ``orderTypes`` does not list.

For an order type not listed here, set the fields on ``Order`` directly: ``Order(orderType=..., action=..., totalQuantity=...)``.

Stable order types
------------------

Standard order types, broadly supported.

Market (``MKT``)
^^^^^^^^^^^^^^^^

Buys or sells at the market bid or offer price.

Likely to fill, and quickly, but with no price protection: it may fill far from the displayed bid or ask.

.. code-block:: python

    MarketOrder("BUY", 100)

- Products: BOND, CFD, EFP, CASH, FUND, FUT, FOP, OPT, STK, WAR

Limit (``LMT``)
^^^^^^^^^^^^^^^

Buys at the limit price or lower, or sells at it or higher.

Never fills at a worse price than the limit; it may not fill.

.. code-block:: python

    LimitOrder("BUY", 100, 50.25)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.

- Products: BOND, CFD, CASH, FUT, FOP, OPT, STK, WAR

Stop (``STP``)
^^^^^^^^^^^^^^

Becomes a market order once the stop price is reached.

A sell stop below the market limits a loss or protects a profit on a long position; a buy stop above it does so on a short sale. Once triggered it may fill well away from the stop price.

.. code-block:: python

    StopOrder("SELL", 100, 45.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``stopPrice``
     - ``auxPrice``
     - The price that triggers the order.

- Products: CFD, BAG, CASH, FUT, FOP, OPT, STK, WAR

Stop Limit (``STP LMT``)
^^^^^^^^^^^^^^^^^^^^^^^^

Becomes a limit order once the stop price is reached.

Like a stop order, but once triggered it fills only at the limit price or better.

.. code-block:: python

    StopLimitOrder("SELL", 100, 44.50, 45.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.
   * - ``stopPrice``
     - ``auxPrice``
     - The price that triggers the order.

- Products: CFD, CASH, FUT, FOP, OPT, STK, WAR

Market on Close (``MOC``)
^^^^^^^^^^^^^^^^^^^^^^^^^

A market order executed as close to the closing price as possible.

.. code-block:: python

    MarketOnCloseOrder("SELL", 100)

- Products: CFD, FUT, STK, WAR

Limit on Close (``LOC``)
^^^^^^^^^^^^^^^^^^^^^^^^

A limit order executed at the close if the closing price is at or better than the limit.

Set imbalanceOnly=True to offer it only against the closing auction's imbalance.

.. code-block:: python

    LimitOnCloseOrder("SELL", 100, 50.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.

- Products: CFD, FUT, STK, WAR

Market on Open (``MKT``)
^^^^^^^^^^^^^^^^^^^^^^^^

A market order executed at the opening price.

A market order with time in force OPG.

.. code-block:: python

    MarketOnOpenOrder("BUY", 100)

- Sets ``tif='OPG'``
- Products: CFD, FUT, STK, OPT, WAR

Limit on Open (``LMT``)
^^^^^^^^^^^^^^^^^^^^^^^

A limit order executed at the open if the opening price is at or better than the limit.

A limit order with time in force OPG.

.. code-block:: python

    LimitOnOpenOrder("BUY", 100, 50.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.

- Sets ``tif='OPG'``
- Products: CFD, STK, OPT, WAR

At Auction (``MTL``)
^^^^^^^^^^^^^^^^^^^^

Entered in the pre-market auction to execute at the calculated opening price; if not filled on the open, it is resubmitted as a limit order at that price or the best bid or ask after the open.

.. code-block:: python

    AtAuctionOrder("BUY", 100, 50.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.

- Sets ``tif='AUC'``
- Products: FUT, STK

Market if Touched (``MIT``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Becomes a market order once the touch price is reached.

The mirror of a stop: a buy below the market or a sell above it, to act on a price level being reached.

.. code-block:: python

    MarketIfTouchedOrder("BUY", 100, 48.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``touchPrice``
     - ``auxPrice``
     - The price that, once touched, triggers the order.

- Products: BOND, CFD, CASH, FUT, FOP, OPT, STK, WAR

Limit if Touched (``LIT``)
^^^^^^^^^^^^^^^^^^^^^^^^^^

Becomes a limit order once the touch price is reached.

.. code-block:: python

    LimitIfTouchedOrder("BUY", 100, 48.10, 48.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.
   * - ``touchPrice``
     - ``auxPrice``
     - The price that, once touched, triggers the order.

- Products: BOND, CFD, CASH, FUT, FOP, OPT, STK, WAR

Trailing Stop (``TRAIL``)
^^^^^^^^^^^^^^^^^^^^^^^^^

A stop that follows the market: its stop price moves with the price by a fixed amount or percent, and never back.

Give trailingAmount or trailingPercent.

.. code-block:: python

    TrailingStopOrder("SELL", 100, trailingPercent=2.0)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``trailingAmount``
     - ``auxPrice``
     - How far the stop trails, in price. Optional.
   * - ``trailingPercent``
     - ``trailingPercent``
     - How far the stop trails, in percent. Optional.
   * - ``trailStopPrice``
     - ``trailStopPrice``
     - The trailing stop price. Optional.

- Exactly one of ``trailingAmount``, ``trailingPercent``
- Products: CFD, CASH, FOP, FUT, OPT, STK, WAR

Trailing Stop Limit (``TRAIL LIMIT``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A trailing stop that, once triggered, becomes a limit order at the limit price, or at lmtPriceOffset from the stop price as it trails.

Give trailingAmount or trailingPercent, and lmtPrice or lmtPriceOffset.

.. code-block:: python

    TrailingStopLimitOrder("SELL", 100, lmtPriceOffset=0.10, trailingAmount=1.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPriceOffset``
     - ``lmtPriceOffset``
     - The limit price's distance from the stop price. Optional.
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price. Optional.
   * - ``trailingAmount``
     - ``auxPrice``
     - How far the stop trails, in price. Optional.
   * - ``trailingPercent``
     - ``trailingPercent``
     - How far the stop trails, in percent. Optional.
   * - ``trailStopPrice``
     - ``trailStopPrice``
     - The trailing stop price. Optional.

- Exactly one of ``trailingAmount``, ``trailingPercent``; ``lmtPriceOffset``, ``lmtPrice``
- Products: BOND, CFD, CASH, FUT, FOP, OPT, STK, WAR

Market to Limit (``MTL``)
^^^^^^^^^^^^^^^^^^^^^^^^^

A market order whose unfilled part becomes a limit order at the price of its first fill.

.. code-block:: python

    MarketToLimitOrder("BUY", 100)

- Products: CFD, FUT, FOP, OPT, STK, WAR

Market with Protection (``MKT PRT``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A market order that, if it does not execute in full at once, is canceled and resubmitted as a limit order at a price the exchange sets close to the market.

IBKR lists it for futures and futures options; an application trading live also sends it for SPXW index options.

.. code-block:: python

    MarketWithProtectionOrder("BUY", 1)

- Products: FUT, FOP

Stop with Protection (``STP PRT``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A stop that becomes a market order with protection once triggered.

.. code-block:: python

    StopWithProtectionOrder("SELL", 1, 4500.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``stopPrice``
     - ``auxPrice``
     - The price that triggers the order.

- Products: FUT

Relative (Pegged to Primary) (``REL``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pegged to the national best bid (buy) or offer (sell), more aggressive by offset. It follows the quote toward the market (a buy rises with the bid) but not away from it.

IBKR describes priceCap as optional, but rejects the order without it in live trading. Not available on paper trading accounts.

.. code-block:: python

    RelativeOrder("BUY", 100, 0.01, 50.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``offset``
     - ``auxPrice``
     - How much more aggressive than the NBBO.
   * - ``priceCap``
     - ``lmtPrice``
     - The worst price accepted, like a limit price.

- Products: CFD, STK, OPT, FUT

Passive Relative (``PASSV REL``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pegged to the national best bid (buy) or offer (sell), less aggressive by offset: a buy subtracts the offset from the bid.

.. code-block:: python

    PassiveRelativeOrder("BUY", 100, 0.01)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``offset``
     - ``auxPrice``
     - How much less aggressive than the NBBO.
   * - ``priceCap``
     - ``lmtPrice``
     - The worst price accepted, like a limit price. Optional.

- Products: STK, WAR

Pegged to Market (``PEG MKT``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pegged to the national best offer (buy) or bid (sell): a buy is priced at the offer less offset, a sell at the bid plus offset.

.. code-block:: python

    PeggedToMarketOrder("BUY", 100, 0.01)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``offset``
     - ``auxPrice``
     - The amount away from the NBBO.
   * - ``priceCap``
     - ``lmtPrice``
     - The worst price accepted, like a limit price. Optional.

- Products: STK

Pegged to Midpoint (``PEG MID``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pegged to the NBBO midpoint, adjusted by offset, never beyond the limit price.

.. code-block:: python

    PeggedToMidpointOrder("BUY", 100, 50.00, offset=0.01)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.
   * - ``offset``
     - ``auxPrice``
     - The amount away from the reference price. Optional.

- Products: STK

Midprice (``MIDPRICE``)
^^^^^^^^^^^^^^^^^^^^^^^

Fills at the NBBO midpoint or better.

IBKR describes priceCap as optional, but rejects the order without it in live trading, and refuses it outside regular trading hours. SMART-routed US stocks only.

.. code-block:: python

    MidpriceOrder("BUY", 100, 50.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``priceCap``
     - ``lmtPrice``
     - The worst price accepted, like a limit price.

- Products: STK
- Requires TWS 975+

Snap to Midpoint (``SNAP MID``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Priced once, when placed, at the NBBO midpoint: a buy less offset, a sell plus offset. It does not move afterwards.

.. code-block:: python

    SnapToMidpointOrder("BUY", 100, 50.00, offset=0.01)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.
   * - ``offset``
     - ``auxPrice``
     - The amount away from the reference price. Optional.

Snap to Primary (``SNAP PRIM``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Priced once, when placed, at the national best bid plus offset (buy) or offer less offset (sell). It does not move afterwards.

.. code-block:: python

    SnapToPrimaryOrder("BUY", 100, 50.00, offset=0.01)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.
   * - ``offset``
     - ``auxPrice``
     - The amount away from the reference price. Optional.

Snap to Market (``SNAP MKT``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Priced once, when placed, at the national best offer less offset (buy) or bid plus offset (sell). It does not move afterwards.

.. code-block:: python

    SnapToMarketOrder("BUY", 100, 50.00, offset=0.01)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.
   * - ``offset``
     - ``auxPrice``
     - The amount away from the reference price. Optional.

Discretionary (``LMT``)
^^^^^^^^^^^^^^^^^^^^^^^

A limit order with a hidden discretionary amount: the market sees only the limit price, but it may execute up to that far beyond.

.. code-block:: python

    DiscretionaryOrder("BUY", 100, 50.00, 0.05)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.
   * - ``discretionaryAmt``
     - ``discretionaryAmt``
     - How far beyond the limit price it may execute.

- Products: STK

Sweep to Fill (``LMT``)
^^^^^^^^^^^^^^^^^^^^^^^

A limit order that takes the best price and, at once, the next best prices, for speed of execution over price.

SMART-routed only.

.. code-block:: python

    SweepToFillOrder("BUY", 100, 50.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.

- Sets ``sweepToFill=True``
- Products: CFD, STK, WAR

Combo with Leg Prices (``LMT``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A limit order for a combo (BAG) contract with a limit price for each leg instead of one for the combo.

One price per leg, in the order of the contract's legs. For one price for the whole combo, use LimitOrder.

.. code-block:: python

    ComboLegPricesOrder("BUY", 1, [2.50, 1.20])

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``legPrices``
     - ``orderComboLegs``
     - The limit price of each leg, in leg order.

- Products: BAG

Venue order types
-----------------

Order types of specific exchanges or venues.

Block (``LMT``)
^^^^^^^^^^^^^^^

A limit order for 50 or more option contracts, executed as a block on ISE.

.. code-block:: python

    BlockOrder("BUY", 50, 2.50)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.

- Sets ``blockOrder=True``
- Products: OPT
- Exchanges: ISE

Box Top (``BOX TOP``)
^^^^^^^^^^^^^^^^^^^^^

A market order at the best price on BOX; any unfilled part becomes a limit order at the price of its fill.

.. code-block:: python

    BoxTopOrder("BUY", 10)

- Products: OPT
- Exchanges: BOX

Auction Limit (``LMT``)
^^^^^^^^^^^^^^^^^^^^^^^

A limit order in a BOX price improvement auction.

.. code-block:: python

    AuctionLimitOrder("BUY", 10, 2.50, 2)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.
   * - ``auctionStrategy``
     - ``auctionStrategy``
     - 1 match, 2 improvement, 3 transparent.

- Products: OPT
- Exchanges: BOX

Pegged to Stock (``PEG STK``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

An option order whose price moves by delta times the underlying's change from the stock reference price.

delta is entered as an absolute value, taken as positive for calls and negative for puts. Without stockRefPrice IBKR uses the underlying's NBBO midpoint at placement; stockRangeLower and stockRangeUpper cancel the order when the underlying leaves the range. On BOX this is the Auction Pegged to Stock order.

.. code-block:: python

    PeggedToStockOrder("BUY", 1, 0.5, 2.50, stockRefPrice=100.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``delta``
     - ``delta``
     - The option's price change per underlying move.
   * - ``startingPrice``
     - ``startingPrice``
     - The option price to start from.
   * - ``stockRefPrice``
     - ``stockRefPrice``
     - The underlying price the change is measured from. Optional.
   * - ``stockRangeLower``
     - ``stockRangeLower``
     - Cancel below this underlying price. Optional.
   * - ``stockRangeUpper``
     - ``stockRangeUpper``
     - Cancel above this underlying price. Optional.

- Products: OPT

Pegged to Best (IBKR ATS) (``PEG BEST``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pegged to the best price on IBKR's ATS.

.. code-block:: python

    PegBestOrder("BUY", 100, 50.00, 100, 100, 0.01)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.
   * - ``minTradeQty``
     - ``minTradeQty``
     - The smallest fill accepted.
   * - ``minCompeteSize``
     - ``minCompeteSize``
     - The minimum size to compete.
   * - ``competeAgainstBestOffset``
     - ``competeAgainstBestOffset``
     - The offset off the midpoint.

- Sets ``notHeld=True``
- Products: STK
- Exchanges: IBKRATS

Pegged to Best up to Midpoint (IBKR ATS) (``PEG BEST``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pegged to the best price on IBKR's ATS, competing up to the midpoint, offset by midOffsetAtWhole or midOffsetAtHalf depending on the spread.

.. code-block:: python

    PegBestUpToMidOrder("BUY", 100, 50.00, 100, 100, 0.01, 0.005)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.
   * - ``minTradeQty``
     - ``minTradeQty``
     - The smallest fill accepted.
   * - ``minCompeteSize``
     - ``minCompeteSize``
     - The minimum size to compete.
   * - ``midOffsetAtWhole``
     - ``midOffsetAtWhole``
     - The offset when the spread is an even number of cents wide.
   * - ``midOffsetAtHalf``
     - ``midOffsetAtHalf``
     - The offset when the spread is an odd number of cents wide.

- Sets ``notHeld=True``, ``competeAgainstBestOffset=Decimal('Infinity')``
- Products: STK
- Exchanges: IBKRATS

Limit (IBKR ATS) (``LMT``)
^^^^^^^^^^^^^^^^^^^^^^^^^^

A not-held limit order on IBKR's ATS.

For non-marketable US stock orders; route the contract to IBKRATS.

.. code-block:: python

    IbkrAtsLimitOrder("BUY", 100, 50.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.

- Sets ``notHeld=True``
- Products: STK
- Exchanges: IBKRATS

Pegged to Midpoint (IBKR ATS) (``PEG MID``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pegged to the midpoint on IBKR's own venue, offset by midOffsetAtWhole or midOffsetAtHalf depending on the spread.

Route stocks to IBKRATS and options to IBUSOPT. Live trading sends it without the offsets or a minimum fill.

.. code-block:: python

    PegMidOrder("BUY", 100, 50.00)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.
   * - ``minTradeQty``
     - ``minTradeQty``
     - The smallest fill accepted. Optional.
   * - ``midOffsetAtWhole``
     - ``midOffsetAtWhole``
     - The offset when the spread is an even number of cents wide. Optional.
   * - ``midOffsetAtHalf``
     - ``midOffsetAtHalf``
     - The offset when the spread is an odd number of cents wide. Optional.

- Sets ``notHeld=True``
- Products: STK, OPT
- Exchanges: IBKRATS, IBUSOPT

Advanced order types
--------------------

Order types with many interacting parameters; test them before relying on them.

Relative + Limit (combo) (``REL + LMT``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

IBKR's relative plus limit combo order, with the combo's limit price. IBKR does not document how it works the legs.

.. code-block:: python

    RelativeLimitComboOrder("BUY", 1, 2.50)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``lmtPrice``
     - ``lmtPrice``
     - The limit price.

- Products: BAG

Relative + Market (combo) (``REL + MKT``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

A combo order whose legs start as relative orders, pegged to the bid (buy) or ask (sell); once a leg fills, the remaining legs are sent at market.

.. code-block:: python

    RelativeMarketComboOrder("BUY", 1)

- Products: BAG

Volatility (``VOL``)
^^^^^^^^^^^^^^^^^^^^

An option order priced from an implied volatility.

volatilityType: 1 daily, 2 annual. With continuousUpdate, TWS updates the price as the underlying moves. Delta-neutral hedging is set with the deltaNeutral* fields.

.. code-block:: python

    VolatilityOrder("BUY", 1, 25.0, 2)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``volatility``
     - ``volatility``
     - The implied volatility, in percent.
   * - ``volatilityType``
     - ``volatilityType``
     - 1 daily, 2 annual.

- Products: FOP, OPT

Pegged to Benchmark (``PEG BENCH``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pegged to another contract: its price moves by peggedChangeAmount each time the reference contract moves by referenceChangeAmount.

Both contracts must use the same currency.

.. code-block:: python

    PeggedToBenchmarkOrder("BUY", 100, 50.00, 12345, "ISLAND", 0.02, 0.01)

.. list-table::
   :header-rows: 1

   * - Parameter
     - Order field
     - Meaning
   * - ``startingPrice``
     - ``startingPrice``
     - The price to start from.
   * - ``referenceContractId``
     - ``referenceContractId``
     - The conId of the contract it is pegged to.
   * - ``referenceExchangeId``
     - ``referenceExchangeId``
     - The reference contract's exchange.
   * - ``peggedChangeAmount``
     - ``peggedChangeAmount``
     - How much the order price changes per step.
   * - ``referenceChangeAmount``
     - ``referenceChangeAmount``
     - How much the reference contract moves per step.
   * - ``isPeggedChangeAmountDecrease``
     - ``isPeggedChangeAmountDecrease``
     - Whether the pegged price decreases rather than increases. Optional.
   * - ``stockRefPrice``
     - ``stockRefPrice``
     - The reference price the change is measured from. Optional.
   * - ``stockRangeLower``
     - ``stockRangeLower``
     - Cancel below this reference price. Optional.
   * - ``stockRangeUpper``
     - ``stockRangeUpper``
     - Cancel above this reference price. Optional.

- Products: STK, OPT

Combo orders
------------

Combo (BAG) contracts also take ordinary order types such as LimitOrder and MarketOrder; the combo order types above are the ones only combos take. How SMART routes a combo is set with ``routing=ComboRouting(...)`` on the order type:

.. code-block:: python

    LimitOrder("BUY", 1, 2.50, routing=ComboRouting(nonGuaranteed=True))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``nonGuaranteed``
     - ``NonGuaranteed`` (bool)
     - Let SMART execute each leg separately for the best execution; the combo is then not guaranteed to fill in proportion.
   * - ``legInPriority``
     - ``LeginPrio`` (int)
     - IBKR's LeginPrio tag (live trading sends 0).
   * - ``dontLegInNext``
     - ``DontLeginNext`` (bool)
     - IBKR's DontLeginNext tag (live trading sends 1).

Order options
-------------

Fields any order type takes as keyword arguments.

Time in force
^^^^^^^^^^^^^

How long the order works: "DAY"; "GTC" until canceled; "IOC" fills what it can at once and cancels the rest; "FOK" fills entirely at once or is canceled; "GTD" until goodTillDate; "DTC" day until canceled; "OPG" for a market or limit on open order. goodAfterTime is when the order becomes active.

Times are 'yyyymmdd hh:mm:ss' with an optional zone, such as '20261231 16:00:00 US/Eastern'.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, tif="GTD", goodTillDate="20261231 16:00:00 US/Eastern")

- Fields: ``tif``, ``goodTillDate``, ``goodAfterTime``
- Stability: stable

Outside regular trading hours
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Lets the order also trigger or fill outside regular trading hours.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, outsideRth=True)

- Fields: ``outsideRth``
- Stability: stable

Overnight session
^^^^^^^^^^^^^^^^^

Includes overnight trading.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, includeOvernight=True)

- Fields: ``includeOvernight``
- Products: STK
- Stability: venue

Cash quantity
^^^^^^^^^^^^^

The quantity as an amount of cash: a forex order in the pair's second currency.

Live trading passes a totalQuantity of 0 with it.

.. code-block:: python

    LimitOrder("BUY", 0, 1.10, cashQty=10_000)

- Fields: ``cashQty``
- Products: CASH
- Stability: venue

Hidden and iceberg
^^^^^^^^^^^^^^^^^^

hidden keeps the order out of the market depth shown to others; displaySize is the size shown, for an iceberg order.

hidden applies only to orders routed to NASDAQ.

.. code-block:: python

    LimitOrder("BUY", 1_000, 50.00, displaySize=100)

- Fields: ``hidden``, ``displaySize``
- Stability: venue

Fill conditions
^^^^^^^^^^^^^^^

allOrNone fills the whole order in a single execution or not at all; minQty makes it a minimum quantity order.

.. code-block:: python

    LimitOrder("BUY", 1_000, 50.00, allOrNone=True)

- Fields: ``allOrNone``, ``minQty``
- Stability: venue

Conditions
^^^^^^^^^^

Activate the order (or with conditionsCancelOrder, cancel it) when conditions on price, time, margin, execution, volume or percent change hold: a list of PriceCondition, TimeCondition, ... joined by their conjunction (and/or).

Only limit orders can be canceled by conditions.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, conditions=[TimeCondition(time="20261231 15:30:00 US/Eastern")])

- Fields: ``conditions``, ``conditionsIgnoreRth``, ``conditionsCancelOrder``
- Stability: stable

One cancels all
^^^^^^^^^^^^^^^

When an order of an ocaGroup executes, in full or in part, the rest are canceled (ocaType 1) or reduced in proportion (2), with overfill protection (block); 3 reduces them without it.

IB.oneCancelsAll(orders, group, type) sets both on a list of orders.

.. code-block:: python

    LimitOrder("SELL", 100, 55.00, ocaGroup="exit-1", ocaType=1)

- Fields: ``ocaGroup``, ``ocaType``
- Stability: stable

Parent orders and transmit
^^^^^^^^^^^^^^^^^^^^^^^^^^

A child order (a bracket's profit taker or stop, an adjustable stop, an FX hedge) names its parent's orderId. TWS holds an order sent with transmit=False; the last of a group, sent with transmit=True, sends its parent and siblings with it.

IB.bracketOrder builds a bracket with ids and transmit set.

.. code-block:: python

    StopOrder("SELL", 100, 45.00, parentId=1, transmit=True)

- Fields: ``parentId``, ``transmit``
- Stability: stable

Preset stop loss and profit taker
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

With slOrderType and ptOrderType "PRESET", TWS attaches a stop loss and profit taker with the parameters of its order presets; slOrderId and ptOrderId are order ids reserved for them.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, slOrderType="PRESET", slOrderId=2, ptOrderType="PRESET", ptOrderId=3)

- Fields: ``slOrderType``, ``slOrderId``, ``ptOrderType``, ``ptOrderId``
- Stability: advanced

Account and reference
^^^^^^^^^^^^^^^^^^^^^

The account the order is for, or a financial advisor's model; and a reference that comes back on the order's executions.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, account="U1234567", orderRef="entry")

- Fields: ``account``, ``modelCode``, ``orderRef``
- Stability: stable

What if
^^^^^^^

Get the order's commission and margin without placing it.

IB.whatIfOrder(contract, order) sets it and returns the OrderState.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, whatIf=True)

- Fields: ``whatIf``
- Stability: stable

Manual order time
^^^^^^^^^^^^^^^^^

For brokers and advisors entering an order by hand: when it was entered, as 'YYYYMMDD-HH:mm:ss' in UTC.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, manualOrderTime="20261015-13:00:00")

- Fields: ``manualOrderTime``
- Stability: venue

CME tagging
^^^^^^^^^^^

Under CME Rule 576, manualOrderIndicator marks an order manual (1) or automated (0); extOperator names the operator, for all US futures exchanges.

.. code-block:: python

    LimitOrder("BUY", 1, 5_000.00, extOperator="trader1", manualOrderIndicator=0)

- Fields: ``extOperator``, ``manualOrderIndicator``
- Products: FUT
- Stability: venue

Customer account
^^^^^^^^^^^^^^^^

For nondisclosed omnibus accounts, where it is required: the identifier of the account within the omnibus structure. Not for other accounts.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, customerAccount="CUST1")

- Fields: ``customerAccount``
- Stability: venue

Attached orders
---------------

``IB.bracketOrder`` builds a bracket. An adjustable stop changes once, when the price penetrates its trigger price: pass an adjustment as ``adjust=`` to a stop, stop limit or trailing stop order type (STP, STP LMT, TRAIL, TRAIL LIMIT). An FX hedge is a market order for 0 attached to its parent, placed on the currency pair's contract.

.. autofunction:: ib_async.ordertypes.AdjustToStop

.. autofunction:: ib_async.ordertypes.AdjustToStopLimit

.. autofunction:: ib_async.ordertypes.AdjustToTrail

.. autofunction:: ib_async.ordertypes.FxHedgeOrder

Modifying orders
----------------

To modify a live order, send it again with ``ib.placeOrder`` and the same orderId. Sending the order back as TWS reports it fails for fields TWS fills in; ``modifiedOrder`` prepares it.

.. autofunction:: ib_async.ordertypes.modifiedOrder

IB algos
--------

An algo works an order of the types it lists (those IBKR shows it working): pass it as ``algo=`` to the order type. Its parameters are optional; IBKR uses its defaults for any left out. An algo the order type cannot take, or an order that breaks the algo's conditions, raises ``OrderTypeError``; ``ib_async.ordertypes.algoOf(order)`` names the algo of any ``Order``.

Adaptive
^^^^^^^^

Works a market or limit order between the bid and ask, trading speed against price by priority.

Day orders only. Live trading found it refused outside regular trading hours, and for CME futures options and SPXW index options.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=Adaptive(priority="Urgent"))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``priority``
     - ``adaptivePriority`` (str)
     - Urgent fills fastest, Patient seeks the best price. One of: Urgent, Normal, Patient.

- Works: LMT, MKT orders
- Needs ``tif`` one of ``''``, ``'DAY'``
- Needs ``outsideRth=False``
- Stability: stable

Arrival Price (``ArrivalPx``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Aims for the bid/ask midpoint at the time the order is submitted, trading off market impact against the risk of the price moving.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=ArrivalPrice(maxPctVol=0.1, riskAversion="Neutral"))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``maxPctVol``
     - ``maxPctVol`` (float)
     - The largest share of the market's volume, 0.1 (10%) to 0.5 (50%).
   * - ``riskAversion``
     - ``riskAversion`` (str)
     - How urgently to complete. One of: Get Done, Aggressive, Neutral, Passive.
   * - ``startTime``
     - ``startTime`` (str)
     - When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``endTime``
     - ``endTime`` (str)
     - When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``forceCompletion``
     - ``forceCompletion`` (bool)
     - Attempt completion by the end of the day.
   * - ``allowPastEndTime``
     - ``allowPastEndTime`` (bool)
     - Keep working after endTime if not done.

- Works: LMT orders
- Stability: advanced

Dark Ice (``DarkIce``)
^^^^^^^^^^^^^^^^^^^^^^

Shows only displaySize of a limit order, randomizing the size shown and keeping the rest hidden.

Day orders only.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=DarkIce(displaySize=100))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``displaySize``
     - ``displaySize`` (int)
     - The size to show.
   * - ``startTime``
     - ``startTime`` (str)
     - When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``endTime``
     - ``endTime`` (str)
     - When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``allowPastEndTime``
     - ``allowPastEndTime`` (bool)
     - Keep working after endTime if not done.

- Works: LMT orders
- Needs ``tif`` one of ``''``, ``'DAY'``
- Stability: advanced

Percentage of Volume (``PctVol``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Trades a fixed share of the market's volume.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=PercentOfVolume(pctVol=0.1))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``pctVol``
     - ``pctVol`` (float)
     - The share of the market's volume, 0.1 (10%) to 0.5 (50%).
   * - ``startTime``
     - ``startTime`` (str)
     - When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``endTime``
     - ``endTime`` (str)
     - When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``noTakeLiq``
     - ``noTakeLiq`` (bool)
     - Attempt never to take liquidity.

- Works: LMT orders
- Stability: advanced

Price Variant Percentage of Volume (``PctVolPx``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Trades a share of volume that changes with the price: by deltaPctVol per move, between minPctVol4Px and maxPctVol4Px.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=PriceVariantPercentOfVolume(pctVol=0.1, deltaPctVol=0.1))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``pctVol``
     - ``pctVol`` (float)
     - The share of the market's volume, 0.1 (10%) to 0.5 (50%).
   * - ``deltaPctVol``
     - ``deltaPctVol`` (float)
     - The change in share per price move, 0.1 (10%) to 0.5 (50%).
   * - ``minPctVol4Px``
     - ``minPctVol4Px`` (float)
     - The lowest share, 0.1 (10%) to 0.5 (50%).
   * - ``maxPctVol4Px``
     - ``maxPctVol4Px`` (float)
     - The highest share, 0.1 (10%) to 0.5 (50%).
   * - ``startTime``
     - ``startTime`` (str)
     - When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``endTime``
     - ``endTime`` (str)
     - When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``noTakeLiq``
     - ``noTakeLiq`` (bool)
     - Attempt never to take liquidity.

- Works: LMT orders
- Stability: advanced

Size Variant Percentage of Volume (``PctVolSz``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Trades a share of volume that moves from startPctVol to endPctVol as the order fills.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=SizeVariantPercentOfVolume(startPctVol=0.2, endPctVol=0.4))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``startPctVol``
     - ``startPctVol`` (float)
     - The share of volume at the start, 0.1 (10%) to 0.5 (50%).
   * - ``endPctVol``
     - ``endPctVol`` (float)
     - The share of volume at the end, 0.1 (10%) to 0.5 (50%).
   * - ``startTime``
     - ``startTime`` (str)
     - When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``endTime``
     - ``endTime`` (str)
     - When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``noTakeLiq``
     - ``noTakeLiq`` (bool)
     - Attempt never to take liquidity.

- Works: LMT orders
- Stability: advanced

Time Variant Percentage of Volume (``PctVolTm``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Trades a share of volume that moves from startPctVol to endPctVol between startTime and endTime.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=TimeVariantPercentOfVolume(startPctVol=0.2, endPctVol=0.4))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``startPctVol``
     - ``startPctVol`` (float)
     - The share of volume at the start, 0.1 (10%) to 0.5 (50%).
   * - ``endPctVol``
     - ``endPctVol`` (float)
     - The share of volume at the end, 0.1 (10%) to 0.5 (50%).
   * - ``startTime``
     - ``startTime`` (str)
     - When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``endTime``
     - ``endTime`` (str)
     - When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``noTakeLiq``
     - ``noTakeLiq`` (bool)
     - Attempt never to take liquidity.

- Works: LMT orders
- Stability: advanced

TWAP (``Twap``)
^^^^^^^^^^^^^^^

Aims for the time-weighted average price from when the order is submitted to when it completes.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=Twap(strategyType="Marketable", startTime="09:30:00 US/Eastern"))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``strategyType``
     - ``strategyType`` (str)
     - Which trades count toward the price. One of: Marketable, Matching, Midpoint, Matching Same Side, Matching Last.
   * - ``startTime``
     - ``startTime`` (str)
     - When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``endTime``
     - ``endTime`` (str)
     - When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``allowPastEndTime``
     - ``allowPastEndTime`` (bool)
     - Keep working after endTime if not done.
   * - ``catchUp``
     - ``catchUp`` (bool)
     - Catch up in time.

- Works: LMT orders
- Products: STK
- Stability: advanced

VWAP (``Vwap``)
^^^^^^^^^^^^^^^

Aims for the volume-weighted average price, on a best-efforts basis.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=Vwap(maxPctVol=0.1))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``maxPctVol``
     - ``maxPctVol`` (float)
     - The largest share of the market's volume, 0.1 (10%) to 0.5 (50%).
   * - ``startTime``
     - ``startTime`` (str)
     - When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``endTime``
     - ``endTime`` (str)
     - When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``allowPastEndTime``
     - ``allowPastEndTime`` (bool)
     - Keep working after endTime if not done.
   * - ``noTakeLiq``
     - ``noTakeLiq`` (bool)
     - Attempt never to take liquidity.
   * - ``speedUp``
     - ``speedUp`` (bool)
     - Compensate for the lower fill rate a limit price causes.

- Works: LMT orders
- Products: STK
- Stability: advanced

Balance Impact and Risk (``BalanceImpactRisk``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For options: balances the market impact of trading against the risk of the price moving.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=BalanceImpactRisk(maxPctVol=0.1, riskAversion="Neutral"))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``maxPctVol``
     - ``maxPctVol`` (float)
     - The largest share of the market's volume, 0.1 (10%) to 0.5 (50%).
   * - ``riskAversion``
     - ``riskAversion`` (str)
     - How urgently to complete. One of: Get Done, Aggressive, Neutral, Passive.
   * - ``forceCompletion``
     - ``forceCompletion`` (bool)
     - Attempt completion by the end of the day.

- Works: LMT orders
- Products: OPT
- Stability: advanced

Minimise Impact (``MinImpact``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

For options: minimizes market impact.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=MinimiseImpact(maxPctVol=0.1))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``maxPctVol``
     - ``maxPctVol`` (float)
     - The largest share of the market's volume, 0.1 (10%) to 0.5 (50%).

- Works: LMT orders
- Products: OPT
- Stability: advanced

Close Price (``ClosePx``)
^^^^^^^^^^^^^^^^^^^^^^^^^

Aims for the closing price: breaks a large order down and times its entry.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=ClosePrice(maxPctVol=0.1, riskAversion="Neutral"))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``maxPctVol``
     - ``maxPctVol`` (float)
     - The largest share of the market's volume, 0.1 (10%) to 0.5 (50%).
   * - ``riskAversion``
     - ``riskAversion`` (str)
     - How urgently to complete. One of: Get Done, Aggressive, Neutral, Passive.
   * - ``startTime``
     - ``startTime`` (str)
     - When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``forceCompletion``
     - ``forceCompletion`` (bool)
     - Attempt completion by the end of the day.

- Works: LMT orders
- Stability: advanced

Accumulate/Distribute (``AD``)
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Splits a large order into componentSize pieces sent timeBetweenOrders seconds apart, optionally randomized.

.. code-block:: python

    LimitOrder("BUY", 100, 50.00, algo=AccumulateDistribute(componentSize=100, timeBetweenOrders=60))

.. list-table::
   :header-rows: 1

   * - Parameter
     - IBKR tag
     - Meaning
   * - ``componentSize``
     - ``componentSize`` (int)
     - The size of each piece; at most the order's size.
   * - ``timeBetweenOrders``
     - ``timeBetweenOrders`` (int)
     - Seconds between pieces.
   * - ``randomizeTime20``
     - ``randomizeTime20`` (bool)
     - Vary the time between pieces by +/- 20%.
   * - ``randomizeSize55``
     - ``randomizeSize55`` (bool)
     - Vary the piece size by +/- 55%.
   * - ``giveUp``
     - ``giveUp`` (int)
     - A number associated with the clearing.
   * - ``catchUp``
     - ``catchUp`` (bool)
     - Catch up in time.
   * - ``waitForFill``
     - ``waitForFill`` (bool)
     - Wait for each piece to fill before the next.
   * - ``startTime``
     - ``activeTimeStart`` (str)
     - When to start, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.
   * - ``endTime``
     - ``activeTimeEnd`` (str)
     - When to finish, as 'hh:mm:ss TMZ' or 'YYYYMMDD-hh:mm:ss TMZ'.

- Works: LMT, MKT, REL orders
- Stability: advanced

IBKR order type codes
---------------------

Every IBKR order type code, with the other spellings IBKR and contract details use for it.

Built
^^^^^

.. list-table::
   :header-rows: 1

   * - Code (other spellings)
     - Order types
   * - ``MKT`` (``MARKET``)
     - ``MarketOrder``, ``MarketOnOpenOrder``
   * - ``LMT`` (``LIMIT``)
     - ``LimitOrder``, ``LimitOnOpenOrder``, ``DiscretionaryOrder``, ``SweepToFillOrder``, ``BlockOrder``, ``AuctionLimitOrder``, ``IbkrAtsLimitOrder``, ``ComboLegPricesOrder``
   * - ``STP`` (``STOP``)
     - ``StopOrder``
   * - ``STP LMT`` (``STOP LIMIT``, ``STOPLIMIT``, ``STOPLMT``, ``STPLMT``)
     - ``StopLimitOrder``
   * - ``REL`` (``RELATIVE``)
     - ``RelativeOrder``
   * - ``TRAIL`` (``TRAILING STOP``)
     - ``TrailingStopOrder``
   * - ``BOX TOP`` (``BOXTOP``, ``BOX_TOP``)
     - ``BoxTopOrder``
   * - ``LIT``
     - ``LimitIfTouchedOrder``
   * - ``LOC`` (``LMT CLS``, ``LMTCLS``)
     - ``LimitOnCloseOrder``
   * - ``MIDPRICE`` (``MIDPX``)
     - ``MidpriceOrder``
   * - ``MIT``
     - ``MarketIfTouchedOrder``
   * - ``MKT PRT`` (``MKTPRT``)
     - ``MarketWithProtectionOrder``
   * - ``MOC`` (``MKT CLS``, ``MKTCLS``)
     - ``MarketOnCloseOrder``
   * - ``MTL`` (``MKT TO LMT``, ``MKTTOLMT``)
     - ``AtAuctionOrder``, ``MarketToLimitOrder``
   * - ``PASSV REL``
     - ``PassiveRelativeOrder``
   * - ``PEG BENCH`` (``PEGBENCH``)
     - ``PeggedToBenchmarkOrder``
   * - ``PEG BEST`` (``PEGBEST``)
     - ``PegBestOrder``, ``PegBestUpToMidOrder``
   * - ``PEG MID`` (``PEGMID``)
     - ``PeggedToMidpointOrder``, ``PegMidOrder``
   * - ``PEG MKT`` (``PEGMKT``)
     - ``PeggedToMarketOrder``
   * - ``PEG STK`` (``PEGSTK``)
     - ``PeggedToStockOrder``
   * - ``REL + LMT`` (``REL+LMT``)
     - ``RelativeLimitComboOrder``
   * - ``REL + MKT`` (``REL+MKT``)
     - ``RelativeMarketComboOrder``
   * - ``SNAP MID`` (``SNAPMID``)
     - ``SnapToMidpointOrder``
   * - ``SNAP MKT`` (``SNAPMKT``)
     - ``SnapToMarketOrder``
   * - ``SNAP PRIM`` (``SNAPPRIM``, ``SNAPREL``)
     - ``SnapToPrimaryOrder``
   * - ``STP PRT`` (``STOP PROTECT``)
     - ``StopWithProtectionOrder``
   * - ``TRAIL LIMIT`` (``TRAILLMT``, ``TRAILLIMIT``)
     - ``TrailingStopLimitOrder``
   * - ``VOL`` (``VOLATILITY``, ``VOLAT``)
     - ``VolatilityOrder``

Not built
^^^^^^^^^

For these, set the fields on ``Order`` directly.

.. list-table::
   :header-rows: 1

   * - Code (other spellings)
     - Why not
   * - ``FIX PEGGED`` (``FIXPEGGED``)
     - IBKR does not document its parameters.
   * - ``PEG PRIM`` (``PEGPRIM``)
     - IBKR marks it uncertain; Relative (REL) is IBKR's order pegged to the primary price.
   * - ``LMT + MKT`` (``LMT+MKT``)
     - TWS takes its combo price as a trigger price; IBKR does not document how the API sends it.
   * - ``TRAIL LIT`` (``TRAILLIT``)
     - IBKR does not document how to build it.
   * - ``TRAIL MIT`` (``TRAILMIT``)
     - IBKR does not document how to build it.
   * - ``TRAIL LMT + MKT``
     - A trailing combo type IBKR does not document for the API.
   * - ``TRAIL REL + MKT``
     - A trailing combo type IBKR does not document for the API.
   * - ``VWAP``
     - IBKR does not document it for the API; the Vwap algo works an order for the volume-weighted average price.
   * - ``QUOTE``
     - A quote in reply to a request for quote, not an order to trade.
   * - ``PPV`` (``PEG PRM VOL``, ``PEGPRIMVOL``, ``PEGPRMVOL``)
     - A volatility-pegged option type IBKR does not document for the API.
   * - ``PDV`` (``PEG MID VOL``, ``PEGMIDVOL``)
     - A volatility-pegged option type IBKR does not document for the API.
   * - ``PMV`` (``PEG MKT VOL``, ``PEGMKTVOL``)
     - A volatility-pegged option type IBKR does not document for the API.
   * - ``PSV`` (``PEG SURF VOL``, ``PEGSURFVOL``, ``PEGSRFVOL``)
     - A volatility-pegged option type IBKR does not document for the API.
