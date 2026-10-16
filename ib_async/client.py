"""Socket client for communicating with Interactive Brokers."""

from __future__ import annotations

import asyncio
import io
import logging
import math
import struct
import time
from collections import deque
from collections.abc import Callable, Sequence
from decimal import Decimal

from eventkit import Event
from google.protobuf.message import Message

from . import _pb_msgids as _M
from . import _proto as _converters
from ._pb_msgids import (
    MIN_SERVER_VER_PROTOBUF,
    PROTOBUF_MSG_ID,
    PROTOBUF_MSG_IDS,
)
from ._server_versions import (
    MAX_CLIENT_VER,
    MIN_SERVER_VER_ADVANCED_ORDER_REJECT,
    MIN_SERVER_VER_AUTO_CANCEL_PARENT,
    MIN_SERVER_VER_CME_TAGGING_FIELDS,
    MIN_SERVER_VER_CUSTOMER_ACCOUNT,
    MIN_SERVER_VER_DURATION,
    MIN_SERVER_VER_FA_PROFILE_DESUPPORT,
    MIN_SERVER_VER_IMBALANCE_ONLY,
    MIN_SERVER_VER_INCLUDE_OVERNIGHT,
    MIN_SERVER_VER_MANUAL_ORDER_TIME,
    MIN_SERVER_VER_MANUAL_ORDER_TIME_EXERCISE_OPTIONS,
    MIN_SERVER_VER_PARAMETRIZED_DAYS_OF_EXECUTIONS,
    MIN_SERVER_VER_PEGBEST_PEGMID_OFFSETS,
    MIN_SERVER_VER_POST_TO_ATS,
    MIN_SERVER_VER_PROFESSIONAL_CUSTOMER,
    MIN_SERVER_VER_REPLACE_FA_END,
    MIN_SERVER_VER_RFQ_FIELDS,
    MIN_SERVER_VER_UNDO_RFQ_FIELDS,
)
from .connection import Connection
from .contract import Contract, TagValue
from .decoder import Decoder
from .objects import ConnectionStats, WshEventData
from .order import OrderCancel
from .util import UNSET_DOUBLE, UNSET_INTEGER, dataclassAsTuple, getLoop, run

# A value written as one field of a binary request message.
WireField = Contract | float | int | str | bool | Decimal | Sequence[TagValue] | None


def _formatContract(c: Contract) -> str:
    """Format a contract as its fields in IBKR's order, separated by NUL."""
    return "\0".join(
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
    )


def _formatField(field: WireField, makeEmpty: bool) -> str:
    """Return the wire text for one field of a binary message.

    With ``makeEmpty``, the IBKR unset values ``UNSET_INTEGER`` and
    ``UNSET_DOUBLE`` are written as the empty string. The server expects
    the empty string for an unset field. Without ``makeEmpty``, they are
    written unchanged. Positive infinity is written as ``Infinity``,
    which is the only spelling the server accepts. One example is
    ``competeAgainstBestOffset`` set to
    ``COMPETE_AGAINST_BEST_OFFSET_UP_TO_MID``. The checks use the exact
    type. A ``bool`` is written as ``1`` or ``0``, not as an ``int``. A
    ``Decimal`` is written with ``str``.
    """
    if isinstance(field, Contract):  # any Contract subclass
        return _formatContract(field)
    if type(field) is str:
        return field
    if type(field) is bool:
        return "1" if field else "0"
    if type(field) is int:
        return "" if makeEmpty and field == UNSET_INTEGER else str(field)
    if type(field) is float:
        if makeEmpty and field == UNSET_DOUBLE:
            return ""
        return "Infinity" if field == math.inf else str(field)
    if field is None:
        return ""
    if type(field) is list or type(field) is tuple:
        return "".join(f"{v.tag}={v.value};" for v in field)
    return str(field)


class Client:
    """
    The TWS API client, built on asyncio.

    The client is fully asynchronous, has its own event-driven
    networking code, and runs on the asyncio event loop.

    This client has the following features:

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

    # ``MaxClientVersion`` advertises the most-recent TWS / IB Gateway
    # server version this client knows how to talk to. The handshake at
    # ``connectAsync`` sends ``v{Min}..{Max}`` and the server picks the
    # min(server-max, our-max) at negotiation time. Bumping this MUST be
    # paired with patches to every send-side / receive-side gated field
    # at gates between the old cap and the new — see
    # ``ib_async/_server_versions.py`` for the symbolic gate constants.
    # As of v3.0 the binary path handles all gates 158-226 and the
    # protobuf path takes over per-message-family at 201-213.
    MinClientVersion = 157
    MaxClientVersion = MAX_CLIENT_VER

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
        self._msgQ: deque[bytes] = deque()
        self._timeQ: deque[float] = deque()

    def serverVersion(self) -> int:
        return self._serverVersion

    def useProtoBuf(self, canonicalMsgId: int) -> bool:
        """True when ``canonicalMsgId`` should be sent as protobuf.

        Consults the ``PROTOBUF_MSG_IDS`` per-message gate table. Messages
        not in the table (and connections below the per-family minimum
        server version) stay on the legacy binary path.
        """
        gate = PROTOBUF_MSG_IDS.get(canonicalMsgId)
        if gate is None:
            return False
        return self._serverVersion >= gate

    def sendProto(self, canonicalMsgId: int, serialized: bytes) -> None:
        """Send a protobuf-framed message.

        Wire framing: 4-byte big-endian length prefix, then 4-byte
        big-endian wire ``msgId = canonical + PROTOBUF_MSG_ID``, then the
        serialized protobuf body. Receivers detect the +200 sentinel and route to
        the protobuf decoder; everything else stays binary.

        Handed to ``sendMsg`` like every binary frame, so protobuf
        messages share the ONE outbound queue. Writing to ``conn``
        directly (as this did) put proto frames outside the
        ``MaxRequests`` / ``RequestsInterval`` pacing budget AND let
        them overtake binary frames already waiting in the queue — on a
        207+ gateway that is most of the session's traffic, including
        every order. Request order and the IBKR pacing contract are not
        optional for order messages.
        """
        wireMsgId = canonicalMsgId + PROTOBUF_MSG_ID
        body = struct.pack(">I", wireMsgId) + serialized
        self.sendMsg(body)

    def _tryProto(
        self, canonicalMsgId: int, build_proto: Callable[[], Message]
    ) -> bool:
        """Emit the protobuf-encoded frame for ``canonicalMsgId`` when the
        negotiated server supports it. Returns True when the proto path
        handled the send so callers can early-return; False when the caller
        must fall through to the binary path.

        ``build_proto`` is invoked only when the proto gate is open, which
        keeps the lazy ``from ._proto.XXX import ...`` deferred so older
        connections never pay the import cost.
        """
        if not self.useProtoBuf(canonicalMsgId):
            return False
        self.sendProto(canonicalMsgId, build_proto().SerializeToString())
        return True

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

    def setOptionalCapabilities(self, optCapab: str) -> None:
        """Set the optional capabilities string sent with ``startApi``.

        The value is included in the START_API frame (binary path field
        4 / proto ``optionalCapabilities``) and gated server-side by
        ``MIN_SERVER_VER_OPTIONAL_CAPABILITIES`` (=72). Our
        ``MinClientVersion`` is 157 so the gate is always satisfied.
        Must be called before ``connectAsync`` to take effect — the
        value is read inside ``startApi`` which fires once during the
        connection handshake.
        """
        self.optCapab = optCapab

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
        # Snapshot ``wasReady`` BEFORE ``reset()`` clears ``_apiReady`` so
        # that user-initiated disconnects fire ``wrapper.connectionClosed``
        # the same way peer-initiated disconnects do via
        # ``_onSocketDisconnected``. Without this, the asyncio
        # connection_lost callback runs after we've already reset, sees
        # ``isReady() == False``, and the teardown — failing in-flight
        # request futures, closing Subscriptions, ending Trades — never
        # runs on explicit ``IB.disconnect()``. ``_onSocketDisconnected``
        # still fires later but its ``wasReady`` snapshot is False so it
        # becomes a no-op (just logs "Disconnected.").
        wasReady = self.isReady()
        self.connState = Client.DISCONNECTED
        self.conn.disconnect()
        if wasReady:
            self.wrapper.connectionClosed()
        self.reset()
        if wasReady:
            self.apiEnd.emit()

    def send(self, *fields: WireField, makeEmpty: bool = True) -> None:
        """Serialize and send the given fields using the IB socket protocol.

        if 'makeEmpty' is True (default), then the IBKR values representing "no value"
        become the empty string."""
        if not self.isConnected():
            raise ConnectionError("Not connected")

        # First field is always the canonical msgId; remaining fields are
        # the body. Pre-201 servers receive both as NUL-terminated text;
        # 201+ servers receive a 4-byte big-endian raw msgId followed by
        # the NUL-terminated body. Sending the legacy text msgId to a 201+ server makes
        # the server fail to decode the frame and silently drop the
        # connection — every binary-path message (startApi, anything
        # that's not in PROTOBUF_MSG_IDS, anything below its proto gate)
        # is affected.
        msgId = fields[0]
        if not isinstance(msgId, int):
            raise TypeError(f"the first field is the message id, not {msgId!r}")
        body = io.StringIO()
        for field in fields[1:]:
            body.write(_formatField(field, makeEmpty))
            body.write("\0")

        text = body.getvalue().encode()
        if self._serverVersion >= MIN_SERVER_VER_PROTOBUF:
            generated = struct.pack(">I", int(msgId)) + text
        else:
            generated = (str(msgId) + "\0").encode() + text
        self.sendMsg(generated)

    def sendMsg(self, msg: bytes | None):
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
            self.conn.sendMsg(self._prefix(msg))
            times.append(t)
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(">>> %r", msg)

        if msgs:
            if not self._isThrottling:
                self._isThrottling = True
                self.throttleStart.emit()
                self._logger.debug("Started to throttle requests")
            loop.call_at(times[0] + self.RequestsInterval, self.sendMsg, None)
        elif self._isThrottling:
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
                    # The binary branch below snoops for ``nextValidId`` (9)
                    # and ``managedAccounts`` (15) to flip ``_apiReady`` and
                    # fire ``apiStart``. On a 207+ gateway TWS sends both of
                    # those via protobuf, so we need the same snoop here.
                    # The proto handlers run before this point, so
                    # ``wrapper.accounts`` is already populated for msgId 15.
                    # For msgId 9 we only need a boolean — ``updateReqId``
                    # itself happens inside ``wrapper.nextValidId``.
                    if not self._apiReady:
                        if canonicalMsgId == 9:
                            self._hasReqId = True
                        elif canonicalMsgId == 15:
                            self._accounts = list(self.wrapper.accounts)
                        if self._hasReqId and self._accounts:
                            self._apiReady = True
                            self.apiStart.emit()
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
        def _proto():
            return _converters.market_data.createMarketDataRequestProto(
                reqId,
                contract,
                genericTickList,
                snapshot,
                regulatorySnapshot,
                marketDataOptions=mktDataOptions,
            )

        if self._tryProto(_M.REQ_MKT_DATA, _proto):
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
        def _proto():
            return _converters.market_data.createCancelMarketDataProto(reqId)

        if self._tryProto(_M.CANCEL_MKT_DATA, _proto):
            return
        self.send(2, 2, reqId)

    def placeOrder(self, orderId, contract, order):
        # IBKR API BUG FIX (applies to BOTH binary and proto paths):
        # IBKR sometimes back-populates the 'volatility' field into live orders, but then if we try to
        # modify an order using cached order objects, IBKR rejects modifications because 'volatility'
        # is not allowed to be set (even though _they_ added it to our previously submitted order).
        # Solution: if an order is NOT a VOL order, reset 'volatility' to UNSET_DOUBLE so the proto
        # path's ``_isValidFloat`` guard skips the field and the binary path's float handler emits
        # an empty string. MUST run before the proto branch below — the proto path's
        # ``createOrderProto`` writes ``volatility`` whenever it differs from UNSET_DOUBLE, so
        # without this reset a TWS-populated value would ride out on every modify and the server
        # would reject it.
        if not order.orderType.startswith("VOL"):
            # ONLY volatility orders can have 'volatility' set when sending API
            # data. None is the v3 dialect's unset: the proto guard skips the
            # field and the binary handler emits an empty string — and the
            # operator-visible Order object never carries a sentinel float.
            order.volatility = None

        # On TWS / IB Gateway server versions that support protobuf for
        # placeOrder (gate 203), emit a ``PlaceOrderRequest`` proto and
        # return; binary fallback below preserves compatibility with
        # older servers. Per-msgId gating (not per-connection): a 207
        # server uses protobuf for orders but binary for historical
        # data, etc.
        def _proto():
            return _converters.orders.createPlaceOrderRequestProto(
                orderId, contract, order
            )

        if self._tryProto(_M.PLACE_ORDER, _proto):
            return

        version = self.serverVersion()

        # The IBKR API protocol is just a series of in-order arguments denoted by position.
        # The server parses all fields based on the first value (the message type).
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

        if (
            order.scalePriceIncrement is not None
            and 0 < order.scalePriceIncrement < UNSET_DOUBLE
        ):
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

        # Gates 178+.

        if version >= MIN_SERVER_VER_CUSTOMER_ACCOUNT:
            fields += [order.customerAccount]

        if version >= MIN_SERVER_VER_PROFESSIONAL_CUSTOMER:
            fields += [order.professionalCustomer]

        # Interim 2-field RFQ block, written ONLY for servers in
        # [RFQ_FIELDS, UNDO_RFQ_FIELDS).  IBKR writes ``("", UNSET_INTEGER)``
        # — bondAccruedInterest plus a placeholder int.
        if MIN_SERVER_VER_RFQ_FIELDS <= version < MIN_SERVER_VER_UNDO_RFQ_FIELDS:
            fields += [order.bondAccruedInterest, UNSET_INTEGER]

        if version >= MIN_SERVER_VER_INCLUDE_OVERNIGHT:
            fields += [order.includeOvernight]

        if version >= MIN_SERVER_VER_CME_TAGGING_FIELDS:
            # ``manualOrderIndicator`` rides at gate 192; ``extOperator``
            # is gate 105 (EXT_OPERATOR) and is already written above as
            # part of the unconditional block — see IBKR ref line 2674.
            fields += [order.manualOrderIndicator]

        if version >= MIN_SERVER_VER_IMBALANCE_ONLY:
            fields += [order.imbalanceOnly]

        self.send(*fields)

    def cancelOrder(self, orderId, orderCancel=None):
        # Accept either a fully-formed ``OrderCancel`` envelope or
        # ``None`` (= no CME-tagging fields). The legacy positional
        # ``manualCancelOrderTime: str`` form is supported for backwards
        # compatibility — a bare string promotes to an OrderCancel
        # carrying just that field.

        if orderCancel is None:
            orderCancel = OrderCancel()
        elif isinstance(orderCancel, str):
            orderCancel = OrderCancel(manualOrderCancelTime=orderCancel)

        def _proto():
            return _converters.orders.createCancelOrderRequestProto(
                orderId,
                manualOrderCancelTime=orderCancel.manualOrderCancelTime,
                extOperator=orderCancel.extOperator,
                manualOrderIndicator=orderCancel.manualOrderIndicator,
            )

        if self._tryProto(_M.CANCEL_ORDER, _proto):
            return

        # Binary wire layout shifts at MIN_SERVER_VER_CME_TAGGING_FIELDS
        # (192): IBKR drops the legacy ``VERSION=1`` prefix and appends
        # ``extOperator`` + ``manualOrderIndicator``. There's also an
        # interim RFQ_FIELDS triplet on servers in [187, 190).
        fields: list[WireField] = [4]
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
        def _proto():
            return _converters.orders.createOpenOrdersRequestProto()

        if self._tryProto(_M.REQ_OPEN_ORDERS, _proto):
            return
        self.send(5, 1)

    def reqAccountUpdates(self, subscribe, acctCode):
        def _proto():
            return _converters.accounts.createAccountDataRequestProto(
                subscribe, acctCode
            )

        if self._tryProto(_M.REQ_ACCT_DATA, _proto):
            return
        self.send(6, 2, subscribe, acctCode)

    def reqExecutions(self, reqId, execFilter):
        def _proto():
            return _converters.orders.createExecutionRequestProto(reqId, execFilter)

        if self._tryProto(_M.REQ_EXECUTIONS, _proto):
            return
        fields: list[WireField] = [
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
        # (PARAMETRIZED_DAYS_OF_EXECUTIONS).  ``getattr`` keeps the wire
        # write decoupled from the dataclass shape. ``lastNDays`` is
        # ``int | None`` on the public surface; the wire wants IBKR's
        # ``UNSET_INTEGER`` sentinel for "no filter" (the binary path's
        # format handler maps that sentinel to empty string under
        # ``makeEmpty``).
        if self.serverVersion() >= MIN_SERVER_VER_PARAMETRIZED_DAYS_OF_EXECUTIONS:
            lastNDays = getattr(execFilter, "lastNDays", None)
            fields += [lastNDays if lastNDays is not None else UNSET_INTEGER]
            specificDates = getattr(execFilter, "specificDates", None) or []
            fields += [len(specificDates)]
            for specificDate in specificDates:
                fields += [specificDate]
        self.send(*fields)

    def reqIds(self, numIds):
        self.send(8, 1, numIds)

    def reqContractDetails(self, reqId, contract):
        def _proto():
            return _converters.contracts.createContractDataRequestProto(reqId, contract)

        if self._tryProto(_M.REQ_CONTRACT_DATA, _proto):
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
        def _proto():
            return _converters.market_data.createMarketDepthRequestProto(
                reqId,
                contract,
                numRows,
                isSmartDepth,
                marketDepthOptions=mktDepthOptions,
            )

        if self._tryProto(_M.REQ_MKT_DEPTH, _proto):
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
        def _proto():
            return _converters.market_data.createCancelMarketDepthProto(
                reqId, isSmartDepth
            )

        if self._tryProto(_M.CANCEL_MKT_DEPTH, _proto):
            return
        self.send(11, 1, reqId, isSmartDepth)

    def reqNewsBulletins(self, allMsgs):
        def _proto():
            return _converters.news.createNewsBulletinsRequestProto(allMsgs)

        if self._tryProto(_M.REQ_NEWS_BULLETINS, _proto):
            return
        self.send(12, 1, allMsgs)

    def cancelNewsBulletins(self):
        def _proto():
            return _converters.news.createCancelNewsBulletinsProto()

        if self._tryProto(_M.CANCEL_NEWS_BULLETINS, _proto):
            return
        self.send(13, 1)

    def setServerLogLevel(self, logLevel):
        def _proto():
            return _converters.rest.createSetServerLogLevelRequestProto(logLevel)

        if self._tryProto(_M.SET_SERVER_LOGLEVEL, _proto):
            return
        self.send(14, 1, logLevel)

    def reqAutoOpenOrders(self, bAutoBind):
        def _proto():
            return _converters.orders.createAutoOpenOrdersRequestProto(bAutoBind)

        if self._tryProto(_M.REQ_AUTO_OPEN_ORDERS, _proto):
            return
        self.send(15, 1, bAutoBind)

    def reqAllOpenOrders(self):
        def _proto():
            return _converters.orders.createAllOpenOrdersRequestProto()

        if self._tryProto(_M.REQ_ALL_OPEN_ORDERS, _proto):
            return
        self.send(16, 1)

    def reqManagedAccts(self):
        def _proto():
            return _converters.accounts.createManagedAccountsRequestProto()

        if self._tryProto(_M.REQ_MANAGED_ACCTS, _proto):
            return
        self.send(17, 1)

    def requestFA(self, faData):
        # FA Profiles (faData == 2) were de-supported at server gate 177:
        # refuse the request here rather than send one no server answers.
        if (
            self.serverVersion() >= MIN_SERVER_VER_FA_PROFILE_DESUPPORT
            and int(faData) == 2
        ):
            raise ValueError(
                "FA profiles (faDataType 2) are not supported from server "
                f"version {MIN_SERVER_VER_FA_PROFILE_DESUPPORT}; this one is "
                f"{self.serverVersion()}"
            )

        def _proto():
            return _converters.accounts.createFARequestProto(faData)

        if self._tryProto(_M.REQ_FA, _proto):
            return
        self.send(18, 1, faData)

    def replaceFA(self, reqId, faData, cxml):
        # FA Profiles (faData == 2) were de-supported at server gate 177
        # (FA_PROFILE_DESUPPORT). Reject locally before sending.
        if (
            self.serverVersion() >= MIN_SERVER_VER_FA_PROFILE_DESUPPORT
            and int(faData) == 2
        ):
            return

        def _proto():
            return _converters.accounts.createFAReplaceProto(reqId, faData, cxml)

        if self._tryProto(_M.REPLACE_FA, _proto):
            return
        # The trailing ``reqId`` field only exists at server gate 157+
        # (REPLACE_FA_END). Sending it to a sub-157 server desyncs the
        # frame, so the write is gated.
        fields: list[WireField] = [19, 1, faData, cxml]
        if self.serverVersion() >= MIN_SERVER_VER_REPLACE_FA_END:
            fields.append(reqId)
        self.send(*fields)

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
        def _proto():
            return _converters.historical.createHistoricalDataRequestProto(
                reqId,
                contract,
                endDateTime,
                durationStr,
                barSizeSetting,
                whatToShow,
                useRTH,
                formatDate,
                keepUpToDate,
                chartOptions=chartOptions,
            )

        if self._tryProto(_M.REQ_HISTORICAL_DATA, _proto):
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
        def _proto():
            return _converters.rest.createExerciseOptionsRequestProto(
                reqId,
                contract,
                exerciseAction,
                exerciseQuantity,
                account,
                override,
                manualOrderTime=manualOrderTime,
                customerAccount=customerAccount,
                professionalCustomer=professionalCustomer,
            )

        if self._tryProto(_M.EXERCISE_OPTIONS, _proto):
            return
        fields: list[WireField] = [
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
        # Gated trailers: each field is only written when the connected
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
        def _proto():
            return _converters.scanner.createScannerSubscriptionRequestProto(
                reqId,
                subscription,
                scannerSubscriptionOptions=scannerSubscriptionOptions,
                scannerSubscriptionFilterOptions=scannerSubscriptionFilterOptions,
            )

        if self._tryProto(_M.REQ_SCANNER_SUBSCRIPTION, _proto):
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
        def _proto():
            return _converters.scanner.createCancelScannerSubscriptionProto(reqId)

        if self._tryProto(_M.CANCEL_SCANNER_SUBSCRIPTION, _proto):
            return
        self.send(23, 1, reqId)

    def reqScannerParameters(self):
        def _proto():
            return _converters.scanner.createScannerParametersRequestProto()

        if self._tryProto(_M.REQ_SCANNER_PARAMETERS, _proto):
            return
        self.send(24, 1)

    def cancelHistoricalData(self, reqId):
        def _proto():
            return _converters.historical.createCancelHistoricalDataProto(reqId)

        if self._tryProto(_M.CANCEL_HISTORICAL_DATA, _proto):
            return
        self.send(25, 1, reqId)

    def reqCurrentTime(self):
        def _proto():
            return _converters.rest.createCurrentTimeRequestProto()

        if self._tryProto(_M.REQ_CURRENT_TIME, _proto):
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

        self.sendProto(
            _M.REQ_CURRENT_TIME_IN_MILLIS,
            _converters.rest.createCurrentTimeInMillisRequestProto().SerializeToString(),
        )

    def reqRealTimeBars(
        self, reqId, contract, barSize, whatToShow, useRTH, realTimeBarsOptions
    ):
        def _proto():
            return _converters.historical.createRealTimeBarsRequestProto(
                reqId,
                contract,
                barSize,
                whatToShow,
                useRTH,
                realTimeBarsOptions=realTimeBarsOptions,
            )

        if self._tryProto(_M.REQ_REAL_TIME_BARS, _proto):
            return
        self.send(
            50, 3, reqId, contract, barSize, whatToShow, useRTH, realTimeBarsOptions
        )

    def cancelRealTimeBars(self, reqId):
        def _proto():
            return _converters.historical.createCancelRealTimeBarsProto(reqId)

        if self._tryProto(_M.CANCEL_REAL_TIME_BARS, _proto):
            return
        self.send(51, 1, reqId)

    def calculateImpliedVolatility(
        self, reqId, contract, optionPrice, underPrice, implVolOptions
    ):
        def _proto():
            return _converters.rest.createCalculateImpliedVolatilityRequestProto(
                reqId,
                contract,
                optionPrice,
                underPrice,
                impliedVolatilityOptions=implVolOptions,
            )

        if self._tryProto(_M.REQ_CALC_IMPLIED_VOLAT, _proto):
            return
        self.send(
            54,
            3,
            reqId,
            contract,
            optionPrice,
            underPrice,
            implVolOptions,
        )

    def calculateOptionPrice(
        self, reqId, contract, volatility, underPrice, optPrcOptions
    ):
        def _proto():
            return _converters.rest.createCalculateOptionPriceRequestProto(
                reqId,
                contract,
                volatility,
                underPrice,
                optionPriceOptions=optPrcOptions,
            )

        if self._tryProto(_M.REQ_CALC_OPTION_PRICE, _proto):
            return
        self.send(
            55,
            3,
            reqId,
            contract,
            volatility,
            underPrice,
            optPrcOptions,
        )

    def cancelCalculateImpliedVolatility(self, reqId):
        def _proto():
            return _converters.rest.createCancelCalculateImpliedVolatilityProto(reqId)

        if self._tryProto(_M.CANCEL_CALC_IMPLIED_VOLAT, _proto):
            return
        self.send(56, 1, reqId)

    def cancelCalculateOptionPrice(self, reqId):
        def _proto():
            return _converters.rest.createCancelCalculateOptionPriceProto(reqId)

        if self._tryProto(_M.CANCEL_CALC_OPTION_PRICE, _proto):
            return
        self.send(57, 1, reqId)

    def reqGlobalCancel(self, orderCancel=None):
        if orderCancel is None:
            orderCancel = OrderCancel()

        def _proto():
            return _converters.orders.createGlobalCancelRequestProto(
                extOperator=orderCancel.extOperator,
                manualOrderIndicator=orderCancel.manualOrderIndicator,
            )

        if self._tryProto(_M.REQ_GLOBAL_CANCEL, _proto):
            return

        # Binary wire layout: pre-192 carries VERSION=1 prefix; >=192
        # drops VERSION and appends extOperator + manualOrderIndicator.
        fields: list[WireField] = [58]
        if self.serverVersion() < MIN_SERVER_VER_CME_TAGGING_FIELDS:
            fields.append(1)  # legacy VERSION
        if self.serverVersion() >= MIN_SERVER_VER_CME_TAGGING_FIELDS:
            fields += [orderCancel.extOperator, orderCancel.manualOrderIndicator]
        self.send(*fields)

    def reqMarketDataType(self, marketDataType):
        def _proto():
            return _converters.market_data.createMarketDataTypeRequestProto(
                marketDataType
            )

        if self._tryProto(_M.REQ_MARKET_DATA_TYPE, _proto):
            return
        self.send(59, 1, marketDataType)

    def reqPositions(self):
        def _proto():
            return _converters.accounts.createPositionsRequestProto()

        if self._tryProto(_M.REQ_POSITIONS, _proto):
            return
        self.send(61, 1)

    def reqAccountSummary(self, reqId, groupName, tags):
        def _proto():
            return _converters.accounts.createAccountSummaryRequestProto(
                reqId, groupName, tags
            )

        if self._tryProto(_M.REQ_ACCOUNT_SUMMARY, _proto):
            return
        self.send(62, 1, reqId, groupName, tags)

    def cancelAccountSummary(self, reqId):
        def _proto():
            return _converters.accounts.createCancelAccountSummaryProto(reqId)

        if self._tryProto(_M.CANCEL_ACCOUNT_SUMMARY, _proto):
            return
        self.send(63, 1, reqId)

    def cancelPositions(self):
        def _proto():
            return _converters.accounts.createCancelPositionsProto()

        if self._tryProto(_M.CANCEL_POSITIONS, _proto):
            return
        self.send(64, 1)

    def verifyRequest(self, apiName, apiVersion):
        self.send(65, 1, apiName, apiVersion)

    def verifyMessage(self, apiData):
        self.send(66, 1, apiData)

    def queryDisplayGroups(self, reqId):
        def _proto():
            return _converters.rest.createQueryDisplayGroupsRequestProto(reqId)

        if self._tryProto(_M.QUERY_DISPLAY_GROUPS, _proto):
            return
        self.send(67, 1, reqId)

    def subscribeToGroupEvents(self, reqId, groupId):
        def _proto():
            return _converters.rest.createSubscribeToGroupEventsRequestProto(
                reqId, groupId
            )

        if self._tryProto(_M.SUBSCRIBE_TO_GROUP_EVENTS, _proto):
            return
        self.send(68, 1, reqId, groupId)

    def updateDisplayGroup(self, reqId, contractInfo):
        def _proto():
            return _converters.rest.createUpdateDisplayGroupRequestProto(
                reqId, contractInfo
            )

        if self._tryProto(_M.UPDATE_DISPLAY_GROUP, _proto):
            return
        self.send(69, 1, reqId, contractInfo)

    def unsubscribeFromGroupEvents(self, reqId):
        def _proto():
            return _converters.rest.createUnsubscribeFromGroupEventsRequestProto(reqId)

        if self._tryProto(_M.UNSUBSCRIBE_FROM_GROUP_EVENTS, _proto):
            return
        self.send(70, 1, reqId)

    def startApi(self):
        def _proto():
            return _converters.rest.createStartApiRequestProto(
                self.clientId, self.optCapab
            )

        if self._tryProto(_M.START_API, _proto):
            return
        self.send(71, 2, self.clientId, self.optCapab)

    def verifyAndAuthRequest(self, apiName, apiVersion, opaqueIsvKey):
        self.send(72, 1, apiName, apiVersion, opaqueIsvKey)

    def verifyAndAuthMessage(self, apiData, xyzResponse):
        self.send(73, 1, apiData, xyzResponse)

    def reqPositionsMulti(self, reqId, account, modelCode):
        def _proto():
            return _converters.accounts.createPositionsMultiRequestProto(
                reqId, account, modelCode
            )

        if self._tryProto(_M.REQ_POSITIONS_MULTI, _proto):
            return
        self.send(74, 1, reqId, account, modelCode)

    def cancelPositionsMulti(self, reqId):
        def _proto():
            return _converters.accounts.createCancelPositionsMultiProto(reqId)

        if self._tryProto(_M.CANCEL_POSITIONS_MULTI, _proto):
            return
        self.send(75, 1, reqId)

    def reqAccountUpdatesMulti(self, reqId, account, modelCode, ledgerAndNLV):
        def _proto():
            return _converters.accounts.createAccountUpdatesMultiRequestProto(
                reqId, account, modelCode, ledgerAndNLV
            )

        if self._tryProto(_M.REQ_ACCOUNT_UPDATES_MULTI, _proto):
            return
        self.send(76, 1, reqId, account, modelCode, ledgerAndNLV)

    def cancelAccountUpdatesMulti(self, reqId):
        def _proto():
            return _converters.accounts.createCancelAccountUpdatesMultiProto(reqId)

        if self._tryProto(_M.CANCEL_ACCOUNT_UPDATES_MULTI, _proto):
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
        def _proto():
            return _converters.rest.createSecDefOptParamsRequestProto(
                reqId,
                underlyingSymbol,
                futFopExchange,
                underlyingSecType,
                underlyingConId,
            )

        if self._tryProto(_M.REQ_SEC_DEF_OPT_PARAMS, _proto):
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
        def _proto():
            return _converters.rest.createSoftDollarTiersRequestProto(reqId)

        if self._tryProto(_M.REQ_SOFT_DOLLAR_TIERS, _proto):
            return
        self.send(79, reqId)

    def reqFamilyCodes(self):
        def _proto():
            return _converters.accounts.createFamilyCodesRequestProto()

        if self._tryProto(_M.REQ_FAMILY_CODES, _proto):
            return
        self.send(80)

    def reqMatchingSymbols(self, reqId, pattern):
        def _proto():
            return _converters.rest.createMatchingSymbolsRequestProto(reqId, pattern)

        if self._tryProto(_M.REQ_MATCHING_SYMBOLS, _proto):
            return
        self.send(81, reqId, pattern)

    def reqMktDepthExchanges(self):
        def _proto():
            return _converters.market_data.createMarketDepthExchangesRequestProto()

        if self._tryProto(_M.REQ_MKT_DEPTH_EXCHANGES, _proto):
            return
        self.send(82)

    def reqSmartComponents(self, reqId, bboExchange):
        def _proto():
            return _converters.rest.createSmartComponentsRequestProto(
                reqId, bboExchange
            )

        if self._tryProto(_M.REQ_SMART_COMPONENTS, _proto):
            return
        self.send(83, reqId, bboExchange)

    def reqNewsArticle(self, reqId, providerCode, articleId, newsArticleOptions):
        def _proto():
            return _converters.news.createNewsArticleRequestProto(
                reqId,
                providerCode,
                articleId,
                newsArticleOptions=newsArticleOptions,
            )

        if self._tryProto(_M.REQ_NEWS_ARTICLE, _proto):
            return
        self.send(84, reqId, providerCode, articleId, newsArticleOptions)

    def reqNewsProviders(self):
        def _proto():
            return _converters.news.createNewsProvidersRequestProto()

        if self._tryProto(_M.REQ_NEWS_PROVIDERS, _proto):
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
        def _proto():
            return _converters.news.createHistoricalNewsRequestProto(
                reqId,
                conId,
                providerCodes,
                startDateTime,
                endDateTime,
                totalResults,
                historicalNewsOptions=historicalNewsOptions,
            )

        if self._tryProto(_M.REQ_HISTORICAL_NEWS, _proto):
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
        def _proto():
            return _converters.historical.createHeadTimestampRequestProto(
                reqId, contract, useRTH, whatToShow, formatDate
            )

        if self._tryProto(_M.REQ_HEAD_TIMESTAMP, _proto):
            return
        self.send(
            87, reqId, contract, contract.includeExpired, useRTH, whatToShow, formatDate
        )

    def reqHistogramData(self, tickerId, contract, useRTH, timePeriod):
        def _proto():
            return _converters.historical.createHistogramDataRequestProto(
                tickerId, contract, bool(useRTH), timePeriod
            )

        if self._tryProto(_M.REQ_HISTOGRAM_DATA, _proto):
            return
        self.send(88, tickerId, contract, contract.includeExpired, useRTH, timePeriod)

    def cancelHistogramData(self, tickerId):
        def _proto():
            return _converters.historical.createCancelHistogramDataProto(tickerId)

        if self._tryProto(_M.CANCEL_HISTOGRAM_DATA, _proto):
            return
        self.send(89, tickerId)

    def cancelHeadTimeStamp(self, reqId):
        def _proto():
            return _converters.historical.createCancelHeadTimestampProto(reqId)

        if self._tryProto(_M.CANCEL_HEAD_TIMESTAMP, _proto):
            return
        self.send(90, reqId)

    def cancelContractData(self, reqId):
        """Cancel an in-flight reqContractDetails. Protobuf-only —
        IBKR ships no binary form (gate 215, MIN_SERVER_VER_CANCEL_CONTRACT_DATA).
        """

        self.sendProto(
            _M.CANCEL_CONTRACT_DATA,
            _converters.historical.createCancelContractDataProto(
                reqId
            ).SerializeToString(),
        )

    def cancelHistoricalTicks(self, reqId):
        """Cancel an in-flight reqHistoricalTicks. Protobuf-only
        (gate 215, MIN_SERVER_VER_CANCEL_CONTRACT_DATA shares the gate).
        """

        self.sendProto(
            _M.CANCEL_HISTORICAL_TICKS,
            _converters.historical.createCancelHistoricalTicksProto(
                reqId
            ).SerializeToString(),
        )

    def reqConfig(self, reqId):
        """Fetch the TWS / IB Gateway runtime config. Protobuf-only
        (gate 219, MIN_SERVER_VER_CONFIG). Server replies with
        ``ConfigResponse`` carrying nested LockAndExitConfig /
        ApiConfig / MessageConfig / OrdersConfig sub-messages.
        """

        self.sendProto(
            _M.REQ_CONFIG,
            _converters.rest.createConfigRequestProto(reqId).SerializeToString(),
        )

    def updateConfig(
        self,
        reqId,
        lockAndExit=None,
        messages=None,
        api=None,
        orders=None,
        acceptedWarnings=None,
        resetAPIOrderSequence=False,
    ):
        """Push a TWS / IB Gateway config update. Protobuf-only
        (gate 221, MIN_SERVER_VER_UPDATE_CONFIG). Server replies
        with ``UpdateConfigResponse`` carrying status + changed-fields list.
        """

        self.sendProto(
            _M.UPDATE_CONFIG,
            _converters.rest.createUpdateConfigRequestProto(
                reqId,
                lockAndExit=lockAndExit,
                messages=messages,
                api=api,
                orders=orders,
                acceptedWarnings=acceptedWarnings,
                resetAPIOrderSequence=resetAPIOrderSequence,
            ).SerializeToString(),
        )

    def reqMarketRule(self, marketRuleId):
        def _proto():
            return _converters.rest.createMarketRuleRequestProto(marketRuleId)

        if self._tryProto(_M.REQ_MARKET_RULE, _proto):
            return
        self.send(91, marketRuleId)

    def reqPnL(self, reqId, account, modelCode):
        def _proto():
            return _converters.scanner.createPnLRequestProto(reqId, account, modelCode)

        if self._tryProto(_M.REQ_PNL, _proto):
            return
        self.send(92, reqId, account, modelCode)

    def cancelPnL(self, reqId):
        def _proto():
            return _converters.scanner.createCancelPnLProto(reqId)

        if self._tryProto(_M.CANCEL_PNL, _proto):
            return
        self.send(93, reqId)

    def reqPnLSingle(self, reqId, account, modelCode, conid):
        def _proto():
            return _converters.scanner.createPnLSingleRequestProto(
                reqId, account, modelCode, conid
            )

        if self._tryProto(_M.REQ_PNL_SINGLE, _proto):
            return
        self.send(94, reqId, account, modelCode, conid)

    def cancelPnLSingle(self, reqId):
        def _proto():
            return _converters.scanner.createCancelPnLSingleProto(reqId)

        if self._tryProto(_M.CANCEL_PNL_SINGLE, _proto):
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
        def _proto():
            return _converters.historical.createHistoricalTicksRequestProto(
                reqId,
                contract,
                startDateTime,
                endDateTime,
                numberOfTicks,
                whatToShow,
                useRth,
                ignoreSize,
                miscOptions=miscOptions,
            )

        if self._tryProto(_M.REQ_HISTORICAL_TICKS, _proto):
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
        def _proto():
            return _converters.market_data.createTickByTickRequestProto(
                reqId, contract, tickType, numberOfTicks, ignoreSize
            )

        if self._tryProto(_M.REQ_TICK_BY_TICK_DATA, _proto):
            return
        self.send(97, reqId, contract, tickType, numberOfTicks, ignoreSize)

    def cancelTickByTickData(self, reqId):
        def _proto():
            return _converters.market_data.createCancelTickByTickProto(reqId)

        if self._tryProto(_M.CANCEL_TICK_BY_TICK_DATA, _proto):
            return
        self.send(98, reqId)

    def reqCompletedOrders(self, apiOnly):
        def _proto():
            return _converters.orders.createCompletedOrdersRequestProto(apiOnly)

        if self._tryProto(_M.REQ_COMPLETED_ORDERS, _proto):
            return
        self.send(99, apiOnly)

    def reqWshMetaData(self, reqId):
        def _proto():
            return _converters.news.createWshMetaDataRequestProto(reqId)

        if self._tryProto(_M.REQ_WSH_META_DATA, _proto):
            return
        self.send(100, reqId)

    def cancelWshMetaData(self, reqId):
        def _proto():
            return _converters.news.createCancelWshMetaDataProto(reqId)

        if self._tryProto(_M.CANCEL_WSH_META_DATA, _proto):
            return
        self.send(101, reqId)

    def reqWshEventData(self, reqId, data: WshEventData):
        def _proto():
            return _converters.news.createWshEventDataRequestProto(reqId, data)

        if self._tryProto(_M.REQ_WSH_EVENT_DATA, _proto):
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
        def _proto():
            return _converters.news.createCancelWshEventDataProto(reqId)

        if self._tryProto(_M.CANCEL_WSH_EVENT_DATA, _proto):
            return
        self.send(103, reqId)

    def reqUserInfo(self, reqId):
        def _proto():
            return _converters.rest.createUserInfoRequestProto(reqId)

        if self._tryProto(_M.REQ_USER_INFO, _proto):
            return
        self.send(104, reqId)
