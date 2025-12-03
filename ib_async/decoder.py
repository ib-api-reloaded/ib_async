"""Deserialize and dispatch messages."""

import logging

from ib_async.protobuf_converters.subscription_converters import createScannerDataList

from .contract import (
    Contract,
    ContractDescription,
    ContractDetails,
    DeltaNeutralContract,
)
from .message import MessageId
from .objects import (
    DepthMktDataDescription,
    FamilyCode,
    HistogramData,
    HistoricalTickBidAsk,
    HistoricalTickLast,
    NewsProvider,
    PriceIncrement,
    SmartComponent,
    SoftDollarTier,
    TagValue,
    TickType,
)
from .order import OrderStatus
from .protobuf.AccountDataEnd_pb2 import AccountDataEnd as AccountDataEndProto
from .protobuf.AccountSummary_pb2 import AccountSummary as AccountSummaryProto
from .protobuf.AccountSummaryEnd_pb2 import (
    AccountSummaryEnd as AccountSummaryEndProto,
)
from .protobuf.AccountUpdateMulti_pb2 import (
    AccountUpdateMulti as AccountUpdateMultiProto,
)
from .protobuf.AccountUpdateMultiEnd_pb2 import (
    AccountUpdateMultiEnd as AccountUpdateMultiEndProto,
)
from .protobuf.AccountUpdateTime_pb2 import AccountUpdateTime as AccountUpdateTimeProto
from .protobuf.AccountValue_pb2 import AccountValue as AccountValueProto
from .protobuf.CommissionAndFeesReport_pb2 import (
    CommissionAndFeesReport as CommissionReportProto,
)
from .protobuf.CompletedOrder_pb2 import CompletedOrder as CompletedOrderProto
from .protobuf.CompletedOrdersEnd_pb2 import (
    CompletedOrdersEnd as CompletedOrdersEndProto,
)
from .protobuf.ContractData_pb2 import ContractData as ContractDataProto
from .protobuf.ContractDataEnd_pb2 import ContractDataEnd as ContractDataEndProto
from .protobuf.CurrentTime_pb2 import CurrentTime as CurrentTimeProto
from .protobuf.CurrentTimeInMillis_pb2 import (
    CurrentTimeInMillis as CurrentTimeInMillisProto,
)
from .protobuf.ErrorMessage_pb2 import ErrorMessage as ErrorMessageProto
from .protobuf.ExecutionDetails_pb2 import ExecutionDetails as ExecutionDetailsProto
from .protobuf.ExecutionDetailsEnd_pb2 import (
    ExecutionDetailsEnd as ExecutionDetailsEndProto,
)
from .protobuf.FundamentalsData_pb2 import FundamentalsData as FundamentalsDataProto
from .protobuf.HeadTimestamp_pb2 import HeadTimestamp as HeadTimestampProto
from .protobuf.HistogramData_pb2 import HistogramData as HistogramDataProto
from .protobuf.HistoricalData_pb2 import HistoricalData as HistoricalDataProto
from .protobuf.HistoricalDataEnd_pb2 import HistoricalDataEnd as HistoricalDataEndProto
from .protobuf.HistoricalDataUpdate_pb2 import (
    HistoricalDataUpdate as HistoricalDataUpdateProto,
)
from .protobuf.HistoricalSchedule_pb2 import (
    HistoricalSchedule as HistoricalScheduleProto,
)
from .protobuf.HistoricalTicks_pb2 import HistoricalTicks as HistoricalTicksProto
from .protobuf.HistoricalTicksBidAsk_pb2 import (
    HistoricalTicksBidAsk as HistoricalTicksBidAskProto,
)
from .protobuf.HistoricalTicksLast_pb2 import (
    HistoricalTicksLast as HistoricalTicksLastProto,
)
from .protobuf.ManagedAccounts_pb2 import ManagedAccounts as ManagedAccountsProto
from .protobuf.MarketDataType_pb2 import MarketDataType as MarketDataTypeProto
from .protobuf.MarketRule_pb2 import MarketRule as MarketRuleProto
from .protobuf.NextValidId_pb2 import NextValidId as NextValidIdProto
from .protobuf.OpenOrder_pb2 import OpenOrder as OpenOrderProto
from .protobuf.OpenOrdersEnd_pb2 import OpenOrdersEnd as OpenOrderEndProto
from .protobuf.OrderStatus_pb2 import OrderStatus as OrderStatusProto
from .protobuf.OrderBound_pb2 import OrderBound as OrderBoundProto
from .protobuf.PortfolioValue_pb2 import PortfolioValue as PortfolioValueProto
from .protobuf.Position_pb2 import Position as PositionProto
from .protobuf.PositionEnd_pb2 import PositionEnd as PositionEndProto
from .protobuf.PnL_pb2 import PnL as PnLProto
from .protobuf.PnLSingle_pb2 import PnLSingle as PnLSingleProto
from .protobuf.RealTimeBarTick_pb2 import RealTimeBarTick as RealTimeBarTickProto
from .protobuf.ScannerParameters_pb2 import ScannerParameters as ScannerParametersProto
from .protobuf.ScannerData_pb2 import ScannerData as ScannerDataProto
from .protobuf.SecDefOptParameter_pb2 import (
    SecDefOptParameter as SecDefOptParameterProto,
)
from .protobuf.SecDefOptParameterEnd_pb2 import (
    SecDefOptParameterEnd as SecDefOptParameterEndProto,
)
from .protobuf.SmartComponents_pb2 import SmartComponents as SmartComponentsProto
from .protobuf.SymbolSamples_pb2 import SymbolSamples as SymbolSamplesProto
from .protobuf.TickGeneric_pb2 import TickGeneric as TickGenericProto
from .protobuf.TickOptionComputation_pb2 import (
    TickOptionComputation as TickOptionComputationProto,
)
from .protobuf.TickPrice_pb2 import TickPrice as TickPriceProto
from .protobuf.TickReqParams_pb2 import TickReqParams as TickReqParamsProto
from .protobuf.TickSize_pb2 import TickSize as TickSizeProto
from .protobuf.TickSnapshotEnd_pb2 import TickSnapshotEnd as TickSnapshotEndProto
from .protobuf.TickString_pb2 import TickString as TickStringProto
from .protobuf.TickByTickData_pb2 import TickByTickData as TickByTickDataProto
from .protobuf.UserInfo_pb2 import UserInfo as UserInfoProto
from .protobuf_converters.account_converters import (
    createAccountSummary,
    createAccountValue,
    createAccountValueFromUpdateMulti,
    createPortfolioItem,
    createPosition,
)
from .protobuf_converters.contract_converters import (
    createContractDescription,
    createContractDetails,
    createOptionChain,
    createSmartComponents,
)
from .protobuf_converters.historical_data_converters import (
    createBarData,
    createBarDataList,
    createHistogramDataEntry,
    createHistoricalSchedule,
    createHistoricalTick,
    createHistoricalTickBidAsk,
    createHistoricalTickLast,
    createRealTimeBarTick,
)
from .protobuf_converters.market_data_converters import (
    createTickGenericData,
    createTickOptionComputation,
    createTickParams,
    createTickPriceData,
    createTickSizeData,
    createTickStringData,
)
from .protobuf_converters.trade_converter import (
    createCommissionReport,
    createContract,
    createFill,
    createOrder,
    createOrderStatus,
    createTradeFromOpenOrder,
)

from .util import NO_VALID_ID, UNSET_DOUBLE, UNSET_INTEGER
from .wrapper import Wrapper


class Decoder:
    """Decode IB messages from bytes to proto and to ib-async objects, then invoke
    corresponding wrapper methods.
    """

    # MessageId.IN -> (DataTypeProto, methodHandler)
    PROTOBUF_MESSAGE_HANDLERS: dict[MessageId.IN, tuple[type, str]] = {
        # Handles NEXT_VALID_ID message during handshake
        MessageId.IN.NEXT_VALID_ID: (NextValidIdProto, "nextValidIdProto"),
        # Handles incoming contract details for reqContractDetails
        MessageId.IN.CONTRACT_DATA: (ContractDataProto, "contractDetailsProto"),
        # Signals the end of a contract details stream
        MessageId.IN.CONTRACT_DATA_END: (
            ContractDataEndProto,
            "contractDetailsEndProto",
        ),
        # Handles the response for reqMarketRule
        MessageId.IN.MARKET_RULE: (MarketRuleProto, "marketRuleProto"),
        # Handles the response for reqMatchingSymbols
        MessageId.IN.SYMBOL_SAMPLES: (SymbolSamplesProto, "symbolSamplesProto"),
        # Handles incoming security definition option parameters for reqSecDefOptParams
        MessageId.IN.SECURITY_DEFINITION_OPTION_PARAMETER: (
            SecDefOptParameterProto,
            "secDefOptParameterProto",
        ),
        # Signals the end of a security definition option parameters stream
        MessageId.IN.SECURITY_DEFINITION_OPTION_PARAMETER_END: (
            SecDefOptParameterEndProto,
            "secDefOptParameterEndProto",
        ),
        # Handles incoming error messages
        MessageId.IN.ERR_MSG: (ErrorMessageProto, "errorMessageProto"),
        # Handles incoming managed accounts list
        MessageId.IN.MANAGED_ACCTS: (ManagedAccountsProto, "managedAccountsProto"),
        # Handles incoming account value updates
        MessageId.IN.ACCT_VALUE: (AccountValueProto, "accountValueProto"),
        MessageId.IN.ACCT_DOWNLOAD_END: (
            AccountDataEndProto,
            "accountDownloadEnd",
        ),
        # Handles incoming position updates
        MessageId.IN.POSITION_DATA: (PositionProto, "positionProto"),
        # Signals the end of a position stream
        MessageId.IN.POSITION_END: (PositionEndProto, "positionEndProto"),
        # Handles incoming multi-account updates
        MessageId.IN.ACCOUNT_UPDATE_MULTI: (
            AccountUpdateMultiProto,
            "accountUpdateMultiProto",
        ),
        # Signals the end of a multi-account update stream
        MessageId.IN.ACCOUNT_UPDATE_MULTI_END: (
            AccountUpdateMultiEndProto,
            "accountUpdateMultiEndProto",
        ),
        # Handles incoming open order updates
        MessageId.IN.OPEN_ORDER: (OpenOrderProto, "openOrderProto"),
        MessageId.IN.OPEN_ORDER_END: (OpenOrderEndProto, "openOrderEndProto"),
        # Handles incoming execution details
        MessageId.IN.EXECUTION_DATA: (ExecutionDetailsProto, "execDetailsProto"),
        MessageId.IN.EXECUTION_DATA_END: (
            ExecutionDetailsEndProto,
            "execDetailsEndProto",
        ),
        # Handles account summary
        MessageId.IN.ACCOUNT_SUMMARY: (AccountSummaryProto, "accountSummaryProto"),
        MessageId.IN.ACCOUNT_SUMMARY_END: (
            AccountSummaryEndProto,
            "accountSummaryEndProto",
        ),
        # Handles order status updates
        MessageId.IN.ORDER_STATUS: (OrderStatusProto, "orderStatusProto"),
        MessageId.IN.COMPLETED_ORDER: (CompletedOrderProto, "completedOrderProto"),
        MessageId.IN.COMPLETED_ORDERS_END: (
            CompletedOrdersEndProto,
            "completedOrdersEndProto",
        ),
        MessageId.IN.ORDER_BOUND: (OrderBoundProto, "orderBoundProto"),
        MessageId.IN.PORTFOLIO_VALUE: (PortfolioValueProto, "updatePortfolioProto"),
        MessageId.IN.ACCT_UPDATE_TIME: (
            AccountUpdateTimeProto,
            "updateAccountTimeProto",
        ),
        MessageId.IN.MARKET_DATA_TYPE: (MarketDataTypeProto, "marketDataTypeProto"),
        MessageId.IN.COMMISSION_AND_FEES_REPORT: (
            CommissionReportProto,
            "commissionReportProto",
        ),
        MessageId.IN.CURRENT_TIME: (CurrentTimeProto, "currentTimeProto"),
        MessageId.IN.CURRENT_TIME_IN_MILLIS: (
            CurrentTimeInMillisProto,
            "currentTimeMiliProto",
        ),
        MessageId.IN.HEAD_TIMESTAMP: (HeadTimestampProto, "headTimestampProto"),
        MessageId.IN.HISTORICAL_DATA: (HistoricalDataProto, "historicalDataProto"),
        MessageId.IN.HISTORICAL_DATA_END: (
            HistoricalDataEndProto,
            "historicalDataProtoEnd",
        ),
        MessageId.IN.HISTORICAL_DATA_UPDATE: (
            HistoricalDataUpdateProto,
            "historicalDataUpdateProto",
        ),
        MessageId.IN.HISTORICAL_TICKS: (HistoricalTicksProto, "historicalTicksProto"),
        MessageId.IN.HISTORICAL_TICKS_BID_ASK: (
            HistoricalTicksBidAskProto,
            "historicalTicksBidAskProto",
        ),
        MessageId.IN.HISTORICAL_TICKS_LAST: (
            HistoricalTicksLastProto,
            "historicalTicksLastProto",
        ),
        MessageId.IN.HISTOGRAM_DATA: (HistogramDataProto, "histogramDataProto"),
        MessageId.IN.HISTORICAL_SCHEDULE: (
            HistoricalScheduleProto,
            "historicalScheduleProto",
        ),
        MessageId.IN.REAL_TIME_BARS: (RealTimeBarTickProto, "realTimeBarTickProto"),
        MessageId.IN.TICK_REQ_PARAMS: (TickReqParamsProto, "tickReqParamsProto"),
        MessageId.IN.TICK_PRICE: (TickPriceProto, "tickPriceProto"),
        MessageId.IN.TICK_SIZE: (TickSizeProto, "tickSizeProto"),
        MessageId.IN.TICK_GENERIC: (TickGenericProto, "tickGenericProto"),
        MessageId.IN.TICK_STRING: (TickStringProto, "tickStringProto"),
        MessageId.IN.TICK_OPTION_COMPUTATION: (
            TickOptionComputationProto,
            "tickOptionComputationProto",
        ),
        MessageId.IN.TICK_SNAPSHOT_END: (TickSnapshotEndProto, "tickSnapshotEndProto"),
        MessageId.IN.TICK_BY_TICK: (
            TickByTickDataProto,
            "tickByTickDataProto",
        ),
        MessageId.IN.FUNDAMENTAL_DATA: (FundamentalsDataProto, "fundamentalsDataProto"),
        MessageId.IN.SCANNER_PARAMETERS: (
            ScannerParametersProto,
            "scannerParametersProto",
        ),
        MessageId.IN.SCANNER_DATA: (ScannerDataProto, "scannerDataProto"),
        MessageId.IN.PNL: (PnLProto, "pnlProto"),
        MessageId.IN.PNL_SINGLE: (PnLSingleProto, "pnlSingleProto"),
        MessageId.IN.USER_INFO: (UserInfoProto, "userInfoProto"),
        MessageId.IN.SMART_COMPONENTS: (SmartComponentsProto, "smartComponentsProto"),
    }

    def __init__(self, wrapper: Wrapper, serverVersion: int):
        self.wrapper = wrapper
        self.serverVersion = serverVersion
        self.logger = logging.getLogger("ib_async.Decoder")

    def processProtoBuf(self, payload: bytes):
        """
        Process a binary Protobuf message payload by calling the appropriate handler
        method.

        `wrapper.PROTOBUF_MESSAGE_HANDLERS.get(msgId) -> (DataTypeProto, methodHandler)`

        """
        msgId_raw = int.from_bytes(payload[:4], "big")
        try:
            msgId = MessageId.IN(msgId_raw)
            handler_info = self.PROTOBUF_MESSAGE_HANDLERS.get(msgId)
            if handler_info:
                proto_class, handler_method_name = handler_info
                proto_message = proto_class()
                proto_message.ParseFromString(payload[4:])
                handler_method = getattr(self, handler_method_name)
                handler_method(proto_message)
            else:
                self.logger.warning("Unknown Protobuf message id: %s", msgId)
        except ValueError as err:
            self.logger.warning(
                "ValueError: Processing protobuf message id: %s, %s", msgId_raw, err
            )
        except Exception as err:
            self.logger.exception(
                "Error processing Protobuf message id: %s, %s", msgId_raw, err
            )

    def errorMessageProto(self, msg: ErrorMessageProto):
        reqId = msg.id
        errorCode = msg.errorCode
        errorMsg = msg.errorMsg
        advancedOrderRejectJson = msg.advancedOrderRejectJson

        self.wrapper.error(reqId, errorCode, errorMsg, advancedOrderRejectJson)

    def contractDetailsProto(self, msg: ContractDataProto):
        reqId = msg.reqId
        contractDetails = createContractDetails(msg)
        self.wrapper.contractDetails(reqId, contractDetails)

    def contractDetailsEndProto(self, msg: ContractDataEndProto):
        self.wrapper.contractDetailsEnd(msg.reqId)

    def symbolSamplesProto(self, msg: SymbolSamplesProto):
        reqId = msg.reqId
        contractDescriptions: list[ContractDescription] = []
        for contractDescriptionProto in msg.contractDescriptions:
            contractDescriptions.append(
                createContractDescription(contractDescriptionProto)
            )
        self.wrapper.symbolSamples(reqId, contractDescriptions)

    def marketRuleProto(self, msg: MarketRuleProto):
        reqId = msg.marketRuleId
        priceIncrements: list[PriceIncrement] = []
        for priceIncrementProto in msg.priceIncrements:
            priceIncrements.append(
                PriceIncrement(
                    lowEdge=priceIncrementProto.lowEdge,
                    increment=priceIncrementProto.increment,
                )
            )
        self.wrapper.marketRule(reqId, priceIncrements)

    def secDefOptParameterProto(self, msg: SecDefOptParameterProto):
        reqId = msg.reqId
        optionChain = createOptionChain(msg)
        self.wrapper.securityDefinitionOptionParameter(reqId, optionChain)

    def secDefOptParameterEndProto(self, msg: SecDefOptParameterEndProto):
        self.wrapper.securityDefinitionOptionParameterEnd(msg.reqId)

    def managedAccountsProto(self, msg: ManagedAccountsProto):
        accountsList = msg.accountsList
        self.wrapper.managedAccounts(accountsList)

    def accountValueProto(self, msg: AccountValueProto):
        accountValue = createAccountValue(msg)
        self.wrapper.updateAccountValue(accountValue)

    def accountDownloadEnd(self, msg: str):
        self.wrapper.accountDownloadEnd(msg)

    def positionProto(self, msg: PositionProto):
        position = createPosition(msg)
        self.wrapper.position(position)

    def positionEndProto(self, msg: PositionEndProto):
        self.wrapper.positionEnd()

    def updatePortfolioProto(self, msg: PortfolioValueProto):
        portfolioItem = createPortfolioItem(msg)
        self.wrapper.updatePortfolio(portfolioItem)

    def accountUpdateMultiProto(self, msg: AccountUpdateMultiProto):
        accountValue = createAccountValueFromUpdateMulti(msg)
        self.wrapper.accountUpdateMulti(msg.reqId, accountValue)

    def accountUpdateMultiEndProto(self, msg: AccountUpdateMultiEndProto):
        self.wrapper.accountUpdateMultiEnd(msg.reqId)

    def accountSummaryProto(self, msg: AccountSummaryProto):
        accountValue = createAccountSummary(msg)
        self.wrapper.accountSummary(msg.reqId, accountValue)

    def accountSummaryEndProto(self, msg: AccountSummaryEndProto):
        self.wrapper.accountSummaryEnd(msg.reqId)

    def nextValidIdProto(self, msg: NextValidIdProto):
        self.wrapper.nextValidId(msg.orderId)

    def openOrderProto(self, msg: OpenOrderProto):
        trade, orderState = createTradeFromOpenOrder(msg)
        if trade:
            self.wrapper.openOrder(trade, orderState)
            return
        self.logger.error("Error processing order, %r", msg)

    def openOrderEndProto(self, msg: OpenOrderEndProto):
        self.wrapper.openOrderEnd()

    def execDetailsProto(self, msg: ExecutionDetailsProto):
        fill = createFill(msg)
        self.wrapper.execDetails(msg.reqId, fill)

    def execDetailsEndProto(self, msg: ExecutionDetailsEndProto):
        self.wrapper.execDetailsEnd(msg.reqId)

    def orderStatusProto(self, msg: OrderStatusProto):
        orderStatus = createOrderStatus(msg)
        self.wrapper.orderStatus(orderStatus)

    def completedOrderProto(self, msg: CompletedOrderProto):
        contract = createContract(msg.contract)
        order = createOrder(msg.order.orderId, msg.contract, msg.order)
        order_status = OrderStatus(orderId=order.orderId, status=msg.orderState.status)
        self.wrapper.completedOrder(contract, order, order_status)

    def completedOrdersEndProto(self, msg: CompletedOrdersEndProto):
        self.wrapper.completedOrdersEnd()

    def orderBoundProto(self, msg: OrderBoundProto):
        permId = msg.permId if msg.HasField("permId") else UNSET_INTEGER
        clientId = msg.clientId if msg.HasField("clientId") else UNSET_INTEGER
        orderId = msg.orderId if msg.HasField("orderId") else UNSET_INTEGER
        self.wrapper.orderBound(permId, clientId, orderId)

    def updateAccountTimeProto(self, msg: AccountUpdateTimeProto):
        time = msg.timeStamp if msg.HasField("timeStamp") else ""
        self.wrapper.updateAccountTime(time)

    def commissionReportProto(self, msg: CommissionReportProto):
        commissionReport = createCommissionReport(msg)
        self.wrapper.commissionReport(commissionReport)

    def currentTimeProto(self, msg: CurrentTimeProto):
        self.wrapper.currentTime(msg.currentTime)

    def currentTimeMiliProto(self, msg: CurrentTimeInMillisProto):
        self.wrapper.currentTimeMili(msg.currentTimeInMillis)

    def headTimestampProto(self, msg: HeadTimestampProto):
        self.wrapper.headTimestamp(msg.reqId, msg.headTimestamp)

    def historicalDataProto(self, msg: HistoricalDataProto):
        bar_data = createBarDataList(msg.historicalDataBars)
        self.wrapper.historicalData(msg.reqId, bar_data)

    def historicalDataProtoEnd(self, msg: HistoricalDataEndProto):
        self.wrapper.historicalDataEnd(msg.reqId, msg.startDateStr, msg.endDateStr)

    def historicalTicksProto(self, msg: HistoricalTicksProto):
        reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID
        isDone = msg.isDone if msg.HasField("isDone") else False
        historicalTicks = []
        if msg.historicalTicks:
            for historicalTickProto in msg.historicalTicks:
                historicalTick = createHistoricalTick(
                    historicalTickProto, self.wrapper.defaults.timezone
                )
                historicalTicks.append(historicalTick)
        self.wrapper.historicalTicks(reqId, historicalTicks, isDone)

    def historicalTicksBidAskProto(self, msg: HistoricalTicksBidAskProto):
        reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID
        isDone = msg.isDone if msg.HasField("isDone") else False
        historicalTicksBidAsk: list[HistoricalTickBidAsk] = []
        if msg.historicalTicksBidAsk:
            for historicalTickProto in msg.historicalTicksBidAsk:
                historicalTickBidAsk = createHistoricalTickBidAsk(
                    historicalTickProto, self.wrapper.defaults.timezone
                )
                historicalTicksBidAsk.append(historicalTickBidAsk)
        self.wrapper.historicalTicksBidAsk(reqId, historicalTicksBidAsk, isDone)

    def historicalTicksLastProto(self, msg: HistoricalTicksLastProto):
        reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID
        isDone = msg.isDone if msg.HasField("isDone") else False
        historicalTicksLast: list[HistoricalTickLast] = []
        if msg.historicalTicksLast:
            for historicalTickProto in msg.historicalTicksLast:
                historicalTickLast = createHistoricalTickLast(
                    historicalTickProto, self.wrapper.defaults.timezone
                )
                historicalTicksLast.append(historicalTickLast)
        self.wrapper.historicalTicksLast(reqId, historicalTicksLast, isDone)

    def histogramDataProto(self, msg: HistogramDataProto):
        histogram: list[HistogramData] = []
        if msg.histogramDataEntries:
            for histogramDataEntryProto in msg.histogramDataEntries:
                histogramEntry = createHistogramDataEntry(histogramDataEntryProto)
                histogram.append(histogramEntry)
        self.wrapper.histogramData(msg.reqId, histogram)

    def historicalDataUpdateProto(self, msg: HistoricalDataUpdateProto):
        reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID
        bar = createBarData(msg.historicalDataBar)
        self.wrapper.historicalDataUpdate(reqId, bar)

    def historicalScheduleProto(self, msg: HistoricalScheduleProto):
        historicalSchedule = createHistoricalSchedule(msg)
        self.wrapper.historicalSchedule(msg.reqId, historicalSchedule)

    def realTimeBarTickProto(self, msg: RealTimeBarTickProto):
        reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID

        realTimeBarTick = createRealTimeBarTick(msg, self.wrapper.defaults.timezone)
        self.wrapper.realtimeBar(reqId, realTimeBarTick)

    def marketDataTypeProto(self, msg: MarketDataTypeProto):
        self.wrapper.marketDataType(msg.reqId, msg.marketDataType)

    def tickReqParamsProto(self, msg: TickReqParamsProto):
        tickParams = createTickParams(msg)
        self.wrapper.tickReqParams(tickParams.reqId, tickParams)

    def tickPriceProto(self, msg: TickPriceProto):
        tickPrice, tickSize = createTickPriceData(msg)
        self.wrapper.priceSizeTick(tickPrice.reqId, tickPrice)
        if tickSize.tickType != TickType.NOT_SET:
            self.wrapper.tickSize(tickSize.reqId, tickSize)

    def tickSizeProto(self, msg: TickSizeProto):
        tickSize = createTickSizeData(msg)
        self.wrapper.tickSize(tickSize.reqId, tickSize)

    def tickGenericProto(self, msg: TickGenericProto):
        tickGeneric = createTickGenericData(msg)
        self.wrapper.tickGeneric(tickGeneric.reqId, tickGeneric)

    def tickStringProto(self, msg: TickStringProto):
        tickString = createTickStringData(msg)
        self.wrapper.tickString(tickString.reqId, tickString)

    def tickOptionComputationProto(self, msg: TickOptionComputationProto):
        tick_computation = createTickOptionComputation(msg)
        self.wrapper.tickOptionComputation(tick_computation.reqId, tick_computation)

    def tickSnapshotEndProto(self, msg: TickSnapshotEndProto):
        reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID
        self.wrapper.tickSnapshotEnd(reqId)

    def tickByTickDataProto(self, msg: TickByTickDataProto):
        reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID
        tickType = msg.tickType if msg.HasField("tickType") else 0

        if tickType == 0:
            pass
        elif tickType == 1 or tickType == 2:
            # Last or AllLast
            if msg.HasField("historicalTickLast"):
                tick_last = createHistoricalTickLast(
                    msg.historicalTickLast, self.wrapper.defaults.timezone
                )
                self.wrapper.tickByTickAllLast(reqId, tick_last)
        elif tickType == 3:
            # BidAsk
            if msg.HasField("historicalTickBidAsk"):
                tick_bid_ask = createHistoricalTickBidAsk(
                    msg.historicalTickBidAsk, self.wrapper.defaults.timezone
                )
                self.wrapper.tickByTickBidAsk(reqId, tick_bid_ask)
        elif tickType == 4:
            # MidPoint
            if msg.HasField("historicalTickMidPoint"):
                tick_mid = createHistoricalTick(
                    msg.historicalTickMidPoint, self.wrapper.defaults.timezone
                )
                self.wrapper.tickByTickMidPoint(reqId, tick_mid)

    def fundamentatalDataProto(self, msg: FundamentalsDataProto):
        self.wrapper.fundamentalData(msg.reqId, msg.fundamentalData)

    def scannerParametersProto(self, msg: ScannerParametersProto):
        xml = msg.xml if msg.HasField("xml") else ""
        self.wrapper.scannerParameters(xml)

    def scannerDataProto(self, msg: ScannerDataProto):
        reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID
        scanData = createScannerDataList(msg)
        self.wrapper.scannerData(reqId, scanData)

    def pnlProto(self, msg: PnLProto):
        reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID
        dailyPnL = msg.dailyPnL if msg.HasField("dailyPnL") else UNSET_DOUBLE
        unrealizedPnL = (
            msg.unrealizedPnL if msg.HasField("unrealizedPnL") else UNSET_DOUBLE
        )
        realizedPnL = msg.realizedPnL if msg.HasField("realizedPnL") else UNSET_DOUBLE

        self.wrapper.pnl(reqId, dailyPnL, unrealizedPnL, realizedPnL)

    def pnlSingleProto(self, msg: PnLSingleProto):
        reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID
        position = int(msg.position) if msg.HasField("position") else UNSET_INTEGER
        dailyPnL = msg.dailyPnL if msg.HasField("dailyPnL") else UNSET_DOUBLE
        unrealizedPnL = (
            msg.unrealizedPnL if msg.HasField("unrealizedPnL") else UNSET_DOUBLE
        )
        realizedPnL = msg.realizedPnL if msg.HasField("realizedPnL") else UNSET_DOUBLE
        value = msg.value if msg.HasField("value") else UNSET_DOUBLE

        self.wrapper.pnlSingle(
            reqId, position, dailyPnL, unrealizedPnL, realizedPnL, value
        )

    def userInfoProto(self, msg: UserInfoProto):
        reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID
        whiteBrandingId = msg.whiteBrandingId if msg.HasField("whiteBrandingId") else ""
        self.wrapper.userInfo(reqId, whiteBrandingId)

    def smartComponentsProto(self, msg: SmartComponentsProto):
        reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID
        components = createSmartComponents(msg)
        self.wrapper.smartComponents(reqId, components)

    ##################### legacy methods ##########################################

    def bondContractDetails(self, fields):
        cd = ContractDetails()
        cd.contract = c = Contract()
        if self.serverVersion < 164:
            fields.pop(0)

        (
            _,
            reqId,
            c.symbol,
            c.secType,
            cd.cusip,
            cd.coupon,
            lastTimes,
            cd.issueDate,
            cd.ratings,
            cd.bondType,
            cd.couponType,
            cd.convertible,
            cd.callable,
            cd.putable,
            cd.descAppend,
            c.exchange,
            c.currency,
            cd.marketName,
            c.tradingClass,
            c.conId,
            cd.minTick,
            *fields,
        ) = fields

        if self.serverVersion < 164:
            fields.pop(0)  # obsolete mdSizeMultiplier

        (
            cd.orderTypes,
            cd.validExchanges,
            cd.nextOptionDate,
            cd.nextOptionType,
            cd.nextOptionPartial,
            cd.notes,
            cd.longName,
            cd.evRule,
            cd.evMultiplier,
            numSecIds,
            *fields,
        ) = fields

        numSecIds = int(numSecIds)
        if numSecIds > 0:
            cd.secIdList = []
            for _ in range(numSecIds):
                tag, value, *fields = fields
                cd.secIdList += [TagValue(tag, value)]

        cd.aggGroup, cd.marketRuleIds, *fields = fields
        if self.serverVersion >= 164:
            (
                cd.minSize,
                cd.sizeIncrement,
                cd.suggestedSizeIncrement,
                # cd.minCashQtySize,
                *fields,
            ) = fields

        times = lastTimes.split("-" if "-" in lastTimes else None)

        if len(times) > 0:
            cd.maturity = times[0]

        if len(times) > 1:
            cd.lastTradeTime = times[1]

        if len(times) > 2:
            cd.timeZoneId = times[2]

        self.parse(cd)
        self.parse(c)
        self.wrapper.bondContractDetails(int(reqId), cd)

    def deltaNeutralValidation(self, fields):
        _, _, reqId, conId, delta, price = fields

        self.wrapper.deltaNeutralValidation(
            int(reqId),
            DeltaNeutralContract(int(conId), float(delta or 0), float(price or 0)),
        )

    def softDollarTiers(self, fields):
        _, reqId, n, *fields = fields
        get = iter(fields).__next__

        tiers = [
            SoftDollarTier(name=get(), val=get(), displayName=get())
            for _ in range(int(n))
        ]

        self.wrapper.softDollarTiers(int(reqId), tiers)

    def familyCodes(self, fields):
        _, n, *fields = fields
        get = iter(fields).__next__

        familyCodes = [
            FamilyCode(accountID=get(), familyCodeStr=get()) for _ in range(int(n))
        ]

        self.wrapper.familyCodes(familyCodes)

    def smartComponents(self, fields):
        _, reqId, n, *fields = fields
        get = iter(fields).__next__

        components = [
            SmartComponent(bitNumber=int(get()), exchange=get(), exchangeLetter=get())
            for _ in range(int(n))
        ]

        self.wrapper.smartComponents(int(reqId), components)

    def mktDepthExchanges(self, fields):
        _, n, *fields = fields
        get = iter(fields).__next__

        descriptions = [
            DepthMktDataDescription(
                exchange=get(),
                secType=get(),
                listingExch=get(),
                serviceDataType=get(),
                aggGroup=int(get()),
            )
            for _ in range(int(n))
        ]

        self.wrapper.mktDepthExchanges(descriptions)

    def newsProviders(self, fields):
        _, n, *fields = fields
        get = iter(fields).__next__

        providers = [NewsProvider(code=get(), name=get()) for _ in range(int(n))]

        self.wrapper.newsProviders(providers)
