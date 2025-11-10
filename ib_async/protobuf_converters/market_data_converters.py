"""
Market data protobuf converters
"""

from dataclasses import dataclass

from ..objects import (
    Contract,
    OptionComputation,
    TagValue,
    TickAttrib,
    TickAttribBidAsk,
    TickAttribLast,
    TickByTickAllLastData,
    TickByTickBidAskData,
    TickByTickMidPointData,
    TickGenericData,
    TickParams,
    TickPriceData,
    TickSizeData,
    TickStringData,
    TickType,
    TickComputationData,
)
from ..protobuf.MarketDataRequest_pb2 import (
    MarketDataRequest as MarketDataRequestProto,
)
from ..protobuf.MarketDataType_pb2 import MarketDataType as MarketDataTypeProto
from ..protobuf.TickPrice_pb2 import TickPrice as TickPriceProto
from ..protobuf.TickSize_pb2 import TickSize as TickSizeProto
from ..protobuf.TickString_pb2 import TickString as TickStringProto
from ..protobuf.TickGeneric_pb2 import TickGeneric as TickGenericProto
from ..protobuf.TickOptionComputation_pb2 import (
    TickOptionComputation as TickOptionComputationProto,
)
from ..protobuf.TickReqParams_pb2 import TickReqParams as TickReqParamsProto
from ..protobuf.HistoricalTickLast_pb2 import (
    HistoricalTickLast as HistoricalTickLastProto,
)
from ..protobuf.HistoricalTickBidAsk_pb2 import (
    HistoricalTickBidAsk as HistoricalTickBidAskProto,
)
from ..protobuf.MarketDataTypeRequest_pb2 import (
    MarketDataTypeRequest as MarketDataTypeRequestProto,
)
from ..protobuf.HistoricalTick_pb2 import HistoricalTick as HistoricalTickProt
from ..protobuf.CancelMarketData_pb2 import CancelMarketData as CancelMarketDataProto
from ..util import NO_VALID_ID, UNSET_DOUBLE, UNSET_INTEGER, isValidIntValue
from .contract_converters import createContractProto
from .historical_data_converters import fillTagValueList


def createMarketDataTypeRequestProto(marketDataType: int) -> MarketDataTypeRequestProto:
    marketDataTypeRequestProto = MarketDataTypeRequestProto()
    if isValidIntValue(marketDataType):
        marketDataTypeRequestProto.marketDataType = marketDataType
    return marketDataTypeRequestProto


def createMarketDataRequestProto(
    reqId: int,
    contract: Contract,
    genericTickList: str,
    snapshot: bool,
    regulatorySnapshot: bool,
    marketDataOptionsList: list[TagValue],
) -> MarketDataRequestProto:
    marketDataRequestProto = MarketDataRequestProto()
    if isValidIntValue(reqId):
        marketDataRequestProto.reqId = reqId
    contractProto = createContractProto(contract, None)
    if contractProto is not None:
        marketDataRequestProto.contract.CopyFrom(contractProto)
    if genericTickList:
        marketDataRequestProto.genericTickList = genericTickList
    if snapshot:
        marketDataRequestProto.snapshot = snapshot
    if regulatorySnapshot:
        marketDataRequestProto.regulatorySnapshot = regulatorySnapshot
    fillTagValueList(marketDataOptionsList, marketDataRequestProto.marketDataOptions)
    return marketDataRequestProto


def cancelMarketDataProto(reqId: int) -> CancelMarketDataProto:
    cancelMarketDataProto = CancelMarketDataProto()
    if isValidIntValue(reqId):
        cancelMarketDataProto.reqId = reqId
    return cancelMarketDataProto


def createTickParams(msg: TickReqParamsProto) -> TickParams:
    """Create a TickParams object from a TickReqParamsProto message."""
    reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID
    minTick = float(msg.minTick) if msg.HasField("minTick") else UNSET_DOUBLE
    bboExchange = msg.bboExchange if msg.HasField("bboExchange") else ""
    snapshotPermissions = (
        msg.snapshotPermissions
        if msg.HasField("snapshotPermissions")
        else UNSET_INTEGER
    )
    tickParams = TickParams(reqId, minTick, bboExchange, snapshotPermissions)
    return tickParams


def createTickPriceData(msg: TickPriceProto) -> tuple[TickPriceData, TickSizeData]:
    """Create a TickPriceData object from a TickPriceProto message."""
    if msg.HasField("reqId"):
        reqId = msg.reqId
    if msg.HasField("tickType") and msg.tickType in TickType:
        tickType = TickType(msg.tickType)
    if msg.HasField("price"):
        price = float(
            msg.price,
        )
    if msg.HasField("size"):
        size = float(msg.size)
    if msg.HasField("attrMask"):
        canAutoExecute = msg.attrMask & 1 != 0
        pastLimit = msg.attrMask & 2 != 0
        preOpen = msg.attrMask & 4 != 0
        attribs = TickAttrib(
            canAutoExecute,
            pastLimit,
            preOpen,
        )

    tickPrice = TickPriceData(reqId, tickType, price, size, attribs)

    sizeTickType = TickType.NOT_SET
    if TickType.BID == tickType:
        sizeTickType = TickType.BID_SIZE
    elif TickType.ASK == tickType:
        sizeTickType = TickType.ASK_SIZE
    elif TickType.LAST == tickType:
        sizeTickType = TickType.LAST_SIZE
    elif TickType.DELAYED_BID == tickType:
        sizeTickType = TickType.DELAYED_BID_SIZE
    elif TickType.DELAYED_ASK == tickType:
        sizeTickType = TickType.DELAYED_ASK_SIZE
    elif TickType.DELAYED_LAST == tickType:
        sizeTickType = TickType.DELAYED_LAST_SIZE

    tickSize = TickSizeData(reqId, sizeTickType, size)
    return tickPrice, tickSize


def createTickSizeData(msg: TickSizeProto) -> TickSizeData:
    """Create a TickSizeData object from a TickSizeProto message."""
    if msg.HasField("reqId"):
        reqId = msg.reqId
    if msg.HasField("tickType") and msg.tickType in TickType:
        tickType = TickType(msg.tickType)
    if msg.HasField("size"):
        size = float(msg.size)
    tickSize = TickSizeData(reqId, tickType, size)
    return tickSize


def createTickStringData(msg: TickStringProto) -> TickStringData:
    """Create a TickStringData object from a TickStringProto message."""
    if msg.HasField("reqId"):
        reqId = msg.reqId
    if msg.HasField("tickType") and msg.tickType in TickType:
        tickType = TickType(msg.tickType)
    if msg.HasField("value"):
        value = msg.value
    tickString = TickStringData(reqId, tickType, value)
    return tickString


def createTickGenericData(msg: TickGenericProto) -> TickGenericData:
    """Create a TickGenericData object from a TickGenericProto message."""
    if msg.HasField("reqId"):
        reqId = msg.reqId
    if msg.HasField("tickType") and msg.tickType in TickType:
        tickType = TickType(msg.tickType)
    if msg.HasField("value"):
        value = msg.value
    tickGeneric = TickGenericData(reqId, tickType, value)
    return tickGeneric


def createTickOptionComputation(msg: TickOptionComputationProto) -> TickComputationData:
    """Create a OptionComputation object from a TickOptionCompuationProto message."""

    tickType = (
            TickType(msg.tickType) if msg.HasField("tickType") else TickType.NOT_SET
        )
    tickAttrib = msg.tickAttrib if msg.HasField("tickAttrib") else UNSET_INTEGER
    impliedVol = msg.impliedVol if msg.HasField("impliedVol") else None
    if impliedVol and impliedVol < 0:  # -1 is the "not computed" indicator
        impliedVol = None
    delta = msg.delta if msg.HasField("delta") else None
    if delta == -2:  # -2 is the "not computed" indicator
        delta = None
    optPrice = msg.optPrice if msg.HasField("optPrice") else None
    if optPrice == -1:  # -1 is the "not computed" indicator
        optPrice = None
    pvDividend = msg.pvDividend if msg.HasField("pvDividend") else None
    if pvDividend == -1:  # -1 is the "not computed" indicator
        pvDividend = None
    gamma = msg.gamma if msg.HasField("gamma") else None
    if gamma == -2:  # -2 is the "not yet computed" indicator
        gamma = None
    vega = msg.vega if msg.HasField("vega") else None
    if vega == -2:  # -2 is the "not yet computed" indicator
        vega = None
    theta = msg.theta if msg.HasField("theta") else None
    if theta == -2:  # -2 is the "not yet computed" indicator
        theta = None
    undPrice = msg.undPrice if msg.HasField("undPrice") else None
    if undPrice == -1:  # -1 is the "not computed" indicator
        undPrice = None

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
    
    tick_comp = TickComputationData(
        reqId=msg.reqId,
        tickType=tickType,
        computation=comp,
    )
    return tick_comp


# def create_tick_by_tick_all_last_data(
#     msg: TickByTickAllLastProto,
# ) -> TickByTickAllLastData:
#     """Create a TickByTickAllLastData object from a TickByTickAllLastProto message."""
#     if msg.HasField("reqId"):
#         reqId = msg.reqId
#     if msg.HasField("tickType"):
#         tickType = msg.tickType
#     if msg.HasField("historicalTickLast"):
#         historicalTickLast = msg.historicalTickLast
#     if msg.HasField("historicalTickBidAsk"):
#         historicalTickBidAsk = msg.historicalTickBidAsk
#     if msg.HasField("historicalTickMidPoint"):
#         historicalTickMidPoint = msg.historicalTickMidPoint

#     tickByTickAllLastData = TickByTickAllLastData(
#         reqId=reqId,
#         tickType=tickType,
#         time=msg.time,
#         price=msg.price,
#         size=msg.size,
#         tickAttribLast=TickAttribLast(
#             pastLimit=msg.tickAttribLast.pastLimit,
#             unreported=msg.tickAttribLast.unreported,
#         ),
#         exchange=msg.exchange,
#         specialConditions=msg.specialConditions,
#     )
#     return tickByTickAllLastData


# def create_tick_by_tick_bid_ask_data(
#     msg: TickByTickBidAskProto,
# ) -> TickByTickBidAskData:
#     """Create a TickByTickBidAskData object from a TickByTickBidAskProto message."""
#     return TickByTickBidAskData(
#         reqId=msg.reqId,
#         time=msg.time,
#         bidPrice=msg.bidPrice,
#         askPrice=msg.askPrice,
#         bidSize=msg.bidSize,
#         askSize=msg.askSize,
#         tickAttribBidAsk=TickAttribBidAsk(
#             bidPastLow=msg.tickAttribBidAsk.bidPastLow,
#             askPastHigh=msg.tickAttribBidAsk.askPastHigh,
#         ),
#     )


# def create_tick_by_tick_mid_point_data(
#     msg: TickByTickMidPointProto,
# ) -> TickByTickMidPointData:
#     """Create a TickByTickMidPointData object from a TickByTickMidPointProto message."""
#     return TickByTickMidPointData(
#         reqId=msg.reqId,
#         time=msg.time,
#         midPoint=msg.midPoint,
#     )
