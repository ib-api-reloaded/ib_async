"""Socket client for communicating with Interactive Brokers."""

from __future__ import annotations

import asyncio
import logging
import struct
import time
from collections import deque

from eventkit import Event
from google.protobuf.message import Message

from . import _pb_msgids as _M
from . import _proto as _converters
from ._pb_msgids import PROTOBUF_MSG_ID
from ._server_versions import MAX_CLIENT_VER, MIN_CLIENT_VER, MIN_SERVER_VER_PROTOBUF
from .connection import Connection
from .decoder import Decoder
from .objects import ConnectionStats, WshEventData
from .order import OrderCancel
from .runtime import ConnectionPhase, ConnectionState, Tally, TransportState
from .util import getLoop, run

# The name of each connection state, indexed by Client.DISCONNECTED,
# Client.CONNECTING and Client.CONNECTED (0, 1, 2).
_PHASES: tuple[ConnectionPhase, ...] = ("disconnected", "connecting", "connected")


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

    Every request is sent as its protobuf message.

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

    # The handshake at ``connectAsync`` sends ``v{Min}..{Max}`` and the
    # server picks min(server max, our max). ``MinClientVersion`` is TWS /
    # IB Gateway 10.51 (server 226), the oldest IBKR accepts; a server
    # older than that is refused at the handshake. ``MaxClientVersion`` is
    # the newest server version this client knows; bumping it must come
    # with the fields of every gate in between (see
    # ``ib_async/_server_versions.py``).
    MinClientVersion = MIN_CLIENT_VER
    MaxClientVersion = MAX_CLIENT_VER

    DISCONNECTED, CONNECTING, CONNECTED = range(3)

    def __init__(self, wrapper, tally: Tally | None = None):
        self.wrapper = wrapper
        # The session's counters (ib_async.runtime); IB passes its wrapper's.
        self.tally = Tally() if tally is None else tally
        self.decoder = Decoder(wrapper, 0, self.tally)
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
        # Set while connectAsync waits for the API to start. A disconnect
        # before the start fails it, so connectAsync raises at once.
        self._apiStarting: asyncio.Future[None] | None = None
        self.reset()

    def reset(self):
        self.connState = Client.DISCONNECTED
        self._apiReady = False
        # The server's error from before the API started, such as 326
        # for a client id already in use. TWS closes the socket after it.
        self._refusal = ""
        self._serverVersion = 0
        self._data = b""
        self._hasReqId = False
        self._reqIdSeq = 0
        self._accounts = []
        self._startTime = time.time()
        # Traffic is counted once, in the session's tally. The current
        # connection's is what the tally counts after these.
        self._framesSentBefore = self.tally.framesSent
        self._bytesSentBefore = self.tally.bytesSent
        self._framesReceivedBefore = self.tally.framesReceived
        self._bytesReceivedBefore = self.tally.bytesReceived
        self._isThrottling = False
        self._msgQ: deque[bytes] = deque()
        self._timeQ: deque[float] = deque()

    def serverVersion(self) -> int:
        return self._serverVersion

    def sendProto(self, canonicalMsgId: int, serialized: bytes) -> None:
        """Send a protobuf-framed message.

        Wire framing: 4-byte big-endian length prefix, then 4-byte
        big-endian wire ``msgId = canonical + PROTOBUF_MSG_ID``, then the
        serialized protobuf body.

        The frame goes through ``sendMsg``, the one outbound queue, so
        every request keeps its order and stays within the
        ``MaxRequests`` / ``RequestsInterval`` pacing budget. Request
        order and IBKR's pacing limits matter most for orders.

        Raises ``ConnectionError`` when not connected: the socket would
        drop the frame without a word, and the request with it.
        """
        if not self.isConnected():
            raise ConnectionError("Not connected")
        wireMsgId = canonicalMsgId + PROTOBUF_MSG_ID
        body = struct.pack(">I", wireMsgId) + serialized
        self.sendMsg(body)

    def _request(self, canonicalMsgId: int, proto: Message) -> None:
        """Send request ``proto`` as message ``canonicalMsgId``."""
        self.sendProto(canonicalMsgId, proto.SerializeToString())

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
            self.tally.bytesReceived - self._bytesReceivedBefore,
            self.conn.numBytesSent,
            self.tally.framesReceived - self._framesReceivedBefore,
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

        The value is sent as the START_API request's
        ``optionalCapabilities``. Must be called before ``connectAsync``
        to take effect — the
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
            self.tally.connectAttempts += 1
            self.host = host
            self.port = int(port)
            self.clientId = int(clientId)
            self.connState = Client.CONNECTING
            self._apiStarting = getLoop().create_future()
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
            self._counted(msg)
            await asyncio.wait_for(self._apiStarting, timeout)
            self._logger.info("API connection ready")
        except BaseException as e:
            self.tally.connectFailures += 1
            self.disconnect()
            msg = f"API connection failed: {e!r}"
            self._logger.error(msg)
            self.apiError.emit(msg)
            if isinstance(e, ConnectionRefusedError):
                self._logger.error("Make sure API port on TWS/IBG is open")
            raise
        finally:
            # The future lives only for this call. A refused or timed-out
            # socket connect raises before the await, and disconnect() then
            # fails the future with nobody waiting on it, so read its
            # failure here; otherwise the loop reports it as never retrieved.
            starting, self._apiStarting = self._apiStarting, None
            if starting is not None and starting.done() and not starting.cancelled():
                starting.exception()

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
        self._failApiStart("Disconnected before the API started")
        self.conn.disconnect()
        if wasReady:
            self.wrapper.connectionClosed()
        self.reset()
        if wasReady:
            self.apiEnd.emit()

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
            framed = self._prefix(msg)
            self.conn.sendMsg(framed)
            self._counted(framed)
            times.append(t)
            if self._logger.isEnabledFor(logging.DEBUG):
                self._logger.debug(">>> %r", msg)

        if msgs:
            self.tally.mostQueued = max(self.tally.mostQueued, len(msgs))
            if not self._isThrottling:
                self._isThrottling = True
                self.tally.throttleStarts += 1
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

    def _counted(self, frame: bytes) -> None:
        """Count a frame written to the socket."""
        self.tally.framesSent += 1
        self.tally.bytesSent += len(frame)

    def connectionState(self) -> ConnectionState:
        """The connection, as :class:`ib_async.runtime.ConnectionState`."""
        return ConnectionState(
            phase=_PHASES[self.connState],
            apiReady=self._apiReady,
            host=self.host,
            port=self.port,
            clientId=self.clientId,
            serverVersion=self._serverVersion or None,
            accounts=tuple(self.wrapper.accounts),
        )

    def transportState(self) -> TransportState:
        """The current connection's traffic and pacing, as
        :class:`ib_async.runtime.TransportState`."""
        tally = self.tally
        return TransportState(
            framesSent=tally.framesSent - self._framesSentBefore,
            bytesSent=tally.bytesSent - self._bytesSentBefore,
            framesReceived=tally.framesReceived - self._framesReceivedBefore,
            bytesReceived=tally.bytesReceived - self._bytesReceivedBefore,
            throttling=self._isThrottling,
            queuedFrames=len(self._msgQ),
            maxRequests=self.MaxRequests,
            requestsInterval=float(self.RequestsInterval),
        )

    def _onSocketHasData(self, data):
        debug = self._logger.isEnabledFor(logging.DEBUG)
        if self._tcpDataArrived:
            self._tcpDataArrived()

        self._data += data
        tally = self.tally
        tally.bytesReceived += len(data)

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
            tally.framesReceived += 1

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
                            self._startedApi()
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
                    self._onSocketDisconnected(
                        f"TWS / IB Gateway server version {self._serverVersion} "
                        f"is older than {self.MinClientVersion} (TWS API 10.51), "
                        "the oldest ib_async supports"
                    )
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
                        self._startedApi()

                # decode and handle the message
                self.decoder.interpret(fields)

        if self._tcpDataProcessed:
            self._tcpDataProcessed()

    def _startedApi(self) -> None:
        self._apiReady = True
        self.tally.connects += 1
        if self._apiStarting is not None and not self._apiStarting.done():
            self._apiStarting.set_result(None)
        self.apiStart.emit()

    def _failApiStart(self, reason: str) -> None:
        if self._apiStarting is not None and not self._apiStarting.done():
            self._apiStarting.set_exception(ConnectionError(reason))

    def startupError(self, errorCode: int, errorString: str) -> None:
        """Record a server error that arrived before the API started.

        TWS sends an error such as 326 (client id already in use) and
        then closes the socket. The close fails ``connectAsync`` with
        this error as the reason. After the API starts this does nothing.
        """
        if not self._apiReady:
            self._refusal = f"Error {errorCode}: {errorString}"

    def _onSocketDisconnected(self, msg):
        wasReady = self.isReady()
        if not self.isConnected():
            self._logger.info("Disconnected.")
        elif not msg:
            if self._refusal:
                msg = f"Peer closed connection after {self._refusal}"
            else:
                msg = "Peer closed connection."
                if not wasReady:
                    msg += f" clientId {self.clientId} already in use?"
        # The socket is gone: a request from an event handler below raises
        # ConnectionError instead of being dropped.
        self.connState = Client.DISCONNECTED

        if msg:
            self._logger.error(msg)
            self.apiError.emit(msg)

        if not wasReady:
            self._failApiStart(
                self._refusal or msg or "Peer closed connection during the handshake"
            )

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

    # client request methods: each sends its request's protobuf message

    def reqMktData(
        self,
        reqId,
        contract,
        genericTickList,
        snapshot,
        regulatorySnapshot,
        mktDataOptions,
    ):
        self._request(
            _M.REQ_MKT_DATA,
            _converters.market_data.createMarketDataRequestProto(
                reqId,
                contract,
                genericTickList,
                snapshot,
                regulatorySnapshot,
                marketDataOptions=mktDataOptions,
            ),
        )

    def cancelMktData(self, reqId):
        self._request(
            _M.CANCEL_MKT_DATA,
            _converters.market_data.createCancelMarketDataProto(reqId),
        )

    def placeOrder(self, orderId, contract, order):
        # IBKR sometimes writes ``volatility`` back into a live order that
        # is not a VOL order, then rejects a modification that sends it.
        # Only a VOL order may carry it, so it is cleared for any other
        # order before the request is built; None leaves it out.
        if not order.orderType.startswith("VOL"):
            order.volatility = None

        self._request(
            _M.PLACE_ORDER,
            _converters.orders.createPlaceOrderRequestProto(orderId, contract, order),
        )

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

        self._request(
            _M.CANCEL_ORDER,
            _converters.orders.createCancelOrderRequestProto(
                orderId,
                manualOrderCancelTime=orderCancel.manualOrderCancelTime,
                extOperator=orderCancel.extOperator,
                manualOrderIndicator=orderCancel.manualOrderIndicator,
            ),
        )

    def reqOpenOrders(self):
        self._request(
            _M.REQ_OPEN_ORDERS, _converters.orders.createOpenOrdersRequestProto()
        )

    def reqAccountUpdates(self, subscribe, acctCode):
        self._request(
            _M.REQ_ACCT_DATA,
            _converters.accounts.createAccountDataRequestProto(subscribe, acctCode),
        )

    def reqExecutions(self, reqId, execFilter):
        self._request(
            _M.REQ_EXECUTIONS,
            _converters.orders.createExecutionRequestProto(reqId, execFilter),
        )

    def reqIds(self, numIds):
        self._request(_M.REQ_IDS, _converters.rest.createIdsRequestProto(numIds))

    def reqContractDetails(self, reqId, contract):
        self._request(
            _M.REQ_CONTRACT_DATA,
            _converters.contracts.createContractDataRequestProto(reqId, contract),
        )

    def reqMktDepth(self, reqId, contract, numRows, isSmartDepth, mktDepthOptions):
        self._request(
            _M.REQ_MKT_DEPTH,
            _converters.market_data.createMarketDepthRequestProto(
                reqId,
                contract,
                numRows,
                isSmartDepth,
                marketDepthOptions=mktDepthOptions,
            ),
        )

    def cancelMktDepth(self, reqId, isSmartDepth):
        self._request(
            _M.CANCEL_MKT_DEPTH,
            _converters.market_data.createCancelMarketDepthProto(reqId, isSmartDepth),
        )

    def reqNewsBulletins(self, allMsgs):
        self._request(
            _M.REQ_NEWS_BULLETINS,
            _converters.news.createNewsBulletinsRequestProto(allMsgs),
        )

    def cancelNewsBulletins(self):
        self._request(
            _M.CANCEL_NEWS_BULLETINS, _converters.news.createCancelNewsBulletinsProto()
        )

    def setServerLogLevel(self, logLevel):
        self._request(
            _M.SET_SERVER_LOGLEVEL,
            _converters.rest.createSetServerLogLevelRequestProto(logLevel),
        )

    def reqAutoOpenOrders(self, bAutoBind):
        self._request(
            _M.REQ_AUTO_OPEN_ORDERS,
            _converters.orders.createAutoOpenOrdersRequestProto(bAutoBind),
        )

    def reqAllOpenOrders(self):
        self._request(
            _M.REQ_ALL_OPEN_ORDERS, _converters.orders.createAllOpenOrdersRequestProto()
        )

    def reqManagedAccts(self):
        self._request(
            _M.REQ_MANAGED_ACCTS,
            _converters.accounts.createManagedAccountsRequestProto(),
        )

    def requestFA(self, faData):
        # IBKR no longer supports FA profiles (faData 2): refuse the
        # request here rather than send one no server answers.
        if int(faData) == 2:
            raise ValueError(
                "FA profiles (faDataType 2) are not supported by TWS / IB Gateway 10.51"
            )
        self._request(_M.REQ_FA, _converters.accounts.createFARequestProto(faData))

    def replaceFA(self, reqId, faData, cxml):
        # IBKR no longer supports FA profiles (faData 2): nothing is sent.
        if int(faData) == 2:
            return
        self._request(
            _M.REPLACE_FA,
            _converters.accounts.createFAReplaceProto(reqId, faData, cxml),
        )

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
        self._request(
            _M.REQ_HISTORICAL_DATA,
            _converters.historical.createHistoricalDataRequestProto(
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
            ),
        )

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
        self._request(
            _M.EXERCISE_OPTIONS,
            _converters.rest.createExerciseOptionsRequestProto(
                reqId,
                contract,
                exerciseAction,
                exerciseQuantity,
                account,
                override,
                manualOrderTime=manualOrderTime,
                customerAccount=customerAccount,
                professionalCustomer=professionalCustomer,
            ),
        )

    def reqScannerSubscription(
        self,
        reqId,
        subscription,
        scannerSubscriptionOptions,
        scannerSubscriptionFilterOptions,
    ):
        self._request(
            _M.REQ_SCANNER_SUBSCRIPTION,
            _converters.scanner.createScannerSubscriptionRequestProto(
                reqId,
                subscription,
                scannerSubscriptionOptions=scannerSubscriptionOptions,
                scannerSubscriptionFilterOptions=scannerSubscriptionFilterOptions,
            ),
        )

    def cancelScannerSubscription(self, reqId):
        self._request(
            _M.CANCEL_SCANNER_SUBSCRIPTION,
            _converters.scanner.createCancelScannerSubscriptionProto(reqId),
        )

    def reqScannerParameters(self):
        self._request(
            _M.REQ_SCANNER_PARAMETERS,
            _converters.scanner.createScannerParametersRequestProto(),
        )

    def cancelHistoricalData(self, reqId):
        self._request(
            _M.CANCEL_HISTORICAL_DATA,
            _converters.historical.createCancelHistoricalDataProto(reqId),
        )

    def reqCurrentTime(self):
        self._request(
            _M.REQ_CURRENT_TIME, _converters.rest.createCurrentTimeRequestProto()
        )

    def reqCurrentTimeInMillis(self):
        """Request the IBKR server clock in milliseconds."""
        self._request(
            _M.REQ_CURRENT_TIME_IN_MILLIS,
            _converters.rest.createCurrentTimeInMillisRequestProto(),
        )

    def reqRealTimeBars(
        self, reqId, contract, barSize, whatToShow, useRTH, realTimeBarsOptions
    ):
        self._request(
            _M.REQ_REAL_TIME_BARS,
            _converters.historical.createRealTimeBarsRequestProto(
                reqId,
                contract,
                barSize,
                whatToShow,
                useRTH,
                realTimeBarsOptions=realTimeBarsOptions,
            ),
        )

    def cancelRealTimeBars(self, reqId):
        self._request(
            _M.CANCEL_REAL_TIME_BARS,
            _converters.historical.createCancelRealTimeBarsProto(reqId),
        )

    def calculateImpliedVolatility(
        self, reqId, contract, optionPrice, underPrice, implVolOptions
    ):
        self._request(
            _M.REQ_CALC_IMPLIED_VOLAT,
            _converters.rest.createCalculateImpliedVolatilityRequestProto(
                reqId,
                contract,
                optionPrice,
                underPrice,
                impliedVolatilityOptions=implVolOptions,
            ),
        )

    def calculateOptionPrice(
        self, reqId, contract, volatility, underPrice, optPrcOptions
    ):
        self._request(
            _M.REQ_CALC_OPTION_PRICE,
            _converters.rest.createCalculateOptionPriceRequestProto(
                reqId,
                contract,
                volatility,
                underPrice,
                optionPriceOptions=optPrcOptions,
            ),
        )

    def cancelCalculateImpliedVolatility(self, reqId):
        self._request(
            _M.CANCEL_CALC_IMPLIED_VOLAT,
            _converters.rest.createCancelCalculateImpliedVolatilityProto(reqId),
        )

    def cancelCalculateOptionPrice(self, reqId):
        self._request(
            _M.CANCEL_CALC_OPTION_PRICE,
            _converters.rest.createCancelCalculateOptionPriceProto(reqId),
        )

    def reqGlobalCancel(self, orderCancel=None):
        if orderCancel is None:
            orderCancel = OrderCancel()
        self._request(
            _M.REQ_GLOBAL_CANCEL,
            _converters.orders.createGlobalCancelRequestProto(
                extOperator=orderCancel.extOperator,
                manualOrderIndicator=orderCancel.manualOrderIndicator,
            ),
        )

    def reqMarketDataType(self, marketDataType):
        self._request(
            _M.REQ_MARKET_DATA_TYPE,
            _converters.market_data.createMarketDataTypeRequestProto(marketDataType),
        )

    def reqPositions(self):
        self._request(
            _M.REQ_POSITIONS, _converters.accounts.createPositionsRequestProto()
        )

    def reqAccountSummary(self, reqId, groupName, tags):
        self._request(
            _M.REQ_ACCOUNT_SUMMARY,
            _converters.accounts.createAccountSummaryRequestProto(
                reqId, groupName, tags
            ),
        )

    def cancelAccountSummary(self, reqId):
        self._request(
            _M.CANCEL_ACCOUNT_SUMMARY,
            _converters.accounts.createCancelAccountSummaryProto(reqId),
        )

    def cancelPositions(self):
        self._request(
            _M.CANCEL_POSITIONS, _converters.accounts.createCancelPositionsProto()
        )

    def verifyRequest(self, apiName, apiVersion):
        self._request(
            _M.VERIFY_REQUEST,
            _converters.rest.createVerifyRequestProto(apiName, apiVersion),
        )

    def verifyMessage(self, apiData):
        self._request(
            _M.VERIFY_MESSAGE, _converters.rest.createVerifyMessageRequestProto(apiData)
        )

    def queryDisplayGroups(self, reqId):
        self._request(
            _M.QUERY_DISPLAY_GROUPS,
            _converters.rest.createQueryDisplayGroupsRequestProto(reqId),
        )

    def subscribeToGroupEvents(self, reqId, groupId):
        self._request(
            _M.SUBSCRIBE_TO_GROUP_EVENTS,
            _converters.rest.createSubscribeToGroupEventsRequestProto(reqId, groupId),
        )

    def updateDisplayGroup(self, reqId, contractInfo):
        self._request(
            _M.UPDATE_DISPLAY_GROUP,
            _converters.rest.createUpdateDisplayGroupRequestProto(reqId, contractInfo),
        )

    def unsubscribeFromGroupEvents(self, reqId):
        self._request(
            _M.UNSUBSCRIBE_FROM_GROUP_EVENTS,
            _converters.rest.createUnsubscribeFromGroupEventsRequestProto(reqId),
        )

    def startApi(self):
        self._request(
            _M.START_API,
            _converters.rest.createStartApiRequestProto(self.clientId, self.optCapab),
        )

    def reqPositionsMulti(self, reqId, account, modelCode):
        self._request(
            _M.REQ_POSITIONS_MULTI,
            _converters.accounts.createPositionsMultiRequestProto(
                reqId, account, modelCode
            ),
        )

    def cancelPositionsMulti(self, reqId):
        self._request(
            _M.CANCEL_POSITIONS_MULTI,
            _converters.accounts.createCancelPositionsMultiProto(reqId),
        )

    def reqAccountUpdatesMulti(self, reqId, account, modelCode, ledgerAndNLV):
        self._request(
            _M.REQ_ACCOUNT_UPDATES_MULTI,
            _converters.accounts.createAccountUpdatesMultiRequestProto(
                reqId, account, modelCode, ledgerAndNLV
            ),
        )

    def cancelAccountUpdatesMulti(self, reqId):
        self._request(
            _M.CANCEL_ACCOUNT_UPDATES_MULTI,
            _converters.accounts.createCancelAccountUpdatesMultiProto(reqId),
        )

    def reqSecDefOptParams(
        self,
        reqId,
        underlyingSymbol,
        futFopExchange,
        underlyingSecType,
        underlyingConId,
    ):
        self._request(
            _M.REQ_SEC_DEF_OPT_PARAMS,
            _converters.rest.createSecDefOptParamsRequestProto(
                reqId,
                underlyingSymbol,
                futFopExchange,
                underlyingSecType,
                underlyingConId,
            ),
        )

    def reqSoftDollarTiers(self, reqId):
        self._request(
            _M.REQ_SOFT_DOLLAR_TIERS,
            _converters.rest.createSoftDollarTiersRequestProto(reqId),
        )

    def reqFamilyCodes(self):
        self._request(
            _M.REQ_FAMILY_CODES, _converters.accounts.createFamilyCodesRequestProto()
        )

    def reqMatchingSymbols(self, reqId, pattern):
        self._request(
            _M.REQ_MATCHING_SYMBOLS,
            _converters.rest.createMatchingSymbolsRequestProto(reqId, pattern),
        )

    def reqMktDepthExchanges(self):
        self._request(
            _M.REQ_MKT_DEPTH_EXCHANGES,
            _converters.market_data.createMarketDepthExchangesRequestProto(),
        )

    def reqSmartComponents(self, reqId, bboExchange):
        self._request(
            _M.REQ_SMART_COMPONENTS,
            _converters.rest.createSmartComponentsRequestProto(reqId, bboExchange),
        )

    def reqNewsArticle(self, reqId, providerCode, articleId, newsArticleOptions):
        self._request(
            _M.REQ_NEWS_ARTICLE,
            _converters.news.createNewsArticleRequestProto(
                reqId,
                providerCode,
                articleId,
                newsArticleOptions=newsArticleOptions,
            ),
        )

    def reqNewsProviders(self):
        self._request(
            _M.REQ_NEWS_PROVIDERS, _converters.news.createNewsProvidersRequestProto()
        )

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
        self._request(
            _M.REQ_HISTORICAL_NEWS,
            _converters.news.createHistoricalNewsRequestProto(
                reqId,
                conId,
                providerCodes,
                startDateTime,
                endDateTime,
                totalResults,
                historicalNewsOptions=historicalNewsOptions,
            ),
        )

    def reqHeadTimeStamp(self, reqId, contract, whatToShow, useRTH, formatDate):
        self._request(
            _M.REQ_HEAD_TIMESTAMP,
            _converters.historical.createHeadTimestampRequestProto(
                reqId, contract, useRTH, whatToShow, formatDate
            ),
        )

    def reqHistogramData(self, tickerId, contract, useRTH, timePeriod):
        self._request(
            _M.REQ_HISTOGRAM_DATA,
            _converters.historical.createHistogramDataRequestProto(
                tickerId, contract, bool(useRTH), timePeriod
            ),
        )

    def cancelHistogramData(self, tickerId):
        self._request(
            _M.CANCEL_HISTOGRAM_DATA,
            _converters.historical.createCancelHistogramDataProto(tickerId),
        )

    def cancelHeadTimeStamp(self, reqId):
        self._request(
            _M.CANCEL_HEAD_TIMESTAMP,
            _converters.historical.createCancelHeadTimestampProto(reqId),
        )

    def cancelContractData(self, reqId):
        """Cancel an in-flight reqContractDetails."""
        self._request(
            _M.CANCEL_CONTRACT_DATA,
            _converters.historical.createCancelContractDataProto(reqId),
        )

    def cancelHistoricalTicks(self, reqId):
        """Cancel an in-flight reqHistoricalTicks."""
        self._request(
            _M.CANCEL_HISTORICAL_TICKS,
            _converters.historical.createCancelHistoricalTicksProto(reqId),
        )

    def reqConfig(self, reqId):
        """Fetch the TWS / IB Gateway runtime config. The server replies
        with ``ConfigResponse`` carrying nested LockAndExitConfig /
        ApiConfig / MessageConfig / OrdersConfig sub-messages.
        """
        self._request(_M.REQ_CONFIG, _converters.rest.createConfigRequestProto(reqId))

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
        """Push a TWS / IB Gateway config update. The server replies
        with ``UpdateConfigResponse`` carrying status + changed-fields list.
        """
        self._request(
            _M.UPDATE_CONFIG,
            _converters.rest.createUpdateConfigRequestProto(
                reqId,
                lockAndExit=lockAndExit,
                messages=messages,
                api=api,
                orders=orders,
                acceptedWarnings=acceptedWarnings,
                resetAPIOrderSequence=resetAPIOrderSequence,
            ),
        )

    def reqMarketRule(self, marketRuleId):
        self._request(
            _M.REQ_MARKET_RULE,
            _converters.rest.createMarketRuleRequestProto(marketRuleId),
        )

    def reqPnL(self, reqId, account, modelCode):
        self._request(
            _M.REQ_PNL,
            _converters.scanner.createPnLRequestProto(reqId, account, modelCode),
        )

    def cancelPnL(self, reqId):
        self._request(_M.CANCEL_PNL, _converters.scanner.createCancelPnLProto(reqId))

    def reqPnLSingle(self, reqId, account, modelCode, conid):
        self._request(
            _M.REQ_PNL_SINGLE,
            _converters.scanner.createPnLSingleRequestProto(
                reqId, account, modelCode, conid
            ),
        )

    def cancelPnLSingle(self, reqId):
        self._request(
            _M.CANCEL_PNL_SINGLE, _converters.scanner.createCancelPnLSingleProto(reqId)
        )

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
        self._request(
            _M.REQ_HISTORICAL_TICKS,
            _converters.historical.createHistoricalTicksRequestProto(
                reqId,
                contract,
                startDateTime,
                endDateTime,
                numberOfTicks,
                whatToShow,
                useRth,
                ignoreSize,
                miscOptions=miscOptions,
            ),
        )

    def reqTickByTickData(self, reqId, contract, tickType, numberOfTicks, ignoreSize):
        self._request(
            _M.REQ_TICK_BY_TICK_DATA,
            _converters.market_data.createTickByTickRequestProto(
                reqId, contract, tickType, numberOfTicks, ignoreSize
            ),
        )

    def cancelTickByTickData(self, reqId):
        self._request(
            _M.CANCEL_TICK_BY_TICK_DATA,
            _converters.market_data.createCancelTickByTickProto(reqId),
        )

    def reqCompletedOrders(self, apiOnly):
        self._request(
            _M.REQ_COMPLETED_ORDERS,
            _converters.orders.createCompletedOrdersRequestProto(apiOnly),
        )

    def reqWshMetaData(self, reqId):
        self._request(
            _M.REQ_WSH_META_DATA, _converters.news.createWshMetaDataRequestProto(reqId)
        )

    def cancelWshMetaData(self, reqId):
        self._request(
            _M.CANCEL_WSH_META_DATA,
            _converters.news.createCancelWshMetaDataProto(reqId),
        )

    def reqWshEventData(self, reqId, data: WshEventData):
        self._request(
            _M.REQ_WSH_EVENT_DATA,
            _converters.news.createWshEventDataRequestProto(reqId, data),
        )

    def cancelWshEventData(self, reqId):
        self._request(
            _M.CANCEL_WSH_EVENT_DATA,
            _converters.news.createCancelWshEventDataProto(reqId),
        )

    def reqUserInfo(self, reqId):
        self._request(
            _M.REQ_USER_INFO, _converters.rest.createUserInfoRequestProto(reqId)
        )
