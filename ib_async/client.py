"""Socket client for communicating with Interactive Brokers."""

import asyncio
import logging
import struct
import time
from collections import deque

from eventkit import Event
from google.protobuf.message import Message

from .connection import Connection
from .contract import Contract
from .decoder import Decoder
from .message import MessageId
from .objects import ConnectionStats, WshEventData
from .order import Order, OrderCancel
from .protobuf.AccountSummaryRequest_pb2 import (
    AccountSummaryRequest as AccountSummaryRequestProto,
)
from .protobuf.AllOpenOrdersRequest_pb2 import (
    AllOpenOrdersRequest as AllOpenOrdersRequestProto,
)
from .protobuf.AutoOpenOrdersRequest_pb2 import (
    AutoOpenOrdersRequest as AutoOpenOrdersRequestProto,
)
from .protobuf.CancelAccountSummary_pb2 import (
    CancelAccountSummary as CancelAccountSummaryProto,
)
from .protobuf.CancelFundamentalsData_pb2 import (
    CancelFundamentalsData as CancelFundamentalsDataProto,
)
from .protobuf.CancelHeadTimestamp_pb2 import (
    CancelHeadTimestamp as CancelHeadTimestampProto,
)
from .protobuf.CancelHistoricalData_pb2 import (
    CancelHistoricalData as CancelHistoricalDataProto,
)
from .protobuf.CancelPositions_pb2 import CancelPositions as CancelPositionsProto
from .protobuf.CancelRealTimeBars_pb2 import (
    CancelRealTimeBars as CancelRealTimeBarsProto,
)
from .protobuf.CancelTickByTick_pb2 import (
    CancelTickByTick as CancelTickByTickProto,
)
from .protobuf.CompletedOrdersRequest_pb2 import (
    CompletedOrdersRequest as CompletedOrdersRequestProto,
)
from .protobuf.ContractDataRequest_pb2 import (
    ContractDataRequest as ContractDataRequestProto,
)
from .protobuf.CurrentTimeInMillisRequest_pb2 import (
    CurrentTimeInMillisRequest as CurrentTimeInMillisRequestProto,
)
from .protobuf.CurrentTimeRequest_pb2 import (
    CurrentTimeRequest as CurrentTimeRequestProto,
)
from .protobuf.IdsRequest_pb2 import IdsRequest as IdsRequestProto
from .protobuf.ManagedAccountsRequest_pb2 import (
    ManagedAccountsRequest as ManagedAccountsRequestProto,
)
from .protobuf.OpenOrdersRequest_pb2 import OpenOrdersRequest as OpenOrdersRequestProto
from .protobuf.PositionsRequest_pb2 import PositionsRequest as PositionsRequestProto
from .protobuf.StartApiRequest_pb2 import StartApiRequest as StartApiRequestProto
from .protobuf_converters.account_converters import (
    createAccountDataRequestProto,
    createAccountMultiRequestProto,
    createCancelAccMultiRequestProto,
    createCancelPositionsMultiRequestProto,
    createFamilyCodesRequestProto,
    createFAReplaceProto,
    createFARequestProto,
    createPositionsMultiRequestProto,
    createSoftDollarTiersRequestProto,
    createUserInfoRequestProto,
)
from .protobuf_converters.base_converters import createSetServerLogLevelRequestProto
from .protobuf_converters.contract_converters import (
    createContractProto,
    createMarketRuleRequestProto,
    createMatchingSymbolsRequestProto,
    createSecDefOptParamsRequestProto,
    createSmartComponentsRequestProto,
)
from .protobuf_converters.historical_data_converters import (
    createCancelHistoricalDataProto,
    createFundamentalsDataRequestProto,
    createHeadTimestampRequestProto,
    createHistogramDataRequestProto,
    createHistoricalDataRequestProto,
    createHistoricalTicksRequestProto,
    createRealTimeBarsRequestProto,
)
from .protobuf_converters.market_data_converters import (
    cancelMarketDataProto,
    createCalculateImpliedVolatilityRequestProto,
    createCalculateOptionPriceRequestProto,
    createCancelCalculateImpliedVolatilityProto,
    createCancelCalculateOptionPriceProto,
    createMarketDataRequestProto,
    createMarketDataTypeRequestProto,
    createTickByTickRequestProto,
)
from .protobuf_converters.news_converters import (
    createCancelNewsBulletinsProto,
    createHistoricalNewsRequestProto,
    createNewsArticleRequestProto,
    createNewsBulletinsRequestProto,
    createNewsProvidersRequestProto,
)
from .protobuf_converters.subscription_converters import (
    createCancelPnLProto,
    createCancelScannerSubscriptionProto,
    createPnLRequestProto,
    createPnLSingleRequestProto,
    createScannerParametersRequestProto,
    createScannerSubscriptionRequestProto,
)
from .protobuf_converters.trade_converters import (
    createCancelOrderRequestProto,
    createExecutionRequestProto,
    createExerciseOptionsRequestProto,
    createGlobalCancelRequestProto,
    createPlaceOrderRequestProto,
)
from .util import getLoop, run


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

    MinClientVersion = 100
    MaxClientVersion = 216  # Updated to support Protobuf

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
        self._hasReqId = False  # Initialize _hasReqId in __init__
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

    def useProtoBuf(self) -> bool:
        result = self.serverVersion() >= 201  # min protobuf server version
        return result

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

    def sendProto(self, msgId: int, proto: Message):
        """Serialize and send the given protobuf message."""
        if not self.isConnected():
            raise ConnectionError("Not connected")
        body = proto.SerializeToString()
        header = msgId.to_bytes(4, "big")
        msg = header + body
        self.sendMsg(msg)

    def sendMsg(self, msg: bytes):
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
                self._logger.debug(
                    ">>> id %s: %s",
                    MessageId.OUT(int.from_bytes(msg[:4], "big")).name,
                    msg,
                )

        if msgs:
            if not self._isThrottling:
                self._isThrottling = True
                self.throttleStart.emit()
                self._logger.info("Started to throttle requests")
            loop.call_at(times[0] + self.RequestsInterval, self.sendMsg)
        else:
            if self._isThrottling:
                self._isThrottling = False
                self.throttleEnd.emit()
                self._logger.info("Stopped to throttle requests")

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
                "Connecting to %s:%s with clientId %s...", host, port, clientId
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

    def _prefix(self, msg):
        """Prefix a message with its length."""
        return struct.pack(f">I{len(msg)}s", len(msg), msg)

    def _onSocketHasData(self, data):
        debug = self._logger.isEnabledFor(logging.DEBUG)
        if self._tcpDataArrived:
            self._tcpDataArrived()

        self._data += data
        self._numBytesRecv += len(data)

        while True:
            if len(self._data) < 4:
                # Not enough data for the length prefix
                break

            # 4-byte prefix tells the message length
            msgEnd = 4 + struct.unpack(">I", self._data[:4])[0]
            if len(self._data) < msgEnd:
                # Incomplete message in buffer
                break

            payload = self._data[4:msgEnd]
            self._data = self._data[msgEnd:]
            self._numMsgRecv += 1

            if not self._serverVersion:
                # connection handshake
                # First message is always the legacy server version string
                fields = payload.decode(errors="backslashreplace").split("\0")
                fields.pop()

                if debug:
                    self._logger.debug("<<< %s", ",".join(fields))

                version, _connTime = fields
                self._serverVersion = int(version)
                self._logger.info(
                    "Established connection, server version %s", self._serverVersion
                )

                if self._serverVersion < 201:  # MIN_SERVER_VER_PROTOBUF
                    self._onSocketDisconnected(
                        f"Server version {self._serverVersion} does not support"
                        " Protobuf. Disconnecting."
                    )
                    return

                self.decoder.serverVersion = self._serverVersion
                self.connState = Client.CONNECTED
                self.startApi()
                self._logger.info("Logged on to server version %s", self._serverVersion)
            else:
                # we are connected
                if not self._apiReady:
                    if self._hasReqId and self._accounts:
                        self._apiReady = True
                        self.apiStart.emit()
                if debug:
                    self._logger.debug(
                        "<<< id %s: %r",
                        MessageId.IN(int.from_bytes(payload[:4], "big")).name,
                        payload,
                    )
                # After handshake, all incoming messages are treated as Protobuf
                # The entire payload (ID + data) is passed to the decoder
                self.decoder.processProtoBuf(payload)

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

        self.wrapper.setEventsDone()
        if wasReady:
            self.wrapper.connectionClosed()

        self.reset()

        if wasReady:
            self.apiEnd.emit()

    def startApi(self):
        startApiRequestProto = StartApiRequestProto()
        if self.clientId >= 0:  # Assuming 0 or negative clientId is invalid
            startApiRequestProto.clientId = self.clientId
        if self.optCapab:  # Only set if not an empty string
            startApiRequestProto.optionalCapabilities = self.optCapab
        self.sendProto(MessageId.OUT.START_API, startApiRequestProto)

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
        mktDataRequestProto = createMarketDataRequestProto(
            reqId,
            contract,
            genericTickList,
            snapshot,
            regulatorySnapshot,
            mktDataOptions,
        )
        self.sendProto(MessageId.OUT.REQ_MKT_DATA, mktDataRequestProto)

    def cancelMktData(self, reqId):
        self.sendProto(
            MessageId.OUT.CANCEL_MKT_DATA,
            cancelMarketDataProto(reqId),
        )

    def placeOrder(self, orderId: int, contract: Contract, order: Order):
        orderRequestProto = createPlaceOrderRequestProto(orderId, contract, order)
        self.sendProto(MessageId.OUT.PLACE_ORDER, orderRequestProto)

    def cancelOrder(self, orderId: int, orderCancel: OrderCancel):
        self.sendProto(
            MessageId.OUT.CANCEL_ORDER,
            createCancelOrderRequestProto(orderId, orderCancel),
        )

    def reqOpenOrders(self):
        openOrdersRequestProto = OpenOrdersRequestProto()
        self.sendProto(
            MessageId.OUT.REQ_OPEN_ORDERS,
            openOrdersRequestProto,
        )

    def reqAccountUpdates(self, subscribe, acctCode):
        proto = createAccountDataRequestProto(subscribe, acctCode)
        self.sendProto(MessageId.OUT.REQ_ACCT_DATA, proto)

    def reqExecutions(self, reqId, execFilter):
        executionRequestProto = createExecutionRequestProto(reqId, execFilter)
        self.sendProto(MessageId.OUT.REQ_EXECUTIONS, executionRequestProto)

    def reqIds(self, numIds: int):
        """Request a new request ID."""
        self._logger.debug("Calling reqIds (Protobuf)")
        proto = IdsRequestProto()
        proto.numIds = numIds
        self.sendProto(MessageId.OUT.REQ_IDS, proto)

    def reqContractDetails(self, reqId, contract):
        contractDetailsRequestProto = ContractDataRequestProto()
        contractDetailsRequestProto.reqId = reqId
        contractProto = createContractProto(contract, None)
        contractDetailsRequestProto.contract.CopyFrom(contractProto)
        self.sendProto(
            MessageId.OUT.REQ_CONTRACT_DATA,
            contractDetailsRequestProto,
        )

    def reqMktDepth(self, reqId, contract, numRows, isSmartDepth, mktDepthOptions):
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
        self.send(11, 1, reqId, isSmartDepth)

    def reqNewsBulletins(self, allMsgs):
        self.sendProto(
            MessageId.OUT.REQ_NEWS_BULLETINS,
            createNewsBulletinsRequestProto(allMsgs),
        )

    def cancelNewsBulletins(self):
        self.sendProto(
            MessageId.OUT.CANCEL_NEWS_BULLETINS,
            createCancelNewsBulletinsProto(),
        )

    def setServerLogLevel(self, logLevel):
        self.sendProto(
            MessageId.OUT.SET_SERVER_LOGLEVEL,
            createSetServerLogLevelRequestProto(logLevel),
        )

    def reqAutoOpenOrders(self, bAutoBind: bool):
        autoOpenOrdersRequestProto = AutoOpenOrdersRequestProto()
        autoOpenOrdersRequestProto.autoBind = bAutoBind
        self.sendProto(
            MessageId.OUT.REQ_AUTO_OPEN_ORDERS,
            autoOpenOrdersRequestProto,
        )

    def reqAllOpenOrders(self):
        allOpenOrdersRequestProto = AllOpenOrdersRequestProto()
        self.sendProto(
            MessageId.OUT.REQ_ALL_OPEN_ORDERS,
            allOpenOrdersRequestProto,
        )

    def reqManagedAccts(self):
        self._logger.debug("Calling reqManagedAccts (Protobuf)")
        proto = ManagedAccountsRequestProto()
        self.sendProto(MessageId.OUT.REQ_MANAGED_ACCTS, proto)

    def requestFA(self, faData):
        faRequestProto = createFARequestProto(faData)
        self.sendProto(MessageId.OUT.REQ_FA, faRequestProto)

    def replaceFA(self, reqId, faData, cxml):
        faReplaceProto = createFAReplaceProto(reqId, faData, cxml)
        self.sendProto(MessageId.OUT.REPLACE_FA, faReplaceProto)

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
        historicalDataRequestProto = createHistoricalDataRequestProto(
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
        )

        self.sendProto(
            MessageId.OUT.REQ_HISTORICAL_DATA,
            historicalDataRequestProto,
        )

    def exerciseOptions(
        self,
        reqId,
        contract,
        exerciseAction,
        exerciseQuantity,
        account,
        override,
        manualOrderTime,
        customerAccount,
        professionalCustomer,
    ):
        self.sendProto(
            MessageId.OUT.EXERCISE_OPTIONS,
            createExerciseOptionsRequestProto(
                reqId,
                contract,
                exerciseAction,
                exerciseQuantity,
                account,
                override,
                manualOrderTime,
                customerAccount,
                professionalCustomer,
            ),
        )

    def reqScannerSubscription(
        self,
        reqId,
        subscription,
        scannerSubscriptionOptions,
        scannerSubscriptionFilterOptions,
    ):
        self.sendProto(
            MessageId.OUT.REQ_SCANNER_SUBSCRIPTION,
            createScannerSubscriptionRequestProto(
                reqId,
                subscription,
                scannerSubscriptionOptions,
                scannerSubscriptionFilterOptions,
            ),
        )

    def cancelScannerSubscription(self, reqId):
        self.sendProto(
            MessageId.OUT.CANCEL_SCANNER_SUBSCRIPTION,
            createCancelScannerSubscriptionProto(reqId),
        )

    def reqScannerParameters(self):
        self.sendProto(
            MessageId.OUT.REQ_SCANNER_PARAMETERS, createScannerParametersRequestProto()
        )

    def cancelHistoricalData(self, reqId):
        cancelRequest = CancelHistoricalDataProto()
        cancelRequest.reqId = reqId
        self.sendProto(MessageId.OUT.CANCEL_HISTORICAL_DATA, cancelRequest)

    def reqCurrentTime(self):
        currentTimeRequestProto = CurrentTimeRequestProto()
        self.sendProto(
            MessageId.OUT.REQ_CURRENT_TIME,
            currentTimeRequestProto,
        )

    def reqCurrentTimeMili(self):
        currentTimeMiliRequestProto = CurrentTimeInMillisRequestProto()
        self.sendProto(
            MessageId.OUT.REQ_CURRENT_TIME_IN_MILLIS,
            currentTimeMiliRequestProto,
        )

    def reqRealTimeBars(
        self, reqId, contract, barSize, whatToShow, useRTH, realTimeBarsOptions
    ):
        realTimeBarsRequestProto = createRealTimeBarsRequestProto(
            reqId, contract, barSize, whatToShow, useRTH, realTimeBarsOptions
        )
        self.sendProto(
            MessageId.OUT.REQ_REAL_TIME_BARS,
            realTimeBarsRequestProto,
        )

    def cancelRealTimeBars(self, reqId):
        self.sendProto(
            MessageId.OUT.CANCEL_REAL_TIME_BARS,
            CancelRealTimeBarsProto(reqId=reqId),
        )

    def reqFundamentalData(self, reqId, contract, reportType, fundamentalDataOptions):
        fundamentalsDataRequestProto = createFundamentalsDataRequestProto(
            reqId, contract, reportType, fundamentalDataOptions
        )
        self.sendProto(
            MessageId.OUT.REQ_FUNDAMENTAL_DATA,
            fundamentalsDataRequestProto,
        )

    def cancelFundamentalData(self, reqId):
        cancelFundamentalProto = CancelFundamentalsDataProto()
        cancelFundamentalProto.reqId = reqId
        self.sendProto(
            MessageId.OUT.CANCEL_FUNDAMENTAL_DATA,
            cancelFundamentalProto,
        )

    def calculateImpliedVolatility(
        self, reqId, contract, optionPrice, underPrice, implVolOptions
    ):
        iv_request = createCalculateImpliedVolatilityRequestProto(
            reqId, contract, optionPrice, underPrice, implVolOptions
        )
        self.sendProto(
            MessageId.OUT.REQ_CALC_IMPLIED_VOLAT,
            iv_request,
        )

    def calculateOptionPrice(
        self, reqId, contract, volatility, underPrice, optPrcOptions
    ):
        opt_price = createCalculateOptionPriceRequestProto(
            reqId, contract, volatility, underPrice, optPrcOptions
        )
        self.sendProto(MessageId.OUT.REQ_CALC_OPTION_PRICE, opt_price)

    def cancelCalculateImpliedVolatility(self, reqId):
        self.sendProto(
            MessageId.OUT.CANCEL_CALC_IMPLIED_VOLAT,
            createCancelCalculateImpliedVolatilityProto(reqId=reqId),
        )

    def cancelCalculateOptionPrice(self, reqId):
        self.sendProto(
            MessageId.OUT.CANCEL_CALC_OPTION_PRICE,
            createCancelCalculateOptionPriceProto(reqId=reqId),
        )

    def reqGlobalCancel(self, orderCancel: OrderCancel):
        self.sendProto(
            MessageId.OUT.REQ_GLOBAL_CANCEL, createGlobalCancelRequestProto(orderCancel)
        )

    def reqMarketDataType(self, marketDataType):
        self.sendProto(
            MessageId.OUT.REQ_MARKET_DATA_TYPE,
            createMarketDataTypeRequestProto(marketDataType=marketDataType),
        )

    def reqPositions(self):
        self.sendProto(MessageId.OUT.REQ_POSITIONS, PositionsRequestProto())

    def cancelPositions(self):
        self.sendProto(
            MessageId.OUT.CANCEL_POSITIONS,
            CancelPositionsProto(),
        )

    def reqPositionsMulti(self, reqId, account, modelCode):
        self.sendProto(
            MessageId.OUT.REQ_POSITIONS_MULTI,
            createPositionsMultiRequestProto(reqId, account, modelCode),
        )

    def cancelPositionsMulti(self, reqId):
        self.sendProto(
            MessageId.OUT.CANCEL_POSITIONS_MULTI,
            createCancelPositionsMultiRequestProto(reqId),
        )

    def reqAccountSummary(self, reqId, groupName, tags):
        proto = AccountSummaryRequestProto(reqId=reqId, group=groupName, tags=tags)
        self.sendProto(MessageId.OUT.REQ_ACCOUNT_SUMMARY, proto)

    def cancelAccountSummary(self, reqId):
        cancelAccountSummaryProto = CancelAccountSummaryProto(reqId=reqId)
        self.sendProto(
            MessageId.OUT.CANCEL_ACCOUNT_SUMMARY,
            cancelAccountSummaryProto,
        )

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

    def verifyAndAuthRequest(self, apiName, apiVersion, opaqueIsvKey):
        self.send(72, 1, apiName, apiVersion, opaqueIsvKey)

    def verifyAndAuthMessage(self, apiData, xyzResponse):
        self.send(73, 1, apiData, xyzResponse)

    def reqAccountUpdatesMulti(
        self, reqId: int, account: str, modelCode: str, ledgerAndNLV: bool
    ):
        reqAccUpdatesMultiProto = createAccountMultiRequestProto(
            reqId, account, modelCode, ledgerAndNLV
        )
        self.sendProto(
            MessageId.OUT.REQ_ACCOUNT_UPDATES_MULTI,
            reqAccUpdatesMultiProto,
        )

    def cancelAccountUpdatesMulti(self, reqId):
        self.sendProto(
            MessageId.OUT.CANCEL_ACCOUNT_UPDATES_MULTI,
            createCancelAccMultiRequestProto(reqId),
        )

    def reqSecDefOptParams(
        self,
        reqId,
        underlyingSymbol,
        futFopExchange,
        underlyingSecType,
        underlyingConId,
    ):
        secDefOptParamsRequestProto = createSecDefOptParamsRequestProto(
            reqId,
            underlyingSymbol,
            futFopExchange,
            underlyingSecType,
            underlyingConId,
        )
        self.sendProto(
            MessageId.OUT.REQ_SEC_DEF_OPT_PARAMS,
            secDefOptParamsRequestProto,
        )

    def reqSoftDollarTiers(self, reqId):
        self.sendProto(
            MessageId.OUT.REQ_SOFT_DOLLAR_TIERS,
            createSoftDollarTiersRequestProto(reqId),
        )

    def reqFamilyCodes(self):
        self.sendProto(
            MessageId.OUT.REQ_FAMILY_CODES,
            createFamilyCodesRequestProto(),
        )

    def reqMatchingSymbols(self, reqId, pattern):
        matchingSymbolsRequestProto = createMatchingSymbolsRequestProto(reqId, pattern)
        self.sendProto(
            MessageId.OUT.REQ_MATCHING_SYMBOLS,
            matchingSymbolsRequestProto,
        )

    def reqMktDepthExchanges(self):
        self.send(82)

    def reqSmartComponents(self, reqId, bboExchange):
        self.sendProto(
            MessageId.OUT.REQ_SMART_COMPONENTS,
            createSmartComponentsRequestProto(reqId, bboExchange),
        )

    def reqNewsArticle(self, reqId, providerCode, articleId, newsArticleOptions):
        self.sendProto(
            MessageId.OUT.REQ_NEWS_ARTICLE,
            createNewsArticleRequestProto(
                reqId, providerCode, articleId, newsArticleOptions
            ),
        )

    def reqNewsProviders(self):
        self.sendProto(
            MessageId.OUT.REQ_NEWS_PROVIDERS,
            createNewsProvidersRequestProto(),
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
        self.sendProto(
            MessageId.OUT.REQ_HISTORICAL_NEWS,
            createHistoricalNewsRequestProto(
                reqId,
                conId,
                providerCodes,
                startDateTime,
                endDateTime,
                totalResults,
                historicalNewsOptions,
            ),
        )

    def reqHeadTimeStamp(self, reqId, contract, whatToShow, useRTH, formatDate):
        headTimestampRequestProto = createHeadTimestampRequestProto(
            reqId, contract, whatToShow, useRTH != 0, formatDate
        )
        self.sendProto(
            MessageId.OUT.REQ_HEAD_TIMESTAMP,
            headTimestampRequestProto,
        )

    def cancelHeadTimeStamp(self, reqId):
        cancelHeadTimestampRequestProto = CancelHeadTimestampProto()
        cancelHeadTimestampRequestProto.reqId = reqId
        self.sendProto(
            MessageId.OUT.CANCEL_HEAD_TIMESTAMP,
            cancelHeadTimestampRequestProto,
        )

    def reqHistogramData(self, tickerId, contract, useRTH, timePeriod):
        self.sendProto(
            MessageId.OUT.REQ_HISTOGRAM_DATA,
            createHistogramDataRequestProto(tickerId, contract, useRTH, timePeriod),
        )

    def cancelHistogramData(self, reqId):
        self.sendProto(
            MessageId.OUT.CANCEL_HISTOGRAM_DATA,
            createCancelHistoricalDataProto(reqId),
        )

    def reqMarketRule(self, marketRuleId: int):
        marketRuleRequestProto = createMarketRuleRequestProto(marketRuleId)
        self.sendProto(MessageId.OUT.REQ_MARKET_RULE, marketRuleRequestProto)

    def reqPnL(self, reqId, account, modelCode):
        self.sendProto(
            MessageId.OUT.REQ_PNL, createPnLRequestProto(reqId, account, modelCode)
        )

    def cancelPnL(self, reqId):
        self.sendProto(MessageId.OUT.CANCEL_PNL, createCancelPnLProto(reqId))

    def reqPnLSingle(self, reqId, account, modelCode, conid):
        self.sendProto(
            MessageId.OUT.REQ_PNL_SINGLE,
            createPnLSingleRequestProto(reqId, account, modelCode, conid),
        )

    def cancelPnLSingle(self, reqId):
        self.sendProto(MessageId.OUT.CANCEL_PNL_SINGLE, createCancelPnLProto(reqId))

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
        historicalTicksRequestProto = createHistoricalTicksRequestProto(
            reqId,
            contract,
            startDateTime,
            endDateTime,
            numberOfTicks,
            whatToShow,
            useRth,
            ignoreSize,
            miscOptions,
        )
        self.sendProto(
            MessageId.OUT.REQ_HISTORICAL_TICKS,
            historicalTicksRequestProto,
        )

    def reqTickByTickData(self, reqId, contract, tickType, numberOfTicks, ignoreSize):
        tickByTickRequestProto = createTickByTickRequestProto(
            reqId, contract, tickType, numberOfTicks, ignoreSize
        )
        self.sendProto(
            MessageId.OUT.REQ_TICK_BY_TICK_DATA,
            tickByTickRequestProto,
        )

    def cancelTickByTickData(self, reqId):
        self.sendProto(
            MessageId.OUT.CANCEL_TICK_BY_TICK_DATA,
            CancelTickByTickProto(reqId=reqId),
        )

    def reqCompletedOrders(self, apiOnly: bool):
        completedOrdersRequestProto = CompletedOrdersRequestProto()
        completedOrdersRequestProto.apiOnly = apiOnly
        self.sendProto(
            MessageId.OUT.REQ_COMPLETED_ORDERS,
            completedOrdersRequestProto,
        )

    def reqWshMetaData(self, reqId):
        self.send(100, reqId)

    def cancelWshMetaData(self, reqId):
        self.send(101, reqId)

    def reqWshEventData(self, reqId, data: WshEventData):
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
        self.send(103, reqId)

    def reqUserInfo(self, reqId):
        self.sendProto(
            MessageId.OUT.REQ_USER_INFO,
            createUserInfoRequestProto(reqId),
        )
