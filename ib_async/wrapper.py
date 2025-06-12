"""Wrapper to handle incoming messages."""

import asyncio
import logging
import time

from collections import defaultdict
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, cast, Final, Optional, TYPE_CHECKING, TypeAlias, Union

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
    BarDataList,
    CommissionReport,
    DepthMktDataDescription,
    Dividends,
    DOMLevel,
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
    PnL,
    PnLSingle,
    PortfolioItem,
    Position,
    PriceIncrement,
    RealTimeBar,
    RealTimeBarList,
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
    dataclassAsDict,
    dataclassUpdate,
    getLoop,
    globalErrorEvent,
    parseIBDatetime,
    UNSET_DOUBLE,
    UNSET_INTEGER,
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
}


SIZE_TICK_MAP: Final[TickDict] = {
    8: "volume",
    74: "volume",
    63: "volumeRate3Min",
    64: "volumeRate5Min",
    65: "volumeRate10Min",
    21: "avVolume",
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

    tickers: dict[int, Ticker] = field(init=False)
    """ hash(Contract) -> Ticker """

    pendingTickers: set[Ticker] = field(init=False)

    reqId2Ticker: dict[int, Ticker] = field(init=False)
    """ reqId -> Ticker """

    ticker2ReqId: dict[Union[int, str], dict[Ticker, int]] = field(init=False)
    """ tickType -> Ticker -> reqId """

    reqId2Subscriber: dict[int, Any] = field(init=False)
    """ live bars or live scan data """

    reqId2PnL: dict[int, PnL] = field(init=False)
    """ reqId -> PnL """

    reqId2PnlSingle: dict[int, PnLSingle] = field(init=False)
    """ reqId -> PnLSingle """

    pnlKey2ReqId: dict[tuple, int] = field(init=False)
    """ (account, modelCode) -> reqId """

    pnlSingleKey2ReqId: dict[tuple, int] = field(init=False)
    """ (account, modelCode, conId) -> reqId """

    lastTime: datetime = field(init=False)
    """ UTC time of last network packet arrival. """

    # Like 'lastTime' but in time.time() float format instead of a datetime object
    # (not to be confused with 'lastTimestamp' of Ticker objects which is the timestamp
    #  of the last trade event)
    time: float = field(init=False)

    accounts: list[str] = field(init=False)
    clientId: int = field(init=False)
    wshMetaReqId: int = field(init=False)
    wshEventReqId: int = field(init=False)
    _reqId2Contract: dict[int, Contract] = field(init=False)
    _timeout: float = field(init=False)

    _futures: dict[Any, asyncio.Future] = field(init=False)
    """ _futures and _results are linked by key. """

    _results: dict[Any, Any] = field(init=False)
    """ _futures and _results are linked by key. """

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
        self.tickers = {}
        self.pendingTickers = set()
        self.reqId2Ticker = {}
        self.ticker2ReqId = defaultdict(dict)
        self.reqId2Subscriber = {}
        self.reqId2PnL = {}
        self.reqId2PnlSingle = {}
        self.pnlKey2ReqId = {}
        self.pnlSingleKey2ReqId = {}
        self.lastTime = datetime.min
        self.time = -1
        self.accounts = []
        self.clientId = -1
        self.wshMetaReqId = 0
        self.wshEventReqId = 0
        self._reqId2Contract = {}
        self._timeout = 0
        self._futures = {}
        self._results = {}
        self.setTimeout(0)

    def setEventsDone(self):
        """Set all subscription-type events as done."""
        events = [ticker.updateEvent for ticker in self.tickers.values()]
        events += [sub.updateEvent for sub in self.reqId2Subscriber.values()]
        for trade in self.trades.values():
            events += [
                trade.statusEvent,
                trade.modifyEvent,
                trade.fillEvent,
                trade.filledEvent,
                trade.commissionReportEvent,
                trade.cancelEvent,
                trade.cancelledEvent,
            ]
        for event in events:
            event.set_done()

    def connectionClosed(self):
        error = ConnectionError("Socket disconnect")
        for future in self._futures.values():
            if not future.done():
                future.set_exception(error)

        globalErrorEvent.emit(error)
        self.reset()

    def startReq(self, key, contract=None, container=None):
        """
        Start a new request and return the future that is associated
        with the key and container. The container is a list by default.
        """
        future: asyncio.Future = asyncio.Future()
        self._futures[key] = future
        self._results[key] = container if container is not None else []

        if contract:
            self._reqId2Contract[key] = contract

        return future

    def _endReq(self, key, result=None, success=True):
        """
        Finish the future of corresponding key with the given result.
        If no result is given then it will be popped of the general results.
        """
        future = self._futures.pop(key, None)
        self._reqId2Contract.pop(key, None)
        if future:
            if result is None:
                result = self._results.pop(key, [])

            if not future.done():
                if success:
                    future.set_result(result)
                else:
                    future.set_exception(result)

    def startTicker(self, reqId: int, contract: Contract, tickType: Union[int, str]):
        """
        Start a tick request that has the reqId associated with the contract.
        Return the ticker.
        """
        ticker = self.tickers.get(hash(contract))
        if not ticker:
            ticker = Ticker(contract=contract, defaults=self.defaults)
            self.tickers[hash(contract)] = ticker

        self.reqId2Ticker[reqId] = ticker
        self._reqId2Contract[reqId] = contract
        self.ticker2ReqId[tickType][ticker] = reqId
        return ticker

    def endTicker(self, ticker: Ticker, tickType: Union[int, str]):
        reqId = self.ticker2ReqId[tickType].pop(ticker, 0)
        self._reqId2Contract.pop(reqId, None)
        return reqId

    def startSubscription(self, reqId, subscriber, contract=None):
        """Register a live subscription."""
        self._reqId2Contract[reqId] = contract
        self.reqId2Subscriber[reqId] = subscriber

    def endSubscription(self, subscriber):
        """Unregister a live subscription."""
        self._reqId2Contract.pop(subscriber.reqId, None)
        self.reqId2Subscriber.pop(subscriber.reqId, None)

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
        self._endReq("accountValues")

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
        self._endReq(reqId)

    def accountSummary(
        self, _reqId: int, account: str, tag: str, value: str, currency: str
    ):
        key = (account, tag, currency)
        acctVal = AccountValue(account, tag, value, currency, "")
        self.acctSummary[key] = acctVal
        self.ib.accountSummaryEvent.emit(acctVal)

    def accountSummaryEnd(self, reqId: int):
        self._endReq(reqId)

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
        results = self._results.get("positions")

        if results is not None:
            results.append(position)

        self.ib.positionEvent.emit(position)

    def positionEnd(self):
        self._endReq("positions")

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
        pnl = self.reqId2PnL.get(reqId)
        if not pnl:
            return

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
        pnlSingle = self.reqId2PnlSingle.get(reqId)
        if not pnlSingle:
            return

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
                self._endReq(order.orderId, orderState)
        else:
            key = self.orderKey(order.clientId, order.orderId, order.permId)
            trade = self.trades.get(key)
            if trade:
                trade.order.permId = order.permId
                trade.order.totalQuantity = order.totalQuantity
                trade.order.lmtPrice = order.lmtPrice
                trade.order.auxPrice = order.auxPrice
                trade.order.orderType = order.orderType
                trade.order.orderRef = order.orderRef
            else:
                # ignore '?' values in the order
                order = Order(
                    **{k: v for k, v in dataclassAsDict(order).items() if v != "?"}
                )
                contract = Contract.recreate(contract)
                orderStatus = OrderStatus(orderId=orderId, status=orderState.status)
                trade = Trade(contract, order, orderStatus, [], [])
                self.trades[key] = trade
                self._logger.info(f"openOrder: {trade}")

            self.permId2Trade.setdefault(order.permId, trade)
            results = self._results.get("openOrders")

            if results is None:
                self.ib.openOrderEvent.emit(trade)
            else:
                # response to reqOpenOrders or reqAllOpenOrders
                results.append(trade)

        # make sure that the client issues order ids larger than any
        # order id encountered (even from other clients) to avoid
        # "Duplicate order id" error
        self.ib.client.updateReqId(orderId + 1)

    def openOrderEnd(self):
        self._endReq("openOrders")

    def completedOrder(self, contract: Contract, order: Order, orderState: OrderState):
        contract = Contract.recreate(contract)
        orderStatus = OrderStatus(orderId=order.orderId, status=orderState.status)
        trade = Trade(contract, order, orderStatus, [], [])
        self._results["completedOrders"].append(trade)

        if order.permId not in self.permId2Trade:
            self.trades[order.permId] = trade
            self.permId2Trade[order.permId] = trade

    def completedOrdersEnd(self):
        self._endReq("completedOrders")

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
            msg: Optional[str]
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
        isLive = reqId not in self._futures
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
            self._results[reqId].append(fill)

    def execDetailsEnd(self, reqId: int):
        self._endReq(reqId)

    def commissionReport(self, commissionReport: CommissionReport):
        if commissionReport.yield_ == UNSET_DOUBLE:
            commissionReport.yield_ = 0.0

        if commissionReport.realizedPNL == UNSET_DOUBLE:
            commissionReport.realizedPNL = 0.0

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
        self._results[reqId].append(contractDetails)

    bondContractDetails = contractDetails

    def contractDetailsEnd(self, reqId: int):
        self._endReq(reqId)

    def symbolSamples(
        self, reqId: int, contractDescriptions: list[ContractDescription]
    ):
        self._endReq(reqId, contractDescriptions)

    def marketRule(self, marketRuleId: int, priceIncrements: list[PriceIncrement]):
        self._endReq(f"marketRule-{marketRuleId}", priceIncrements)

    def marketDataType(self, reqId: int, marketDataId: int):
        ticker = self.reqId2Ticker.get(reqId)
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
        bars = self.reqId2Subscriber.get(reqId)
        if bars is not None:
            bars.append(bar)
            self.ib.barUpdateEvent.emit(bars, True)
            bars.updateEvent.emit(bars, True)

    def historicalData(self, reqId: int, bar: BarData):
        results = self._results.get(reqId)
        if results is not None:
            bar.date = parseIBDatetime(bar.date)  # type: ignore
            results.append(bar)

    def historicalDataEnd(self, reqId, _start: str, _end: str):
        self._endReq(reqId)

    def historicalDataUpdate(self, reqId: int, bar: BarData):
        bars = self.reqId2Subscriber.get(reqId)
        if not bars:
            return

        bar.date = parseIBDatetime(bar.date)  # type: ignore
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
            dt = parseIBDatetime(headTimestamp)
            self._endReq(reqId, dt)
        except ValueError as exc:
            self._endReq(reqId, exc, False)

    def historicalTicks(self, reqId: int, ticks: list[HistoricalTick], done: bool):
        result = self._results.get(reqId)
        if result is not None:
            result += ticks

        if done:
            self._endReq(reqId)

    def historicalTicksBidAsk(
        self, reqId: int, ticks: list[HistoricalTickBidAsk], done: bool
    ):
        result = self._results.get(reqId)
        if result is not None:
            result += ticks

        if done:
            self._endReq(reqId)

    def historicalTicksLast(
        self, reqId: int, ticks: list[HistoricalTickLast], done: bool
    ):
        result = self._results.get(reqId)
        if result is not None:
            result += ticks

        if done:
            self._endReq(reqId)

    # additional wrapper method provided by Client
    def priceSizeTick(self, reqId: int, tickType: int, price: float, size: float):
        ticker = self.reqId2Ticker.get(reqId)
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
        ticker = self.reqId2Ticker.get(reqId)
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
        self._endReq(reqId)

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
        ticker = self.reqId2Ticker.get(reqId)
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
        ticker = self.reqId2Ticker.get(reqId)
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
        ticker = self.reqId2Ticker.get(reqId)
        if not ticker:
            self._logger.error(f"tickByTickMidPoint: Unknown reqId: {reqId}")
            return

        tick = TickByTickMidPoint(self.lastTime, midPoint)
        ticker.tickByTicks.append(tick)
        self.pendingTickers.add(ticker)

    def tickString(self, reqId: int, tickType: int, value: str):
        if not (ticker := self.reqId2Ticker.get(reqId)):
            return

        try:
            if tickType == 32:
                ticker.bidExchange = value
            elif tickType == 33:
                ticker.askExchange = value
            elif tickType == 84:
                ticker.lastExchange = value
            elif tickType == 45:
                timestamp = int(value)

                # only populate if timestamp isn't '0' (we don't want to report "last trade: 20,000 days ago")
                if timestamp:
                    ticker.lastTimestamp = datetime.fromtimestamp(
                        timestamp, self.defaultTimezone
                    )
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
            elif tickType in {48, 77}:
                # RT Volume or RT Trade Volume string format:
                # price;size;ms since epoch;total volume;VWAP;single trade
                # example:
                # 701.28;1;1348075471534;67854;701.46918464;true
                priceStr, sizeStr, rtTime, volume, vwap, _ = value.split(";")
                if volume:
                    if tickType == 48:
                        ticker.rtVolume = float(volume)
                    elif tickType == 77:
                        ticker.rtTradeVolume = float(volume)

                if vwap:
                    ticker.vwap = float(vwap)

                if rtTime:
                    ticker.rtTime = datetime.fromtimestamp(
                        int(rtTime) / 1000, self.defaultTimezone
                    )

                if priceStr == "":
                    return

                price = float(priceStr)
                size = float(sizeStr)

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
        ticker = self.reqId2Ticker.get(reqId)
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
        ticker = self.reqId2Ticker.get(reqId)
        if not ticker:
            return

        ticker.minTick = minTick
        ticker.bboExchange = bboExchange
        ticker.snapshotPermissions = snapshotPermissions

    def smartComponents(self, reqId, components):
        self._endReq(reqId, components)

    def mktDepthExchanges(
        self, depthMktDataDescriptions: list[DepthMktDataDescription]
    ):
        self._endReq("mktDepthExchanges", depthMktDataDescriptions)

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
        ticker = self.reqId2Ticker[reqId]

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
        ticker = self.reqId2Ticker.get(reqId)
        if ticker:
            # reply from reqMktData
            # https://interactivebrokers.github.io/tws-api/tick_types.html

            assert tickType in GREEKS_TICK_MAP, (
                f"Received tick {tickType=} {tickAttrib=} but we don't have an attribute mapping for it? Triggered from {ticker.contract=}"
            )

            setattr(ticker, GREEKS_TICK_MAP[tickType], comp)
            self.pendingTickers.add(ticker)
        elif reqId in self._futures:
            # reply from calculateImpliedVolatility or calculateOptionPrice
            self._endReq(reqId, comp)
        else:
            self._logger.error(f"tickOptionComputation: Unknown reqId: {reqId}")

    def deltaNeutralValidation(self, reqId: int, dnc: DeltaNeutralContract):
        pass

    def fundamentalData(self, reqId: int, data: str):
        self._endReq(reqId, data)

    def scannerParameters(self, xml: str):
        self._endReq("scannerParams", xml)

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
        dataList = self.reqId2Subscriber.get(reqId)
        if dataList is None:
            dataList = self._results.get(reqId)

        if dataList is not None:
            if rank == 0:
                dataList.clear()
            dataList.append(data)

    def scannerDataEnd(self, reqId: int):
        dataList = self._results.get(reqId)
        if dataList is not None:
            self._endReq(reqId)
        else:
            dataList = self.reqId2Subscriber.get(reqId)

        if dataList is not None:
            self.ib.scannerDataEvent.emit(dataList)
            dataList.updateEvent.emit(dataList)

    def histogramData(self, reqId: int, items: list[HistogramData]):
        result = [HistogramData(item.price, item.count) for item in items]
        self._endReq(reqId, result)

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
        self._results[reqId].append(chain)

    def securityDefinitionOptionParameterEnd(self, reqId: int):
        self._endReq(reqId)

    def newsProviders(self, newsProviders: list[NewsProvider]):
        newsProviders = [NewsProvider(code=p.code, name=p.name) for p in newsProviders]
        self._endReq("newsProviders", newsProviders)

    def tickNews(
        self,
        _reqId: int,
        timeStamp: int,
        providerCode: str,
        articleId: str,
        headline: str,
        extraData: str,
    ):
        news = NewsTick(timeStamp, providerCode, articleId, headline, extraData)
        self.newsTicks.append(news)
        self.ib.tickNewsEvent.emit(news)

    def newsArticle(self, reqId: int, articleType: int, articleText: str):
        article = NewsArticle(articleType, articleText)
        self._endReq(reqId, article)

    def historicalNews(
        self, reqId: int, time: str, providerCode: str, articleId: str, headline: str
    ):
        dt = parseIBDatetime(time)
        dt = cast(datetime, dt)
        article = HistoricalNews(dt, providerCode, articleId, headline)
        self._results[reqId].append(article)

    def historicalNewsEnd(self, reqId, _hasMore: bool):
        self._endReq(reqId)

    def updateNewsBulletin(
        self, msgId: int, msgType: int, message: str, origExchange: str
    ):
        bulletin = NewsBulletin(msgId, msgType, message, origExchange)
        self.msgId2NewsBulletin[msgId] = bulletin
        self.ib.newsBulletinEvent.emit(bulletin)

    def receiveFA(self, _faDataType: int, faXmlData: str):
        self._endReq("requestFA", faXmlData)

    def currentTime(self, time: int):
        dt = datetime.fromtimestamp(time, self.defaultTimezone)
        self._endReq("currentTime", dt)

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
        pass

    def historicalSchedule(
        self,
        reqId: int,
        startDateTime: str,
        endDateTime: str,
        timeZone: str,
        sessions: list[HistoricalSession],
    ):
        schedule = HistoricalSchedule(startDateTime, endDateTime, timeZone, sessions)
        self._endReq(reqId, schedule)

    def wshMetaData(self, reqId: int, dataJson: str):
        self.ib.wshMetaEvent.emit(dataJson)
        self._endReq(reqId, dataJson)

    def wshEventData(self, reqId: int, dataJson: str):
        self.ib.wshEvent.emit(dataJson)
        self._endReq(reqId, dataJson)

    def userInfo(self, reqId: int, whiteBrandingId: str):
        self._endReq(reqId)

    def softDollarTiers(self, reqId: int, tiers: list[SoftDollarTier]):
        pass

    def familyCodes(self, familyCodes: list[FamilyCode]):
        pass

    def error(
        self, reqId: int, errorCode: int, errorString: str, advancedOrderRejectJson: str
    ):
        # https://interactivebrokers.github.io/tws-api/message_codes.html
        # https://ibkrcampus.com/campus/ibkr-api-page/twsapi-doc/#api-error-codes
        isRequest = reqId in self._futures
        trade = None

        # reqId is a local orderId, but is delivered as -1 if this is a non-order-related error
        if reqId != -1:
            trade = self.trades.get((self.clientId, reqId))

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
        # Note: error 321 means error validing, but if the message is the result of a MODIFY, the order _is still live_ and we must not delete it.
        # TODO: investigate if error 321 happens on _new_ order placement with incorrect parameters too, then we should probably delete the order.

        # Previously this was included as a Warning condition, but 202 is literally "Order Canceled" error status, so now it is an order-delete error:
        # 202 - Order cancelled - Reason:

        warningCodes = frozenset({105, 110, 165, 321, 329, 399, 404, 434, 492, 10167})
        isWarning = errorCode in warningCodes or 2100 <= errorCode < 2200

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

        contract = self._reqId2Contract.get(reqId)
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
                # the request failed
                if self.ib.RaiseRequestErrors:
                    error = RequestError(reqId, errorCode, errorString)
                    self._endReq(reqId, error, success=False)
                else:
                    self._endReq(reqId)
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
            # for scan data subscription there are no longer matching results
            dataList = self.reqId2Subscriber.get(reqId)
            if dataList:
                dataList.clear()
                dataList.updateEvent.emit(dataList)
        elif errorCode == 317:
            # Market depth data has been RESET
            ticker = self.reqId2Ticker.get(reqId)
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
            # Please resubscribe real-time bars immediately
            bars = self.reqId2Subscriber.get(reqId)
            if isinstance(bars, RealTimeBarList):
                self.ib.client.cancelRealTimeBars(reqId)
                self.ib.client.reqRealTimeBars(
                    reqId,
                    bars.contract,
                    bars.barSize,
                    bars.whatToShow,
                    bars.useRTH,
                    bars.realTimeBarsOptions,
                )
            elif isinstance(bars, BarDataList):
                self.ib.client.cancelHistoricalData(reqId)
                self.ib.client.reqHistoricalData(
                    reqId,
                    bars.contract,
                    bars.endDateTime,
                    bars.durationStr,
                    bars.barSizeSetting,
                    bars.whatToShow,
                    bars.useRTH,
                    bars.formatDate,
                    bars.keepUpToDate,
                    bars.chartOptions,
                )

        self.ib.errorEvent.emit(reqId, errorCode, errorString, contract)

    def tcpDataArrived(self):
        self.lastTime = datetime.now(self.defaultTimezone)
        self.time = time.time()
        for ticker in self.pendingTickers:
            ticker.ticks = []
            ticker.tickByTicks = []
            ticker.domTicks = []

        self.pendingTickers = set()

    def tcpDataProcessed(self):
        self.ib.updateEvent.emit()
        if self.pendingTickers:
            for ticker in self.pendingTickers:
                ticker.time = self.lastTime
                ticker.timestamp = self.time
                ticker.updateEvent.emit(ticker)

            self.ib.pendingTickersEvent.emit(self.pendingTickers)
