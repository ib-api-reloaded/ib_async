"""
Market data protobuf converters
"""

from collections.abc import Callable
from math import nan
from typing import Any, TypeAlias

from ..objects import (
    Contract,
    OptionComputation,
    TagValue,
    TickAttrib,
    TickComputationData,
    TickDeliveryType,
    TickGenericData,
    TickParams,
    TickPriceData,
    TickSizeData,
    TickStringData,
    TickType,
)
from ..protobuf.CalculateImpliedVolatilityRequest_pb2 import (
    CalculateImpliedVolatilityRequest as CalculateImpliedVolatilityRequestProto,
)
from ..protobuf.CalculateOptionPriceRequest_pb2 import (
    CalculateOptionPriceRequest as CalculateOptionPriceRequestProto,
)
from ..protobuf.CancelCalculateImpliedVolatility_pb2 import (
    CancelCalculateImpliedVolatility as CancelCalculateImpliedVolatilityProto,
)
from ..protobuf.CancelCalculateOptionPrice_pb2 import (
    CancelCalculateOptionPrice as CancelCalculateOptionPriceProto,
)
from ..protobuf.CancelMarketData_pb2 import CancelMarketData as CancelMarketDataProto
from ..protobuf.MarketDataRequest_pb2 import (
    MarketDataRequest as MarketDataRequestProto,
)
from ..protobuf.MarketDataTypeRequest_pb2 import (
    MarketDataTypeRequest as MarketDataTypeRequestProto,
)
from ..protobuf.TickByTickRequest_pb2 import TickByTickRequest as TickByTickRequestProto
from ..protobuf.TickGeneric_pb2 import TickGeneric as TickGenericProto
from ..protobuf.TickOptionComputation_pb2 import (
    TickOptionComputation as TickOptionComputationProto,
)
from ..protobuf.TickPrice_pb2 import TickPrice as TickPriceProto
from ..protobuf.TickReqParams_pb2 import TickReqParams as TickReqParamsProto
from ..protobuf.TickSize_pb2 import TickSize as TickSizeProto
from ..protobuf.TickString_pb2 import TickString as TickStringProto
from ..util import (
    NO_VALID_ID,
    UNSET_DOUBLE,
    UNSET_INTEGER,
    isValidIntValue,
)
from .base_converters import ib_defaults
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


def createTickByTickRequestProto(
    reqId: int, contract: Contract, tickType: str, numberOfTicks: int, ignoreSize: bool
) -> TickByTickRequestProto:
    tickByTickRequestProto = TickByTickRequestProto()
    if isValidIntValue(reqId):
        tickByTickRequestProto.reqId = reqId
    contractProto = createContractProto(contract, None)
    if contractProto is not None:
        tickByTickRequestProto.contract.CopyFrom(contractProto)
    if tickType:
        tickByTickRequestProto.tickType = tickType
    if isValidIntValue(numberOfTicks):
        tickByTickRequestProto.numberOfTicks = numberOfTicks
    if ignoreSize:
        tickByTickRequestProto.ignoreSize = ignoreSize
    return tickByTickRequestProto


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


def createTickPriceData(msg: TickPriceProto) -> TickPriceData:
    """Create a TickPriceData object from a TickPriceProto message."""
    reqId = msg.reqId if msg.HasField("reqId") else NO_VALID_ID

    tickType = (
        TickType(msg.tickType)
        if msg.HasField("tickType") and msg.tickType in TickType
        else TickType.NOT_SET
    )

    price = float(msg.price) if msg.HasField("price") else ib_defaults.emptyPrice
    size = float(msg.size) if msg.HasField("size") else ib_defaults.emptySize

    attribs = TickAttrib()
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

    return tickPrice


def createTickSizeData(msg: TickSizeProto) -> TickSizeData:
    """Create a TickSizeData object from a TickSizeProto message."""
    reqId = NO_VALID_ID
    tickType = TickType.NOT_SET
    size = ib_defaults.emptySize
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
    reqId = NO_VALID_ID
    tickType = TickType.NOT_SET
    value = ib_defaults.unset

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
    reqId = NO_VALID_ID
    tickType = TickType.NOT_SET
    value = ib_defaults.unset
    if msg.HasField("reqId"):
        reqId = msg.reqId
    if msg.HasField("tickType") and msg.tickType in TickType:
        tickType = TickType(msg.tickType)
    if msg.HasField("value"):
        value = msg.value
    tickGeneric = TickGenericData(reqId, tickType, value)
    return tickGeneric


TickDeliveryProto: TypeAlias = (
    TickPriceProto | TickSizeProto | TickStringProto | TickGenericProto
)


def createTickData(msg: TickDeliveryProto) -> TickDeliveryType:
    delivery_map: dict[type[TickDeliveryProto], Callable[[Any], TickDeliveryType]] = {
        TickPriceProto: createTickPriceData,
        TickSizeProto: createTickSizeData,
        TickStringProto: createTickStringData,
        TickGenericProto: createTickGenericData,
    }

    create_method = delivery_map.get(type(msg))

    if create_method is None:
        # runtime error
        raise ValueError(
            f"createTickData - no converter found for tick delivery type: {type(msg)}"
        )

    return create_method(msg)


def createTickOptionComputation(msg: TickOptionComputationProto) -> TickComputationData:
    """Create a OptionComputation object from a TickOptionCompuationProto message."""

    tickType = TickType(msg.tickType) if msg.HasField("tickType") else TickType.NOT_SET
    tickAttrib = msg.tickAttrib if msg.HasField("tickAttrib") else UNSET_INTEGER
    impliedVol = msg.impliedVol if msg.HasField("impliedVol") else ib_defaults.unset
    if impliedVol and impliedVol < 0:  # -1 is the "not computed" indicator
        impliedVol = ib_defaults.unset
    delta = msg.delta if msg.HasField("delta") else ib_defaults.unset
    if delta == -2:  # -2 is the "not computed" indicator
        delta = ib_defaults.unset
    optPrice = msg.optPrice if msg.HasField("optPrice") else ib_defaults.unset
    if optPrice == -1:  # -1 is the "not computed" indicator
        optPrice = ib_defaults.unset
    pvDividend = msg.pvDividend if msg.HasField("pvDividend") else ib_defaults.unset
    if pvDividend == -1:  # -1 is the "not computed" indicator
        pvDividend = ib_defaults.unset
    gamma = msg.gamma if msg.HasField("gamma") else ib_defaults.unset
    if gamma == -2:  # -2 is the "not yet computed" indicator
        gamma = ib_defaults.unset
    vega = msg.vega if msg.HasField("vega") else ib_defaults.unset
    if vega == -2:  # -2 is the "not yet computed" indicator
        vega = ib_defaults.unset
    theta = msg.theta if msg.HasField("theta") else ib_defaults.unset
    if theta == -2:  # -2 is the "not yet computed" indicator
        theta = ib_defaults.unset
    undPrice = msg.undPrice if msg.HasField("undPrice") else ib_defaults.unset
    if undPrice == -1:  # -1 is the "not computed" indicator
        undPrice = ib_defaults.unset

    comp = OptionComputation(
        tickAttrib,
        impliedVol if impliedVol != -1 else ib_defaults.unset,
        delta if delta != -2 else ib_defaults.unset,
        optPrice if optPrice != -1 else ib_defaults.unset,
        pvDividend if pvDividend != -1 else ib_defaults.unset,
        gamma if gamma != -2 else ib_defaults.unset,
        vega if vega != -2 else ib_defaults.unset,
        theta if theta != -2 else ib_defaults.unset,
        undPrice if undPrice != -1 else ib_defaults.unset,
    )

    tick_comp = TickComputationData(
        reqId=msg.reqId,
        tickType=tickType,
        computation=comp,
    )
    return tick_comp


def createCalculateImpliedVolatilityRequestProto(
    reqId: int,
    contract: Contract,
    optionPrice: float,
    underPrice: float,
    impliedVolatilityOptionsList: list[TagValue],
) -> CalculateImpliedVolatilityRequestProto:
    calculateImpliedVolatilityRequestProto = CalculateImpliedVolatilityRequestProto()
    if isValidIntValue(reqId):
        calculateImpliedVolatilityRequestProto.reqId = reqId
    contractProto = createContractProto(contract, None)
    if contractProto is not None:
        calculateImpliedVolatilityRequestProto.contract.CopyFrom(contractProto)
    if optionPrice != UNSET_DOUBLE:
        calculateImpliedVolatilityRequestProto.optionPrice = optionPrice
    if underPrice != UNSET_DOUBLE:
        calculateImpliedVolatilityRequestProto.underPrice = underPrice
    fillTagValueList(
        impliedVolatilityOptionsList,
        calculateImpliedVolatilityRequestProto.impliedVolatilityOptions,
    )
    return calculateImpliedVolatilityRequestProto


def createCalculateOptionPriceRequestProto(
    reqId: int,
    contract: Contract,
    volatility: float,
    underPrice: float,
    optionPriceOptionsList: list[TagValue],
) -> CalculateOptionPriceRequestProto:
    calculateOptionPriceRequestProto = CalculateOptionPriceRequestProto()
    if isValidIntValue(reqId):
        calculateOptionPriceRequestProto.reqId = reqId
    contractProto = createContractProto(contract, None)
    if contractProto is not None:
        calculateOptionPriceRequestProto.contract.CopyFrom(contractProto)
    if volatility != UNSET_DOUBLE:
        calculateOptionPriceRequestProto.volatility = volatility
    if underPrice != UNSET_DOUBLE:
        calculateOptionPriceRequestProto.underPrice = underPrice
    fillTagValueList(
        optionPriceOptionsList, calculateOptionPriceRequestProto.optionPriceOptions
    )
    return calculateOptionPriceRequestProto


def createCancelCalculateImpliedVolatilityProto(
    reqId: int,
) -> CancelCalculateImpliedVolatilityProto:
    cancelCalculateImpliedVolatilityProto = CancelCalculateImpliedVolatilityProto()
    if isValidIntValue(reqId):
        cancelCalculateImpliedVolatilityProto.reqId = reqId
    return cancelCalculateImpliedVolatilityProto


def createCancelCalculateOptionPriceProto(
    reqId: int,
) -> CancelCalculateOptionPriceProto:
    cancelCalculateOptionPriceProto = CancelCalculateOptionPriceProto()
    if isValidIntValue(reqId):
        cancelCalculateOptionPriceProto.reqId = reqId
    return cancelCalculateOptionPriceProto
