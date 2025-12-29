"""Wrapper to handle incoming messages."""

from __future__ import annotations

import asyncio
import logging
import time
from collections import defaultdict
from collections.abc import Hashable
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Generic,
    TypeAlias,
    TypeVar,
    cast,
)
from weakref import WeakKeyDictionary

import eventkit as ev

from .contract import (
    Contract,
    ContractDescription,
    ContractDetails,
    DeltaNeutralContract,
    ScanData,
)
from .objects import (
    AccountValue,
    BarData,
    BarDataList,
    CommissionReport,
    DepthMktDataDescription,
    DOMLevel,
    FamilyCode,
    Fill,
    HistogramData,
    HistoricalNews,
    HistoricalSchedule,
    HistoricalTickType,
    IBDefaults,
    MktDepthData,
    NewsArticle,
    NewsBulletin,
    NewsProvider,
    NewsTick,
    OptionChain,
    PnL,
    PnLSingle,
    PortfolioItem,
    Position,
    PriceIncrement,
    RealTimeBar,
    RealTimeBarList,
    ScanDataList,
    SoftDollarTier,
    TickComputationData,
    TickDeliveryType,
    TickParams,
    TradeLogEntry,
)
from .order import Order, OrderState, OrderStatus, Trade
from .ticker import Ticker
from .util import (
    EPOCH,
    dataclassUpdate,
    getLoop,
    globalErrorEvent,
    parseIBDatetime,
)

if TYPE_CHECKING:
    from .ib import IB


OrderKeyType: TypeAlias = int | tuple[int, int]
SubscriptionType: TypeAlias = ScanDataList | RealTimeBarList | BarDataList

# K = any hashable thing: str, int, UUID, tuple, frozenset, etc.
K = TypeVar("K", bound=Hashable)
V = TypeVar("V")


class BiDict(Generic[K, V]):
    """
    Bidirectional mapping with full support for composite keys (tuples, etc.)
        reqId (int)             ↔ object
        object_id (hashable)    ↔ request_id

    - O(1) lookup in both directions
    - Automatically keeps both indexes in sync
    - Does NOT hold strong reference to `obj` via object_id → prevents leaks
    - Optionally tracks objects weakly if you ever need obj → request_id lookup

    Usage:
    =====

    tickers = BiDict[int,Ticker]()
    # add an entry with keys reqId and hash(ticker.contract), value ticker
    tickers.add(reqId,hash(ticker.contract),ticker)

    # reqId -> object
    tickers.get_by_request_id(reqId) # return ticker for reqId
    # object_id -> object
    # object_id could be a tuple ie. (order.clientId, order.orderId, order.permId)
    tickers.get_by_object_id(hash(ticker.contract)) # return ticker for contract
    tickers.get_request_id(hash(ticker.contract)) # return reqId for contract
    #
    # requires tickers = BiDict[int,Ticker](track_objects_weakly=True)
    tickers.get_request_id_by_object(ticker) # return reqId for object
    # remove
    tickers.remove_by_request_id(reqId) # remove ticker for reqId
    tickers.remove_by_object_id(hash(ticker.contract)) # remove ticker for contract
    # contains, by reqId or object_id
    reqId in tickers
    hash(ticker.contract) in tickers
    """

    def __init__(self, *, track_objects_weakly: bool = False) -> None:
        """Bidirectional mapping

        Args:
            track_objects_weakly (bool, optional): enable get_request_id_by_object,
                                                using weakreferences. Defaults to False.
        """
        # Primary storage: request_id → (object_id, object)
        self._by_request: dict[int, tuple[K, V]] = {}
        # Reverse index: object_id → request_id (object_id is usually str/int)
        self._request_by_object_id: dict[K, int] = {}
        # Optional: weak mapping from object instance → request_id
        self._track_objects_weakly = track_objects_weakly
        if track_objects_weakly:
            self._request_by_object: WeakKeyDictionary[Any, int] = WeakKeyDictionary()
        else:
            self._request_by_object = None  # type: ignore

    def __repr__(self) -> str:
        return repr(self._by_request)

    def values(self) -> list[V]:
        return [v for _, v in self._by_request.values()]

    def add(self, request_id: int, object_id: K, obj: V) -> None:
        """
        Add values to the map.
            request_id (int): identifies ie reqId
            object_id (K): object identifier, ie (account, tag, currency, "") for
                           accountValue.
            obj (V): the object to store, Ticker, AccountValue, etc.
        """
        self._remove_existing(request_id, object_id, obj)

        self._by_request[request_id] = (object_id, obj)
        self._request_by_object_id[object_id] = request_id
        if self._track_objects_weakly and self._request_by_object is not None:
            self._request_by_object[obj] = request_id

    def get_by_request_id(self, request_id: int) -> V | None:
        """
        Get value by request id.
            request_id (int): identifies ie reqId, permId

        Returns:
            Value stored, or None if not found.
        """
        entry = self._by_request.get(request_id)
        return entry[1] if entry else None

    def get_by_object_id(self, object_id: K) -> V | None:
        """Get value by object id, ie hash(contract)

        Args:
            object_id (K): ie. hash(contract), (account, tag, currency, "")

        Returns:
            V | None: value stored, or None if not found.
        """
        request_id = self._request_by_object_id.get(object_id)
        if request_id is not None:
            return self._by_request[request_id][1]
        return None

    def get_request_id(self, object_id: K) -> int | None:
        """Get request id by object id

        Args:
            object_id (K): ie. hash(contract), (account, tag, currency, "")

        Returns:
            int | None: request_id, or None if not found.
        """
        return self._request_by_object_id.get(object_id)

    def get_request_id_by_object(self, obj: V) -> int | None:
        """Get reqquest_od by object.
        Only works if track_objects_weakly=True

        Args:
            obj (V): value

        Returns:
            int | None: request_id, or None if not found.
        """
        if self._request_by_object is not None:
            return self._request_by_object.get(obj)
        return None

    def remove_by_request_id(self, request_id: int) -> None:
        if request_id not in self._by_request:
            return
        object_id, obj = self._by_request.pop(request_id)
        self._request_by_object_id.pop(object_id, None)
        if self._request_by_object is not None:
            self._request_by_object.pop(obj, None)

    def remove_by_object_id(self, object_id: K) -> None:
        request_id = self._request_by_object_id.pop(object_id, None)
        if request_id is not None:
            entry = self._by_request.pop(request_id, None)
            if entry and self._request_by_object is not None:
                _, obj = entry
                self._request_by_object.pop(obj, None)

    def update_request_id(self, object_id: K, new_request_id: int):
        """
        Updates the request_id associated with an existing entry, identified by its
        object_id.

        This method is used when the primary request_id (e.g., permId for a Trade)
        is not known at the time of initial creation and is later assigned by the API.
        It re-indexes the object within the BiDict using the new request_id while
        preserving the object's identity and its association with the object_id.

        Args:
            object_id (K): The unique identifier for the object (e.g., (clientId,
                           orderId) for a Trade).
            new_request_id (int): The new, permanent request ID to associate with the
                                  object (e.g., permId).
        """
        old_request_id = self._request_by_object_id.get(object_id)
        if old_request_id is None or old_request_id == new_request_id:
            # Entry doesn't exist or is already correct, nothing to do.
            return

        # Pop the old entry and add it back with the new request_id
        entry = self._by_request.pop(old_request_id, None)
        if entry:
            self._by_request[new_request_id] = entry
            # Update the reverse mapping to point to the new request_id
            self._request_by_object_id[object_id] = new_request_id
            # Update the weak object mapping if it exists
            if self._track_objects_weakly and self._request_by_object:
                _, obj = entry
                self._request_by_object[obj] = new_request_id

    def _remove_existing(self, request_id: int, object_id: K, obj: V) -> None:
        """Clean up old request_id and object_id mapping."""

        if request_id in self._by_request:
            old_id, old_obj = self._by_request[request_id]
            self._request_by_object_id.pop(old_id, None)
            if self._request_by_object is not None:
                self._request_by_object.pop(old_obj, None)

        # Clean up any previous mapping using same object_id
        if object_id in self._request_by_object_id:
            old_req_id = self._request_by_object_id[object_id]
            old_entry = self._by_request.pop(old_req_id, None)
            if old_entry and self._request_by_object is not None:
                _, old_obj = old_entry
                self._request_by_object.pop(old_obj, None)

    def __len__(self) -> int:
        return len(self._by_request)

    def __contains__(self, key: object) -> bool:
        if isinstance(key, int):
            return key in self._by_request
        return key in self._request_by_object_id


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
    """Wrapper implementation for use with the IB class.

    Wrapper keeps track of `state`, accounts, accoutn values, positions, etc. and 
    respond to requests, subscriptions and streming data.
    """

    # reference back to IB so wrapper can access API methods
    ib: IB

    accountValues: dict[tuple, AccountValue] = field(init=False)
    """ (account, tag, currency, modelCode) -> AccountValue """

    acctSummary: dict[tuple, AccountValue] = field(init=False)
    """ (account, tag, currency) -> AccountValue """

    portfolio: dict[str, dict[int, PortfolioItem]] = field(init=False)
    """ account -> conId -> PortfolioItem """

    positions: dict[str, dict[int, Position]] = field(init=False)
    """ account -> conId -> Position """

    trades: BiDict[OrderKeyType, Trade] = field(init=False)
    """
    by request id: permId -> Trade
    by object id: (client, orderId) or permId -> Trade
    """

    _isReady: bool = field(init=False, default=False)
    """ wrapper initial status state """

    fills: dict[str, Fill] = field(init=False)
    """ execId -> Fill """

    newsTicks: list[NewsTick] = field(init=False)

    newsBulletins: dict[int, NewsBulletin] = field(init=False)
    """ msgId -> NewsBulletin """

    tickers: BiDict[int, Ticker] = field(init=False)
    """
    reqId -> Ticker
    hash(Contract) -> Ticker
    Ticker -> reqId
    """

    pendingTickers: set[Ticker] = field(init=False)

    subscriptions: BiDict[int, SubscriptionType] = field(init=False)
    """ live bars or live scan data """

    Pnl: BiDict[tuple[str, str], PnL] = field(init=False)
    """ reqId -> PnL
    (account, modelCode) -> reqId
    """

    pnlSingles: BiDict[tuple[str, str, int], PnLSingle] = field(init=False)
    """ reqId -> PnLSingle
    (account, modelCode, conId) -> reqId
    """

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
    _timeout: float = field(init=False)

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
        self.response_bus = ev.Event("Response bus")
        self.reset()

    def reset(self):
        self.accountValues = {}
        self.acctSummary = {}
        self.portfolio = defaultdict(dict)
        self.positions = defaultdict(dict)
        self.trades = BiDict[OrderKeyType, Trade]()
        self.subscriptions = BiDict[int, SubscriptionType]()
        self._isReady = False
        self.fills = {}
        self.newsTicks = []
        self.newsBulletins = {}
        self.tickers = BiDict[int, Ticker]()
        self.pendingTickers = set()
        self.Pnl = BiDict[tuple[str, str], PnL]()
        self.pnlSingles = BiDict[tuple[str, str, int], PnLSingle]()
        self.lastTime = datetime.min
        self.time = -1
        self.accounts = []
        self.clientId = -1
        self.wshMetaReqId = 0
        self.wshEventReqId = 0
        self._timeout = 0
        self.setTimeout(0)

    def setEventsDone(self):
        """Set all subscription-type events as done."""
        self._logger.debug("wrapper.setEventsDone")
        events = [ticker.updateEvent for ticker in self.tickers.values()]
        events += [sub.updateEvent for sub in self.subscriptions.values()]
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
        events += [self.response_bus]
        for event in events:
            event.set_done()

    def connectionClosed(self):
        error = ConnectionError("Socket disconnect")

        globalErrorEvent.emit(error)
        self.reset()

    def _endReq(self, reqId: int | str):
        self.response_bus.emit(reqId, None)

    def startTicker(self, reqId: int, contract: Contract):
        """
        Start a tick request that has the reqId associated with the contract.
        Return the ticker.
        """
        ticker = self.tickers.get_by_request_id(reqId)
        if not ticker:
            ticker = Ticker(contract=contract, defaults=self.defaults)
            self.tickers.add(reqId, hash(ticker.contract), ticker)
            ticker.ticker_bus.takewhile(lambda data, t: data is not None).connect(
                ticker._on_ticker_data
            )

        return ticker

    def endTicker(self, ticker: Ticker):
        reqId = self.tickers.get_request_id(hash(ticker.contract))
        if reqId:
            self.tickers.remove_by_request_id(reqId)
            ticker.ticker_bus.emit(None, None)
        return reqId

    def startSubscription(
        self, reqId: int, subscriber: SubscriptionType, contract: Contract | None = None
    ):
        """Register a live subscription."""
        if contract:
            # ib.reqRealTimeBars or ib.reqHistoricalDataAsync
            self.subscriptions.add(reqId, hash(contract), subscriber)

        else:
            # ib.reqScannerSubscription
            self.subscriptions.add(reqId, reqId, subscriber)
        # start subscription
        subscriber.subscription_bus.takewhile(lambda data: data is not None).map(
            self.ib._raise_if_error
        ).partial(self.ib).connect(subscriber._on_data)

    def endSubscription(self, subscriber):
        """Unregister a live subscription."""
        subscriber.subscription_bus.emit(None)
        self.subscriptions.remove_by_request_id(subscriber.reqId)

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

    def nextValidId(self, reqId: int):
        self.ib.client.updateReqId(reqId)
        self.ib.client._hasReqId = True

    def managedAccounts(self, accountsList: str):
        self.accounts = (
            accountsList.split(",") if isinstance(accountsList, str) else accountsList
        )
        self.ib.client._accounts = self.accounts

    def updateAccountTime(self, timestamp: str):
        self.accountTime = timestamp

    def updateAccountValue(self, value: AccountValue):
        key = (value.account, value.tag, value.currency, "")
        self.accountValues[key] = value
        if self._isReady:
            self.ib.accountValueEvent.emit(value)

    def accountDownloadEnd(self, _account: str):
        """sent after updateAccountValue and updatePortfolio both finished"""
        self._endReq("accountValues")

    def accountUpdateMulti(self, reqId: int, value: AccountValue):
        key = (value.account, value.tag, value.currency, value.modelCode)
        self.accountValues[key] = value
        if self._isReady:
            self.ib.accountValueEvent.emit(value)
        self.response_bus.emit(reqId, value)

    def accountUpdateMultiEnd(self, reqId: int):
        self._endReq(reqId)

    def accountSummary(self, reqId: int, accountValue: AccountValue):
        key = (accountValue.account, accountValue.tag, accountValue.currency)
        self.acctSummary[key] = accountValue
        if self._isReady:
            self.ib.accountValueEvent.emit(accountValue)
        self.response_bus.emit(reqId, accountValue)

    def accountSummaryEnd(self, reqId: int):
        self._endReq(reqId)

    def updatePortfolio(self, portfolioItem: PortfolioItem):
        account_portfolio = self.portfolio[portfolioItem.account]
        if portfolioItem.position == 0:
            account_portfolio.pop(portfolioItem.contract.conId, None)
        else:
            account_portfolio[portfolioItem.contract.conId] = portfolioItem

        if self._isReady:
            self.ib.updatePortfolioEvent.emit(portfolioItem)

    def position(self, position: Position):
        account_positions = self.positions[position.account]
        if position.position == 0:
            account_positions.pop(position.contract.conId, None)
        else:
            account_positions[position.contract.conId] = position

        if self._isReady:
            self.ib.positionEvent.emit(position)
        self.response_bus.emit("position", position)

    def positionEnd(self):
        self._endReq("position")

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
        pnl = self.Pnl.get_by_request_id(reqId)
        if pnl:
            pnl.pnl_bus.emit(dailyPnL, unrealizedPnL, realizedPnL)
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
        pnlSingle = self.pnlSingles.get_by_request_id(reqId)
        if pnlSingle:
            pnlSingle.pnl_single_bus.emit(
                pos, dailyPnL, unrealizedPnL, realizedPnL, value
            )
            self.ib.pnlSingleEvent.emit(pnlSingle)

    def orderKey(self, clientId: int, orderId: int, permId: int) -> OrderKeyType:
        key: OrderKeyType
        if orderId <= 0:
            # order is placed manually from TWS
            key = permId
        else:
            key = (clientId, orderId)
        return key

    def openOrder(self, trade: Trade, orderState: OrderState):
        """
        This wrapper is called to:

        * feed in open orders at startup;
        * feed in open orders or order updates from other clients and TWS
          if clientId=master id;
        * feed in manual orders and order updates from TWS if clientId=0;
        * handle openOrders and allOpenOrders responses.
        """
        if trade.order.whatIf:
            self.response_bus.emit(trade.order.orderId, orderState)
            return

        key = self.orderKey(
            trade.order.clientId, trade.order.orderId, trade.order.permId
        )
        existing_trade = self.trades.get_by_object_id(key)

        if existing_trade:
            # Trade is already known (from placeOrder), so update it
            # 1. Mutate the existing trade object in-place
            dataclassUpdate(existing_trade.order, trade.order)
            dataclassUpdate(existing_trade.orderStatus, trade.orderStatus)

            # 2. Re-index the BiDict with the final permId
            self.trades.update_request_id(key, existing_trade.order.permId)

        else:
            # This is a new trade, likely placed manually from TWS
            self.trades.add(trade.order.permId, key, trade)
            self._logger.info(f"openOrder: {trade}")

        final_trade = existing_trade or trade
        if self._isReady:
            self.ib.openOrderEvent.emit(final_trade)
        if final_trade.order.orderId > 0:
            self.ib.client.updateReqId(final_trade.order.orderId + 1)
        self.response_bus.emit("openOrders", final_trade)

    def openOrderEnd(self):
        self._endReq("openOrders")

    def completedOrder(
        self, contract: Contract, order: Order, orderStatus: OrderStatus
    ):
        contract = Contract.recreate(contract)
        trade = Trade(contract, order, orderStatus, [], [])

        if order.permId not in self.trades:
            key = self.orderKey(order.clientId, order.orderId, order.permId)
            self.trades.add(order.permId, key, trade)
        self._logger.debug(f"completedOrders: {trade}")
        self.response_bus.emit("completedOrders", trade)

    def completedOrdersEnd(self):
        self._endReq("completedOrders")

    def orderStatus(self, orderStatus: OrderStatus):
        key = self.orderKey(
            orderStatus.clientId, orderStatus.orderId, orderStatus.permId
        )
        trade = self.trades.get_by_object_id(key)
        if trade:
            if trade.orderStatus != orderStatus:
                msg = ""
                trade.orderStatus = orderStatus
            elif (
                orderStatus.status == "Submitted"
                and trade.log
                and trade.log[-1].message == "Modify"
            ):
                # order modifications are acknowledged
                msg = "Modified"
            else:
                msg = None

            if msg:
                logEntry = TradeLogEntry(self.lastTime, orderStatus.status, msg)
                trade.log.append(logEntry)
                self._logger.info(f"orderStatus: {trade}")

                if self._isReady:
                    trade.statusEvent.emit(trade)
                    self.ib.orderStatusEvent.emit(trade)

                    if orderStatus.status == OrderStatus.Cancelled:
                        trade.cancelledEvent.emit(trade)
                    elif orderStatus.status == OrderStatus.Filled:
                        trade.filledEvent.emit(trade)
        else:
            self._logger.error(
                "orderStatus: No order found for orderId %s and clientId %s",
                orderStatus.orderId,
                orderStatus.clientId,
            )

    def execDetails(self, reqId: int, fill: Fill):
        """
        This wrapper handles both live fills and responses to
        reqExecutions.
        """
        permId = fill.execution.permId
        trade = self.trades.get_by_request_id(permId)
        if not trade:
            key = self.orderKey(fill.execution.clientId, fill.execution.orderId, permId)
            trade = self.trades.get_by_object_id(key)
        # TODO: debug why spread contracts aren't fully detailed here. They have no
        # legs in execDetails, but they do in orderStatus?
        if trade and fill.contract == trade.contract:
            fill.contract = trade.contract
        else:
            fill.contract = Contract.recreate(fill.contract)

        if fill.execution.execId not in self.fills:
            self.fills[fill.execution.execId] = fill
            if trade:
                trade.fills.append(fill)
                time = self.lastTime if self._isReady else fill.execution.time
                logEntry = TradeLogEntry(
                    time,
                    trade.orderStatus.status,
                    f"Fill {fill.execution.shares}@{fill.execution.price}",
                )
                trade.log.append(logEntry)
                if self._isReady:
                    self._logger.info("execDetails: %s", fill)
                    self.ib.execDetailsEvent.emit(trade, fill)
                    trade.fillEvent.emit(trade, fill)

        self.response_bus.emit(reqId, fill)

    def execDetailsEnd(self, reqId: int):
        self._endReq(reqId)

    def commissionReport(self, commissionReport: CommissionReport):
        """After a fill TWS API will send us the final commission report.
        commissionReportEvent emits final values
        """
        fill: Fill | None = self.fills.get(commissionReport.execId)

        if not fill:
            # commission report is not for this client
            return

        trade = self.trades.get_by_request_id(fill.execution.permId)
        if not trade:
            return

        report = dataclassUpdate(fill.commissionReport, commissionReport)

        self._logger.info(f"commissionReport: {report}")
        if self._isReady and trade:
            self.ib.commissionReportEvent.emit(trade, fill, commissionReport)
            trade.commissionReportEvent.emit(trade, fill, commissionReport)
        else:
            # this is not a live execution and the order was filled
            # before this connection started
            pass

    def orderBound(self, permId: int, clientId: int, orderId: int):
        """
        https://www.interactivebrokers.com/campus/ibkr-api-page/twsapi-doc/#order-bound-notification
        """
        self._logger.info(
            "Bound order with permId: %s, clientId: %s, orderId: %s",
            permId,
            clientId,
            orderId,
        )
        self.ib.orderBoundEvent.emit(permId, clientId, orderId)

    def contractDetails(self, reqId: int, contractDetails: ContractDetails):
        self.response_bus.emit(reqId, contractDetails)

    bondContractDetails = contractDetails

    def contractDetailsEnd(self, reqId: int):
        self._endReq(reqId)

    def symbolSamples(
        self, reqId: int, contractDescriptions: list[ContractDescription]
    ):
        self.response_bus.emit(reqId, contractDescriptions)

    def marketRule(self, marketRuleId: int, priceIncrements: list[PriceIncrement]):
        self.response_bus.emit(f"marketRule-{marketRuleId}", priceIncrements)

    def marketDataType(self, reqId: int, marketDataId: int):
        ticker = self.tickers.get_by_request_id(reqId)
        if ticker:
            ticker.marketDataType = marketDataId

    def realtimeBar(self, reqId: int, bar: RealTimeBar):
        if bar is not None:
            bars_subscription = self.subscriptions.get_by_request_id(reqId)
            if bars_subscription is not None:
                bars_subscription.subscription_bus.emit(bar)

    def historicalData(self, reqId: int, bars: list[BarData]):
        if bars is not None:
            self.response_bus.emit(reqId, bars)

    def historicalDataEnd(self, reqId, _start: str, _end: str):
        self._endReq(reqId)

    def historicalDataUpdate(self, reqId: int, bar: BarData):
        subscription = self.subscriptions.get_by_request_id(reqId)
        if subscription:
            subscription.subscription_bus.emit(bar)

    def headTimestamp(self, reqId: int, headTimestamp: str):
        try:
            dt = parseIBDatetime(headTimestamp)
            self.response_bus.emit(reqId, dt)
        except ValueError as exc:
            self.response_bus.emit(reqId, exc)

    def historicalTicks(self, reqId: int, ticks: list[HistoricalTickType], done: bool):
        self.response_bus.emit(reqId, ticks)
        if done:
            self._endReq(reqId)

    def tickerDelivery(self, reqId: int, tickData: TickDeliveryType):
        ticker = self.tickers.get_by_request_id(reqId)
        if not ticker:
            self._logger.error("tickerDelivery: Unknown reqId: %s, %r", reqId, tickData)
            return
        ticker.ticker_bus.emit(tickData, self.lastTime)
        self.pendingTickers.add(ticker)

    def tickReqParams(self, reqId: int, tickParams: TickParams):
        if not (ticker := self.tickers.get_by_request_id(reqId)):
            return
        ticker.minTick = tickParams.minTick
        ticker.bboExchange = tickParams.bboExchange
        ticker.snapshotPermissions = tickParams.snapshotPermissions

    def tickSnapshotEnd(self, reqId: int):
        ticker = self.tickers.get_by_request_id(reqId)
        if ticker:
            self.endTicker(ticker)
            return

        self._logger.error(f"tickSnapshotEnd: Unknown reqId: {reqId}")

    def tickByTick(self, reqId: int, tickByTick: HistoricalTickType):
        ticker = self.tickers.get_by_request_id(reqId)
        if not ticker:
            self._logger.error(f"tickByTick: Unknown reqId: {reqId}")
            return
        ticker.ticker_bus.emit(tickByTick, EPOCH)
        self.pendingTickers.add(ticker)

    def tickOptionComputation(self, reqId: int, tick_computation: TickComputationData):
        ticker = self.tickers.get_by_request_id(reqId)
        if ticker:
            # reply from reqMktData
            # https://interactivebrokers.github.io/tws-api/tick_types.html

            ticker.ticker_bus.emit(tick_computation, self.lastTime)
            self.pendingTickers.add(ticker)
        elif reqId:
            # reply from calculateImpliedVolatility or calculateOptionPrice
            self.response_bus.emit(reqId, tick_computation.computation)
        else:
            self._logger.error(f"tickOptionComputation: Unknown reqId: {reqId}")

    def smartComponents(self, reqId, components):
        self.response_bus.emit(reqId, components)

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
        ticker = self.tickers.get_by_request_id(reqId)
        if not ticker:
            self._logger.error(f"updateMktDepthL2: Unknown reqId: {reqId}")
            return

        # 'dom' is a dict so we can address position updates directly
        dom = ticker.domBidsDict if side else ticker.domAsksDict

        # if you're curious when these operations run and what they do, enable this too:
        # fmt: off
        # print("BID" if side else "ASK", "OPERATION", operation, "at position",
        # position, "for price", price, "at qty", size)
        # assert list(dom.keys()) == list(range(0, len(dom))), f"Keys aren't
        # sequential? {dom} :: {ticker}"
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

    def deltaNeutralValidation(self, reqId: int, dnc: DeltaNeutralContract):
        pass

    def fundamentalData(self, reqId: int, data: str):
        self.response_bus.emit(reqId, data)

    def scannerParameters(self, xml: str):
        self.response_bus.emit("scannerParams", xml)

    def scannerData(self, reqId: int, scanData: list[ScanData]):
        dataList = self.subscriptions.get_by_request_id(reqId)

        if dataList is not None:
            dataList.subscription_bus.emit(scanData)

    def scannerDataEnd(self, reqId: int):
        dataList = self.subscriptions.get_by_request_id(reqId)
        if dataList is not None:
            self.endSubscription(dataList)

    def histogramData(self, reqId: int, items: list[HistogramData]):
        self.response_bus.emit(reqId, items)

    def securityDefinitionOptionParameter(self, reqId: int, optionChain: OptionChain):
        self.response_bus.emit(reqId, optionChain)

    def securityDefinitionOptionParameterEnd(self, reqId: int):
        self._endReq(reqId)

    def newsProviders(self, newsProviders: list[NewsProvider]):
        self.response_bus.emit("newsProviders", newsProviders)
        self._endReq("newsProviders")

    def tickNews(
        self,
        _reqId: int,
        newsTick: NewsTick,
    ):
        self.newsTicks.append(newsTick)
        self.ib.tickNewsEvent.emit(newsTick)

    def newsArticle(self, reqId: int, newsArticle:NewsArticle):
        self.response_bus.emit(reqId,newsArticle)

    def historicalNews(
        self, reqId: int, historicalNews: HistoricalNews
    ):
        self.response_bus.emit(reqId, historicalNews)

    def historicalNewsEnd(self, reqId, _hasMore: bool):
        self._endReq(reqId)

    def updateNewsBulletin(
        self, msgId: int, newsBulletin:NewsBulletin
    ):
        self.newsBulletins[msgId] = newsBulletin
        self.ib.newsBulletinEvent.emit(newsBulletin)

    def receiveFA(self, _faDataType: int, faXmlData: str):
        self.response_bus.emit("requestFA", faXmlData)
        self._endReq("requestFA")

    def replaceFAEnd(self, reqId:int,text:str):
        self._logger.info("Replace FA Response: %s, %s", reqId, text)
        
    def currentTime(self, time: int):
        dt = datetime.fromtimestamp(time, self.defaultTimezone)
        self.response_bus.emit("currentTime", dt)

    def currentTimeMili(self, time: int):
        dt = datetime.fromtimestamp(time / 1000, self.defaultTimezone)
        self.response_bus.emit("currentTimeMili", dt)

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
        schedule: HistoricalSchedule,
    ):
        self.response_bus.emit(reqId, schedule)

    def wshMetaData(self, reqId: int, dataJson: str):
        self.ib.wshMetaEvent.emit(dataJson)
        self._endReq(reqId, dataJson)

    def wshEventData(self, reqId: int, dataJson: str):
        self.ib.wshEvent.emit(dataJson)
        self._endReq(reqId, dataJson)

    def userInfo(self, reqId: int, whiteBrandingId: str):
        self.response_bus.emit(reqId, whiteBrandingId)

    def softDollarTiers(self, reqId: int, tiers: list[SoftDollarTier]):
        pass

    def familyCodes(self, familyCodes: list[FamilyCode]):
        pass

    def error(
        self,
        reqId: int,
        errorCode: int,
        errorString: str,
        advancedOrderRejectJson: str = "",
    ):
        self._logger.debug("IBKR API reqID: %s error: %s", reqId, errorString)
        # https://interactivebrokers.github.io/tws-api/message_codes.html
        # https://ibkrcampus.com/campus/ibkr-api-page/twsapi-doc/#api-error-codes
        isRequest = 0 < reqId <= self.ib.client._reqIdSeq or (
            isinstance(reqId, str) and reqId.startswith("marketRule")
        )

        trade = None

        # reqId is a local orderId, but is delivered as -1 if this is a
        # non-order-related error
        if reqId != -1:
            trade = self.trades.get_by_object_id((self.clientId, reqId))

        # Warnings are currently:
        # 105 - Order being modified does not match the original order. (?)
        # 110 - The price does not conform to the minimum price variation for this
        # contract.
        # 165 - Historical market Data Service query message.
        # 321 - Server error when validating an API client request.
        # 329 - Order modify failed. Cannot change to the new order type.
        # 399 - Order message error
        # 404 -	Shares for this order are not immediately available for short sale. The
        # order will be held while we attempt to locate the shares.
        # 434 -	The order size cannot be zero.
        # 492 - ? not listed
        # 10167 ? not listed
        # Note: error 321 means error validing, but if the message is the result of a
        # MODIFY, the order _is still live_ and we must not delete it.
        # TODO: investigate if error 321 happens on _new_ order placement with
        # incorrect parameters too, then we should probably delete the order.

        # Previously this was included as a Warning condition, but 202 is literally
        # "Order Canceled" error status, so now it is an order-delete error:
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
        # get contract
        if reqId in self.subscriptions:
            subscription = self.subscriptions.get_by_request_id(reqId)
            contract = getattr(subscription, "contract", None)
        elif reqId in self.tickers:
            ticker = self.tickers.get_by_request_id(reqId)
            contract = getattr(ticker, "contract", None)
        else:
            contract = None
        if contract:
            msg += f", contract: {contract}"

        if isWarning:
            # Record warnings into the trade object, but unlike the _error_ case,
            # DO NOT delete the trade object because the order is STILL LIVE at the
            # broker.
            if trade:
                status = trade.orderStatus.status = OrderStatus.ValidationError
                logEntry = TradeLogEntry(self.lastTime, status, msg, errorCode)
                trade.log.append(logEntry)
                self._logger.warning(f"IBKR API validation warning: {trade}")
                self.ib.orderStatusEvent.emit(trade)
                trade.statusEvent.emit(trade)
            else:
                # else, this is a non-trade-related warning message
                if isRequest:
                    # It's a new eventkit-based request. Emit the error on the
                    # response_bus. The pipeline is responsible for raising it.
                    if self.ib.RaiseRequestErrors:
                        error = RequestError(reqId, errorCode, errorString)
                        self.response_bus.emit(reqId, error)
                    else:
                        # a None will be interpreted as an empty result
                        self._logger.error("is request %s, %s", reqId, msg)
                        self.response_bus.emit(reqId, None)
                self._logger.info(msg)
        else:
            self._logger.error(msg)
            if isRequest:
                # It's a new eventkit-based request. Emit the error on the
                # response_bus. The pipeline is responsible for raising it.
                if self.ib.RaiseRequestErrors:
                    error = RequestError(reqId, errorCode, errorString)
                    self.response_bus.emit(reqId, error)
                else:
                    # a None will be interpreted as an empty result
                    self.response_bus.emit(reqId, None)
            elif trade:
                # something is wrong with the order, cancel it
                if advancedOrderRejectJson:
                    trade.advancedError = advancedOrderRejectJson

                # Errors can mean two things:
                #  - new order is REJECTED
                #  - existing order is server-canceled (DAY orders, margin problems)
                #  - modification to *existing* order just has an update error, but the
                # order is STILL LIVE
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
            dataList = self.subscriptions.get_by_request_id(reqId)
            if dataList:
                dataList.clear()
                dataList.updateEvent.emit(dataList)
        elif errorCode == 317:
            # Market depth data has been RESET
            ticker = self.tickers.get_by_request_id(reqId)
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
            bars = self.subscriptions.get_by_request_id(reqId)
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
