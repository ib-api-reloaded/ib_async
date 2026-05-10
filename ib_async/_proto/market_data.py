"""Protobuf converters for market data and tick streams.

Pure functions: every converter takes only proto inputs (or domain
inputs on the send side). No reads from module-level state. ``HasField``
guards every optional read; ``safe_decimal`` handles every wire string
that carries a Decimal-shaped numeric. Where the wrapper signature
takes ``float`` (the Ticker hot path is still float pending the P3b
benchmark), wire ``string``-encoded sizes are routed through ``float``
at the converter boundary so the wrapper's existing comparisons keep
working.

This file plugs the contributor PR's gaps for ``MARKET_DEPTH``,
``MARKET_DEPTH_L2``, ``MKT_DEPTH_EXCHANGES``, ``REROUTE_MKT_DATA_REQ``,
``REROUTE_MKT_DEPTH_REQ``, and ``DELTA_NEUTRAL_VALIDATION`` — none of
which the upstream PR touched. The remaining tickOptionComputation
shape mirrors the binary path's silent treatment of IBKR's sentinels
(``-1``, ``-2``) so the wrapper's existing ``tickOptionComputation``
``if x != -1 else None`` logic continues to apply post-decode.

Wire shapes:

* ``TickPrice.size`` is ``string`` (wire-Decimal) — coerced to ``float``
  via ``safe_decimal`` then float() so wrapper comparisons (e.g.
  ``size == 0``) keep working.
* ``MarketDepthData.size`` and ``size`` fields throughout the file are
  similarly string-on-wire, float-at-call-site.
* ``MarketDepthData.price`` is wire ``double`` and routed unchanged.

The send-side ``createXxxRequestProto`` factories mirror the binary
``Client.send(...)`` shape: every caller-supplied field gets written
into the proto, including bool flags whose proto3 default would
otherwise silently swallow a ``True``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from .._pb import (
    CancelMarketData_pb2,
    CancelMarketDepth_pb2,
    CancelTickByTick_pb2,
    DepthMarketDataDescription_pb2,
    MarketDataRequest_pb2,
    MarketDataType_pb2,
    MarketDataTypeRequest_pb2,
    MarketDepth_pb2,
    MarketDepthData_pb2,
    MarketDepthExchanges_pb2,
    MarketDepthExchangesRequest_pb2,
    MarketDepthL2_pb2,
    MarketDepthRequest_pb2,
    RerouteMarketDataRequest_pb2,
    RerouteMarketDepthRequest_pb2,
    TickAttribBidAsk_pb2,
    TickAttribLast_pb2,
    TickByTickData_pb2,
    TickByTickRequest_pb2,
    TickGeneric_pb2,
    TickOptionComputation_pb2,
    TickPrice_pb2,
    TickReqParams_pb2,
    TickSize_pb2,
    TickSnapshotEnd_pb2,
    TickString_pb2,
)
from .._server_versions import (
    MIN_SERVER_VER_PAST_LIMIT,
    MIN_SERVER_VER_PRE_OPEN_BID_ASK,
)
from ..contract import Contract
from ..objects import (
    DepthMktDataDescription,
    TickAttrib,
    TickAttribBidAsk,
    TickAttribLast,
)
from .contracts import createContractProto
from .safe import safe_decimal

# Slotted-frozen dataclass return shapes for converters. Each one names
# the wrapper method whose positional arguments it carries and exposes
# named fields at call sites.


@dataclass(slots=True, frozen=True)
class PriceSizeTickArgs:
    """``Wrapper.priceSizeTick(reqId, tickType, price, size, attrib)`` args.

    ``attrib`` carries the canAutoExecute / pastLimit / preOpen flags
    decoded from the wire ``attrMask`` bitfield. See
    ``decodeTickAttribFromMask`` for the bit layout.
    """

    reqId: int
    tickType: int
    price: float
    size: float
    attrib: TickAttrib


@dataclass(slots=True, frozen=True)
class TickSizeArgs:
    """``Wrapper.tickSize(reqId, tickType, size)`` args."""

    reqId: int
    tickType: int
    size: float


@dataclass(slots=True, frozen=True)
class TickGenericArgs:
    """``Wrapper.tickGeneric(reqId, tickType, value)`` args."""

    reqId: int
    tickType: int
    value: float


@dataclass(slots=True, frozen=True)
class TickStringArgs:
    """``Wrapper.tickString(reqId, tickType, value)`` args."""

    reqId: int
    tickType: int
    value: str


@dataclass(slots=True, frozen=True)
class TickReqParamsArgs:
    """``Wrapper.tickReqParams(reqId, minTick, bboExchange, snapshotPermissions)`` args."""

    reqId: int
    minTick: float
    bboExchange: str
    snapshotPermissions: int


@dataclass(slots=True, frozen=True)
class TickOptionComputationArgs:
    """``Wrapper.tickOptionComputation(reqId, tickType, tickAttrib, impliedVol,
    delta, optPrice, pvDividend, gamma, vega, theta, undPrice)`` args."""

    reqId: int
    tickType: int
    tickAttrib: int
    impliedVol: float
    delta: float
    optPrice: float
    pvDividend: float
    gamma: float
    vega: float
    theta: float
    undPrice: float


@dataclass(slots=True, frozen=True)
class MarketDataTypeArgs:
    """``Wrapper.marketDataType(reqId, marketDataType)`` args."""

    reqId: int
    marketDataType: int


@dataclass(slots=True, frozen=True)
class UpdateMktDepthArgs:
    """``Wrapper.updateMktDepth(reqId, position, operation, side, price, size)`` args."""

    reqId: int
    position: int
    operation: int
    side: int
    price: float
    size: float


@dataclass(slots=True, frozen=True)
class UpdateMktDepthL2Args:
    """``Wrapper.updateMktDepthL2(reqId, position, marketMaker, operation, side,
    price, size, isSmartDepth)`` args."""

    reqId: int
    position: int
    marketMaker: str
    operation: int
    side: int
    price: float
    size: float
    isSmartDepth: bool


@dataclass(slots=True, frozen=True)
class RerouteMktReqArgs:
    """``Wrapper.rerouteMktDataReq`` / ``rerouteMktDepthReq(reqId, conId, exchange)`` args."""

    reqId: int
    conId: int
    exchange: str


@dataclass(slots=True, frozen=True)
class TickByTickAllLastArgs:
    """``Wrapper.tickByTickAllLast(reqId, tickType, time, price, size,
    tickAttribLast, exchange, specialConditions)`` args."""

    reqId: int
    tickType: int
    time: int
    price: float
    size: float
    tickAttribLast: TickAttribLast
    exchange: str
    specialConditions: str


@dataclass(slots=True, frozen=True)
class TickByTickBidAskArgs:
    """``Wrapper.tickByTickBidAsk(reqId, time, bidPrice, askPrice, bidSize,
    askSize, tickAttribBidAsk)`` args."""

    reqId: int
    time: int
    bidPrice: float
    askPrice: float
    bidSize: float
    askSize: float
    tickAttribBidAsk: TickAttribBidAsk


@dataclass(slots=True, frozen=True)
class TickByTickMidPointArgs:
    """``Wrapper.tickByTickMidPoint(reqId, time, midPoint)`` args."""

    reqId: int
    time: int
    midPoint: float


# ``dispatchTickByTick`` returns one of these branch shapes based on
# which oneof variant the proto carried, or ``None`` when no oneof
# variant was set.
TickByTickDispatch: TypeAlias = (
    TickByTickAllLastArgs | TickByTickBidAskArgs | TickByTickMidPointArgs | None
)


def _wireSizeToFloat(s: str) -> float:
    """Coerce a wire-string size to ``float`` for wrapper signatures.

    Goes through ``safe_decimal`` so empty / "nan" / garbage land as
    zero rather than raising. The wrapper's ``size == 0`` checks are
    semantically equivalent to "size is unset" on the binary path.
    """
    d = safe_decimal(s)
    return float(d) if d is not None else 0.0


# ---------------------------------------------------------------------------
# TickPrice — combined price+size dispatch (msgId 1 receive)
# ---------------------------------------------------------------------------


def decodeTickAttribFromMask(attrMask: int, serverVersion: int) -> TickAttrib:
    """Decode the wire ``attrMask`` bitfield into a ``TickAttrib`` dataclass.

    Bit layout (mirrors IBKR's ``processTickPriceMsg``):

    - pre-PAST_LIMIT (109): ``canAutoExecute = (attrMask == 1)``
    - PAST_LIMIT (109)+:    ``canAutoExecute = bit 0``, ``pastLimit = bit 1``
    - PRE_OPEN_BID_ASK (132)+: ``preOpen = bit 2``
    """
    attrib = TickAttrib()
    if serverVersion >= MIN_SERVER_VER_PAST_LIMIT:
        attrib.canAutoExecute = bool(attrMask & 1)
        attrib.pastLimit = bool(attrMask & 2)
        if serverVersion >= MIN_SERVER_VER_PRE_OPEN_BID_ASK:
            attrib.preOpen = bool(attrMask & 4)
    else:
        attrib.canAutoExecute = attrMask == 1
    return attrib


def createPriceSizeTickArgs(
    proto: TickPrice_pb2.TickPrice,
    serverVersion: int = 0,
) -> PriceSizeTickArgs:
    """``Wrapper.priceSizeTick(reqId, tickType, price, size, attrib)`` args.

    The wire ``attrMask`` decodes into a ``TickAttrib`` carrying
    ``canAutoExecute`` / ``pastLimit`` / ``preOpen`` flags so user code
    can gate trading decisions on the IBKR liquidity-quality bits.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    tickType = proto.tickType if proto.HasField("tickType") else 0
    price = float(proto.price) if proto.HasField("price") else 0.0
    size = _wireSizeToFloat(proto.size) if proto.HasField("size") else 0.0
    attrMask = proto.attrMask if proto.HasField("attrMask") else 0
    attrib = decodeTickAttribFromMask(attrMask, serverVersion)
    return PriceSizeTickArgs(
        reqId=reqId, tickType=tickType, price=price, size=size, attrib=attrib
    )


# ---------------------------------------------------------------------------
# TickSize / TickGeneric / TickString
# ---------------------------------------------------------------------------


def createTickSizeArgs(proto: TickSize_pb2.TickSize) -> TickSizeArgs:
    """``Wrapper.tickSize(reqId, tickType, size)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    tickType = proto.tickType if proto.HasField("tickType") else 0
    size = _wireSizeToFloat(proto.size) if proto.HasField("size") else 0.0
    return TickSizeArgs(reqId=reqId, tickType=tickType, size=size)


def createTickGenericArgs(
    proto: TickGeneric_pb2.TickGeneric,
) -> TickGenericArgs:
    """``Wrapper.tickGeneric(reqId, tickType, value)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    tickType = proto.tickType if proto.HasField("tickType") else 0
    value = float(proto.value) if proto.HasField("value") else 0.0
    return TickGenericArgs(reqId=reqId, tickType=tickType, value=value)


def createTickStringArgs(proto: TickString_pb2.TickString) -> TickStringArgs:
    """``Wrapper.tickString(reqId, tickType, value)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    tickType = proto.tickType if proto.HasField("tickType") else 0
    value = proto.value if proto.HasField("value") else ""
    return TickStringArgs(reqId=reqId, tickType=tickType, value=value)


# ---------------------------------------------------------------------------
# TickReqParams (msgId 81) / TickSnapshotEnd (msgId 57)
# ---------------------------------------------------------------------------


def createTickReqParamsArgs(
    proto: TickReqParams_pb2.TickReqParams,
) -> TickReqParamsArgs:
    """``Wrapper.tickReqParams(reqId, minTick, bboExchange, snapshotPermissions)`` args.

    Wire ``minTick`` is a string (Decimal precision); we coerce to
    float to match the wrapper signature. The two trailing
    ``lastPricePrecision`` / ``lastSizePrecision`` strings are dropped
    — the wrapper has no slots for them today.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    minTick = _wireSizeToFloat(proto.minTick) if proto.HasField("minTick") else 0.0
    bboExchange = proto.bboExchange if proto.HasField("bboExchange") else ""
    snapshotPermissions = (
        proto.snapshotPermissions if proto.HasField("snapshotPermissions") else 0
    )
    return TickReqParamsArgs(
        reqId=reqId,
        minTick=minTick,
        bboExchange=bboExchange,
        snapshotPermissions=snapshotPermissions,
    )


def createTickSnapshotEndReqId(proto: TickSnapshotEnd_pb2.TickSnapshotEnd) -> int:
    return proto.reqId if proto.HasField("reqId") else -1


# ---------------------------------------------------------------------------
# TickOptionComputation (msgId 21)
# ---------------------------------------------------------------------------


def createTickOptionComputationArgs(
    proto: TickOptionComputation_pb2.TickOptionComputation,
) -> TickOptionComputationArgs:
    """``Wrapper.tickOptionComputation(reqId, tickType, tickAttrib, impliedVol,
    delta, optPrice, pvDividend, gamma, vega, theta, undPrice)`` args.

    The wrapper itself maps IBKR sentinels (``-1``, ``-2``) to ``None``
    on the resulting ``OptionComputation`` so we pass the wire values
    through unchanged. Unset doubles default to 0.0; the wrapper's
    sentinel checks treat ``0.0`` as "real value", so negative
    sentinels are produced only when the wire actually carries them.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    tickType = proto.tickType if proto.HasField("tickType") else 0
    tickAttrib = proto.tickAttrib if proto.HasField("tickAttrib") else 0
    impliedVol = float(proto.impliedVol) if proto.HasField("impliedVol") else 0.0
    delta = float(proto.delta) if proto.HasField("delta") else 0.0
    optPrice = float(proto.optPrice) if proto.HasField("optPrice") else 0.0
    pvDividend = float(proto.pvDividend) if proto.HasField("pvDividend") else 0.0
    gamma = float(proto.gamma) if proto.HasField("gamma") else 0.0
    vega = float(proto.vega) if proto.HasField("vega") else 0.0
    theta = float(proto.theta) if proto.HasField("theta") else 0.0
    undPrice = float(proto.undPrice) if proto.HasField("undPrice") else 0.0
    return TickOptionComputationArgs(
        reqId=reqId,
        tickType=tickType,
        tickAttrib=tickAttrib,
        impliedVol=impliedVol,
        delta=delta,
        optPrice=optPrice,
        pvDividend=pvDividend,
        gamma=gamma,
        vega=vega,
        theta=theta,
        undPrice=undPrice,
    )


# ---------------------------------------------------------------------------
# TickByTickData (msgId 99) — oneof dispatch by tickType / inner shape
# ---------------------------------------------------------------------------


def createTickAttribBidAsk(
    proto: TickAttribBidAsk_pb2.TickAttribBidAsk,
) -> TickAttribBidAsk:
    return TickAttribBidAsk(
        bidPastLow=proto.bidPastLow if proto.HasField("bidPastLow") else False,
        askPastHigh=proto.askPastHigh if proto.HasField("askPastHigh") else False,
    )


def createTickAttribLast(proto: TickAttribLast_pb2.TickAttribLast) -> TickAttribLast:
    return TickAttribLast(
        pastLimit=proto.pastLimit if proto.HasField("pastLimit") else False,
        unreported=proto.unreported if proto.HasField("unreported") else False,
    )


def dispatchTickByTick(proto: TickByTickData_pb2.TickByTickData) -> TickByTickDispatch:
    """Decode a TickByTickData into one of the branch dataclasses the
    decoder can dispatch through, or ``None`` when no oneof variant
    was set.

    Tick types 1 and 2 ("last" and "all-last") share the same
    HistoricalTickLast inner shape; the outer ``tickType`` field
    distinguishes which the wire carried.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    tickType = proto.tickType if proto.HasField("tickType") else 0

    if proto.HasField("historicalTickLast"):
        inner = proto.historicalTickLast
        return TickByTickAllLastArgs(
            reqId=reqId,
            tickType=tickType,
            time=inner.time if inner.HasField("time") else 0,
            price=float(inner.price) if inner.HasField("price") else 0.0,
            size=_wireSizeToFloat(inner.size) if inner.HasField("size") else 0.0,
            tickAttribLast=createTickAttribLast(inner.tickAttribLast)
            if inner.HasField("tickAttribLast")
            else TickAttribLast(),
            exchange=inner.exchange if inner.HasField("exchange") else "",
            specialConditions=inner.specialConditions
            if inner.HasField("specialConditions")
            else "",
        )
    if proto.HasField("historicalTickBidAsk"):
        innerBA = proto.historicalTickBidAsk
        return TickByTickBidAskArgs(
            reqId=reqId,
            time=innerBA.time if innerBA.HasField("time") else 0,
            bidPrice=float(innerBA.priceBid) if innerBA.HasField("priceBid") else 0.0,
            askPrice=float(innerBA.priceAsk) if innerBA.HasField("priceAsk") else 0.0,
            bidSize=_wireSizeToFloat(innerBA.sizeBid)
            if innerBA.HasField("sizeBid")
            else 0.0,
            askSize=_wireSizeToFloat(innerBA.sizeAsk)
            if innerBA.HasField("sizeAsk")
            else 0.0,
            tickAttribBidAsk=createTickAttribBidAsk(innerBA.tickAttribBidAsk)
            if innerBA.HasField("tickAttribBidAsk")
            else TickAttribBidAsk(),
        )
    if proto.HasField("historicalTickMidPoint"):
        innerMP = proto.historicalTickMidPoint
        return TickByTickMidPointArgs(
            reqId=reqId,
            time=innerMP.time if innerMP.HasField("time") else 0,
            midPoint=float(innerMP.price) if innerMP.HasField("price") else 0.0,
        )
    return None


# ---------------------------------------------------------------------------
# MarketDataType (msgId 58)
# ---------------------------------------------------------------------------


def createMarketDataTypeArgs(
    proto: MarketDataType_pb2.MarketDataType,
) -> MarketDataTypeArgs:
    """``Wrapper.marketDataType(reqId, marketDataType)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    marketDataType = proto.marketDataType if proto.HasField("marketDataType") else 0
    return MarketDataTypeArgs(reqId=reqId, marketDataType=marketDataType)


# ---------------------------------------------------------------------------
# MarketDepth (msgId 12) / MarketDepthL2 (msgId 13)
# ---------------------------------------------------------------------------


_DepthDataInner: TypeAlias = tuple[int, int, int, float, float, str, bool]


def _depthDataArgs(
    data: MarketDepthData_pb2.MarketDepthData,
) -> _DepthDataInner:
    """Common decode for the inner MarketDepthData payload."""
    position = data.position if data.HasField("position") else 0
    operation = data.operation if data.HasField("operation") else 0
    side = data.side if data.HasField("side") else 0
    price = float(data.price) if data.HasField("price") else 0.0
    size = _wireSizeToFloat(data.size) if data.HasField("size") else 0.0
    marketMaker = data.marketMaker if data.HasField("marketMaker") else ""
    isSmartDepth = data.isSmartDepth if data.HasField("isSmartDepth") else False
    return position, operation, side, price, size, marketMaker, isSmartDepth


def createUpdateMktDepthArgs(
    proto: MarketDepth_pb2.MarketDepth,
) -> UpdateMktDepthArgs:
    """``Wrapper.updateMktDepth(reqId, position, operation, side, price, size)`` args.

    ``MarketDepth`` does not carry the ``marketMaker`` slot (that's
    L2-only); the inner data carries it but the wrapper overload
    discards it for the L1 code path.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    if not proto.HasField("marketDepthData"):
        return UpdateMktDepthArgs(
            reqId=reqId, position=0, operation=0, side=0, price=0.0, size=0.0
        )
    position, operation, side, price, size, _, _ = _depthDataArgs(proto.marketDepthData)
    return UpdateMktDepthArgs(
        reqId=reqId,
        position=position,
        operation=operation,
        side=side,
        price=price,
        size=size,
    )


def createUpdateMktDepthL2Args(
    proto: MarketDepthL2_pb2.MarketDepthL2,
) -> UpdateMktDepthL2Args:
    """``Wrapper.updateMktDepthL2(reqId, position, marketMaker, operation,
    side, price, size, isSmartDepth)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    if not proto.HasField("marketDepthData"):
        return UpdateMktDepthL2Args(
            reqId=reqId,
            position=0,
            marketMaker="",
            operation=0,
            side=0,
            price=0.0,
            size=0.0,
            isSmartDepth=False,
        )
    position, operation, side, price, size, marketMaker, isSmartDepth = _depthDataArgs(
        proto.marketDepthData
    )
    return UpdateMktDepthL2Args(
        reqId=reqId,
        position=position,
        marketMaker=marketMaker,
        operation=operation,
        side=side,
        price=price,
        size=size,
        isSmartDepth=isSmartDepth,
    )


# ---------------------------------------------------------------------------
# DepthMarketDataDescription (msgId 82) — list payload
# ---------------------------------------------------------------------------


def createDepthMktDataDescription(
    proto: DepthMarketDataDescription_pb2.DepthMarketDataDescription,
) -> DepthMktDataDescription:
    return DepthMktDataDescription(
        exchange=proto.exchange if proto.HasField("exchange") else "",
        secType=proto.secType if proto.HasField("secType") else "",
        listingExch=proto.listingExch if proto.HasField("listingExch") else "",
        serviceDataType=proto.serviceDataType
        if proto.HasField("serviceDataType")
        else "",
        aggGroup=proto.aggGroup if proto.HasField("aggGroup") else 0,
    )


def createMarketDepthExchangesList(
    proto: MarketDepthExchanges_pb2.MarketDepthExchanges,
) -> list[DepthMktDataDescription]:
    """``Wrapper.mktDepthExchanges(list)`` payload."""
    return [createDepthMktDataDescription(d) for d in proto.depthMarketDataDescriptions]


# ---------------------------------------------------------------------------
# Reroute requests (msgId 64 / 65 receive)
# ---------------------------------------------------------------------------


def createRerouteMktDataReqArgs(
    proto: RerouteMarketDataRequest_pb2.RerouteMarketDataRequest,
) -> RerouteMktReqArgs:
    """``Wrapper.rerouteMktDataReq(reqId, conId, exchange)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    conId = proto.conId if proto.HasField("conId") else 0
    exchange = proto.exchange if proto.HasField("exchange") else ""
    return RerouteMktReqArgs(reqId=reqId, conId=conId, exchange=exchange)


def createRerouteMktDepthReqArgs(
    proto: RerouteMarketDepthRequest_pb2.RerouteMarketDepthRequest,
) -> RerouteMktReqArgs:
    """``Wrapper.rerouteMktDepthReq(reqId, conId, exchange)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    conId = proto.conId if proto.HasField("conId") else 0
    exchange = proto.exchange if proto.HasField("exchange") else ""
    return RerouteMktReqArgs(reqId=reqId, conId=conId, exchange=exchange)


# ===========================================================================
# Send-side request envelopes
# ===========================================================================


def createMarketDataRequestProto(
    reqId: int,
    contract: Contract,
    genericTickList: str,
    snapshot: bool,
    regulatorySnapshot: bool,
) -> MarketDataRequest_pb2.MarketDataRequest:
    proto = MarketDataRequest_pb2.MarketDataRequest()
    proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    proto.genericTickList = genericTickList
    proto.snapshot = snapshot
    proto.regulatorySnapshot = regulatorySnapshot
    return proto


def createCancelMarketDataProto(reqId: int) -> CancelMarketData_pb2.CancelMarketData:
    proto = CancelMarketData_pb2.CancelMarketData()
    proto.reqId = reqId
    return proto


def createMarketDataTypeRequestProto(
    marketDataType: int,
) -> MarketDataTypeRequest_pb2.MarketDataTypeRequest:
    proto = MarketDataTypeRequest_pb2.MarketDataTypeRequest()
    proto.marketDataType = marketDataType
    return proto


def createMarketDepthRequestProto(
    reqId: int, contract: Contract, numRows: int, isSmartDepth: bool
) -> MarketDepthRequest_pb2.MarketDepthRequest:
    proto = MarketDepthRequest_pb2.MarketDepthRequest()
    proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    proto.numRows = numRows
    proto.isSmartDepth = isSmartDepth
    return proto


def createCancelMarketDepthProto(
    reqId: int, isSmartDepth: bool
) -> CancelMarketDepth_pb2.CancelMarketDepth:
    proto = CancelMarketDepth_pb2.CancelMarketDepth()
    proto.reqId = reqId
    proto.isSmartDepth = isSmartDepth
    return proto


def createMarketDepthExchangesRequestProto() -> (
    MarketDepthExchangesRequest_pb2.MarketDepthExchangesRequest
):
    return MarketDepthExchangesRequest_pb2.MarketDepthExchangesRequest()


def createTickByTickRequestProto(
    reqId: int,
    contract: Contract,
    tickType: str,
    numberOfTicks: int,
    ignoreSize: bool,
) -> TickByTickRequest_pb2.TickByTickRequest:
    proto = TickByTickRequest_pb2.TickByTickRequest()
    proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    proto.tickType = tickType
    proto.numberOfTicks = numberOfTicks
    proto.ignoreSize = ignoreSize
    return proto


def createCancelTickByTickProto(reqId: int) -> CancelTickByTick_pb2.CancelTickByTick:
    proto = CancelTickByTick_pb2.CancelTickByTick()
    proto.reqId = reqId
    return proto


# ---------------------------------------------------------------------------
# DeltaNeutralValidation (msgId 56)
# ---------------------------------------------------------------------------
# IBKR does not ship a dedicated ``DeltaNeutralValidation`` proto — the
# validation message is encoded as the existing ``DeltaNeutralContract``
# proto directly. The decoder dispatches msgId 56 to ``createDeltaNeutralContract``
# from ``contracts.py`` and packages it with the reqId at the call site.
