"""Wrapper to handle incoming messages."""

import asyncio
import logging
import time
from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Final, TypeAlias, cast
from zoneinfo import ZoneInfo

from ib_async._requests import (
    CompositeKey,
    ReqIdKey,
    RequestRegistry,
    SingletonKey,
    WhatIfKey,
)
from ib_async._subscriptions import (
    HistoricalBarsSub,
    MktDataSub,
    PnLSingleSub,
    PnLSub,
    RealTimeBarsSub,
    ScannerSub,
    SubscriptionRegistry,
)
from ib_async.contract import (
    Contract,
    ContractDescription,
    ContractDetails,
    DeltaNeutralContract,
    ScanData,
)
from ib_async.objects import (
    AccountValue,
    BarData,
    CommissionReport,
    DepthMktDataDescription,
    Dividends,
    DOMLevel,
    EfpData,
    Execution,
    FamilyCode,
    Fill,
    FundamentalRatios,
    HistogramData,
    HistoricalNews,
    HistoricalSchedule,
    HistoricalSession,
    HistoricalTick,
    HistoricalTickBidAsk,
    HistoricalTickLast,
    IBDefaults,
    MktDepthData,
    NewsArticle,
    NewsBulletin,
    NewsProvider,
    NewsTick,
    OptionChain,
    OptionComputation,
    PortfolioItem,
    Position,
    PriceIncrement,
    RealTimeBar,
    ScanDataList,
    SoftDollarTier,
    TickAttribBidAsk,
    TickAttribLast,
    TickByTickAllLast,
    TickByTickBidAsk,
    TickByTickMidPoint,
    TickData,
    TradeLogEntry,
)
from ib_async.order import Order, OrderState, OrderStatus, Trade
from ib_async.ticker import Ticker
from ib_async.util import (
    UNSET_DOUBLE,
    UNSET_INTEGER,
    dataclassAsDict,
    dataclassUpdate,
    getLoop,
    globalErrorEvent,
    parseIBDatetime,
)

if TYPE_CHECKING:
    from ib_async.ib import IB


OrderKeyType: TypeAlias = int | tuple[int, int]
TickDict: TypeAlias = dict[int, str]

PRICE_TICK_MAP: Final[TickDict] = {
    6: "high",
    72: "high",
    7: "low",
    73: "low",
    9: "close",
    75: "close",
    14: "open",
    76: "open",
    15: "low13week",
    16: "high13week",
    17: "low26week",
    18: "high26week",
    19: "low52week",
    20: "high52week",
    35: "auctionPrice",
    37: "markPrice",
    50: "bidYield",
    103: "bidYield",
    51: "askYield",
    104: "askYield",
    52: "lastYield",
    57: "lastRthTrade",
    78: "creditmanMarkPrice",
    79: "creditmanSlowMarkPrice",
    92: "etfNavClose",
    93: "etfNavPriorClose",
    94: "etfNavBid",
    95: "etfNavAsk",
    96: "etfNavLast",
    97: "etfFrozenNavLast",
    98: "etfNavHigh",
    99: "etfNavLow",
    101: "estimatedIpoMidpoint",
    102: "finalIpoLast",
}


SIZE_TICK_MAP: Final[TickDict] = {
    8: "volume",
    74: "volume",
    63: "volumeRate3Min",
    64: "volumeRate5Min",
    65: "volumeRate10Min",
    21: "avVolume",
    22: "openInterest",
    27: "callOpenInterest",
    28: "putOpenInterest",
    29: "callVolume",
    30: "putVolume",
    34: "auctionVolume",
    36: "auctionImbalance",
    61: "regulatoryImbalance",
    86: "futuresOpenInterest",
    87: "avOptionVolume",
    89: "shortableShares",
}

GENERIC_TICK_MAP: Final[TickDict] = {
    23: "histVolatility",
    24: "impliedVolatility",
    31: "indexFuturePremium",
    46: "shortable",
    49: "halted",
    54: "tradeCount",
    55: "tradeRate",
    56: "volumeRate",
    58: "rtHistVolatility",
    60: "bondFactorMultiplier",
    90: "delayedHalted",
}

GREEKS_TICK_MAP: Final[TickDict] = {
    10: "bidGreeks",
    80: "bidGreeks",
    11: "askGreeks",
    81: "askGreeks",
    12: "lastGreeks",
    82: "lastGreeks",
    13: "modelGreeks",
    83: "modelGreeks",
    53: "custGreeks",
}

EFP_TICK_MAP: Final[TickDict] = {
    38: "bidEfp",
    39: "askEfp",
    40: "lastEfp",
    41: "openEfp",
    42: "highEfp",
    43: "lowEfp",
    44: "closeEfp",
}

STRING_TICK_MAP: Final[TickDict] = {
    25: "optionBidExch",
    26: "optionAskExch",
    32: "bidExchange",
    33: "askExchange",
    84: "lastExchange",
    85: "lastRegTime",
    91: "reutersMutualFunds",
    100: "socialMarketAnalytics",
}

TIMESTAMP_TICK_MAP: Final[TickDict] = {
    45: "lastTimestamp",
    88: "delayedLastTimestamp",
}

RT_VOLUME_TICK_MAP: Final[TickDict] = {
    48: "rtVolume",
    77: "rtTradeVolume",
}


class RequestError(Exception):
    """
    Exception to raise when the API reports an error that can be tied to
    a single request.
    """

    def __init__(self, reqId: int, code: int, message: str):
        """
        Args:
          reqId: Original request ID.
          code: Original error code.
          message: Original error message.
        """
        super().__init__(f"[reqId {reqId}] API error: {code}: {message}")
        self.reqId = reqId
        self.code = code
        self.message = message


# Warnings are currently:
# 105 - Order being modified does not match the original order. (?)
# 110 - The price does not conform to the minimum price variation for this contract.
# 165 - Historical market Data Service query message.
# 321 - Server error when validating an API client request.
# 329 - Order modify failed. Cannot change to the new order type.
# 399 - Order message error
# 404 -	Shares for this order are not immediately available for short sale. The order will be held while we attempt to locate the shares.
# 434 -	The order size cannot be zero.
# 492 - ? not listed
# 10167 ? not listed
# 10349 - Warning about "Order TIF was set to DAY based on order preset" but does NOT cancel active order
# Note: error 321 means error validing, but if the message is the result of a MODIFY, the order _is still live_ and we must not delete it.
# TODO: investigate if error 321 happens on _new_ order placement with incorrect parameters too, then we should probably delete the order.

# Previously this was included as a Warning condition, but 202 is literally "Order Canceled" error status, so now it is an order-delete error:
# 202 - Order cancelled - Reason:

_WARNING_CODES: Final[frozenset[int]] = frozenset(
    {105, 110, 165, 321, 329, 399, 404, 434, 492, 10167, 10349}
)


# Order fields that TWS may legitimately update at runtime via openOrder
# callbacks for an order we already track. Why a whitelist instead of a full
# merge: TWS sometimes returns placeholder/default values for fields the user
# set locally at placement time, so a blanket copy would clobber user intent.
# (See git history of wrapper.openOrder — this list has grown each time a
# specific live-mutable field was found to be silently dropped.)
#
# Allowlist over denylist by design: the failure mode of a denylist is that a
# TWS placeholder value silently overwrites a user-set field — catastrophic
# for live trading. The failure mode of the allowlist is that a TWS-managed
# runtime field (e.g. a new trailing-stop variant) doesn't auto-propagate to
# ``Trade.order`` until added here — annoying but recoverable, and callers
# can read ``Trade.serverOrder`` for the raw TWS view in the meantime.
MUTABLE_ORDER_FIELDS: Final[tuple[str, ...]] = (
    "permId",
    "totalQuantity",
    "lmtPrice",
    "auxPrice",
    "orderType",
    "orderRef",
    # Trailing-stop runtime state (issue #102): IBKR ratchets trailStopPrice
    # as the market moves, and users can edit it (or lmtPriceOffset on a
    # TRAIL LIMIT) directly in TWS. Both arrive on every openOrder update.
    "trailStopPrice",
    "trailingPercent",
    "lmtPriceOffset",
    # Adjustable-stop runtime state — same shape as trailing-stop fields:
    # TWS owns these once the order is live and pushes updates via openOrder.
    "adjustedOrderType",
    "triggerPrice",
    "adjustedStopPrice",
    "adjustedStopLimitPrice",
    "adjustedTrailingAmount",
    "adjustableTrailingUnit",
)


@dataclass
class Wrapper:
    """Wrapper implementation for use with the IB class."""

    # reference back to IB so wrapper can access API methods
    ib: "IB"

    accountValues: dict[tuple, AccountValue] = field(init=False)
    """ (account, tag, currency, modelCode) -> AccountValue """

    acctSummary: dict[tuple, AccountValue] = field(init=False)
    """ (account, tag, currency) -> AccountValue """

    portfolio: dict[str, dict[int, PortfolioItem]] = field(init=False)
    """ account -> conId -> PortfolioItem """

    positions: dict[str, dict[int, Position]] = field(init=False)
    """ account -> conId -> Position """

    trades: dict[OrderKeyType, Trade] = field(init=False)
    """ (client, orderId) or permId -> Trade """

    permId2Trade: dict[int, Trade] = field(init=False)
    """ permId -> Trade """

    fills: dict[str, Fill] = field(init=False)
    """ execId -> Fill """

    newsTicks: list[NewsTick] = field(init=False)

    msgId2NewsBulletin: dict[int, NewsBulletin] = field(init=False)
    """ msgId -> NewsBulletin """

    pendingTickers: set[Ticker] = field(init=False)

    lastTime: datetime = field(init=False)
    """ UTC time of last network packet arrival. """

    # Like 'lastTime' but in time.time() float format instead of a datetime object
    # (not to be confused with 'lastTimestamp' of Ticker objects which is the timestamp
    #  of the last trade event)
    time: float = field(init=False)

    accounts: list[str] = field(init=False)
    clientId: int = field(init=False)
    # Active reqId for the (singleton) Wall Street Horizon meta /
    # event subscriptions. ``IB.reqWshMetaData`` /
    # ``IB.reqWshEventData`` and their cancel siblings coordinate
    # through these per-connection slots; they are reset to 0 in
    # :meth:`reset` so a watchdog reconnect starts fresh.
    _wshMetaReqId: int = field(init=False)
    _wshEventReqId: int = field(init=False)
    _timeout: float = field(init=False)

    requests: RequestRegistry = field(init=False)
    """Source of truth for in-flight request correlation. Owns each
    request's future, accumulator container, and originating contract.
    See :mod:`ib_async._requests`."""

    subscriptions: SubscriptionRegistry = field(init=False)
    """Source of truth for live data subscriptions: mktData, tickByTick,
    mktDepth, real-time bars, historical bars with keepUpToDate, scanner,
    PnL. See :mod:`ib_async._subscriptions`."""

    _logger: logging.Logger = field(
        default_factory=lambda: logging.getLogger("ib_async.wrapper")
    )
    _timeoutHandle: asyncio.TimerHandle | None = None

    # value used when a field has missing, empty, or not populated data
    defaults: IBDefaults = field(default_factory=IBDefaults)

    def __post_init__(self):
        # extract values from defaults objects just to use locally
        self.defaultTimezone = self.defaults.timezone
        self.defaultEmptyPrice = self.defaults.emptyPrice
        self.defaultEmptySize = self.defaults.emptySize

        self.reset()

    def reset(self):
        self.accountValues = {}
        self.acctSummary = {}
        self.portfolio = defaultdict(dict)
        self.positions = defaultdict(dict)
        self.trades = {}
        self.permId2Trade = {}
        self.fills = {}
        self.newsTicks = []
        self.msgId2NewsBulletin = {}
        self.pendingTickers = set()
        self.lastTime = datetime.min
        self.time = -1
        self.accounts = []
        self.clientId = -1
        self._wshMetaReqId = 0
        self._wshEventReqId = 0
        self._timeout = 0
        self.requests = RequestRegistry()
        self.subscriptions = SubscriptionRegistry(self)
        # Cache the bound method on the hot per-tick path so each tick
        # handler does ``self._get_ticker(reqId)`` (one C-level dict.get
        # via the bound-method's __self__) instead of
        # ``self.subscriptions.get_ticker(reqId)`` which allocates a
        # fresh bound-method object per call.
        self._get_ticker = self.subscriptions.get_ticker
        self.setTimeout(0)

    def connectionClosed(self):
        """Tear down every awaiter and observable in a deterministic order.

        IBKR runs a daily server-side reset; the client is expected to
        observe a socket disconnect, drain every awaiting consumer with
        a final state transition, and let the watchdog resync on
        reconnect. The order below matters:

        1. Fail every in-flight request future so any ``await`` woken
           up from this disconnect raises a ``ConnectionError`` rather
           than blocking forever.
        2. Close every live :class:`Subscription` with
           ``send_cancel=False`` (the socket is gone). Each Subscription
           sets done on its per-subscriber ``updateEvent`` — bars,
           scanner data lists — so consumers awaiting more updates
           wake up.
        3. Set done on the pooled ``Ticker.updateEvent`` for every
           Ticker we know about. Tickers are shared across mktData /
           tickByTick / mktDepth subscriptions and are therefore not
           owned by any individual Subscription.
        4. For every still-live trade, emit a final ``Inactive``
           transition + audit log entry, then set done on every
           per-trade event. Trades that were already in a done state
           keep their terminal status; we only set done on their events.
        5. Emit ``globalErrorEvent`` so any module-wide observer is
           notified.
        6. ``reset()`` wipes wrapper state. The watchdog reconnects and
           re-syncs from the server.
        """

        error = ConnectionError("Socket disconnect")

        # Snapshot Tickers are private (not in the pool), so gather them
        # from their still-live subscriptions before close_all drops the
        # reqId index — otherwise an awaiter on a snapshot Ticker's
        # ``updateEvent`` would never wake after a mid-snapshot disconnect.
        snapshot_tickers = [
            sub.ticker
            for sub in self.subscriptions
            if isinstance(sub, MktDataSub) and sub.snapshot and sub.ticker is not None
        ]

        self.requests.fail_all(error)
        self.subscriptions.close_all(send_cancel=False)

        for ticker in self.subscriptions.pooled_tickers():
            ticker.updateEvent.set_done()
        for ticker in snapshot_tickers:
            ticker.updateEvent.set_done()

        now = datetime.now(self.defaultTimezone)
        # Snapshot the trades dict because ``trade.statusEvent.emit`` and
        # ``self.ib.orderStatusEvent.emit`` below run user callbacks; a
        # callback that calls ``IB.placeOrder`` would mutate
        # ``self.trades`` mid-iteration and raise RuntimeError.
        for trade in list(self.trades.values()):
            if not trade.isDone():
                trade.orderStatus.status = OrderStatus.Inactive
                trade.log.append(
                    TradeLogEntry(now, OrderStatus.Inactive, "Disconnected")
                )
                self.ib.orderStatusEvent.emit(trade)
                trade.statusEvent.emit(trade)
            for event in (
                trade.statusEvent,
                trade.modifyEvent,
                trade.fillEvent,
                trade.filledEvent,
                trade.commissionReportEvent,
                trade.cancelEvent,
                trade.cancelledEvent,
            ):
                event.set_done()

        globalErrorEvent.emit(error)
        self.reset()

    def _normalizeDatetime(self, value: datetime | Any) -> datetime | Any:
        """Convert datetime values to the configured default timezone."""
        if not isinstance(value, datetime):
            return value

        if value.tzinfo is None:
            tz = ZoneInfo(str(self.ib.TimezoneTWS)) if self.ib.TimezoneTWS else None
            value = value.replace(tzinfo=tz or self.defaultTimezone)

        return value.astimezone(self.defaultTimezone)

    def contractForReqId(self, reqId: int) -> Contract | None:
        """
        Return the originating contract for ``reqId`` if one is known,
        consulting the subscription side first and falling back to the
        in-flight request side.

        The two registries are the only stores of contract identity:
        :attr:`subscriptions` owns it for live data flows (mktData,
        tickByTick, mktDepth, bars, scanners), and :attr:`requests`
        owns it for one-shot data requests that carried a ``contract``
        through ``open(...)``.
        """
        sub = self.subscriptions.get_sub(reqId)
        if sub is not None:
            return sub.contract

        req = self.requests.get(ReqIdKey(reqId))
        if req is not None:
            return req.contract
        return None

    def _snapshotContractForReqId(self, reqId: int) -> Contract | None:
        """Return a defensive copy of the contract for ``reqId`` so a
        stored snapshot survives later mutation of the original
        Contract. Used by ``tickNews`` to stamp NewsTick events."""
        contract = self.contractForReqId(reqId)
        return Contract.recreate(contract) if contract else None

    def orderKey(self, clientId: int, orderId: int, permId: int) -> OrderKeyType:
        key: OrderKeyType
        if orderId <= 0:
            # order is placed manually from TWS
            key = permId
        else:
            key = (clientId, orderId)
        return key

    def setTimeout(self, timeout: float):
        self.lastTime = datetime.now(self.defaultTimezone)
        if self._timeoutHandle:
            self._timeoutHandle.cancel()

        self._timeoutHandle = None
        self._timeout = timeout

        if timeout:
            self._setTimer(timeout)

    def _setTimer(self, delay: float = 0):
        if self.lastTime == datetime.min:
            return

        now = datetime.now(self.defaultTimezone)
        diff = (now - self.lastTime).total_seconds()

        if not delay:
            delay = self._timeout - diff

        if delay > 0:
            loop = getLoop()
            self._timeoutHandle = loop.call_later(delay, self._setTimer)
        else:
            self._logger.debug("Timeout")
            self.setTimeout(0)
            self.ib.timeoutEvent.emit(diff)

    # Helper methods for tick processing

    def _processTimestampTick(self, ticker: Ticker, fieldName: str, value: str):
        """Convert timestamp string to datetime and set on ticker field."""
        timestamp = int(value)
        # Only populate if timestamp isn't '0' (we don't want to report "last trade: 20,000 days ago")
        if timestamp:
            setattr(
                ticker,
                fieldName,
                datetime.fromtimestamp(timestamp, self.defaultTimezone),
            )

    def _processRtVolumeTick(
        self, ticker: Ticker, tickType: int, value: str
    ) -> tuple[float, float] | None:
        """
        Parse RT Volume or RT Trade Volume tick.

        Format: price;size;ms since epoch;total volume;VWAP;single trade
        Example: 701.28;1;1348075471534;67854;701.46918464;true

        Returns (price, size) tuple if valid, None otherwise.
        """
        priceStr, sizeStr, rtTime, volume, vwap, _ = value.split(";")

        if volume:
            # Set volume field based on tick type
            volumeField = RT_VOLUME_TICK_MAP[tickType]
            setattr(ticker, volumeField, float(volume))

        if vwap:
            ticker.vwap = float(vwap)

        if rtTime:
            ticker.rtTime = datetime.fromtimestamp(
                int(rtTime) / 1000, self.defaultTimezone
            )

        if priceStr == "":
            return None

        return (float(priceStr), float(sizeStr))

    # wrapper methods

    def connectAck(self):
        pass

    def nextValidId(self, reqId: int):
        pass

    def managedAccounts(self, accountsList: str):
        self.accounts = [a for a in accountsList.split(",") if a]

    def updateAccountTime(self, timestamp: str):
        pass

    def updateAccountValue(self, tag: str, val: str, currency: str, account: str):
        key = (account, tag, currency, "")
        acctVal = AccountValue(account, tag, val, currency, "")
        self.accountValues[key] = acctVal
        self.ib.accountValueEvent.emit(acctVal)

    def accountDownloadEnd(self, _account: str):
        # sent after updateAccountValue and updatePortfolio both finished
        self.requests.set_result(SingletonKey("accountValues"))

    def accountUpdateMulti(
        self,
        reqId: int,
        account: str,
        modelCode: str,
        tag: str,
        val: str,
        currency: str,
    ):
        key = (account, tag, currency, modelCode)
        acctVal = AccountValue(account, tag, val, currency, modelCode)
        self.accountValues[key] = acctVal
        self.ib.accountValueEvent.emit(acctVal)

    def accountUpdateMultiEnd(self, reqId: int):
        self.requests.set_result(ReqIdKey(reqId))

    def accountSummary(
        self, _reqId: int, account: str, tag: str, value: str, currency: str
    ):
        key = (account, tag, currency)
        acctVal = AccountValue(account, tag, value, currency, "")
        self.acctSummary[key] = acctVal
        self.ib.accountSummaryEvent.emit(acctVal)

    def accountSummaryEnd(self, reqId: int):
        self.requests.set_result(ReqIdKey(reqId))

    def updatePortfolio(
        self,
        contract: Contract,
        posSize: float,
        marketPrice: float,
        marketValue: float,
        averageCost: float,
        unrealizedPNL: float,
        realizedPNL: float,
        account: str,
    ):
        contract = Contract.recreate(contract)
        portfItem = PortfolioItem(
            contract,
            posSize,
            marketPrice,
            marketValue,
            averageCost,
            unrealizedPNL,
            realizedPNL,
            account,
        )
        portfolioItems = self.portfolio[account]

        if posSize == 0:
            portfolioItems.pop(contract.conId, None)
        else:
            portfolioItems[contract.conId] = portfItem

        self._logger.info(f"updatePortfolio: {portfItem}")
        self.ib.updatePortfolioEvent.emit(portfItem)

    def position(
        self, account: str, contract: Contract, posSize: float, avgCost: float
    ):
        contract = Contract.recreate(contract)
        position = Position(account, contract, posSize, avgCost)
        positions = self.positions[account]

        # if this updates position to 0 quantity, remove the position
        if posSize == 0:
            positions.pop(contract.conId, None)
        else:
            # else, add or replace the position in-place
            positions[contract.conId] = position

        self._logger.info(f"position: {position}")
        # Append to a live reqPositionsAsync accumulator if one is in
        # flight; the registry call is a no-op otherwise, so the live
        # position-update event below always fires.
        self.requests.append(SingletonKey("positions"), position)

        self.ib.positionEvent.emit(position)

    def positionEnd(self):
        self.requests.set_result(SingletonKey("positions"))

    def positionMulti(
        self,
        reqId: int,
        account: str,
        modelCode: str,
        contract: Contract,
        pos: float,
        avgCost: float,
    ):
        pass

    def positionMultiEnd(self, reqId: int):
        pass

    def pnl(
        self, reqId: int, dailyPnL: float, unrealizedPnL: float, realizedPnL: float
    ):
        sub = self.subscriptions.get_sub(reqId)
        if not isinstance(sub, PnLSub):
            return

        pnl = sub.pnl
        pnl.dailyPnL = dailyPnL
        pnl.unrealizedPnL = unrealizedPnL
        pnl.realizedPnL = realizedPnL
        self.ib.pnlEvent.emit(pnl)

    def pnlSingle(
        self,
        reqId: int,
        pos: int,
        dailyPnL: float,
        unrealizedPnL: float,
        realizedPnL: float,
        value: float,
    ):
        sub = self.subscriptions.get_sub(reqId)
        if not isinstance(sub, PnLSingleSub):
            return

        pnlSingle = sub.pnlSingle
        pnlSingle.position = pos
        pnlSingle.dailyPnL = dailyPnL
        pnlSingle.unrealizedPnL = unrealizedPnL
        pnlSingle.realizedPnL = realizedPnL
        pnlSingle.value = value
        self.ib.pnlSingleEvent.emit(pnlSingle)

    def openOrder(
        self, orderId: int, contract: Contract, order: Order, orderState: OrderState
    ):
        """
        This wrapper is called to:

        * feed in open orders at startup;
        * feed in open orders or order updates from other clients and TWS
          if clientId=master id;
        * feed in manual orders and order updates from TWS if clientId=0;
        * handle openOrders and allOpenOrders responses.
        """
        if order.whatIf:
            # response to whatIfOrder
            if float(orderState.initMarginChange) != UNSET_DOUBLE:
                self.requests.set_result(WhatIfKey(order.orderId), orderState)
        else:
            key = self.orderKey(order.clientId, order.orderId, order.permId)
            trade = self.trades.get(key)
            # Snapshot of TWS's unmerged view, with `?` placeholders
            # stripped. Stored on the trade as `serverOrder` so callers
            # can read fields that the MUTABLE_ORDER_FIELDS allowlist
            # does not yet propagate into ``trade.order``.
            serverOrderSnapshot = Order(
                **{k: v for k, v in dataclassAsDict(order).items() if v != "?"}
            )
            if trade:
                for fieldName in MUTABLE_ORDER_FIELDS:
                    setattr(trade.order, fieldName, getattr(order, fieldName))
                trade.serverOrder = serverOrderSnapshot
            else:
                contract = Contract.recreate(contract)
                orderStatus = OrderStatus(orderId=orderId, status=orderState.status)
                trade = Trade(
                    contract,
                    serverOrderSnapshot,
                    orderStatus,
                    [],
                    [],
                    serverOrder=serverOrderSnapshot,
                )
                self.trades[key] = trade
                self._logger.info(f"openOrder: {trade}")

            self.permId2Trade.setdefault(order.permId, trade)
            # If a reqOpenOrdersAsync / reqAllOpenOrdersAsync is currently
            # collecting, accumulate the snapshot; otherwise this is a
            # live order update arriving outside any pending request and
            # should fire the live event instead.
            if SingletonKey("openOrders") in self.requests:
                self.requests.append(SingletonKey("openOrders"), trade)
            else:
                self.ib.openOrderEvent.emit(trade)

        # make sure that the client issues order ids larger than any
        # order id encountered (even from other clients) to avoid
        # "Duplicate order id" error
        self.ib.client.updateReqId(orderId + 1)

    def openOrderEnd(self):
        self.requests.set_result(SingletonKey("openOrders"))

    def completedOrder(self, contract: Contract, order: Order, orderState: OrderState):
        contract = Contract.recreate(contract)
        orderStatus = OrderStatus(orderId=order.orderId, status=orderState.status)
        trade = Trade(contract, order, orderStatus, [], [])
        # No-op if the request was already settled (e.g. a stray second
        # wave after completedOrdersEnd already fired), instead of the
        # KeyError the legacy direct-index access used to raise.
        self.requests.append(SingletonKey("completedOrders"), trade)

        if order.permId not in self.permId2Trade:
            self.trades[order.permId] = trade
            self.permId2Trade[order.permId] = trade

    def completedOrdersEnd(self):
        self.requests.set_result(SingletonKey("completedOrders"))

    def orderStatus(
        self,
        orderId: int,
        status: str,
        filled: float,
        remaining: float,
        avgFillPrice: float,
        permId: int,
        parentId: int,
        lastFillPrice: float,
        clientId: int,
        whyHeld: str,
        mktCapPrice: float = 0.0,
    ):
        key = self.orderKey(clientId, orderId, permId)
        trade = self.trades.get(key)
        if trade:
            msg: str | None
            oldStatus = trade.orderStatus.status
            new = dict(
                status=status,
                filled=filled,
                remaining=remaining,
                avgFillPrice=avgFillPrice,
                permId=permId,
                parentId=parentId,
                lastFillPrice=lastFillPrice,
                clientId=clientId,
                whyHeld=whyHeld,
                mktCapPrice=mktCapPrice,
            )
            curr = dataclassAsDict(trade.orderStatus)
            isChanged = curr != {**curr, **new}

            if isChanged:
                dataclassUpdate(trade.orderStatus, **new)
                msg = ""
            elif (
                status == "Submitted"
                and trade.log
                and trade.log[-1].message == "Modify"
            ):
                # order modifications are acknowledged
                msg = "Modified"
            else:
                msg = None

            if msg is not None:
                logEntry = TradeLogEntry(self.lastTime, status, msg)
                trade.log.append(logEntry)
                self._logger.info(f"orderStatus: {trade}")
                self.ib.orderStatusEvent.emit(trade)
                trade.statusEvent.emit(trade)
                if status != oldStatus:
                    if status == OrderStatus.Filled:
                        trade.filledEvent.emit(trade)
                    elif status == OrderStatus.Cancelled:
                        trade.cancelledEvent.emit(trade)
        else:
            self._logger.error(
                "orderStatus: No order found for orderId %s and clientId %s",
                orderId,
                clientId,
            )

    def execDetails(self, reqId: int, contract: Contract, execution: Execution):
        """
        This wrapper handles both live fills and responses to
        reqExecutions.
        """
        self._logger.info(f"execDetails {execution}")
        if execution.orderId == UNSET_INTEGER:
            # bug in TWS: executions of manual orders have unset value
            execution.orderId = 0

        trade = self.permId2Trade.get(execution.permId)
        if not trade:
            key = self.orderKey(execution.clientId, execution.orderId, execution.permId)
            trade = self.trades.get(key)

        # TODO: debug why spread contracts aren't fully detailed here. They have no legs in execDetails, but they do in orderStatus?
        if trade and contract == trade.contract:
            contract = trade.contract
        else:
            contract = Contract.recreate(contract)

        execId = execution.execId
        isLive = ReqIdKey(reqId) not in self.requests
        time = self.lastTime if isLive else execution.time
        fill = Fill(contract, execution, CommissionReport(), time)
        if execId not in self.fills:
            # first time we see this execution so add it
            self.fills[execId] = fill
            if trade:
                trade.fills.append(fill)
                logEntry = TradeLogEntry(
                    time,
                    trade.orderStatus.status,
                    f"Fill {execution.shares}@{execution.price}",
                )
                trade.log.append(logEntry)
                if isLive:
                    self._logger.info(f"execDetails: {fill}")
                    self.ib.execDetailsEvent.emit(trade, fill)
                    trade.fillEvent(trade, fill)

        if not isLive:
            self.requests.append(ReqIdKey(reqId), fill)

    def execDetailsEnd(self, reqId: int):
        self.requests.set_result(ReqIdKey(reqId))

    def commissionReport(self, commissionReport: CommissionReport):
        if commissionReport.yield_ == UNSET_DOUBLE:
            commissionReport.yield_ = self.defaults.unset

        if commissionReport.realizedPNL == UNSET_DOUBLE:
            commissionReport.realizedPNL = self.defaults.unset

        fill = self.fills.get(commissionReport.execId)
        if fill:
            report = dataclassUpdate(fill.commissionReport, commissionReport)
            self._logger.info(f"commissionReport: {report}")
            trade = self.permId2Trade.get(fill.execution.permId)
            if trade:
                self.ib.commissionReportEvent.emit(trade, fill, report)
                trade.commissionReportEvent.emit(trade, fill, report)
            else:
                # this is not a live execution and the order was filled
                # before this connection started
                pass
        else:
            # commission report is not for this client
            pass

    def orderBound(self, reqId: int, apiClientId: int, apiOrderId: int):
        pass

    def contractDetails(self, reqId: int, contractDetails: ContractDetails):
        self.requests.append(ReqIdKey(reqId), contractDetails)

    bondContractDetails = contractDetails

    def contractDetailsEnd(self, reqId: int):
        self.requests.set_result(ReqIdKey(reqId))

    def symbolSamples(
        self, reqId: int, contractDescriptions: list[ContractDescription]
    ):
        self.requests.set_result(ReqIdKey(reqId), contractDescriptions)

    def marketRule(self, marketRuleId: int, priceIncrements: list[PriceIncrement]):
        self.requests.set_result(
            CompositeKey("marketRule", (marketRuleId,)), priceIncrements
        )

    def marketDataType(self, reqId: int, marketDataId: int):
        ticker = self._get_ticker(reqId)
        if ticker:
            ticker.marketDataType = marketDataId

    def realtimeBar(
        self,
        reqId: int,
        time: int,
        open_: float,
        high: float,
        low: float,
        close: float,
        volume: float,
        wap: float,
        count: int,
    ):
        dt = datetime.fromtimestamp(time, self.defaultTimezone)
        bar = RealTimeBar(dt, -1, open_, high, low, close, volume, wap, count)
        sub = self.subscriptions.get_sub(reqId)
        if not isinstance(sub, RealTimeBarsSub):
            return
        bars = sub.bars
        bars.append(bar)
        self.ib.barUpdateEvent.emit(bars, True)
        bars.updateEvent.emit(bars, True)

    def historicalData(self, reqId: int, bar: BarData):
        if ReqIdKey(reqId) not in self.requests:
            return
        bar.date = self._normalizeDatetime(parseIBDatetime(bar.date))  # type: ignore[arg-type]
        self.requests.append(ReqIdKey(reqId), bar)

    def historicalDataEnd(self, reqId, _start: str, _end: str):
        self.requests.set_result(ReqIdKey(reqId))

    def historicalDataUpdate(self, reqId: int, bar: BarData):
        sub = self.subscriptions.get_sub(reqId)
        if not isinstance(sub, HistoricalBarsSub):
            return
        bars = sub.bars
        if not bars:
            return

        bar.date = self._normalizeDatetime(parseIBDatetime(bar.date))  # type: ignore[arg-type]
        lastDate = bars[-1].date
        if bar.date < lastDate:
            return

        hasNewBar = len(bars) == 0 or bar.date > lastDate
        if hasNewBar:
            bars.append(bar)
        elif bars[-1] != bar:
            bars[-1] = bar
        else:
            return

        self.ib.barUpdateEvent.emit(bars, hasNewBar)
        bars.updateEvent.emit(bars, hasNewBar)

    def headTimestamp(self, reqId: int, headTimestamp: str):
        try:
            dt = self._normalizeDatetime(parseIBDatetime(headTimestamp))
            self.requests.set_result(ReqIdKey(reqId), dt)
        except ValueError as exc:
            self.requests.set_error(ReqIdKey(reqId), exc)

    def historicalTicks(self, reqId: int, ticks: list[HistoricalTick], done: bool):
        self.requests.extend(ReqIdKey(reqId), ticks)
        if done:
            self.requests.set_result(ReqIdKey(reqId))

    def historicalTicksBidAsk(
        self, reqId: int, ticks: list[HistoricalTickBidAsk], done: bool
    ):
        self.requests.extend(ReqIdKey(reqId), ticks)
        if done:
            self.requests.set_result(ReqIdKey(reqId))

    def historicalTicksLast(
        self, reqId: int, ticks: list[HistoricalTickLast], done: bool
    ):
        self.requests.extend(ReqIdKey(reqId), ticks)
        if done:
            self.requests.set_result(ReqIdKey(reqId))

    # additional wrapper method provided by Client
    def priceSizeTick(self, reqId: int, tickType: int, price: float, size: float):
        ticker = self._get_ticker(reqId)
        if not ticker:
            self._logger.error(f"priceSizeTick: Unknown reqId: {reqId}")
            return

        # self._logger.error(f"WHAT R U DOING: {tickType=} {price=} {size=}")

        # Allow overwriting IBKR's default "empty price" of -1 when there is no qty/size on a side.
        # https://interactivebrokers.github.io/tws-api/tick_types.html
        if tickType in {1, 66}:
            # Note: Keep these size==0 overrides INSIDE each tickType where it is needed because
            #       other tickTypes like open/high/low/close are values with size=0 but those
            #       are still valid prices to receive.
            # Bid/Ask updates always have a Price+Size delivered at the same time, while the
            # other properties are mainly price-only delivery methods.
            if size == 0:
                price = self.defaultEmptyPrice
                size = self.defaultEmptySize

            ticker.prevBid = ticker.bid
            ticker.prevBidSize = ticker.bidSize
            ticker.bid = price
            ticker.bidSize = size
        elif tickType in {2, 67}:
            if size == 0:
                price = self.defaultEmptyPrice
                size = self.defaultEmptySize

            ticker.prevAsk = ticker.ask
            ticker.prevAskSize = ticker.askSize
            ticker.ask = price
            ticker.askSize = size
        elif tickType in {4, 68}:
            # for 'last' values, price can be valid with size=0 for updates like 'last SPX price' since SPX doesn't trade
            # Workaround: for TICK-NYSE, it is valid to have price=-1, size=0 because it can float between -10,000 and 10,000
            #             and it also never reports a size. As a workaround, check if ticker.close exists as a proxy for "not TICK-NYSE"
            #             because TICK-NYSE never has open/close values populated.
            if price == -1 and size == 0 and ticker.close > 0:
                price = self.defaultEmptyPrice
                size = self.defaultEmptySize

            # BUG? IBKR is sometimes sending a GOOD VALUE followed by a PREVIOUS value all under tickType=4?
            # e.g. I get the SPX close delivered first with size=0, then I get another data point with size=1 priced one point lower,
            # but since the older price is delivered second, it replaces the "last" value with a wrong value? Not sure if it's
            # an IBKR data problem or a logic problem somewhere here?
            # More research: IBKR also shows the bad value in their own app, so there is a data bug in their own server logic somewhere.

            # self._logger.error(f"[{tickType=}] updating last price size: {price=} {size=} :: BEFORE {ticker=}")
            # self._logger.error(f"[{tickType=}] SETTING {ticker.prevLast=} = {ticker.last=}; {ticker.prevLastSize=} = {ticker.lastSize=}")

            ticker.prevLast = ticker.last
            ticker.prevLastSize = ticker.lastSize
            ticker.last = price
            ticker.lastSize = size

            # self._logger.error(f"[{tickType=}] SET {ticker.prevLast=} = {ticker.last=}; {ticker.prevLastSize=} = {ticker.lastSize=}")
            # self._logger.error(f"[{tickType=}] updating last price size: {price=} {size=} :: AFTER {ticker=}")
        else:
            assert tickType in PRICE_TICK_MAP, (
                f"Received tick {tickType=} {price=} but we don't have an attribute mapping for it? Triggered from {ticker.contract=}"
            )

            setattr(ticker, PRICE_TICK_MAP[tickType], price)

        if price or size:
            tick = TickData(self.lastTime, tickType, price, size)
            ticker.ticks.append(tick)

        self.pendingTickers.add(ticker)

    def tickSize(self, reqId: int, tickType: int, size: float):
        ticker = self._get_ticker(reqId)
        if not ticker:
            self._logger.error(f"tickSize: Unknown reqId: {reqId}")
            return

        price = self.defaultEmptyPrice

        # self._logger.error(
        #     f"tickSize with tickType {tickType}: " f"processing value: {size!r}"
        # )

        # https://interactivebrokers.github.io/tws-api/tick_types.html
        if tickType in {0, 69}:
            if size == ticker.bidSize:
                return

            ticker.prevBidSize = ticker.bidSize
            if size == 0:
                ticker.bid = self.defaultEmptyPrice
                ticker.bidSize = self.defaultEmptySize
            else:
                price = ticker.bid
                ticker.bidSize = size
        elif tickType in {3, 70}:
            if size == ticker.askSize:
                return

            ticker.prevAskSize = ticker.askSize
            if size == 0:
                ticker.ask = self.defaultEmptyPrice
                ticker.askSize = self.defaultEmptySize
            else:
                price = ticker.ask
                ticker.askSize = size
        elif tickType in {5, 71}:
            price = ticker.last

            if ticker.isUnset(price):
                return

            if size != ticker.lastSize:
                ticker.prevLastSize = ticker.lastSize
                ticker.lastSize = size
        else:
            assert tickType in SIZE_TICK_MAP, (
                f"Received tick {tickType=} {size=} but we don't have an attribute mapping for it? Triggered from {ticker.contract=}"
            )

            setattr(ticker, SIZE_TICK_MAP[tickType], size)

        if price or size:
            tick = TickData(self.lastTime, tickType, price, size)
            ticker.ticks.append(tick)

        self.pendingTickers.add(ticker)

    def tickSnapshotEnd(self, reqId: int):
        self.requests.set_result(ReqIdKey(reqId))
        # A snapshot's subscription lifecycle ends here: IB auto-completes
        # snapshots, so close it (without a wire cancel — cancelling a
        # snapshot is a protocol error) to drop the one-shot subscription
        # and its private Ticker from the registry. Without this, every
        # ``reqMktData(snapshot=True)`` would leave its sub (and Ticker)
        # pinned in the reqId index for the life of the connection. Close
        # is idempotent, so ``reqTickersAsync`` re-closing in its
        # ``finally`` is a no-op.
        sub = self.subscriptions.get_sub(reqId)
        if isinstance(sub, MktDataSub) and sub.snapshot:
            sub.close(send_cancel=False)

    def tickByTickAllLast(
        self,
        reqId: int,
        tickType: int,
        time: int,
        price: float,
        size: float,
        tickAttribLast: TickAttribLast,
        exchange,
        specialConditions,
    ):
        ticker = self._get_ticker(reqId)
        if not ticker:
            self._logger.error(f"tickByTickAllLast: Unknown reqId: {reqId}")
            return

        if price == -1 and size == 0:
            price = self.defaultEmptyPrice
            size = self.defaultEmptySize

        ticker.prevLast = ticker.last
        ticker.prevLastSize = ticker.lastSize
        ticker.last = price
        ticker.lastSize = size

        tick = TickByTickAllLast(
            tickType,
            self.lastTime,
            price,
            size,
            tickAttribLast,
            exchange,
            specialConditions,
        )

        ticker.tickByTicks.append(tick)
        self.pendingTickers.add(ticker)

    def tickByTickBidAsk(
        self,
        reqId: int,
        time: int,
        bidPrice: float,
        askPrice: float,
        bidSize: float,
        askSize: float,
        tickAttribBidAsk: TickAttribBidAsk,
    ):
        ticker = self._get_ticker(reqId)
        if not ticker:
            self._logger.error(f"tickByTickBidAsk: Unknown reqId: {reqId}")
            return

        if bidPrice != ticker.bid:
            ticker.prevBid = ticker.bid
            ticker.bid = bidPrice if bidPrice > 0 else self.defaultEmptyPrice

        if bidSize != ticker.bidSize:
            ticker.prevBidSize = ticker.bidSize
            ticker.bidSize = bidSize if bidSize > 0 else self.defaultEmptySize

        if askPrice != ticker.ask:
            ticker.prevAsk = ticker.ask
            ticker.ask = askPrice if askPrice > 0 else self.defaultEmptyPrice

        if askSize != ticker.askSize:
            ticker.prevAskSize = ticker.askSize
            ticker.askSize = askSize if askSize > 0 else self.defaultEmptySize

        tick = TickByTickBidAsk(
            self.lastTime, bidPrice, askPrice, bidSize, askSize, tickAttribBidAsk
        )

        ticker.tickByTicks.append(tick)
        self.pendingTickers.add(ticker)

    def tickByTickMidPoint(self, reqId: int, time: int, midPoint: float):
        ticker = self._get_ticker(reqId)
        if not ticker:
            self._logger.error(f"tickByTickMidPoint: Unknown reqId: {reqId}")
            return

        tick = TickByTickMidPoint(self.lastTime, midPoint)
        ticker.tickByTicks.append(tick)
        self.pendingTickers.add(ticker)

    def tickString(self, reqId: int, tickType: int, value: str):
        if not (ticker := self._get_ticker(reqId)):
            return

        try:
            # Simple string assignments (O(1) dict lookup)
            if tickType in STRING_TICK_MAP:
                setattr(ticker, STRING_TICK_MAP[tickType], value)
            elif tickType in TIMESTAMP_TICK_MAP:
                # Timestamp conversion (O(1) dict lookup)
                self._processTimestampTick(ticker, TIMESTAMP_TICK_MAP[tickType], value)
            elif tickType == 47:
                # https://web.archive.org/web/20200725010343/https://interactivebrokers.github.io/tws-api/fundamental_ratios_tags.html
                d = dict(
                    t.split("=")
                    for t in value.split(";")
                    if t  # type: ignore
                )  # type: ignore
                for k, v in d.items():
                    with suppress(ValueError):
                        if v == "-99999.99":
                            v = "nan"
                        d[k] = float(v)  # type: ignore
                        d[k] = int(v)  # type: ignore
                ticker.fundamentalRatios = FundamentalRatios(**d)
            elif tickType in RT_VOLUME_TICK_MAP:
                # RT Volume or RT Trade Volume (O(1) dict lookup + helper)
                result = self._processRtVolumeTick(ticker, tickType, value)
                if result:
                    price, size = result
                    ticker.prevLast = ticker.last
                    ticker.prevLastSize = ticker.lastSize
                    ticker.last = price
                    ticker.lastSize = size
                    tick = TickData(self.lastTime, tickType, price, size)
                    ticker.ticks.append(tick)
            elif tickType == 59:
                # Dividend tick:
                # https://interactivebrokers.github.io/tws-api/tick_types.html#ib_dividends
                # example value: '0.83,0.92,20130219,0.23'
                past12, next12, nextDate, nextAmount = value.split(",")
                ticker.dividends = Dividends(
                    float(past12) if past12 else None,
                    float(next12) if next12 else None,
                    parseIBDatetime(nextDate) if nextDate else None,
                    float(nextAmount) if nextAmount else None,
                )
            else:
                self._logger.error(
                    f"tickString with tickType {tickType}: unhandled value: {value!r}"
                )

            self.pendingTickers.add(ticker)
        except ValueError:
            self._logger.error(
                f"tickString with tickType {tickType}: malformed value: {value!r}"
            )

    def tickGeneric(self, reqId: int, tickType: int, value: float):
        ticker = self._get_ticker(reqId)
        if not ticker:
            return

        try:
            value = float(value)
            value = value if value > 0 else self.defaultEmptySize
        except ValueError:
            self._logger.error(
                f"[tickType {tickType}] genericTick: malformed value: {value!r}"
            )
            return

        assert tickType in GENERIC_TICK_MAP, (
            f"Received tick {tickType=} {value=} but we don't have an attribute mapping for it? Triggered from {ticker.contract=}"
        )

        setattr(ticker, GENERIC_TICK_MAP[tickType], value)

        tick = TickData(self.lastTime, tickType, value, 0)
        ticker.ticks.append(tick)
        self.pendingTickers.add(ticker)

    def tickReqParams(
        self, reqId: int, minTick: float, bboExchange: str, snapshotPermissions: int
    ):
        ticker = self._get_ticker(reqId)
        if not ticker:
            return

        ticker.minTick = minTick
        ticker.bboExchange = bboExchange
        ticker.snapshotPermissions = snapshotPermissions

    def smartComponents(self, reqId, components):
        self.requests.set_result(ReqIdKey(reqId), components)

    def mktDepthExchanges(
        self, depthMktDataDescriptions: list[DepthMktDataDescription]
    ):
        self.requests.set_result(
            SingletonKey("mktDepthExchanges"), depthMktDataDescriptions
        )

    def updateMktDepth(
        self,
        reqId: int,
        position: int,
        operation: int,
        side: int,
        price: float,
        size: float,
    ):
        self.updateMktDepthL2(reqId, position, "", operation, side, price, size)

    def updateMktDepthL2(
        self,
        reqId: int,
        position: int,
        marketMaker: str,
        operation: int,
        side: int,
        price: float,
        size: float,
        isSmartDepth: bool = False,
    ):
        # operation: 0 = insert, 1 = update, 2 = delete
        # side: 0 = ask, 1 = bid
        ticker = self._get_ticker(reqId)
        if ticker is None:
            return

        # 'dom' is a dict so we can address position updates directly
        dom = ticker.domBidsDict if side else ticker.domAsksDict

        # if you're curious when these operations run and what they do, enable this too:
        # fmt: off
        # print("BID" if side else "ASK", "OPERATION", operation, "at position", position, "for price", price, "at qty", size)
        # assert list(dom.keys()) == list(range(0, len(dom))), f"Keys aren't sequential? {dom} :: {ticker}"
        # fmt: on

        if operation in {0, 1}:
            # '0' is INSERT NEW
            # '1' is UPDATE EXISTING
            # We are using the same operation for "insert or overwrite" directly.
            dom[position] = DOMLevel(price, size, marketMaker)
        elif operation == 2:
            # '2' is DELETE EXISTING
            size = 0
            try:
                level = dom.pop(position)
                price = level.price
            except Exception as _:
                # invalid position requested for removal, so ignore the request
                pass

        # To retain the original API structure, we convert all sorted dict
        # values into lists for users to consume.
        # Users can also read ticker.domBidsDict or ticker.domAsksDict directly.
        values = list(dom.values())
        if side:
            # Update BID for users
            ticker.domBids = values
        else:
            # Update ASK for users
            ticker.domAsks = values

        # TODO: add optional debugging check. In a correctly working system, we should
        #       technically always have sequential bid and ask position entries, but
        #       in the past we have seen gaps or missing values.

        tick = MktDepthData(
            self.lastTime, position, marketMaker, operation, side, price, size
        )
        ticker.domTicks.append(tick)
        self.pendingTickers.add(ticker)

    def tickOptionComputation(
        self,
        reqId: int,
        tickType: int,
        tickAttrib: int,
        impliedVol: float,
        delta: float,
        optPrice: float,
        pvDividend: float,
        gamma: float,
        vega: float,
        theta: float,
        undPrice: float,
    ):
        comp = OptionComputation(
            tickAttrib,
            impliedVol if impliedVol != -1 else None,
            delta if delta != -2 else None,
            optPrice if optPrice != -1 else None,
            pvDividend if pvDividend != -1 else None,
            gamma if gamma != -2 else None,
            vega if vega != -2 else vega,
            theta if theta != -2 else theta,
            undPrice if undPrice != -1 else None,
        )
        ticker = self._get_ticker(reqId)
        if ticker:
            # reply from reqMktData
            # https://interactivebrokers.github.io/tws-api/tick_types.html

            assert tickType in GREEKS_TICK_MAP, (
                f"Received tick {tickType=} {tickAttrib=} but we don't have an attribute mapping for it? Triggered from {ticker.contract=}"
            )

            setattr(ticker, GREEKS_TICK_MAP[tickType], comp)
            self.pendingTickers.add(ticker)
        elif ReqIdKey(reqId) in self.requests:
            # reply from calculateImpliedVolatility or calculateOptionPrice
            self.requests.set_result(ReqIdKey(reqId), comp)
        else:
            self._logger.error(f"tickOptionComputation: Unknown reqId: {reqId}")

    def deltaNeutralValidation(self, reqId: int, dnc: DeltaNeutralContract):
        pass

    def fundamentalData(self, reqId: int, data: str):
        self.requests.set_result(ReqIdKey(reqId), data)

    def scannerParameters(self, xml: str):
        self.requests.set_result(SingletonKey("scannerParams"), xml)

    def scannerData(
        self,
        reqId: int,
        rank: int,
        contractDetails: ContractDetails,
        distance: str,
        benchmark: str,
        projection: str,
        legsStr: str,
    ):
        data = ScanData(rank, contractDetails, distance, benchmark, projection, legsStr)
        # Live subscription wins over a one-shot reqScannerDataAsync;
        # both deliver the same dataList shape, so the rest of the
        # handler is shared.
        sub = self.subscriptions.get_sub(reqId)
        dataList: ScanDataList | None = None
        if isinstance(sub, ScannerSub):
            dataList = sub.dataList
        else:
            req = self.requests.get(ReqIdKey(reqId))
            if req is not None:
                dataList = req.container

        if dataList is not None:
            if rank == 0:
                dataList.clear()
            dataList.append(data)

    def scannerDataEnd(self, reqId: int):
        # Resolve which dataList this end-of-stream applies to.
        # One-shot scanner reqs are tracked in :attr:`requests`; live
        # subscriptions in :attr:`subscriptions`. Only the one-shot path
        # settles a future.
        req = self.requests.get(ReqIdKey(reqId))
        if req is not None:
            dataList = req.container
            self.requests.set_result(ReqIdKey(reqId))
        else:
            sub = self.subscriptions.get_sub(reqId)
            dataList = sub.dataList if isinstance(sub, ScannerSub) else None

        if dataList is not None:
            self.ib.scannerDataEvent.emit(dataList)
            dataList.updateEvent.emit(dataList)

    def histogramData(self, reqId: int, items: list[HistogramData]):
        result = [HistogramData(item.price, item.count) for item in items]
        self.requests.set_result(ReqIdKey(reqId), result)

    def securityDefinitionOptionParameter(
        self,
        reqId: int,
        exchange: str,
        underlyingConId: int,
        tradingClass: str,
        multiplier: str,
        expirations: list[str],
        strikes: list[float],
    ):
        chain = OptionChain(
            exchange, underlyingConId, tradingClass, multiplier, expirations, strikes
        )
        self.requests.append(ReqIdKey(reqId), chain)

    def securityDefinitionOptionParameterEnd(self, reqId: int):
        self.requests.set_result(ReqIdKey(reqId))

    def newsProviders(self, newsProviders: list[NewsProvider]):
        newsProviders = [NewsProvider(code=p.code, name=p.name) for p in newsProviders]
        self.requests.set_result(SingletonKey("newsProviders"), newsProviders)

    def tickNews(
        self,
        reqId: int,
        timeStamp: int,
        providerCode: str,
        articleId: str,
        headline: str,
        extraData: str,
    ):
        news = NewsTick(
            timeStamp,
            providerCode,
            articleId,
            headline,
            extraData,
            contract=self._snapshotContractForReqId(reqId),
        )
        self.newsTicks.append(news)
        self.ib.tickNewsEvent.emit(news)

    def newsArticle(self, reqId: int, articleType: int, articleText: str):
        article = NewsArticle(articleType, articleText)
        self.requests.set_result(ReqIdKey(reqId), article)

    def historicalNews(
        self, reqId: int, time: str, providerCode: str, articleId: str, headline: str
    ):
        dt = parseIBDatetime(time)
        dt = cast(datetime, dt)
        article = HistoricalNews(dt, providerCode, articleId, headline)
        self.requests.append(ReqIdKey(reqId), article)

    def historicalNewsEnd(self, reqId, _hasMore: bool):
        self.requests.set_result(ReqIdKey(reqId))

    def updateNewsBulletin(
        self, msgId: int, msgType: int, message: str, origExchange: str
    ):
        bulletin = NewsBulletin(msgId, msgType, message, origExchange)
        self.msgId2NewsBulletin[msgId] = bulletin
        self.ib.newsBulletinEvent.emit(bulletin)

    def receiveFA(self, _faDataType: int, faXmlData: str):
        self.requests.set_result(SingletonKey("requestFA"), faXmlData)

    def currentTime(self, time: int):
        dt = datetime.fromtimestamp(time, self.defaultTimezone)
        self.requests.set_result(SingletonKey("currentTime"), dt)

    def rerouteMktDataReq(self, reqId: int, conId: int, exchange: str):
        self.ib.rerouteMktDataReqEvent.emit(reqId, conId, exchange)

    def rerouteMktDepthReq(self, reqId: int, conId: int, exchange: str):
        self.ib.rerouteMktDepthReqEvent.emit(reqId, conId, exchange)

    def tickEFP(
        self,
        reqId: int,
        tickType: int,
        basisPoints: float,
        formattedBasisPoints: str,
        totalDividends: float,
        holdDays: int,
        futureLastTradeDate: str,
        dividendImpact: float,
        dividendsToLastTradeDate: float,
    ):
        ticker = self._get_ticker(reqId)
        if not ticker:
            return

        # Create EFP data object with all available information
        # Note: totalDividends parameter is actually the implied future price per IBKR docs
        efpData = EfpData(
            basisPoints=basisPoints,
            formattedBasisPoints=formattedBasisPoints,
            impliedFuture=totalDividends,
            holdDays=holdDays,
            futureLastTradeDate=futureLastTradeDate,
            dividendImpact=dividendImpact,
            dividendsToLastTradeDate=dividendsToLastTradeDate,
        )

        # Store in appropriate field based on tick type (O(1) dict lookup)
        if tickType in EFP_TICK_MAP:
            setattr(ticker, EFP_TICK_MAP[tickType], efpData)
            self.pendingTickers.add(ticker)

    def historicalSchedule(
        self,
        reqId: int,
        startDateTime: str,
        endDateTime: str,
        timeZone: str,
        sessions: list[HistoricalSession],
    ):
        schedule = HistoricalSchedule(startDateTime, endDateTime, timeZone, sessions)
        self.requests.set_result(ReqIdKey(reqId), schedule)

    def wshMetaData(self, reqId: int, dataJson: str):
        self.ib.wshMetaEvent.emit(dataJson)
        self.requests.set_result(ReqIdKey(reqId), dataJson)

    def wshEventData(self, reqId: int, dataJson: str):
        self.ib.wshEvent.emit(dataJson)
        self.requests.set_result(ReqIdKey(reqId), dataJson)

    def userInfo(self, reqId: int, whiteBrandingId: str):
        self.requests.set_result(ReqIdKey(reqId))

    def softDollarTiers(self, reqId: int, tiers: list[SoftDollarTier]):
        pass

    def familyCodes(self, familyCodes: list[FamilyCode]):
        pass

    def error(
        self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson: str
    ):
        # https://interactivebrokers.github.io/tws-api/message_codes.html
        # https://ibkrcampus.com/campus/ibkr-api-page/twsapi-doc/#api-error-codes
        # reqId == -1 is the IBKR convention for a system-level error
        # with no associated request or order — short-circuit both
        # registry and trade lookups (skipping the two RequestKey
        # allocations ``find_by_reqid`` would do) for the common case.
        inflightRequest = None
        trade = None
        if reqId != -1:
            # The wire delivers a raw integer reqId; the registry may
            # have the request under either ReqIdKey or WhatIfKey, so
            # resolve via the numeric helper that checks both.
            inflightRequest = self.requests.find_by_reqid(reqId)
            trade = self.trades.get((self.clientId, reqId))
            # Trades are never evicted from ``self.trades``, so a late
            # or replayed error for an already-finished order would
            # otherwise corrupt its status (warning branch sets
            # ValidationError) or set ``advancedError`` (error branch)
            # on a completed trade. Treat done trades as absent here so
            # the rest of the function only acts on live orders.
            if trade and trade.isDone():
                trade = None
        isRequest = inflightRequest is not None

        isWarning = errorCode in _WARNING_CODES or 2100 <= errorCode < 2200

        if errorCode == 110 and isRequest:
            # whatIf request failed
            isWarning = False

        if (
            errorCode == 110
            and trade
            and trade.orderStatus.status == OrderStatus.PendingSubmit
        ):
            # invalid price for a new order must cancel it
            isWarning = False

        msg = f"{'Warning' if isWarning else 'Error'} {errorCode}, reqId {reqId}: {errorString}"

        contract = self.contractForReqId(reqId)
        if contract:
            msg += f", contract: {contract}"

        if isWarning:
            # Record warnings into the trade object, but unlike the _error_ case,
            # DO NOT delete the trade object because the order is STILL LIVE at the broker.
            if trade:
                status = trade.orderStatus.status = OrderStatus.ValidationError
                logEntry = TradeLogEntry(self.lastTime, status, msg, errorCode)
                trade.log.append(logEntry)
                self._logger.warning(f"IBKR API validation warning: {trade}")
                self.ib.orderStatusEvent.emit(trade)
                trade.statusEvent.emit(trade)
            else:
                # else, this is a non-trade-related warning message
                self._logger.info(msg)
        else:
            self._logger.error(msg)
            if isRequest:
                # the request failed — settle the future via whichever
                # typed key it was actually registered under
                assert inflightRequest is not None
                if self.ib.RaiseRequestErrors:
                    error = RequestError(reqId, errorCode, errorString)
                    self.requests.set_error(inflightRequest.key, error)
                else:
                    self.requests.set_result(inflightRequest.key)
            elif trade:
                # something is wrong with the order, cancel it
                if advancedOrderRejectJson:
                    trade.advancedError = advancedOrderRejectJson

                # Errors can mean two things:
                #  - new order is REJECTED
                #  - existing order is server-canceled (DAY orders, margin problems)
                #  - modification to *existing* order just has an update error, but the order is STILL LIVE
                if not trade.isDone():
                    status = trade.orderStatus.status = OrderStatus.Cancelled
                    logEntry = TradeLogEntry(self.lastTime, status, msg, errorCode)
                    trade.log.append(logEntry)
                    self._logger.warning(f"Canceled order: {trade}")
                    self.ib.orderStatusEvent.emit(trade)
                    trade.statusEvent.emit(trade)
                    trade.cancelledEvent.emit(trade)

        if errorCode == 165:
            # For scan data subscription there are no longer matching results.
            sub = self.subscriptions.get_sub(reqId)
            if isinstance(sub, ScannerSub) and sub.dataList:
                sub.dataList.clear()
                sub.dataList.updateEvent.emit(sub.dataList)
        elif errorCode == 317:
            # Market depth data has been RESET
            ticker = self._get_ticker(reqId)
            if ticker:
                # clear all DOM levels
                ticker.domTicks += [
                    MktDepthData(self.lastTime, 0, "", 2, 0, level.price, 0)
                    for level in ticker.domAsks
                ]
                ticker.domTicks += [
                    MktDepthData(self.lastTime, 0, "", 2, 1, level.price, 0)
                    for level in ticker.domBids
                ]
                ticker.domAsks.clear()
                ticker.domBids.clear()
                ticker.domBidsDict.clear()
                ticker.domAsksDict.clear()
                self.pendingTickers.add(ticker)
        elif errorCode == 10225:
            # Bust event occurred, current subscription is deactivated.
            # Re-subscribe immediately so bars keep flowing.
            sub = self.subscriptions.get_sub(reqId)
            if isinstance(sub, RealTimeBarsSub):
                rtBars = sub.bars
                self.ib.client.cancelRealTimeBars(reqId)
                self.ib.client.reqRealTimeBars(
                    reqId,
                    rtBars.contract,
                    rtBars.barSize,
                    rtBars.whatToShow,
                    rtBars.useRTH,
                    rtBars.realTimeBarsOptions,
                )
            elif isinstance(sub, HistoricalBarsSub):
                hBars = sub.bars
                self.ib.client.cancelHistoricalData(reqId)
                self.ib.client.reqHistoricalData(
                    reqId,
                    hBars.contract,
                    hBars.endDateTime,
                    hBars.durationStr,
                    hBars.barSizeSetting,
                    hBars.whatToShow,
                    hBars.useRTH,
                    hBars.formatDate,
                    hBars.keepUpToDate,
                    hBars.chartOptions,
                )

        # A snapshot terminates on EITHER tickSnapshotEnd (success) or a
        # hard error (e.g. 200 / 354 / 10197): IB never sends
        # tickSnapshotEnd after rejecting a snapshot. ``reqMktData(snapshot
        # =True)`` opens no request future and has no ``finally``, so without
        # this its one-shot MktDataSub — and its private Ticker — would stay
        # pinned in the registry for the life of the connection, and is
        # uncancellable (snapshot subs are not in the market-data dedup
        # index). Warnings must NOT close it: 10167 ("displaying delayed
        # data") is a warning that still completes via tickSnapshotEnd. Close
        # is idempotent, so reqTickersAsync re-closing in its ``finally`` is a
        # no-op.
        if not isWarning:
            sub = self.subscriptions.get_sub(reqId)
            if isinstance(sub, MktDataSub) and sub.snapshot:
                sub.close(send_cancel=False)

        self.ib.errorEvent.emit(reqId, errorCode, errorString, contract)

    def tcpDataArrived(self):
        self.lastTime = datetime.now(self.defaultTimezone)
        self.time = time.time()
        for ticker in self.pendingTickers:
            ticker.ticks = []
            ticker.tickByTicks = []
            ticker.domTicks = []

        # In-place clear avoids allocating a fresh set per TCP packet.
        self.pendingTickers.clear()

    def tcpDataProcessed(self):
        self.ib.updateEvent.emit()
        if self.pendingTickers:
            for ticker in self.pendingTickers:
                ticker.time = self.lastTime
                ticker.timestamp = self.time
                ticker.updateEvent.emit(ticker)

            self.ib.pendingTickersEvent.emit(self.pendingTickers)
