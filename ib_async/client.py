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
        #  - Convert positive infinity to the IBKR ``INFINITY_STR``
        #    constant. IBKR's reference (``ibapi/const.py``) defines this
        #    as the literal ``"Infinity"`` (not ``"Infinite"``); the
        #    server parses ``"Infinity"`` for fields like
        #    ``competeAgainstBestOffset = COMPETE_AGAINST_BEST_OFFSET_UP_TO_MID``
        #    and rejects any other spelling. Sending ``"Infinite"``
        #    silently corrupts those mid-peg orders.
        #  - else, convert float to string normally
        float: lambda f: ""
        if (makeEmpty and f == UNSET_DOUBLE)
        else ("Infinity" if (f == math.inf) else str(f)),

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

    # ``MaxClientVersion`` advertises the most-recent TWS / IB Gateway
    # server version this client knows how to talk to. The handshake at
    # ``connectAsync`` sends ``v{Min}..{Max}`` and the server picks the
    # min(server-max, our-max) at negotiation time. Bumping this MUST be
    # paired with patches to every send-side / receive-side gated field
    # at gates between the old cap and the new — see
    # ``ib_async/_server_versions.py`` for the symbolic gate constants.
    # As of v3.0 the binary path handles all gates 158-225 and the
    # protobuf path takes over per-message-family at 201-213.
    MinClientVersion = 157
    MaxClientVersion = 225

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

    def _tryProto(self, canonicalMsgId: int, build_proto: Callable[[], Any]) -> bool:
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

        Mirrors IBKR ``EClient.setOptionalCapabilities``. The value is
        included in the START_API frame (binary path field 4 / proto
        ``optionalCapabilities``) and gated server-side by
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

        # First field is always the canonical msgId; remaining fields are
        # the body. Pre-201 servers receive both as NUL-terminated text;
        # 201+ servers receive a 4-byte big-endian raw msgId followed by
        # the NUL-terminated body, mirroring IBKR ``comm.make_msg``'s
        # ``useRawIntMsgId`` branch (`make_msg(msgId, useRawIntMsgId=True,
        # text)`). Sending the legacy text msgId to a 201+ server makes
        # the server fail to decode the frame and silently drop the
        # connection — every binary-path message (startApi, anything
        # that's not in PROTOBUF_MSG_IDS, anything below its proto gate)
        # is affected.
        msgId = fields[0]
        body = io.StringIO()
        for field in fields[1:]:
            # Fetch type converter for this field (falls back to 'str(field)' as a default for unmatched types)
            # (extra `isinstance()` wrapper needed here because Contract subclasses are their own type, but we want
            #  to only match against the Contract parent class for formatting operations)
            convert = FORMAT_HANDLERS.get(
                Contract if isinstance(field, Contract) else type(field), str
            )
            body.write(convert(field))
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
            from ._proto.market_data import createMarketDataRequestProto

            return createMarketDataRequestProto(
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
            from ._proto.market_data import createCancelMarketDataProto

            return createCancelMarketDataProto(reqId)

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
            # ONLY volatility orders can have 'volatility' set when sending API data.
            order.volatility = UNSET_DOUBLE

        # On TWS / IB Gateway server versions that support protobuf for
        # placeOrder (gate 203), emit a ``PlaceOrderRequest`` proto and
        # return; binary fallback below preserves compatibility with
        # older servers. Per-msgId gating (not per-connection): a 207
        # server uses protobuf for orders but binary for historical
        # data, etc.
        def _proto():
            from ._proto.orders import createPlaceOrderRequestProto

            return createPlaceOrderRequestProto(orderId, contract, order)

        if self._tryProto(_M.PLACE_ORDER, _proto):
            return

        version = self.serverVersion()

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

        # Gates 178+ — mirror IBKR ``client.py:placeOrder`` lines 2746-2763.

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
        from .order import OrderCancel

        if orderCancel is None:
            orderCancel = OrderCancel()
        elif isinstance(orderCancel, str):
            orderCancel = OrderCancel(manualOrderCancelTime=orderCancel)

        def _proto():
            from ._proto.orders import createCancelOrderRequestProto

            return createCancelOrderRequestProto(
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
        def _proto():
            from ._proto.orders import createOpenOrdersRequestProto

            return createOpenOrdersRequestProto()

        if self._tryProto(_M.REQ_OPEN_ORDERS, _proto):
            return
        self.send(5, 1)

    def reqAccountUpdates(self, subscribe, acctCode):
        def _proto():
            from ._proto.accounts import createAccountDataRequestProto

            return createAccountDataRequestProto(subscribe, acctCode)

        if self._tryProto(_M.REQ_ACCT_DATA, _proto):
            return
        self.send(6, 2, subscribe, acctCode)

    def reqExecutions(self, reqId, execFilter):
        def _proto():
            from ._proto.orders import createExecutionRequestProto

            return createExecutionRequestProto(reqId, execFilter)

        if self._tryProto(_M.REQ_EXECUTIONS, _proto):
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
            from ._proto.contracts import createContractDataRequestProto

            return createContractDataRequestProto(reqId, contract)

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
            from ._proto.market_data import createMarketDepthRequestProto

            return createMarketDepthRequestProto(
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
            from ._proto.market_data import createCancelMarketDepthProto

            return createCancelMarketDepthProto(reqId, isSmartDepth)

        if self._tryProto(_M.CANCEL_MKT_DEPTH, _proto):
            return
        self.send(11, 1, reqId, isSmartDepth)

    def reqNewsBulletins(self, allMsgs):
        def _proto():
            from ._proto.news import createNewsBulletinsRequestProto

            return createNewsBulletinsRequestProto(allMsgs)

        if self._tryProto(_M.REQ_NEWS_BULLETINS, _proto):
            return
        self.send(12, 1, allMsgs)

    def cancelNewsBulletins(self):
        def _proto():
            from ._proto.news import createCancelNewsBulletinsProto

            return createCancelNewsBulletinsProto()

        if self._tryProto(_M.CANCEL_NEWS_BULLETINS, _proto):
            return
        self.send(13, 1)

    def setServerLogLevel(self, logLevel):
        def _proto():
            from ._proto.rest import createSetServerLogLevelRequestProto

            return createSetServerLogLevelRequestProto(logLevel)

        if self._tryProto(_M.SET_SERVER_LOGLEVEL, _proto):
            return
        self.send(14, 1, logLevel)

    def reqAutoOpenOrders(self, bAutoBind):
        def _proto():
            from ._proto.orders import createAutoOpenOrdersRequestProto

            return createAutoOpenOrdersRequestProto(bAutoBind)

        if self._tryProto(_M.REQ_AUTO_OPEN_ORDERS, _proto):
            return
        self.send(15, 1, bAutoBind)

    def reqAllOpenOrders(self):
        def _proto():
            from ._proto.orders import createAllOpenOrdersRequestProto

            return createAllOpenOrdersRequestProto()

        if self._tryProto(_M.REQ_ALL_OPEN_ORDERS, _proto):
            return
        self.send(16, 1)

    def reqManagedAccts(self):
        def _proto():
            from ._proto.accounts import createManagedAccountsRequestProto

            return createManagedAccountsRequestProto()

        if self._tryProto(_M.REQ_MANAGED_ACCTS, _proto):
            return
        self.send(17, 1)

    def requestFA(self, faData):
        # FA Profiles (faData == 2) were de-supported at server gate 177.
        # IBKR's reference rejects this request locally instead of letting
        # the server bounce it; mirror that to match wire parity.
        if (
            self.serverVersion() >= MIN_SERVER_VER_FA_PROFILE_DESUPPORT
            and int(faData) == 2
        ):
            return

        def _proto():
            from ._proto.accounts import createFARequestProto

            return createFARequestProto(faData)

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
            from ._proto.accounts import createFAReplaceProto

            return createFAReplaceProto(reqId, faData, cxml)

        if self._tryProto(_M.REPLACE_FA, _proto):
            return
        # The trailing ``reqId`` field only exists at server gate 157+
        # (REPLACE_FA_END). Sending it to a sub-157 server desyncs the
        # frame — IBKR's reference gates this write conditionally.
        fields: list[Any] = [19, 1, faData, cxml]
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
            from ._proto.historical import createHistoricalDataRequestProto

            return createHistoricalDataRequestProto(
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
            from ._proto.rest import createExerciseOptionsRequestProto

            return createExerciseOptionsRequestProto(
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
        def _proto():
            from ._proto.scanner import createScannerSubscriptionRequestProto

            return createScannerSubscriptionRequestProto(
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
            from ._proto.scanner import createCancelScannerSubscriptionProto

            return createCancelScannerSubscriptionProto(reqId)

        if self._tryProto(_M.CANCEL_SCANNER_SUBSCRIPTION, _proto):
            return
        self.send(23, 1, reqId)

    def reqScannerParameters(self):
        def _proto():
            from ._proto.scanner import createScannerParametersRequestProto

            return createScannerParametersRequestProto()

        if self._tryProto(_M.REQ_SCANNER_PARAMETERS, _proto):
            return
        self.send(24, 1)

    def cancelHistoricalData(self, reqId):
        def _proto():
            from ._proto.historical import createCancelHistoricalDataProto

            return createCancelHistoricalDataProto(reqId)

        if self._tryProto(_M.CANCEL_HISTORICAL_DATA, _proto):
            return
        self.send(25, 1, reqId)

    def reqCurrentTime(self):
        def _proto():
            from ._proto.rest import createCurrentTimeRequestProto

            return createCurrentTimeRequestProto()

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
        from ._proto.rest import createCurrentTimeInMillisRequestProto

        self.sendProto(
            _M.REQ_CURRENT_TIME_IN_MILLIS,
            createCurrentTimeInMillisRequestProto().SerializeToString(),
        )

    def reqRealTimeBars(
        self, reqId, contract, barSize, whatToShow, useRTH, realTimeBarsOptions
    ):
        def _proto():
            from ._proto.historical import createRealTimeBarsRequestProto

            return createRealTimeBarsRequestProto(
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
            from ._proto.historical import createCancelRealTimeBarsProto

            return createCancelRealTimeBarsProto(reqId)

        if self._tryProto(_M.CANCEL_REAL_TIME_BARS, _proto):
            return
        self.send(51, 1, reqId)

    def reqFundamentalData(self, reqId, contract, reportType, fundamentalDataOptions):
        def _proto():
            from ._proto.scanner import createFundamentalsDataRequestProto

            return createFundamentalsDataRequestProto(
                reqId,
                contract,
                reportType,
                fundamentalsDataOptions=fundamentalDataOptions,
            )

        if self._tryProto(_M.REQ_FUNDAMENTAL_DATA, _proto):
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
        def _proto():
            from ._proto.scanner import createCancelFundamentalsDataProto

            return createCancelFundamentalsDataProto(reqId)

        if self._tryProto(_M.CANCEL_FUNDAMENTAL_DATA, _proto):
            return
        self.send(53, 1, reqId)

    def calculateImpliedVolatility(
        self, reqId, contract, optionPrice, underPrice, implVolOptions
    ):
        def _proto():
            from ._proto.rest import createCalculateImpliedVolatilityRequestProto

            return createCalculateImpliedVolatilityRequestProto(
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
            from ._proto.rest import createCalculateOptionPriceRequestProto

            return createCalculateOptionPriceRequestProto(
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
            from ._proto.rest import createCancelCalculateImpliedVolatilityProto

            return createCancelCalculateImpliedVolatilityProto(reqId)

        if self._tryProto(_M.CANCEL_CALC_IMPLIED_VOLAT, _proto):
            return
        self.send(56, 1, reqId)

    def cancelCalculateOptionPrice(self, reqId):
        def _proto():
            from ._proto.rest import createCancelCalculateOptionPriceProto

            return createCancelCalculateOptionPriceProto(reqId)

        if self._tryProto(_M.CANCEL_CALC_OPTION_PRICE, _proto):
            return
        self.send(57, 1, reqId)

    def reqGlobalCancel(self, orderCancel=None):
        from .order import OrderCancel

        if orderCancel is None:
            orderCancel = OrderCancel()

        def _proto():
            from ._proto.orders import createGlobalCancelRequestProto

            return createGlobalCancelRequestProto(
                extOperator=orderCancel.extOperator,
                manualOrderIndicator=orderCancel.manualOrderIndicator,
            )

        if self._tryProto(_M.REQ_GLOBAL_CANCEL, _proto):
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
        def _proto():
            from ._proto.market_data import createMarketDataTypeRequestProto

            return createMarketDataTypeRequestProto(marketDataType)

        if self._tryProto(_M.REQ_MARKET_DATA_TYPE, _proto):
            return
        self.send(59, 1, marketDataType)

    def reqPositions(self):
        def _proto():
            from ._proto.accounts import createPositionsRequestProto

            return createPositionsRequestProto()

        if self._tryProto(_M.REQ_POSITIONS, _proto):
            return
        self.send(61, 1)

    def reqAccountSummary(self, reqId, groupName, tags):
        def _proto():
            from ._proto.accounts import createAccountSummaryRequestProto

            return createAccountSummaryRequestProto(reqId, groupName, tags)

        if self._tryProto(_M.REQ_ACCOUNT_SUMMARY, _proto):
            return
        self.send(62, 1, reqId, groupName, tags)

    def cancelAccountSummary(self, reqId):
        def _proto():
            from ._proto.accounts import createCancelAccountSummaryProto

            return createCancelAccountSummaryProto(reqId)

        if self._tryProto(_M.CANCEL_ACCOUNT_SUMMARY, _proto):
            return
        self.send(63, 1, reqId)

    def cancelPositions(self):
        def _proto():
            from ._proto.accounts import createCancelPositionsProto

            return createCancelPositionsProto()

        if self._tryProto(_M.CANCEL_POSITIONS, _proto):
            return
        self.send(64, 1)

    def verifyRequest(self, apiName, apiVersion):
        self.send(65, 1, apiName, apiVersion)

    def verifyMessage(self, apiData):
        self.send(66, 1, apiData)

    def queryDisplayGroups(self, reqId):
        def _proto():
            from ._proto.rest import createQueryDisplayGroupsRequestProto

            return createQueryDisplayGroupsRequestProto(reqId)

        if self._tryProto(_M.QUERY_DISPLAY_GROUPS, _proto):
            return
        self.send(67, 1, reqId)

    def subscribeToGroupEvents(self, reqId, groupId):
        def _proto():
            from ._proto.rest import createSubscribeToGroupEventsRequestProto

            return createSubscribeToGroupEventsRequestProto(reqId, groupId)

        if self._tryProto(_M.SUBSCRIBE_TO_GROUP_EVENTS, _proto):
            return
        self.send(68, 1, reqId, groupId)

    def updateDisplayGroup(self, reqId, contractInfo):
        def _proto():
            from ._proto.rest import createUpdateDisplayGroupRequestProto

            return createUpdateDisplayGroupRequestProto(reqId, contractInfo)

        if self._tryProto(_M.UPDATE_DISPLAY_GROUP, _proto):
            return
        self.send(69, 1, reqId, contractInfo)

    def unsubscribeFromGroupEvents(self, reqId):
        def _proto():
            from ._proto.rest import createUnsubscribeFromGroupEventsRequestProto

            return createUnsubscribeFromGroupEventsRequestProto(reqId)

        if self._tryProto(_M.UNSUBSCRIBE_FROM_GROUP_EVENTS, _proto):
            return
        self.send(70, 1, reqId)

    def startApi(self):
        def _proto():
            from ._proto.rest import createStartApiRequestProto

            return createStartApiRequestProto(self.clientId, self.optCapab)

        if self._tryProto(_M.START_API, _proto):
            return
        self.send(71, 2, self.clientId, self.optCapab)

    def verifyAndAuthRequest(self, apiName, apiVersion, opaqueIsvKey):
        self.send(72, 1, apiName, apiVersion, opaqueIsvKey)

    def verifyAndAuthMessage(self, apiData, xyzResponse):
        self.send(73, 1, apiData, xyzResponse)

    def reqPositionsMulti(self, reqId, account, modelCode):
        def _proto():
            from ._proto.accounts import createPositionsMultiRequestProto

            return createPositionsMultiRequestProto(reqId, account, modelCode)

        if self._tryProto(_M.REQ_POSITIONS_MULTI, _proto):
            return
        self.send(74, 1, reqId, account, modelCode)

    def cancelPositionsMulti(self, reqId):
        def _proto():
            from ._proto.accounts import createCancelPositionsMultiProto

            return createCancelPositionsMultiProto(reqId)

        if self._tryProto(_M.CANCEL_POSITIONS_MULTI, _proto):
            return
        self.send(75, 1, reqId)

    def reqAccountUpdatesMulti(self, reqId, account, modelCode, ledgerAndNLV):
        def _proto():
            from ._proto.accounts import createAccountUpdatesMultiRequestProto

            return createAccountUpdatesMultiRequestProto(
                reqId, account, modelCode, ledgerAndNLV
            )

        if self._tryProto(_M.REQ_ACCOUNT_UPDATES_MULTI, _proto):
            return
        self.send(76, 1, reqId, account, modelCode, ledgerAndNLV)

    def cancelAccountUpdatesMulti(self, reqId):
        def _proto():
            from ._proto.accounts import createCancelAccountUpdatesMultiProto

            return createCancelAccountUpdatesMultiProto(reqId)

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
            from ._proto.rest import createSecDefOptParamsRequestProto

            return createSecDefOptParamsRequestProto(
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
            from ._proto.rest import createSoftDollarTiersRequestProto

            return createSoftDollarTiersRequestProto(reqId)

        if self._tryProto(_M.REQ_SOFT_DOLLAR_TIERS, _proto):
            return
        self.send(79, reqId)

    def reqFamilyCodes(self):
        def _proto():
            from ._proto.accounts import createFamilyCodesRequestProto

            return createFamilyCodesRequestProto()

        if self._tryProto(_M.REQ_FAMILY_CODES, _proto):
            return
        self.send(80)

    def reqMatchingSymbols(self, reqId, pattern):
        def _proto():
            from ._proto.rest import createMatchingSymbolsRequestProto

            return createMatchingSymbolsRequestProto(reqId, pattern)

        if self._tryProto(_M.REQ_MATCHING_SYMBOLS, _proto):
            return
        self.send(81, reqId, pattern)

    def reqMktDepthExchanges(self):
        def _proto():
            from ._proto.market_data import createMarketDepthExchangesRequestProto

            return createMarketDepthExchangesRequestProto()

        if self._tryProto(_M.REQ_MKT_DEPTH_EXCHANGES, _proto):
            return
        self.send(82)

    def reqSmartComponents(self, reqId, bboExchange):
        def _proto():
            from ._proto.rest import createSmartComponentsRequestProto

            return createSmartComponentsRequestProto(reqId, bboExchange)

        if self._tryProto(_M.REQ_SMART_COMPONENTS, _proto):
            return
        self.send(83, reqId, bboExchange)

    def reqNewsArticle(self, reqId, providerCode, articleId, newsArticleOptions):
        def _proto():
            from ._proto.news import createNewsArticleRequestProto

            return createNewsArticleRequestProto(
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
            from ._proto.news import createNewsProvidersRequestProto

            return createNewsProvidersRequestProto()

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
            from ._proto.news import createHistoricalNewsRequestProto

            return createHistoricalNewsRequestProto(
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
            from ._proto.historical import createHeadTimestampRequestProto

            return createHeadTimestampRequestProto(
                reqId, contract, useRTH, whatToShow, formatDate
            )

        if self._tryProto(_M.REQ_HEAD_TIMESTAMP, _proto):
            return
        self.send(
            87, reqId, contract, contract.includeExpired, useRTH, whatToShow, formatDate
        )

    def reqHistogramData(self, tickerId, contract, useRTH, timePeriod):
        def _proto():
            from ._proto.historical import createHistogramDataRequestProto

            return createHistogramDataRequestProto(
                tickerId, contract, bool(useRTH), timePeriod
            )

        if self._tryProto(_M.REQ_HISTOGRAM_DATA, _proto):
            return
        self.send(88, tickerId, contract, contract.includeExpired, useRTH, timePeriod)

    def cancelHistogramData(self, tickerId):
        def _proto():
            from ._proto.historical import createCancelHistogramDataProto

            return createCancelHistogramDataProto(tickerId)

        if self._tryProto(_M.CANCEL_HISTOGRAM_DATA, _proto):
            return
        self.send(89, tickerId)

    def cancelHeadTimeStamp(self, reqId):
        def _proto():
            from ._proto.historical import createCancelHeadTimestampProto

            return createCancelHeadTimestampProto(reqId)

        if self._tryProto(_M.CANCEL_HEAD_TIMESTAMP, _proto):
            return
        self.send(90, reqId)

    def cancelContractData(self, reqId):
        """Cancel an in-flight reqContractDetails. Protobuf-only —
        IBKR ships no binary form (gate 215, MIN_SERVER_VER_CANCEL_CONTRACT_DATA).
        """
        from ._pb_msgids import CANCEL_CONTRACT_DATA
        from ._proto.historical import createCancelContractDataProto

        self.sendProto(
            CANCEL_CONTRACT_DATA,
            createCancelContractDataProto(reqId).SerializeToString(),
        )

    def cancelHistoricalTicks(self, reqId):
        """Cancel an in-flight reqHistoricalTicks. Protobuf-only
        (gate 215, MIN_SERVER_VER_CANCEL_CONTRACT_DATA shares the gate).
        """
        from ._pb_msgids import CANCEL_HISTORICAL_TICKS
        from ._proto.historical import createCancelHistoricalTicksProto

        self.sendProto(
            CANCEL_HISTORICAL_TICKS,
            createCancelHistoricalTicksProto(reqId).SerializeToString(),
        )

    def reqConfig(self, reqId):
        """Fetch the TWS / IB Gateway runtime config. Protobuf-only
        (gate 219, MIN_SERVER_VER_CONFIG). Server replies with
        ``ConfigResponse`` carrying nested LockAndExitConfig /
        ApiConfig / MessageConfig / OrdersConfig sub-messages.
        """
        from ._pb_msgids import REQ_CONFIG
        from ._proto.rest import createConfigRequestProto

        self.sendProto(REQ_CONFIG, createConfigRequestProto(reqId).SerializeToString())

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
        from ._pb_msgids import UPDATE_CONFIG
        from ._proto.rest import createUpdateConfigRequestProto

        self.sendProto(
            UPDATE_CONFIG,
            createUpdateConfigRequestProto(
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
            from ._proto.rest import createMarketRuleRequestProto

            return createMarketRuleRequestProto(marketRuleId)

        if self._tryProto(_M.REQ_MARKET_RULE, _proto):
            return
        self.send(91, marketRuleId)

    def reqPnL(self, reqId, account, modelCode):
        def _proto():
            from ._proto.scanner import createPnLRequestProto

            return createPnLRequestProto(reqId, account, modelCode)

        if self._tryProto(_M.REQ_PNL, _proto):
            return
        self.send(92, reqId, account, modelCode)

    def cancelPnL(self, reqId):
        def _proto():
            from ._proto.scanner import createCancelPnLProto

            return createCancelPnLProto(reqId)

        if self._tryProto(_M.CANCEL_PNL, _proto):
            return
        self.send(93, reqId)

    def reqPnLSingle(self, reqId, account, modelCode, conid):
        def _proto():
            from ._proto.scanner import createPnLSingleRequestProto

            return createPnLSingleRequestProto(reqId, account, modelCode, conid)

        if self._tryProto(_M.REQ_PNL_SINGLE, _proto):
            return
        self.send(94, reqId, account, modelCode, conid)

    def cancelPnLSingle(self, reqId):
        def _proto():
            from ._proto.scanner import createCancelPnLSingleProto

            return createCancelPnLSingleProto(reqId)

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
            from ._proto.historical import createHistoricalTicksRequestProto

            return createHistoricalTicksRequestProto(
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
            from ._proto.market_data import createTickByTickRequestProto

            return createTickByTickRequestProto(
                reqId, contract, tickType, numberOfTicks, ignoreSize
            )

        if self._tryProto(_M.REQ_TICK_BY_TICK_DATA, _proto):
            return
        self.send(97, reqId, contract, tickType, numberOfTicks, ignoreSize)

    def cancelTickByTickData(self, reqId):
        def _proto():
            from ._proto.market_data import createCancelTickByTickProto

            return createCancelTickByTickProto(reqId)

        if self._tryProto(_M.CANCEL_TICK_BY_TICK_DATA, _proto):
            return
        self.send(98, reqId)

    def reqCompletedOrders(self, apiOnly):
        def _proto():
            from ._proto.orders import createCompletedOrdersRequestProto

            return createCompletedOrdersRequestProto(apiOnly)

        if self._tryProto(_M.REQ_COMPLETED_ORDERS, _proto):
            return
        self.send(99, apiOnly)

    def reqWshMetaData(self, reqId):
        def _proto():
            from ._proto.news import createWshMetaDataRequestProto

            return createWshMetaDataRequestProto(reqId)

        if self._tryProto(_M.REQ_WSH_META_DATA, _proto):
            return
        self.send(100, reqId)

    def cancelWshMetaData(self, reqId):
        def _proto():
            from ._proto.news import createCancelWshMetaDataProto

            return createCancelWshMetaDataProto(reqId)

        if self._tryProto(_M.CANCEL_WSH_META_DATA, _proto):
            return
        self.send(101, reqId)

    def reqWshEventData(self, reqId, data: WshEventData):
        def _proto():
            from ._proto.news import createWshEventDataRequestProto

            return createWshEventDataRequestProto(reqId, data)

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
            from ._proto.news import createCancelWshEventDataProto

            return createCancelWshEventDataProto(reqId)

        if self._tryProto(_M.CANCEL_WSH_EVENT_DATA, _proto):
            return
        self.send(103, reqId)

    def reqUserInfo(self, reqId):
        def _proto():
            from ._proto.rest import createUserInfoRequestProto

            return createUserInfoRequestProto(reqId)

        if self._tryProto(_M.REQ_USER_INFO, _proto):
            return
        self.send(104, reqId)
