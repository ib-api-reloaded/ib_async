"""Socket client for communicating with Interactive Brokers."""

import asyncio
import io
import logging
import math
import struct
import time
from collections import deque
from collections.abc import Callable
from typing import Any, Final

from eventkit import Event

from . import _pb_msgids as _M
from ._pb_msgids import (
    MIN_SERVER_VER_PROTOBUF,
    PROTOBUF_MSG_ID,
    PROTOBUF_MSG_IDS,
)
from ._server_versions import (
    MIN_SERVER_VER_ADVANCED_ORDER_REJECT,
    MIN_SERVER_VER_AUTO_CANCEL_PARENT,
    MIN_SERVER_VER_CME_TAGGING_FIELDS,
    MIN_SERVER_VER_CUSTOMER_ACCOUNT,
    MIN_SERVER_VER_DURATION,
    MIN_SERVER_VER_IMBALANCE_ONLY,
    MIN_SERVER_VER_INCLUDE_OVERNIGHT,
    MIN_SERVER_VER_MANUAL_ORDER_TIME,
    MIN_SERVER_VER_MANUAL_ORDER_TIME_EXERCISE_OPTIONS,
    MIN_SERVER_VER_PARAMETRIZED_DAYS_OF_EXECUTIONS,
    MIN_SERVER_VER_PEGBEST_PEGMID_OFFSETS,
    MIN_SERVER_VER_POST_TO_ATS,
    MIN_SERVER_VER_PROFESSIONAL_CUSTOMER,
    MIN_SERVER_VER_RFQ_FIELDS,
    MIN_SERVER_VER_UNDO_RFQ_FIELDS,
)
from .connection import Connection
from .contract import Contract
from .decoder import Decoder
from .objects import ConnectionStats, WshEventData
from .util import UNSET_DOUBLE, UNSET_INTEGER, dataclassAsTuple, getLoop, run


def _make_format_handlers(makeEmpty: bool) -> dict[Any, Callable[[Any], str]]:
    """Build the IBKR-protocol field-format handler table.

    The two module-level dict instances below
    (``_FORMAT_HANDLERS_EMPTY`` / ``_FORMAT_HANDLERS_KEEP``) are
    constructed once at import time; ``Client.send`` selects between
    them by the ``makeEmpty`` flag instead of rebuilding the dict
    (and its closures) on every outbound message.
    """
    # fmt: off
    return {
        # Contracts are formatted in IBKR null delimiter format
        Contract: lambda c: "\0".join([
            str(f)
            for f in (
                c.conId,
                c.symbol,
                c.secType,
                c.lastTradeDateOrContractMonth,
                c.strike,
                c.right,
                c.multiplier,
                c.exchange,
                c.primaryExchange,
                c.currency,
                c.localSymbol,
                c.tradingClass,
            )
        ]),

        # Float conversion has 3 stages:
        #  - Convert 'IBKR unset' double to empty (if requested)
        #  - Convert infinity to 'Infinite' string (if appropriate)
        #  - else, convert float to string normally
        float: lambda f: ""
        if (makeEmpty and f == UNSET_DOUBLE)
        else ("Infinite" if (f == math.inf) else str(f)),

        # Int conversion has 2 stages:
        #  - Convert 'IBKR unset' to empty (if requested)
        #  - else, convert int to string normally
        int: lambda f: "" if makeEmpty and f == UNSET_INTEGER else str(f),

        # None is always just an empty string.
        # (due to a quirk of Python, 'type(None)' is how you properly generate the NoneType value)
        type(None): lambda _: "",

        # Strings are always strings
        str: lambda s: s,

        # Bools become strings "1" or "0"
        bool: lambda b: "1" if b else "0",

        # Lists of tags become semicolon-appended KV pairs
        list: lambda lst: "".join([f"{v.tag}={v.value};" for v in lst]),
    }
    # fmt: on


_FORMAT_HANDLERS_EMPTY: Final[dict[Any, Callable[[Any], str]]] = _make_format_handlers(
    makeEmpty=True
)
_FORMAT_HANDLERS_KEEP: Final[dict[Any, Callable[[Any], str]]] = _make_format_handlers(
    makeEmpty=False
)


class Client:
    """
    Replacement for ``ibapi.client.EClient`` that uses asyncio.

    The client is fully asynchronous and has its own
    event-driven networking code that replaces the
    networking code of the standard EClient.
    It also replaces the infinite loop of ``EClient.run()``
    with the asyncio event loop. It can be used as a drop-in
    replacement for the standard EClient as provided by IBAPI.

    Compared to the standard EClient this client has the following
    additional features:

    * ``client.connect()`` will block until the client is ready to
      serve requests; It is not necessary to wait for ``nextValidId``
      to start requests as the client has already done that.
      The reqId is directly available with :py:meth:`.getReqId()`.

    * ``client.connectAsync()`` is a coroutine for connecting asynchronously.

    * When blocking, ``client.connect()`` can be made to time out with
      the timeout parameter (default 2 seconds).

    * Optional ``wrapper.priceSizeTick(reqId, tickType, price, size)`` that
      combines price and size instead of the two wrapper methods
      priceTick and sizeTick.

    * Automatic request throttling.

    * Optional ``wrapper.tcpDataArrived()`` method;
      If the wrapper has this method it is invoked directly after
      a network packet has arrived.
      A possible use is to timestamp all data in the packet with
      the exact same time.

    * Optional ``wrapper.tcpDataProcessed()`` method;
      If the wrapper has this method it is invoked after the
      network packet's data has been handled.
      A possible use is to write or evaluate the newly arrived data in
      one batch instead of item by item.

    Parameters:
      MaxRequests (int):
        Throttle the number of requests to ``MaxRequests`` per
        ``RequestsInterval`` seconds. Set to 0 to disable throttling.
      RequestsInterval (float):
        Time interval (in seconds) for request throttling.
      MinClientVersion (int):
        Client protocol version.
      MaxClientVersion (int):
        Client protocol version.

    Events:
      * ``apiStart`` ()
      * ``apiEnd`` ()
      * ``apiError`` (errorMsg: str)
      * ``throttleStart`` ()
      * ``throttleEnd`` ()
    """

    events = ("apiStart", "apiEnd", "apiError", "throttleStart", "throttleEnd")

    MaxRequests = 45
    RequestsInterval = 1

    MinClientVersion = 157
    MaxClientVersion = 178

    DISCONNECTED, CONNECTING, CONNECTED = range(3)

    def __init__(self, wrapper):
        self.wrapper = wrapper
        self.decoder = Decoder(wrapper, 0)
        self.apiStart = Event("apiStart")
        self.apiEnd = Event("apiEnd")
        self.apiError = Event("apiError")
        self.throttleStart = Event("throttleStart")
        self.throttleEnd = Event("throttleEnd")
        self._logger = logging.getLogger("ib_async.client")

        self.conn = Connection()
        self.conn.hasData += self._onSocketHasData
        self.conn.disconnected += self._onSocketDisconnected

        # extra optional wrapper methods
        self._priceSizeTick = getattr(wrapper, "priceSizeTick", None)
        self._tcpDataArrived = getattr(wrapper, "tcpDataArrived", None)
        self._tcpDataProcessed = getattr(wrapper, "tcpDataProcessed", None)

        self.host = ""
        self.port = -1
        self.clientId = -1
        self.optCapab = ""
        self.connectOptions = b""
        self.reset()

    def reset(self):
        self.connState = Client.DISCONNECTED
        self._apiReady = False
        self._serverVersion = 0
        self._data = b""
        self._hasReqId = False
        self._reqIdSeq = 0
        self._accounts = []
        self._startTime = time.time()
        self._numBytesRecv = 0
        self._numMsgRecv = 0
        self._isThrottling = False
        self._msgQ: deque[str] = deque()
        self._timeQ: deque[float] = deque()

    def serverVersion(self) -> int:
        return self._serverVersion

    def useProtoBuf(self, canonicalMsgId: int) -> bool:
        """True when ``canonicalMsgId`` should be sent as protobuf.

        Consults the ``PROTOBUF_MSG_IDS`` per-message gate table mirrored
        from IBKR's reference. Messages not in the table (and connections
        below the per-family minimum server version) stay on the legacy
        binary path.
        """
        gate = PROTOBUF_MSG_IDS.get(canonicalMsgId)
        if gate is None:
            return False
        return self._serverVersion >= gate

    def sendProto(self, canonicalMsgId: int, serialized: bytes) -> None:
        """Send a protobuf-framed message.

        Wire framing matches IBKR ``ibapi/comm.py:make_msg_proto``:
        4-byte big-endian length prefix, then 4-byte big-endian wire
        ``msgId = canonical + PROTOBUF_MSG_ID``, then the serialized
        protobuf body. Receivers detect the +200 sentinel and route to
        the protobuf decoder; everything else stays binary.
        """
        wireMsgId = canonicalMsgId + PROTOBUF_MSG_ID
        body = struct.pack(">I", wireMsgId) + serialized
        self.conn.sendMsg(self._prefix(body))

    def run(self):
        loop = getLoop()
        loop.run_forever()

    def isConnected(self):
        return self.connState == Client.CONNECTED

    def isReady(self) -> bool:
        """Is the API connection up and running?"""
        return self._apiReady

    def connectionStats(self) -> ConnectionStats:
        """Get statistics about the connection."""
        if not self.isReady():
            raise ConnectionError("Not connected")

        return ConnectionStats(
            self._startTime,
            time.time() - self._startTime,
            self._numBytesRecv,
            self.conn.numBytesSent,
            self._numMsgRecv,
            self.conn.numMsgSent,
        )

    def getReqId(self) -> int:
        """Get new request ID."""
        if not self.isReady():
            raise ConnectionError("Not connected")

        newId = self._reqIdSeq
        self._reqIdSeq += 1
        return newId

    def updateReqId(self, minReqId):
        """Update the next reqId to be at least ``minReqId``."""
        self._reqIdSeq = max(self._reqIdSeq, minReqId)

    def getAccounts(self) -> list[str]:
        """Get the list of account names that are under management."""
        if not self.isReady():
            raise ConnectionError("Not connected")
        return self._accounts

    def setConnectOptions(self, connectOptions: str):
        """
        Set additional connect options.

        Args:
            connectOptions: Use "+PACEAPI" to use request-pacing built
                into TWS/gateway 974+ (obsolete).
        """
        self.connectOptions = connectOptions.encode()

    def connect(self, host: str, port: int, clientId: int, timeout: float | None = 2.0):
        """
        Connect to a running TWS or IB gateway application.

        Args:
            host: Host name or IP address.
            port: Port number.
            clientId: ID number to use for this client; must be unique per
                connection.
            timeout: If establishing the connection takes longer than
                ``timeout`` seconds then the ``asyncio.TimeoutError`` exception
                is raised. Set to 0 to disable timeout.
        """
        run(self.connectAsync(host, port, clientId, timeout))

    async def connectAsync(self, host, port, clientId, timeout=2.0):
        try:
            self._logger.info(
                f"Connecting to {host}:{port} with clientId {clientId}..."
            )
            self.host = host
            self.port = int(port)
            self.clientId = int(clientId)
            self.connState = Client.CONNECTING
            timeout = timeout or None
            await asyncio.wait_for(self.conn.connectAsync(host, port), timeout)
            self._logger.info("Connected")
            msg = b"API\0" + self._prefix(
                b"v%d..%d%s"
                % (
                    self.MinClientVersion,
                    self.MaxClientVersion,
                    b" " + self.connectOptions if self.connectOptions else b"",
                )
            )
            self.conn.sendMsg(msg)
            await asyncio.wait_for(self.apiStart, timeout)
            self._logger.info("API connection ready")
        except BaseException as e:
            self.disconnect()
            msg = f"API connection failed: {e!r}"
            self._logger.error(msg)
            self.apiError.emit(msg)
            if isinstance(e, ConnectionRefusedError):
                self._logger.error("Make sure API port on TWS/IBG is open")
            raise

    def disconnect(self):
        """Disconnect from IB connection."""
        self._logger.info("Disconnecting")
        self.connState = Client.DISCONNECTED
        self.conn.disconnect()
        self.reset()

    def send(self, *fields, makeEmpty=True):
        """Serialize and send the given fields using the IB socket protocol.

        if 'makeEmpty' is True (default), then the IBKR values representing "no value"
        become the empty string."""
        if not self.isConnected():
            raise ConnectionError("Not connected")

        # The two handler dicts are built once at module import — see
        # ``_make_format_handlers`` above for the full table including
        # the per-type lambdas and their inline rationales.
        FORMAT_HANDLERS = _FORMAT_HANDLERS_EMPTY if makeEmpty else _FORMAT_HANDLERS_KEEP

        # start of new message
        msg = io.StringIO()

        for field in fields:
            # Fetch type converter for this field (falls back to 'str(field)' as a default for unmatched types)
            # (extra `isinstance()` wrapper needed here because Contract subclasses are their own type, but we want
            #  to only match against the Contract parent class for formatting operations)
            convert = FORMAT_HANDLERS.get(
                Contract if isinstance(field, Contract) else type(field), str
            )

            # Convert field to IBKR protocol string part
            s = convert(field)

            # Append converted IBKR protocol string to message buffer
            msg.write(s)
            msg.write("\0")

        generated = msg.getvalue()
        self.sendMsg(generated)

    def sendMsg(self, msg: str):
        loop = getLoop()
        t = loop.time()
        times = self._timeQ
        msgs = self._msgQ
        while times and t - times[0] > self.RequestsInterval:
            times.popleft()

        if msg:
            msgs.append(msg)

        while msgs and (len(times) < self.MaxRequests or not self.MaxRequests):
            msg = msgs.popleft()
            self.conn.sendMsg(self._prefix(msg.encode()))
            times.append(t)
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(">>> %s", msg[:-1].replace("\0", ","))

        if msgs:
            if not self._isThrottling:
                self._isThrottling = True
                self.throttleStart.emit()
                self._logger.debug("Started to throttle requests")
            loop.call_at(times[0] + self.RequestsInterval, self.sendMsg, None)
        else:
            if self._isThrottling:
                self._isThrottling = False
                self.throttleEnd.emit()
                self._logger.debug("Stopped to throttle requests")

    def _prefix(self, msg):
        # prefix a message with its length
        return struct.pack(">I", len(msg)) + msg

    def _onSocketHasData(self, data):
        debug = self._logger.isEnabledFor(logging.DEBUG)
        if self._tcpDataArrived:
            self._tcpDataArrived()

        self._data += data
        self._numBytesRecv += len(data)

        while True:
            if len(self._data) <= 4:
                break

            # 4 byte prefix tells the message length
            msgEnd = 4 + struct.unpack(">I", self._data[:4])[0]
            if len(self._data) < msgEnd:
                # insufficient data for now
                break

            body = self._data[4:msgEnd]
            self._data = self._data[msgEnd:]
            self._numMsgRecv += 1

            # Wire framing depends on server version and the +200 sentinel.
            # Pre-handshake and legacy (<201) servers use NUL-separated
            # text. From 201 onwards the body opens with a 4-byte big-endian
            # wire msgId; if that wire msgId is greater than the protobuf
            # sentinel (200) the body is a protobuf payload, otherwise it
            # is a binary frame with the new 4-byte msgId framing.
            if self._serverVersion >= MIN_SERVER_VER_PROTOBUF:
                wireMsgId = struct.unpack(">I", body[:4])[0]
                payload = body[4:]
                if wireMsgId > PROTOBUF_MSG_ID:
                    canonicalMsgId = wireMsgId - PROTOBUF_MSG_ID
                    if debug:
                        self._logger.debug(
                            "<<< proto %d, %d bytes", canonicalMsgId, len(payload)
                        )
                    self.decoder.processProtoBuf(canonicalMsgId, payload)
                    continue
                fields = [
                    str(wireMsgId),
                    *payload.decode(errors="backslashreplace").split("\0"),
                ]
                fields.pop()
            else:
                fields = body.decode(errors="backslashreplace").split("\0")
                fields.pop()

            if debug:
                self._logger.debug("<<< %s", ",".join(fields))

            if not self._serverVersion and len(fields) == 2:
                # this concludes the handshake
                version, _connTime = fields
                self._serverVersion = int(version)
                if self._serverVersion < self.MinClientVersion:
                    self._onSocketDisconnected("TWS/gateway version must be >= 972")
                    return
                self.decoder.serverVersion = self._serverVersion
                self.connState = Client.CONNECTED
                self.startApi()
                self.wrapper.connectAck()
                self._logger.info(f"Logged on to server version {self._serverVersion}")
            else:
                if not self._apiReady:
                    # snoop for nextValidId and managedAccounts response,
                    # when both are in then the client is ready
                    msgId = int(fields[0])
                    if msgId == 9:
                        _, _, validId = fields
                        self.updateReqId(int(validId))
                        self._hasReqId = True
                    elif msgId == 15:
                        _, _, accts = fields
                        self._accounts = [a for a in accts.split(",") if a]
                    if self._hasReqId and self._accounts:
                        self._apiReady = True
                        self.apiStart.emit()

                # decode and handle the message
                self.decoder.interpret(fields)

        if self._tcpDataProcessed:
            self._tcpDataProcessed()

    def _onSocketDisconnected(self, msg):
        wasReady = self.isReady()
        if not self.isConnected():
            self._logger.info("Disconnected.")
        elif not msg:
            msg = "Peer closed connection."
            if not wasReady:
                msg += f" clientId {self.clientId} already in use?"

        if msg:
            self._logger.error(msg)
            self.apiError.emit(msg)

        # ``connectionClosed`` is the single teardown path: it fails
        # every in-flight request, closes every Subscription, sets done
        # on per-subscriber and per-trade events, and resets wrapper
        # state. We only call it when the API was actually ready —
        # before that, no requests, subscriptions, or trades exist.
        if wasReady:
            self.wrapper.connectionClosed()

        self.reset()

        if wasReady:
            self.apiEnd.emit()

    # client request methods
    # the message type id is sent first, often followed by a version number

    def reqMktData(
        self,
        reqId,
        contract,
        genericTickList,
        snapshot,
        regulatorySnapshot,
        mktDataOptions,
    ):
        if self.useProtoBuf(_M.REQ_MKT_DATA):
            from ._proto.market_data import createMarketDataRequestProto

            self.sendProto(
                _M.REQ_MKT_DATA,
                createMarketDataRequestProto(
                    reqId, contract, genericTickList, snapshot, regulatorySnapshot
                ).SerializeToString(),
            )
            return
        fields = [1, 11, reqId, contract]

        if contract.secType == "BAG":
            legs = contract.comboLegs or []
            fields += [len(legs)]
            for leg in legs:
                fields += [leg.conId, leg.ratio, leg.action, leg.exchange]

        dnc = contract.deltaNeutralContract
        if dnc:
            fields += [True, dnc.conId, dnc.delta, dnc.price]
        else:
            fields += [False]

        fields += [genericTickList, snapshot, regulatorySnapshot, mktDataOptions]
        self.send(*fields)

    def cancelMktData(self, reqId):
        if self.useProtoBuf(_M.CANCEL_MKT_DATA):
            from ._proto.market_data import createCancelMarketDataProto

            self.sendProto(
                _M.CANCEL_MKT_DATA,
                createCancelMarketDataProto(reqId).SerializeToString(),
            )
            return
        self.send(2, 2, reqId)

    def placeOrder(self, orderId, contract, order):
        # On TWS / IB Gateway server versions that support protobuf for
        # placeOrder (gate 203), emit a ``PlaceOrderRequest`` proto and
        # return; binary fallback below preserves compatibility with
        # older servers. Per-msgId gating (not per-connection): a 207
        # server uses protobuf for orders but binary for historical
        # data, etc.
        if self.useProtoBuf(_M.PLACE_ORDER):
            from ._proto.orders import createPlaceOrderRequestProto

            proto = createPlaceOrderRequestProto(orderId, contract, order)
            self.sendProto(_M.PLACE_ORDER, proto.SerializeToString())
            return

        version = self.serverVersion()

        # IBKR API BUG FIX:
        # IBKR sometimes back-populates the 'volatility' field into live orders, but then if we try to
        # modify an order using cached order objects, IBKR rejects modifications because 'volatility'
        # is not allowed to be set (even though _they_ added it to our previously submitted order).
        # Solution: if an order is NOT a VOL order, delete the 'volatility' value to prevent this error.
        if not order.orderType.startswith("VOL"):
            # ONLY volatility orders can have 'volatility' set when sending API data.
            order.volatility = None

        # The IBKR API protocol is just a series of in-order arguments denoted by position.
        # The upstream API parses all fields based on the first value (the message type).
        fields = [
            3,  # PLACE_ORDER message type
            orderId,
            contract,
            contract.secIdType,
            contract.secId,
            order.action,
            order.totalQuantity,
            order.orderType,
            order.lmtPrice,
            order.auxPrice,
            order.tif,
            order.ocaGroup,
            order.account,
            order.openClose,
            order.origin,
            order.orderRef,
            order.transmit,
            order.parentId,
            order.blockOrder,
            order.sweepToFill,
            order.displaySize,
            order.triggerMethod,
            order.outsideRth,
            order.hidden,
        ]

        if contract.secType == "BAG":
            legs = contract.comboLegs or []
            fields += [len(legs)]
            for leg in legs:
                fields += [
                    leg.conId,
                    leg.ratio,
                    leg.action,
                    leg.exchange,
                    leg.openClose,
                    leg.shortSaleSlot,
                    leg.designatedLocation,
                    leg.exemptCode,
                ]

            legs = order.orderComboLegs or []
            fields += [len(legs)]
            for leg in legs:
                fields += [leg.price]

            params = order.smartComboRoutingParams or []
            fields += [len(params)]
            for param in params:
                fields += [param.tag, param.value]

        fields += [
            "",
            order.discretionaryAmt,
            order.goodAfterTime,
            order.goodTillDate,
            order.faGroup,
            order.faMethod,
            order.faPercentage,
        ]

        if version < 177:
            fields += [order.faProfile]

        fields += [
            order.modelCode,
            order.shortSaleSlot,
            order.designatedLocation,
            order.exemptCode,
            order.ocaType,
            order.rule80A,
            order.settlingFirm,
            order.allOrNone,
            order.minQty,
            order.percentOffset,
            order.eTradeOnly,  # always False
            order.firmQuoteOnly,  # always False
            order.nbboPriceCap,  # always UNSET
            order.auctionStrategy,
            order.startingPrice,
            order.stockRefPrice,
            order.delta,
            order.stockRangeLower,
            order.stockRangeUpper,
            order.overridePercentageConstraints,
            order.volatility,
            order.volatilityType,
            order.deltaNeutralOrderType,
            order.deltaNeutralAuxPrice,
        ]

        if order.deltaNeutralOrderType:
            fields += [
                order.deltaNeutralConId,
                order.deltaNeutralSettlingFirm,
                order.deltaNeutralClearingAccount,
                order.deltaNeutralClearingIntent,
                order.deltaNeutralOpenClose,
                order.deltaNeutralShortSale,
                order.deltaNeutralShortSaleSlot,
                order.deltaNeutralDesignatedLocation,
            ]

        fields += [
            order.continuousUpdate,
            order.referencePriceType,
            order.trailStopPrice,
            order.trailingPercent,
            order.scaleInitLevelSize,
            order.scaleSubsLevelSize,
            order.scalePriceIncrement,
        ]

        if 0 < order.scalePriceIncrement < UNSET_DOUBLE:
            fields += [
                order.scalePriceAdjustValue,
                order.scalePriceAdjustInterval,
                order.scaleProfitOffset,
                order.scaleAutoReset,
                order.scaleInitPosition,
                order.scaleInitFillQty,
                order.scaleRandomPercent,
            ]

        fields += [
            order.scaleTable,
            order.activeStartTime,
            order.activeStopTime,
            order.hedgeType,
        ]

        if order.hedgeType:
            fields += [order.hedgeParam]

        fields += [
            order.optOutSmartRouting,
            order.clearingAccount,
            order.clearingIntent,
            order.notHeld,
        ]

        dnc = contract.deltaNeutralContract
        if dnc:
            fields += [True, dnc.conId, dnc.delta, dnc.price]
        else:
            fields += [False]

        fields += [order.algoStrategy]
        if order.algoStrategy:
            params = order.algoParams or []
            fields += [len(params)]
            for param in params:
                fields += [param.tag, param.value]

        fields += [
            order.algoId,
            order.whatIf,
            order.orderMiscOptions,
            order.solicited,
            order.randomizeSize,
            order.randomizePrice,
        ]

        if order.orderType in {"PEG BENCH", "PEGBENCH"}:
            fields += [
                order.referenceContractId,
                order.isPeggedChangeAmountDecrease,
                order.peggedChangeAmount,
                order.referenceChangeAmount,
                order.referenceExchangeId,
            ]

        fields += [len(order.conditions)]
        if order.conditions:
            for cond in order.conditions:
                fields += dataclassAsTuple(cond)
            fields += [order.conditionsIgnoreRth, order.conditionsCancelOrder]

        fields += [
            order.adjustedOrderType,
            order.triggerPrice,
            order.lmtPriceOffset,
            order.adjustedStopPrice,
            order.adjustedStopLimitPrice,
            order.adjustedTrailingAmount,
            order.adjustableTrailingUnit,
            order.extOperator,
            order.softDollarTier.name,
            order.softDollarTier.val,
            order.cashQty,
            order.mifid2DecisionMaker,
            order.mifid2DecisionAlgo,
            order.mifid2ExecutionTrader,
            order.mifid2ExecutionAlgo,
            order.dontUseAutoPriceForHedge,
            order.isOmsContainer,
            order.discretionaryUpToLimitPrice,
            order.usePriceMgmtAlgo,
        ]

        if version >= MIN_SERVER_VER_DURATION:
            fields += [order.duration]

        if version >= MIN_SERVER_VER_POST_TO_ATS:
            fields += [order.postToAts]

        if version >= MIN_SERVER_VER_AUTO_CANCEL_PARENT:
            fields += [order.autoCancelParent]

        if version >= MIN_SERVER_VER_ADVANCED_ORDER_REJECT:
            fields += [order.advancedErrorOverride]

        if version >= MIN_SERVER_VER_MANUAL_ORDER_TIME:
            fields += [order.manualOrderTime]

        if version >= MIN_SERVER_VER_PEGBEST_PEGMID_OFFSETS:
            if contract.exchange == "IBKRATS":
                fields += [order.minTradeQty]
            if order.orderType in {"PEG BEST", "PEGBEST"}:
                fields += [order.minCompeteSize, order.competeAgainstBestOffset]
                if order.competeAgainstBestOffset == math.inf:
                    fields += [order.midOffsetAtWhole, order.midOffsetAtHalf]
            elif order.orderType in {"PEG MID", "PEGMID"}:
                fields += [order.midOffsetAtWhole, order.midOffsetAtHalf]

        # Gates 178+ — mirror IBKR ``client.py:placeOrder`` lines 2746-2763.
        # Fields not yet on our ``Order`` dataclass use ``getattr`` so the
        # writes are decoupled from the sibling task that adds them.

        if version >= MIN_SERVER_VER_CUSTOMER_ACCOUNT:
            fields += [getattr(order, "customerAccount", "")]

        if version >= MIN_SERVER_VER_PROFESSIONAL_CUSTOMER:
            fields += [getattr(order, "professionalCustomer", False)]

        # Interim 2-field RFQ block, written ONLY for servers in
        # [RFQ_FIELDS, UNDO_RFQ_FIELDS).  IBKR writes ``("", UNSET_INTEGER)``
        # — bondAccruedInterest plus a placeholder int.
        if MIN_SERVER_VER_RFQ_FIELDS <= version < MIN_SERVER_VER_UNDO_RFQ_FIELDS:
            fields += [getattr(order, "bondAccruedInterest", ""), UNSET_INTEGER]

        if version >= MIN_SERVER_VER_INCLUDE_OVERNIGHT:
            fields += [getattr(order, "includeOvernight", False)]

        if version >= MIN_SERVER_VER_CME_TAGGING_FIELDS:
            # ``manualOrderIndicator`` rides at gate 192; ``extOperator``
            # is gate 105 (EXT_OPERATOR) and is already written above as
            # part of the unconditional block — see IBKR ref line 2674.
            fields += [getattr(order, "manualOrderIndicator", UNSET_INTEGER)]

        if version >= MIN_SERVER_VER_IMBALANCE_ONLY:
            fields += [order.imbalanceOnly]

        self.send(*fields)

    def cancelOrder(self, orderId, orderCancel=None):
        # Accept either a fully-formed ``OrderCancel`` envelope or
        # ``None`` (= no CME-tagging fields). The legacy positional
        # ``manualCancelOrderTime: str`` form is supported for backwards
        # compatibility — a bare string promotes to an OrderCancel
        # carrying just that field.
        from .order import OrderCancel

        if orderCancel is None:
            orderCancel = OrderCancel()
        elif isinstance(orderCancel, str):
            orderCancel = OrderCancel(manualOrderCancelTime=orderCancel)

        if self.useProtoBuf(_M.CANCEL_ORDER):
            from ._proto.orders import createCancelOrderRequestProto

            proto = createCancelOrderRequestProto(
                orderId,
                manualOrderCancelTime=orderCancel.manualOrderCancelTime,
                extOperator=orderCancel.extOperator,
                manualOrderIndicator=orderCancel.manualOrderIndicator,
            )
            self.sendProto(_M.CANCEL_ORDER, proto.SerializeToString())
            return

        # Binary wire layout shifts at MIN_SERVER_VER_CME_TAGGING_FIELDS
        # (192): IBKR drops the legacy ``VERSION=1`` prefix and appends
        # ``extOperator`` + ``manualOrderIndicator``. There's also an
        # interim RFQ_FIELDS triplet on servers in [187, 190).
        fields: list[Any] = [4]
        if self.serverVersion() < MIN_SERVER_VER_CME_TAGGING_FIELDS:
            fields.append(1)  # legacy VERSION
        fields.append(orderId)
        if self.serverVersion() >= MIN_SERVER_VER_MANUAL_ORDER_TIME:
            fields.append(orderCancel.manualOrderCancelTime)
        if (
            MIN_SERVER_VER_RFQ_FIELDS
            <= self.serverVersion()
            < MIN_SERVER_VER_UNDO_RFQ_FIELDS
        ):
            fields += ["", "", UNSET_INTEGER]
        if self.serverVersion() >= MIN_SERVER_VER_CME_TAGGING_FIELDS:
            fields += [orderCancel.extOperator, orderCancel.manualOrderIndicator]
        self.send(*fields)

    def reqOpenOrders(self):
        if self.useProtoBuf(_M.REQ_OPEN_ORDERS):
            from ._proto.orders import createOpenOrdersRequestProto

            self.sendProto(
                _M.REQ_OPEN_ORDERS, createOpenOrdersRequestProto().SerializeToString()
            )
            return
        self.send(5, 1)

    def reqAccountUpdates(self, subscribe, acctCode):
        if self.useProtoBuf(_M.REQ_ACCT_DATA):
            from ._proto.accounts import createAccountDataRequestProto

            self.sendProto(
                _M.REQ_ACCT_DATA,
                createAccountDataRequestProto(subscribe, acctCode).SerializeToString(),
            )
            return
        self.send(6, 2, subscribe, acctCode)

    def reqExecutions(self, reqId, execFilter):
        if self.useProtoBuf(_M.REQ_EXECUTIONS):
            from ._proto.orders import createExecutionRequestProto

            proto = createExecutionRequestProto(reqId, execFilter)
            self.sendProto(_M.REQ_EXECUTIONS, proto.SerializeToString())
            return
        fields: list[Any] = [
            7,
            3,
            reqId,
            execFilter.clientId,
            execFilter.acctCode,
            execFilter.time,
            execFilter.symbol,
            execFilter.secType,
            execFilter.exchange,
            execFilter.side,
        ]
        # ``lastNDays`` and ``specificDates`` arrived at gate 200
        # (PARAMETRIZED_DAYS_OF_EXECUTIONS).  The dataclass fields don't
        # exist on ``ExecutionFilter`` yet — sibling task adds them —
        # so ``getattr`` keeps the wire write decoupled.
        if self.serverVersion() >= MIN_SERVER_VER_PARAMETRIZED_DAYS_OF_EXECUTIONS:
            fields += [getattr(execFilter, "lastNDays", UNSET_INTEGER)]
            specificDates = getattr(execFilter, "specificDates", None) or []
            fields += [len(specificDates)]
            for specificDate in specificDates:
                fields += [specificDate]
        self.send(*fields)

    def reqIds(self, numIds):
        self.send(8, 1, numIds)

    def reqContractDetails(self, reqId, contract):
        if self.useProtoBuf(_M.REQ_CONTRACT_DATA):
            from ._proto.contracts import createContractDataRequestProto

            proto = createContractDataRequestProto(reqId, contract)
            self.sendProto(_M.REQ_CONTRACT_DATA, proto.SerializeToString())
            return
        fields = [
            9,
            8,
            reqId,
            contract,
            contract.includeExpired,
            contract.secIdType,
            contract.secId,
        ]

        if self.serverVersion() >= 176:
            fields += [contract.issuerId]

        self.send(*fields)

    def reqMktDepth(self, reqId, contract, numRows, isSmartDepth, mktDepthOptions):
        if self.useProtoBuf(_M.REQ_MKT_DEPTH):
            from ._proto.market_data import createMarketDepthRequestProto

            self.sendProto(
                _M.REQ_MKT_DEPTH,
                createMarketDepthRequestProto(
                    reqId, contract, numRows, isSmartDepth
                ).SerializeToString(),
            )
            return
        self.send(
            10,
            5,
            reqId,
            contract.conId,
            contract.symbol,
            contract.secType,
            contract.lastTradeDateOrContractMonth,
            contract.strike,
            contract.right,
            contract.multiplier,
            contract.exchange,
            contract.primaryExchange,
            contract.currency,
            contract.localSymbol,
            contract.tradingClass,
            numRows,
            isSmartDepth,
            mktDepthOptions,
        )

    def cancelMktDepth(self, reqId, isSmartDepth):
        if self.useProtoBuf(_M.CANCEL_MKT_DEPTH):
            from ._proto.market_data import createCancelMarketDepthProto

            self.sendProto(
                _M.CANCEL_MKT_DEPTH,
                createCancelMarketDepthProto(reqId, isSmartDepth).SerializeToString(),
            )
            return
        self.send(11, 1, reqId, isSmartDepth)

    def reqNewsBulletins(self, allMsgs):
        if self.useProtoBuf(_M.REQ_NEWS_BULLETINS):
            from ._proto.news import createNewsBulletinsRequestProto

            self.sendProto(
                _M.REQ_NEWS_BULLETINS,
                createNewsBulletinsRequestProto(allMsgs).SerializeToString(),
            )
            return
        self.send(12, 1, allMsgs)

    def cancelNewsBulletins(self):
        if self.useProtoBuf(_M.CANCEL_NEWS_BULLETINS):
            from ._proto.news import createCancelNewsBulletinsProto

            self.sendProto(
                _M.CANCEL_NEWS_BULLETINS,
                createCancelNewsBulletinsProto().SerializeToString(),
            )
            return
        self.send(13, 1)

    def setServerLogLevel(self, logLevel):
        if self.useProtoBuf(_M.SET_SERVER_LOGLEVEL):
            from ._proto.rest import createSetServerLogLevelRequestProto

            self.sendProto(
                _M.SET_SERVER_LOGLEVEL,
                createSetServerLogLevelRequestProto(logLevel).SerializeToString(),
            )
            return
        self.send(14, 1, logLevel)

    def reqAutoOpenOrders(self, bAutoBind):
        if self.useProtoBuf(_M.REQ_AUTO_OPEN_ORDERS):
            from ._proto.orders import createAutoOpenOrdersRequestProto

            self.sendProto(
                _M.REQ_AUTO_OPEN_ORDERS,
                createAutoOpenOrdersRequestProto(bAutoBind).SerializeToString(),
            )
            return
        self.send(15, 1, bAutoBind)

    def reqAllOpenOrders(self):
        if self.useProtoBuf(_M.REQ_ALL_OPEN_ORDERS):
            from ._proto.orders import createAllOpenOrdersRequestProto

            self.sendProto(
                _M.REQ_ALL_OPEN_ORDERS,
                createAllOpenOrdersRequestProto().SerializeToString(),
            )
            return
        self.send(16, 1)

    def reqManagedAccts(self):
        if self.useProtoBuf(_M.REQ_MANAGED_ACCTS):
            from ._proto.accounts import createManagedAccountsRequestProto

            self.sendProto(
                _M.REQ_MANAGED_ACCTS,
                createManagedAccountsRequestProto().SerializeToString(),
            )
            return
        self.send(17, 1)

    def requestFA(self, faData):
        if self.useProtoBuf(_M.REQ_FA):
            from ._proto.accounts import createFARequestProto

            self.sendProto(_M.REQ_FA, createFARequestProto(faData).SerializeToString())
            return
        self.send(18, 1, faData)

    def replaceFA(self, reqId, faData, cxml):
        if self.useProtoBuf(_M.REPLACE_FA):
            from ._proto.accounts import createFAReplaceProto

            self.sendProto(
                _M.REPLACE_FA,
                createFAReplaceProto(reqId, faData, cxml).SerializeToString(),
            )
            return
        self.send(19, 1, faData, cxml, reqId)

    def reqHistoricalData(
        self,
        reqId,
        contract,
        endDateTime,
        durationStr,
        barSizeSetting,
        whatToShow,
        useRTH,
        formatDate,
        keepUpToDate,
        chartOptions,
    ):
        if self.useProtoBuf(_M.REQ_HISTORICAL_DATA):
            from ._proto.historical import createHistoricalDataRequestProto

            self.sendProto(
                _M.REQ_HISTORICAL_DATA,
                createHistoricalDataRequestProto(
                    reqId,
                    contract,
                    endDateTime,
                    durationStr,
                    barSizeSetting,
                    whatToShow,
                    useRTH,
                    formatDate,
                    keepUpToDate,
                ).SerializeToString(),
            )
            return
        fields = [
            20,
            reqId,
            contract,
            contract.includeExpired,
            endDateTime,
            barSizeSetting,
            durationStr,
            useRTH,
            whatToShow,
            formatDate,
        ]

        if contract.secType == "BAG":
            legs = contract.comboLegs or []
            fields += [len(legs)]
            for leg in legs:
                fields += [leg.conId, leg.ratio, leg.action, leg.exchange]

        fields += [keepUpToDate, chartOptions]
        self.send(*fields)

    def exerciseOptions(
        self,
        reqId,
        contract,
        exerciseAction,
        exerciseQuantity,
        account,
        override,
        manualOrderTime: str = "",
        customerAccount: str = "",
        professionalCustomer: bool = False,
    ):
        if self.useProtoBuf(_M.EXERCISE_OPTIONS):
            from ._proto.rest import createExerciseOptionsRequestProto

            self.sendProto(
                _M.EXERCISE_OPTIONS,
                createExerciseOptionsRequestProto(
                    reqId,
                    contract,
                    exerciseAction,
                    exerciseQuantity,
                    account,
                    override,
                    manualOrderTime=manualOrderTime,
                    customerAccount=customerAccount,
                    professionalCustomer=professionalCustomer,
                ).SerializeToString(),
            )
            return
        fields: list[Any] = [
            21,
            2,
            reqId,
            contract.conId,
            contract.symbol,
            contract.secType,
            contract.lastTradeDateOrContractMonth,
            contract.strike,
            contract.right,
            contract.multiplier,
            contract.exchange,
            contract.currency,
            contract.localSymbol,
            contract.tradingClass,
            exerciseAction,
            exerciseQuantity,
            account,
            override,
        ]
        # Gated trailers mirror IBKR ``client.py:exerciseOptions`` lines
        # 1775-1786.  Each field is only written when the connected
        # server actually understands it — sending an extra trailer to a
        # pre-180 server desyncs the wire frame.
        if self.serverVersion() >= MIN_SERVER_VER_MANUAL_ORDER_TIME_EXERCISE_OPTIONS:
            fields += [manualOrderTime]
        if self.serverVersion() >= MIN_SERVER_VER_CUSTOMER_ACCOUNT:
            fields += [customerAccount]
        if self.serverVersion() >= MIN_SERVER_VER_PROFESSIONAL_CUSTOMER:
            fields += [professionalCustomer]
        self.send(*fields)

    def reqScannerSubscription(
        self,
        reqId,
        subscription,
        scannerSubscriptionOptions,
        scannerSubscriptionFilterOptions,
    ):
        if self.useProtoBuf(_M.REQ_SCANNER_SUBSCRIPTION):
            from ._proto.scanner import createScannerSubscriptionRequestProto

            self.sendProto(
                _M.REQ_SCANNER_SUBSCRIPTION,
                createScannerSubscriptionRequestProto(
                    reqId, subscription
                ).SerializeToString(),
            )
            return
        sub = subscription
        self.send(
            22,
            reqId,
            sub.numberOfRows,
            sub.instrument,
            sub.locationCode,
            sub.scanCode,
            sub.abovePrice,
            sub.belowPrice,
            sub.aboveVolume,
            sub.marketCapAbove,
            sub.marketCapBelow,
            sub.moodyRatingAbove,
            sub.moodyRatingBelow,
            sub.spRatingAbove,
            sub.spRatingBelow,
            sub.maturityDateAbove,
            sub.maturityDateBelow,
            sub.couponRateAbove,
            sub.couponRateBelow,
            sub.excludeConvertible,
            sub.averageOptionVolumeAbove,
            sub.scannerSettingPairs,
            sub.stockTypeFilter,
            scannerSubscriptionFilterOptions,
            scannerSubscriptionOptions,
        )

    def cancelScannerSubscription(self, reqId):
        if self.useProtoBuf(_M.CANCEL_SCANNER_SUBSCRIPTION):
            from ._proto.scanner import createCancelScannerSubscriptionProto

            self.sendProto(
                _M.CANCEL_SCANNER_SUBSCRIPTION,
                createCancelScannerSubscriptionProto(reqId).SerializeToString(),
            )
            return
        self.send(23, 1, reqId)

    def reqScannerParameters(self):
        if self.useProtoBuf(_M.REQ_SCANNER_PARAMETERS):
            from ._proto.scanner import createScannerParametersRequestProto

            self.sendProto(
                _M.REQ_SCANNER_PARAMETERS,
                createScannerParametersRequestProto().SerializeToString(),
            )
            return
        self.send(24, 1)

    def cancelHistoricalData(self, reqId):
        if self.useProtoBuf(_M.CANCEL_HISTORICAL_DATA):
            from ._proto.historical import createCancelHistoricalDataProto

            self.sendProto(
                _M.CANCEL_HISTORICAL_DATA,
                createCancelHistoricalDataProto(reqId).SerializeToString(),
            )
            return
        self.send(25, 1, reqId)

    def reqCurrentTime(self):
        if self.useProtoBuf(_M.REQ_CURRENT_TIME):
            from ._proto.rest import createCurrentTimeRequestProto

            self.sendProto(
                _M.REQ_CURRENT_TIME,
                createCurrentTimeRequestProto().SerializeToString(),
            )
            return
        self.send(49, 1)

    def reqCurrentTimeInMillis(self):
        """Request the IBKR server clock in milliseconds. Protobuf only —
        no binary fallback (IBKR never shipped this on the legacy wire).

        Raises ``ValueError`` on servers below
        ``MIN_SERVER_VER_PROTOBUF_REST_MESSAGES_3`` (213). The wire
        frame would otherwise leave with the protobuf +200 sentinel
        for a server that has no idea what to do with it, leaving
        the awaiter wedged forever.
        """
        if not self.useProtoBuf(_M.REQ_CURRENT_TIME_IN_MILLIS):
            raise ValueError(
                "reqCurrentTimeInMillis requires TWS / IB Gateway server "
                "version >= 213 (protobuf REST messages); current server "
                f"version is {self._serverVersion}."
            )
        from ._proto.rest import createCurrentTimeInMillisRequestProto

        self.sendProto(
            _M.REQ_CURRENT_TIME_IN_MILLIS,
            createCurrentTimeInMillisRequestProto().SerializeToString(),
        )

    def reqRealTimeBars(
        self, reqId, contract, barSize, whatToShow, useRTH, realTimeBarsOptions
    ):
        if self.useProtoBuf(_M.REQ_REAL_TIME_BARS):
            from ._proto.historical import createRealTimeBarsRequestProto

            self.sendProto(
                _M.REQ_REAL_TIME_BARS,
                createRealTimeBarsRequestProto(
                    reqId, contract, barSize, whatToShow, useRTH
                ).SerializeToString(),
            )
            return
        self.send(
            50, 3, reqId, contract, barSize, whatToShow, useRTH, realTimeBarsOptions
        )

    def cancelRealTimeBars(self, reqId):
        if self.useProtoBuf(_M.CANCEL_REAL_TIME_BARS):
            from ._proto.historical import createCancelRealTimeBarsProto

            self.sendProto(
                _M.CANCEL_REAL_TIME_BARS,
                createCancelRealTimeBarsProto(reqId).SerializeToString(),
            )
            return
        self.send(51, 1, reqId)

    def reqFundamentalData(self, reqId, contract, reportType, fundamentalDataOptions):
        if self.useProtoBuf(_M.REQ_FUNDAMENTAL_DATA):
            from ._proto.scanner import createFundamentalsDataRequestProto

            self.sendProto(
                _M.REQ_FUNDAMENTAL_DATA,
                createFundamentalsDataRequestProto(
                    reqId, contract, reportType
                ).SerializeToString(),
            )
            return
        options = fundamentalDataOptions or []
        self.send(
            52,
            2,
            reqId,
            contract.conId,
            contract.symbol,
            contract.secType,
            contract.exchange,
            contract.primaryExchange,
            contract.currency,
            contract.localSymbol,
            reportType,
            len(options),
            options,
        )

    def cancelFundamentalData(self, reqId):
        if self.useProtoBuf(_M.CANCEL_FUNDAMENTAL_DATA):
            from ._proto.scanner import createCancelFundamentalsDataProto

            self.sendProto(
                _M.CANCEL_FUNDAMENTAL_DATA,
                createCancelFundamentalsDataProto(reqId).SerializeToString(),
            )
            return
        self.send(53, 1, reqId)

    def calculateImpliedVolatility(
        self, reqId, contract, optionPrice, underPrice, implVolOptions
    ):
        if self.useProtoBuf(_M.REQ_CALC_IMPLIED_VOLAT):
            from ._proto.rest import createCalculateImpliedVolatilityRequestProto

            self.sendProto(
                _M.REQ_CALC_IMPLIED_VOLAT,
                createCalculateImpliedVolatilityRequestProto(
                    reqId, contract, optionPrice, underPrice
                ).SerializeToString(),
            )
            return
        self.send(
            54,
            3,
            reqId,
            contract,
            optionPrice,
            underPrice,
            len(implVolOptions),
            implVolOptions,
        )

    def calculateOptionPrice(
        self, reqId, contract, volatility, underPrice, optPrcOptions
    ):
        if self.useProtoBuf(_M.REQ_CALC_OPTION_PRICE):
            from ._proto.rest import createCalculateOptionPriceRequestProto

            self.sendProto(
                _M.REQ_CALC_OPTION_PRICE,
                createCalculateOptionPriceRequestProto(
                    reqId, contract, volatility, underPrice
                ).SerializeToString(),
            )
            return
        self.send(
            55,
            3,
            reqId,
            contract,
            volatility,
            underPrice,
            len(optPrcOptions),
            optPrcOptions,
        )

    def cancelCalculateImpliedVolatility(self, reqId):
        if self.useProtoBuf(_M.CANCEL_CALC_IMPLIED_VOLAT):
            from ._proto.rest import createCancelCalculateImpliedVolatilityProto

            self.sendProto(
                _M.CANCEL_CALC_IMPLIED_VOLAT,
                createCancelCalculateImpliedVolatilityProto(reqId).SerializeToString(),
            )
            return
        self.send(56, 1, reqId)

    def cancelCalculateOptionPrice(self, reqId):
        if self.useProtoBuf(_M.CANCEL_CALC_OPTION_PRICE):
            from ._proto.rest import createCancelCalculateOptionPriceProto

            self.sendProto(
                _M.CANCEL_CALC_OPTION_PRICE,
                createCancelCalculateOptionPriceProto(reqId).SerializeToString(),
            )
            return
        self.send(57, 1, reqId)

    def reqGlobalCancel(self, orderCancel=None):
        from .order import OrderCancel

        if orderCancel is None:
            orderCancel = OrderCancel()

        if self.useProtoBuf(_M.REQ_GLOBAL_CANCEL):
            from ._proto.orders import createGlobalCancelRequestProto

            self.sendProto(
                _M.REQ_GLOBAL_CANCEL,
                createGlobalCancelRequestProto(
                    extOperator=orderCancel.extOperator,
                    manualOrderIndicator=orderCancel.manualOrderIndicator,
                ).SerializeToString(),
            )
            return

        # Binary wire layout: pre-192 carries VERSION=1 prefix; >=192
        # drops VERSION and appends extOperator + manualOrderIndicator.
        fields: list[Any] = [58]
        if self.serverVersion() < MIN_SERVER_VER_CME_TAGGING_FIELDS:
            fields.append(1)  # legacy VERSION
        if self.serverVersion() >= MIN_SERVER_VER_CME_TAGGING_FIELDS:
            fields += [orderCancel.extOperator, orderCancel.manualOrderIndicator]
        self.send(*fields)

    def reqMarketDataType(self, marketDataType):
        if self.useProtoBuf(_M.REQ_MARKET_DATA_TYPE):
            from ._proto.market_data import createMarketDataTypeRequestProto

            self.sendProto(
                _M.REQ_MARKET_DATA_TYPE,
                createMarketDataTypeRequestProto(marketDataType).SerializeToString(),
            )
            return
        self.send(59, 1, marketDataType)

    def reqPositions(self):
        if self.useProtoBuf(_M.REQ_POSITIONS):
            from ._proto.accounts import createPositionsRequestProto

            self.sendProto(
                _M.REQ_POSITIONS, createPositionsRequestProto().SerializeToString()
            )
            return
        self.send(61, 1)

    def reqAccountSummary(self, reqId, groupName, tags):
        if self.useProtoBuf(_M.REQ_ACCOUNT_SUMMARY):
            from ._proto.accounts import createAccountSummaryRequestProto

            self.sendProto(
                _M.REQ_ACCOUNT_SUMMARY,
                createAccountSummaryRequestProto(
                    reqId, groupName, tags
                ).SerializeToString(),
            )
            return
        self.send(62, 1, reqId, groupName, tags)

    def cancelAccountSummary(self, reqId):
        if self.useProtoBuf(_M.CANCEL_ACCOUNT_SUMMARY):
            from ._proto.accounts import createCancelAccountSummaryProto

            self.sendProto(
                _M.CANCEL_ACCOUNT_SUMMARY,
                createCancelAccountSummaryProto(reqId).SerializeToString(),
            )
            return
        self.send(63, 1, reqId)

    def cancelPositions(self):
        if self.useProtoBuf(_M.CANCEL_POSITIONS):
            from ._proto.accounts import createCancelPositionsProto

            self.sendProto(
                _M.CANCEL_POSITIONS,
                createCancelPositionsProto().SerializeToString(),
            )
            return
        self.send(64, 1)

    def verifyRequest(self, apiName, apiVersion):
        self.send(65, 1, apiName, apiVersion)

    def verifyMessage(self, apiData):
        self.send(66, 1, apiData)

    def queryDisplayGroups(self, reqId):
        self.send(67, 1, reqId)

    def subscribeToGroupEvents(self, reqId, groupId):
        self.send(68, 1, reqId, groupId)

    def updateDisplayGroup(self, reqId, contractInfo):
        self.send(69, 1, reqId, contractInfo)

    def unsubscribeFromGroupEvents(self, reqId):
        self.send(70, 1, reqId)

    def startApi(self):
        if self.useProtoBuf(_M.START_API):
            from ._proto.rest import createStartApiRequestProto

            self.sendProto(
                _M.START_API,
                createStartApiRequestProto(
                    self.clientId, self.optCapab
                ).SerializeToString(),
            )
            return
        self.send(71, 2, self.clientId, self.optCapab)

    def verifyAndAuthRequest(self, apiName, apiVersion, opaqueIsvKey):
        self.send(72, 1, apiName, apiVersion, opaqueIsvKey)

    def verifyAndAuthMessage(self, apiData, xyzResponse):
        self.send(73, 1, apiData, xyzResponse)

    def reqPositionsMulti(self, reqId, account, modelCode):
        if self.useProtoBuf(_M.REQ_POSITIONS_MULTI):
            from ._proto.accounts import createPositionsMultiRequestProto

            self.sendProto(
                _M.REQ_POSITIONS_MULTI,
                createPositionsMultiRequestProto(
                    reqId, account, modelCode
                ).SerializeToString(),
            )
            return
        self.send(74, 1, reqId, account, modelCode)

    def cancelPositionsMulti(self, reqId):
        if self.useProtoBuf(_M.CANCEL_POSITIONS_MULTI):
            from ._proto.accounts import createCancelPositionsMultiProto

            self.sendProto(
                _M.CANCEL_POSITIONS_MULTI,
                createCancelPositionsMultiProto(reqId).SerializeToString(),
            )
            return
        self.send(75, 1, reqId)

    def reqAccountUpdatesMulti(self, reqId, account, modelCode, ledgerAndNLV):
        if self.useProtoBuf(_M.REQ_ACCOUNT_UPDATES_MULTI):
            from ._proto.accounts import createAccountUpdatesMultiRequestProto

            self.sendProto(
                _M.REQ_ACCOUNT_UPDATES_MULTI,
                createAccountUpdatesMultiRequestProto(
                    reqId, account, modelCode, ledgerAndNLV
                ).SerializeToString(),
            )
            return
        self.send(76, 1, reqId, account, modelCode, ledgerAndNLV)

    def cancelAccountUpdatesMulti(self, reqId):
        if self.useProtoBuf(_M.CANCEL_ACCOUNT_UPDATES_MULTI):
            from ._proto.accounts import createCancelAccountUpdatesMultiProto

            self.sendProto(
                _M.CANCEL_ACCOUNT_UPDATES_MULTI,
                createCancelAccountUpdatesMultiProto(reqId).SerializeToString(),
            )
            return
        self.send(77, 1, reqId)

    def reqSecDefOptParams(
        self,
        reqId,
        underlyingSymbol,
        futFopExchange,
        underlyingSecType,
        underlyingConId,
    ):
        if self.useProtoBuf(_M.REQ_SEC_DEF_OPT_PARAMS):
            from ._proto.rest import createSecDefOptParamsRequestProto

            self.sendProto(
                _M.REQ_SEC_DEF_OPT_PARAMS,
                createSecDefOptParamsRequestProto(
                    reqId,
                    underlyingSymbol,
                    futFopExchange,
                    underlyingSecType,
                    underlyingConId,
                ).SerializeToString(),
            )
            return
        self.send(
            78,
            reqId,
            underlyingSymbol,
            futFopExchange,
            underlyingSecType,
            underlyingConId,
        )

    def reqSoftDollarTiers(self, reqId):
        if self.useProtoBuf(_M.REQ_SOFT_DOLLAR_TIERS):
            from ._proto.rest import createSoftDollarTiersRequestProto

            self.sendProto(
                _M.REQ_SOFT_DOLLAR_TIERS,
                createSoftDollarTiersRequestProto(reqId).SerializeToString(),
            )
            return
        self.send(79, reqId)

    def reqFamilyCodes(self):
        if self.useProtoBuf(_M.REQ_FAMILY_CODES):
            from ._proto.accounts import createFamilyCodesRequestProto

            self.sendProto(
                _M.REQ_FAMILY_CODES,
                createFamilyCodesRequestProto().SerializeToString(),
            )
            return
        self.send(80)

    def reqMatchingSymbols(self, reqId, pattern):
        if self.useProtoBuf(_M.REQ_MATCHING_SYMBOLS):
            from ._proto.rest import createMatchingSymbolsRequestProto

            self.sendProto(
                _M.REQ_MATCHING_SYMBOLS,
                createMatchingSymbolsRequestProto(reqId, pattern).SerializeToString(),
            )
            return
        self.send(81, reqId, pattern)

    def reqMktDepthExchanges(self):
        if self.useProtoBuf(_M.REQ_MKT_DEPTH_EXCHANGES):
            from ._proto.market_data import createMarketDepthExchangesRequestProto

            self.sendProto(
                _M.REQ_MKT_DEPTH_EXCHANGES,
                createMarketDepthExchangesRequestProto().SerializeToString(),
            )
            return
        self.send(82)

    def reqSmartComponents(self, reqId, bboExchange):
        if self.useProtoBuf(_M.REQ_SMART_COMPONENTS):
            from ._proto.rest import createSmartComponentsRequestProto

            self.sendProto(
                _M.REQ_SMART_COMPONENTS,
                createSmartComponentsRequestProto(
                    reqId, bboExchange
                ).SerializeToString(),
            )
            return
        self.send(83, reqId, bboExchange)

    def reqNewsArticle(self, reqId, providerCode, articleId, newsArticleOptions):
        if self.useProtoBuf(_M.REQ_NEWS_ARTICLE):
            from ._proto.news import createNewsArticleRequestProto

            self.sendProto(
                _M.REQ_NEWS_ARTICLE,
                createNewsArticleRequestProto(
                    reqId, providerCode, articleId
                ).SerializeToString(),
            )
            return
        self.send(84, reqId, providerCode, articleId, newsArticleOptions)

    def reqNewsProviders(self):
        if self.useProtoBuf(_M.REQ_NEWS_PROVIDERS):
            from ._proto.news import createNewsProvidersRequestProto

            self.sendProto(
                _M.REQ_NEWS_PROVIDERS,
                createNewsProvidersRequestProto().SerializeToString(),
            )
            return
        self.send(85)

    def reqHistoricalNews(
        self,
        reqId,
        conId,
        providerCodes,
        startDateTime,
        endDateTime,
        totalResults,
        historicalNewsOptions,
    ):
        if self.useProtoBuf(_M.REQ_HISTORICAL_NEWS):
            from ._proto.news import createHistoricalNewsRequestProto

            self.sendProto(
                _M.REQ_HISTORICAL_NEWS,
                createHistoricalNewsRequestProto(
                    reqId,
                    conId,
                    providerCodes,
                    startDateTime,
                    endDateTime,
                    totalResults,
                ).SerializeToString(),
            )
            return
        self.send(
            86,
            reqId,
            conId,
            providerCodes,
            startDateTime,
            endDateTime,
            totalResults,
            historicalNewsOptions,
        )

    def reqHeadTimeStamp(self, reqId, contract, whatToShow, useRTH, formatDate):
        if self.useProtoBuf(_M.REQ_HEAD_TIMESTAMP):
            from ._proto.historical import createHeadTimestampRequestProto

            self.sendProto(
                _M.REQ_HEAD_TIMESTAMP,
                createHeadTimestampRequestProto(
                    reqId, contract, useRTH, whatToShow, formatDate
                ).SerializeToString(),
            )
            return
        self.send(
            87, reqId, contract, contract.includeExpired, useRTH, whatToShow, formatDate
        )

    def reqHistogramData(self, tickerId, contract, useRTH, timePeriod):
        if self.useProtoBuf(_M.REQ_HISTOGRAM_DATA):
            from ._proto.historical import createHistogramDataRequestProto

            self.sendProto(
                _M.REQ_HISTOGRAM_DATA,
                createHistogramDataRequestProto(
                    tickerId, contract, bool(useRTH), timePeriod
                ).SerializeToString(),
            )
            return
        self.send(88, tickerId, contract, contract.includeExpired, useRTH, timePeriod)

    def cancelHistogramData(self, tickerId):
        if self.useProtoBuf(_M.CANCEL_HISTOGRAM_DATA):
            from ._proto.historical import createCancelHistogramDataProto

            self.sendProto(
                _M.CANCEL_HISTOGRAM_DATA,
                createCancelHistogramDataProto(tickerId).SerializeToString(),
            )
            return
        self.send(89, tickerId)

    def cancelHeadTimeStamp(self, reqId):
        if self.useProtoBuf(_M.CANCEL_HEAD_TIMESTAMP):
            from ._proto.historical import createCancelHeadTimestampProto

            self.sendProto(
                _M.CANCEL_HEAD_TIMESTAMP,
                createCancelHeadTimestampProto(reqId).SerializeToString(),
            )
            return
        self.send(90, reqId)

    def reqMarketRule(self, marketRuleId):
        if self.useProtoBuf(_M.REQ_MARKET_RULE):
            from ._proto.rest import createMarketRuleRequestProto

            self.sendProto(
                _M.REQ_MARKET_RULE,
                createMarketRuleRequestProto(marketRuleId).SerializeToString(),
            )
            return
        self.send(91, marketRuleId)

    def reqPnL(self, reqId, account, modelCode):
        if self.useProtoBuf(_M.REQ_PNL):
            from ._proto.scanner import createPnLRequestProto

            self.sendProto(
                _M.REQ_PNL,
                createPnLRequestProto(reqId, account, modelCode).SerializeToString(),
            )
            return
        self.send(92, reqId, account, modelCode)

    def cancelPnL(self, reqId):
        if self.useProtoBuf(_M.CANCEL_PNL):
            from ._proto.scanner import createCancelPnLProto

            self.sendProto(
                _M.CANCEL_PNL, createCancelPnLProto(reqId).SerializeToString()
            )
            return
        self.send(93, reqId)

    def reqPnLSingle(self, reqId, account, modelCode, conid):
        if self.useProtoBuf(_M.REQ_PNL_SINGLE):
            from ._proto.scanner import createPnLSingleRequestProto

            self.sendProto(
                _M.REQ_PNL_SINGLE,
                createPnLSingleRequestProto(
                    reqId, account, modelCode, conid
                ).SerializeToString(),
            )
            return
        self.send(94, reqId, account, modelCode, conid)

    def cancelPnLSingle(self, reqId):
        if self.useProtoBuf(_M.CANCEL_PNL_SINGLE):
            from ._proto.scanner import createCancelPnLSingleProto

            self.sendProto(
                _M.CANCEL_PNL_SINGLE,
                createCancelPnLSingleProto(reqId).SerializeToString(),
            )
            return
        self.send(95, reqId)

    def reqHistoricalTicks(
        self,
        reqId,
        contract,
        startDateTime,
        endDateTime,
        numberOfTicks,
        whatToShow,
        useRth,
        ignoreSize,
        miscOptions,
    ):
        if self.useProtoBuf(_M.REQ_HISTORICAL_TICKS):
            from ._proto.historical import createHistoricalTicksRequestProto

            self.sendProto(
                _M.REQ_HISTORICAL_TICKS,
                createHistoricalTicksRequestProto(
                    reqId,
                    contract,
                    startDateTime,
                    endDateTime,
                    numberOfTicks,
                    whatToShow,
                    useRth,
                    ignoreSize,
                ).SerializeToString(),
            )
            return
        self.send(
            96,
            reqId,
            contract,
            contract.includeExpired,
            startDateTime,
            endDateTime,
            numberOfTicks,
            whatToShow,
            useRth,
            ignoreSize,
            miscOptions,
        )

    def reqTickByTickData(self, reqId, contract, tickType, numberOfTicks, ignoreSize):
        if self.useProtoBuf(_M.REQ_TICK_BY_TICK_DATA):
            from ._proto.market_data import createTickByTickRequestProto

            self.sendProto(
                _M.REQ_TICK_BY_TICK_DATA,
                createTickByTickRequestProto(
                    reqId, contract, tickType, numberOfTicks, ignoreSize
                ).SerializeToString(),
            )
            return
        self.send(97, reqId, contract, tickType, numberOfTicks, ignoreSize)

    def cancelTickByTickData(self, reqId):
        if self.useProtoBuf(_M.CANCEL_TICK_BY_TICK_DATA):
            from ._proto.market_data import createCancelTickByTickProto

            self.sendProto(
                _M.CANCEL_TICK_BY_TICK_DATA,
                createCancelTickByTickProto(reqId).SerializeToString(),
            )
            return
        self.send(98, reqId)

    def reqCompletedOrders(self, apiOnly):
        if self.useProtoBuf(_M.REQ_COMPLETED_ORDERS):
            from ._proto.orders import createCompletedOrdersRequestProto

            self.sendProto(
                _M.REQ_COMPLETED_ORDERS,
                createCompletedOrdersRequestProto(apiOnly).SerializeToString(),
            )
            return
        self.send(99, apiOnly)

    def reqWshMetaData(self, reqId):
        if self.useProtoBuf(_M.REQ_WSH_META_DATA):
            from ._proto.news import createWshMetaDataRequestProto

            self.sendProto(
                _M.REQ_WSH_META_DATA,
                createWshMetaDataRequestProto(reqId).SerializeToString(),
            )
            return
        self.send(100, reqId)

    def cancelWshMetaData(self, reqId):
        if self.useProtoBuf(_M.CANCEL_WSH_META_DATA):
            from ._proto.news import createCancelWshMetaDataProto

            self.sendProto(
                _M.CANCEL_WSH_META_DATA,
                createCancelWshMetaDataProto(reqId).SerializeToString(),
            )
            return
        self.send(101, reqId)

    def reqWshEventData(self, reqId, data: WshEventData):
        if self.useProtoBuf(_M.REQ_WSH_EVENT_DATA):
            from ._proto.news import createWshEventDataRequestProto

            self.sendProto(
                _M.REQ_WSH_EVENT_DATA,
                createWshEventDataRequestProto(reqId, data).SerializeToString(),
            )
            return
        fields = [102, reqId, data.conId]
        if self.serverVersion() >= 171:
            fields += [
                data.filter,
                data.fillWatchlist,
                data.fillPortfolio,
                data.fillCompetitors,
            ]
        if self.serverVersion() >= 173:
            fields += [data.startDate, data.endDate, data.totalLimit]
        self.send(*fields, makeEmpty=False)

    def cancelWshEventData(self, reqId):
        if self.useProtoBuf(_M.CANCEL_WSH_EVENT_DATA):
            from ._proto.news import createCancelWshEventDataProto

            self.sendProto(
                _M.CANCEL_WSH_EVENT_DATA,
                createCancelWshEventDataProto(reqId).SerializeToString(),
            )
            return
        self.send(103, reqId)

    def reqUserInfo(self, reqId):
        if self.useProtoBuf(_M.REQ_USER_INFO):
            from ._proto.rest import createUserInfoRequestProto

            self.sendProto(
                _M.REQ_USER_INFO,
                createUserInfoRequestProto(reqId).SerializeToString(),
            )
            return
        self.send(104, reqId)
