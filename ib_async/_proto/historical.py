"""Protobuf converters for historical bars, ticks, schedule, and head timestamp.

Pure functions: every converter takes only proto inputs (or domain
inputs on the send side). No reads from module-level state. ``HasField``
guards every optional read; ``safe_decimal`` produces the
``Decimal | None`` shape that ``BarData`` / ``RealTimeBar`` adopted in
the v3.0 dataclass migration.

Wire shape notes:

* ``HistoricalDataBar.{open,high,low,close}`` are wire ``double``;
  ``volume`` and ``WAP`` are wire ``string`` (Decimal-precision). Both
  route through ``safe_decimal`` (with ``str()`` for doubles so binary
  float imprecision doesn't leak into the Decimal). ``date`` is the
  raw wire string — the wrapper's ``_normalizeDatetime`` parses it.
* ``RealTimeBarTick`` is the proto wrapper for what the wire historically
  called RealTimeBars (msgId 50). The wrapper's ``realtimeBar`` method
  takes positional args ``(reqId, time, open, high, low, close, volume,
  wap, count)``.
* ``HistoricalTick`` family ``size`` fields are strings; ``time`` is
  int64 (epoch seconds). ``HistoricalTick`` records remain
  ``float``-typed in this commit pending the Ticker hot-path benchmark
  (see ``_proto/market_data.py`` rationale).
* ``HistoricalSchedule`` carries a repeated ``HistoricalSession`` slot;
  the converter unpacks it into the existing domain ``HistoricalSchedule``
  dataclass with ``HistoricalSession`` children.

Send-side request envelopes follow the same discipline as the rest of
``_proto/``: every caller-supplied field — including bool flags whose
proto3 default would silently swallow a ``True`` — is written into the
proto.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .._pb import (
    CancelContractData_pb2,
    CancelHeadTimestamp_pb2,
    CancelHistogramData_pb2,
    CancelHistoricalData_pb2,
    CancelHistoricalTicks_pb2,
    CancelRealTimeBars_pb2,
    HeadTimestamp_pb2,
    HeadTimestampRequest_pb2,
    HistogramData_pb2,
    HistogramDataEntry_pb2,
    HistogramDataRequest_pb2,
    HistoricalData_pb2,
    HistoricalDataBar_pb2,
    HistoricalDataEnd_pb2,
    HistoricalDataRequest_pb2,
    HistoricalDataUpdate_pb2,
    HistoricalSchedule_pb2,
    HistoricalSession_pb2,
    HistoricalTick_pb2,
    HistoricalTickBidAsk_pb2,
    HistoricalTickLast_pb2,
    HistoricalTicks_pb2,
    HistoricalTicksBidAsk_pb2,
    HistoricalTicksLast_pb2,
    HistoricalTicksRequest_pb2,
    RealTimeBarsRequest_pb2,
    RealTimeBarTick_pb2,
)
from ..contract import Contract, TagValue
from ..objects import (
    BarData,
    HistogramData,
    HistoricalSession,
    HistoricalTick,
    HistoricalTickBidAsk,
    HistoricalTickLast,
)
from ..util import UNSET_INTEGER
from .contracts import createContractProto
from .market_data import createTickAttribBidAsk, createTickAttribLast
from .safe import fill_tag_value_map, safe_decimal, wire_size_to_float

# Frozen-slotted dataclass return shapes for converter functions. Each one
# names the wrapper method whose positional arguments it carries so call
# sites read as ``self.wrapper.X(*astuple(args))`` (or by named field)
# without losing the type story.


@dataclass(slots=True, frozen=True)
class HistoricalDataBars:
    """``Wrapper.historicalData(reqId, bar)`` — batched per-reqId bars."""

    reqId: int
    bars: list[BarData]


@dataclass(slots=True, frozen=True)
class HistoricalDataEndArgs:
    """``Wrapper.historicalDataEnd(reqId, start, end)`` args."""

    reqId: int
    start: str
    end: str


@dataclass(slots=True, frozen=True)
class HistoricalDataUpdateArgs:
    """``Wrapper.historicalDataUpdate(reqId, bar)`` args."""

    reqId: int
    bar: BarData


@dataclass(slots=True, frozen=True)
class RealtimeBarArgs:
    """``Wrapper.realtimeBar(reqId, time, open_, high, low, close, volume, wap, count)`` args."""

    reqId: int
    time: int
    open_: Decimal | None
    high: Decimal | None
    low: Decimal | None
    close: Decimal | None
    volume: Decimal | None
    wap: Decimal | None
    count: int


@dataclass(slots=True, frozen=True)
class HeadTimestampArgs:
    """``Wrapper.headTimestamp(reqId, headTimestamp)`` args."""

    reqId: int
    headTimestamp: str


@dataclass(slots=True, frozen=True)
class HistogramDataArgs:
    """``Wrapper.histogramData(reqId, items)`` args."""

    reqId: int
    items: list[HistogramData]


@dataclass(slots=True, frozen=True)
class HistoricalScheduleArgs:
    """``Wrapper.historicalSchedule(reqId, startDateTime, endDateTime, timeZone, sessions)`` args."""

    reqId: int
    startDateTime: str
    endDateTime: str
    timeZone: str
    sessions: list[HistoricalSession]


@dataclass(slots=True, frozen=True)
class HistoricalTicksArgs:
    """``Wrapper.historicalTicks(reqId, ticks, done)`` args."""

    reqId: int
    ticks: list[HistoricalTick]
    done: bool


@dataclass(slots=True, frozen=True)
class HistoricalTicksBidAskArgs:
    """``Wrapper.historicalTicksBidAsk(reqId, ticks, done)`` args."""

    reqId: int
    ticks: list[HistoricalTickBidAsk]
    done: bool


@dataclass(slots=True, frozen=True)
class HistoricalTicksLastArgs:
    """``Wrapper.historicalTicksLast(reqId, ticks, done)`` args."""

    reqId: int
    ticks: list[HistoricalTickLast]
    done: bool


# ---------------------------------------------------------------------------
# HistoricalDataBar — building block for HistoricalData / Update
# ---------------------------------------------------------------------------


def createBarData(proto: HistoricalDataBar_pb2.HistoricalDataBar) -> BarData:
    """Decode a HistoricalDataBar proto into the v3.0 Decimal-native ``BarData``.

    Doubles are routed through ``str()`` before ``safe_decimal`` so
    fractional values like ``0.1`` round-trip cleanly. Wire-string
    ``volume`` / ``WAP`` route through ``safe_decimal`` directly.
    """
    return BarData(
        date=proto.date if proto.HasField("date") else "",  # type: ignore[arg-type]
        open=safe_decimal(proto.open) if proto.HasField("open") else None,
        high=safe_decimal(proto.high) if proto.HasField("high") else None,
        low=safe_decimal(proto.low) if proto.HasField("low") else None,
        close=safe_decimal(proto.close) if proto.HasField("close") else None,
        volume=safe_decimal(proto.volume) if proto.HasField("volume") else None,
        average=safe_decimal(proto.WAP) if proto.HasField("WAP") else None,
        barCount=proto.barCount if proto.HasField("barCount") else 0,
    )


# ---------------------------------------------------------------------------
# HistoricalData (msgId 17 receive) + End (msgId 19 receive)
# ---------------------------------------------------------------------------


def createHistoricalDataBars(
    proto: HistoricalData_pb2.HistoricalData,
) -> HistoricalDataBars:
    """Decode a HistoricalData proto into ``HistoricalDataBars(reqId, bars)``.

    The wrapper's ``historicalData(reqId, bar)`` is called per-bar by
    the binary path; the protobuf path delivers all bars in a single
    repeated field. Caller iterates and dispatches.
    """
    reqId = proto.reqId if proto.HasField("reqId") else -1
    bars = [createBarData(b) for b in proto.historicalDataBars]
    return HistoricalDataBars(reqId=reqId, bars=bars)


def createHistoricalDataEndArgs(
    proto: HistoricalDataEnd_pb2.HistoricalDataEnd,
) -> HistoricalDataEndArgs:
    """``Wrapper.historicalDataEnd(reqId, start, end)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    start = proto.startDateStr if proto.HasField("startDateStr") else ""
    end = proto.endDateStr if proto.HasField("endDateStr") else ""
    return HistoricalDataEndArgs(reqId=reqId, start=start, end=end)


# ---------------------------------------------------------------------------
# HistoricalDataUpdate (msgId 90 receive)
# ---------------------------------------------------------------------------


def createHistoricalDataUpdateArgs(
    proto: HistoricalDataUpdate_pb2.HistoricalDataUpdate,
) -> HistoricalDataUpdateArgs:
    """``Wrapper.historicalDataUpdate(reqId, bar)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    if proto.HasField("historicalDataBar"):
        bar = createBarData(proto.historicalDataBar)
    else:
        bar = BarData()
    return HistoricalDataUpdateArgs(reqId=reqId, bar=bar)


# ---------------------------------------------------------------------------
# RealTimeBarTick (msgId 50 receive) — wire name for live real-time bars
# ---------------------------------------------------------------------------


def createRealtimeBarArgs(
    proto: RealTimeBarTick_pb2.RealTimeBarTick,
) -> RealtimeBarArgs:
    """``Wrapper.realtimeBar(reqId, time, open_, high, low, close, volume, wap, count)`` args.

    OHLC fields route through ``safe_decimal`` to match the
    Decimal-native ``RealTimeBar`` shape; wrapper signature accepts
    ``Decimal | None``.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    time_ = int(proto.time) if proto.HasField("time") else 0
    open_ = safe_decimal(proto.open) if proto.HasField("open") else None
    high = safe_decimal(proto.high) if proto.HasField("high") else None
    low = safe_decimal(proto.low) if proto.HasField("low") else None
    close = safe_decimal(proto.close) if proto.HasField("close") else None
    volume = safe_decimal(proto.volume) if proto.HasField("volume") else None
    wap = safe_decimal(proto.WAP) if proto.HasField("WAP") else None
    count = proto.count if proto.HasField("count") else 0
    return RealtimeBarArgs(
        reqId=reqId,
        time=time_,
        open_=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        wap=wap,
        count=count,
    )


# ---------------------------------------------------------------------------
# HeadTimestamp (msgId 88 receive)
# ---------------------------------------------------------------------------


def createHeadTimestampArgs(
    proto: HeadTimestamp_pb2.HeadTimestamp,
) -> HeadTimestampArgs:
    """``Wrapper.headTimestamp(reqId, headTimestamp)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    head = proto.headTimestamp if proto.HasField("headTimestamp") else ""
    return HeadTimestampArgs(reqId=reqId, headTimestamp=head)


# ---------------------------------------------------------------------------
# HistogramData (msgId 89 receive)
# ---------------------------------------------------------------------------


def createHistogramDataEntry(
    proto: HistogramDataEntry_pb2.HistogramDataEntry,
) -> HistogramData:
    """The proto's nested entry maps onto the domain ``HistogramData``
    dataclass directly (the domain does not distinguish container vs
    entry — each entry IS a ``HistogramData`` row).
    """
    price = float(proto.price) if proto.HasField("price") else 0.0
    size = safe_decimal(proto.size) if proto.HasField("size") else None
    return HistogramData(price=price, size=size)


def createHistogramDataArgs(
    proto: HistogramData_pb2.HistogramData,
) -> HistogramDataArgs:
    """``Wrapper.histogramData(reqId, items)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    items = [createHistogramDataEntry(e) for e in proto.histogramDataEntries]
    return HistogramDataArgs(reqId=reqId, items=items)


# ---------------------------------------------------------------------------
# HistoricalSchedule (msgId 106 receive)
# ---------------------------------------------------------------------------


def createHistoricalSession(
    proto: HistoricalSession_pb2.HistoricalSession,
) -> HistoricalSession:
    return HistoricalSession(
        startDateTime=proto.startDateTime if proto.HasField("startDateTime") else "",
        endDateTime=proto.endDateTime if proto.HasField("endDateTime") else "",
        refDate=proto.refDate if proto.HasField("refDate") else "",
    )


def createHistoricalScheduleArgs(
    proto: HistoricalSchedule_pb2.HistoricalSchedule,
) -> HistoricalScheduleArgs:
    """``Wrapper.historicalSchedule(reqId, startDateTime, endDateTime,
    timeZone, sessions)`` args. The wrapper builds the
    ``HistoricalSchedule`` dataclass from these primitives itself."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    startDateTime = proto.startDateTime if proto.HasField("startDateTime") else ""
    endDateTime = proto.endDateTime if proto.HasField("endDateTime") else ""
    timeZone = proto.timeZone if proto.HasField("timeZone") else ""
    sessions = [createHistoricalSession(s) for s in proto.historicalSessions]
    return HistoricalScheduleArgs(
        reqId=reqId,
        startDateTime=startDateTime,
        endDateTime=endDateTime,
        timeZone=timeZone,
        sessions=sessions,
    )


# ---------------------------------------------------------------------------
# HistoricalTick / HistoricalTickBidAsk / HistoricalTickLast (per-tick)
# ---------------------------------------------------------------------------


def createHistoricalTick(
    proto: HistoricalTick_pb2.HistoricalTick,
) -> HistoricalTick:
    return HistoricalTick(
        time=proto.time if proto.HasField("time") else 0,  # type: ignore[arg-type]
        price=float(proto.price) if proto.HasField("price") else 0.0,
        size=wire_size_to_float(proto.size) if proto.HasField("size") else 0.0,
    )


def createHistoricalTickBidAsk(
    proto: HistoricalTickBidAsk_pb2.HistoricalTickBidAsk,
) -> HistoricalTickBidAsk:
    return HistoricalTickBidAsk(
        time=proto.time if proto.HasField("time") else 0,  # type: ignore[arg-type]
        tickAttribBidAsk=createTickAttribBidAsk(proto.tickAttribBidAsk)
        if proto.HasField("tickAttribBidAsk")
        else None,  # type: ignore[arg-type]
        priceBid=float(proto.priceBid) if proto.HasField("priceBid") else 0.0,
        priceAsk=float(proto.priceAsk) if proto.HasField("priceAsk") else 0.0,
        sizeBid=wire_size_to_float(proto.sizeBid) if proto.HasField("sizeBid") else 0.0,
        sizeAsk=wire_size_to_float(proto.sizeAsk) if proto.HasField("sizeAsk") else 0.0,
    )


def createHistoricalTickLast(
    proto: HistoricalTickLast_pb2.HistoricalTickLast,
) -> HistoricalTickLast:
    return HistoricalTickLast(
        time=proto.time if proto.HasField("time") else 0,  # type: ignore[arg-type]
        tickAttribLast=createTickAttribLast(proto.tickAttribLast)
        if proto.HasField("tickAttribLast")
        else None,  # type: ignore[arg-type]
        price=float(proto.price) if proto.HasField("price") else 0.0,
        size=wire_size_to_float(proto.size) if proto.HasField("size") else 0.0,
        exchange=proto.exchange if proto.HasField("exchange") else "",
        specialConditions=proto.specialConditions
        if proto.HasField("specialConditions")
        else "",
    )


# ---------------------------------------------------------------------------
# HistoricalTicks / HistoricalTicksBidAsk / HistoricalTicksLast (batched)
# ---------------------------------------------------------------------------


def createHistoricalTicksArgs(
    proto: HistoricalTicks_pb2.HistoricalTicks,
) -> HistoricalTicksArgs:
    """``Wrapper.historicalTicks(reqId, ticks, done)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    ticks = [createHistoricalTick(t) for t in proto.historicalTicks]
    done = proto.isDone if proto.HasField("isDone") else False
    return HistoricalTicksArgs(reqId=reqId, ticks=ticks, done=done)


def createHistoricalTicksBidAskArgs(
    proto: HistoricalTicksBidAsk_pb2.HistoricalTicksBidAsk,
) -> HistoricalTicksBidAskArgs:
    """``Wrapper.historicalTicksBidAsk(reqId, ticks, done)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    ticksBA = [createHistoricalTickBidAsk(t) for t in proto.historicalTicksBidAsk]
    done = proto.isDone if proto.HasField("isDone") else False
    return HistoricalTicksBidAskArgs(reqId=reqId, ticks=ticksBA, done=done)


def createHistoricalTicksLastArgs(
    proto: HistoricalTicksLast_pb2.HistoricalTicksLast,
) -> HistoricalTicksLastArgs:
    """``Wrapper.historicalTicksLast(reqId, ticks, done)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    ticksLast = [createHistoricalTickLast(t) for t in proto.historicalTicksLast]
    done = proto.isDone if proto.HasField("isDone") else False
    return HistoricalTicksLastArgs(reqId=reqId, ticks=ticksLast, done=done)


# ===========================================================================
# Send-side request envelopes
# ===========================================================================


def createHistoricalDataRequestProto(
    reqId: int,
    contract: Contract,
    endDateTime: str,
    durationStr: str,
    barSizeSetting: str,
    whatToShow: str,
    useRTH: int,
    formatDate: int,
    keepUpToDate: bool,
    chartOptions: list[TagValue] | None = None,
) -> HistoricalDataRequest_pb2.HistoricalDataRequest:
    # Each scalar gated per IBKR's ``client_utils.createHistoricalDataRequestProto``:
    # reqId / formatDate via isValidIntValue; strings via non-empty;
    # bools via truthy.
    proto = HistoricalDataRequest_pb2.HistoricalDataRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    if endDateTime:
        proto.endDateTime = endDateTime
    if barSizeSetting:
        proto.barSizeSetting = barSizeSetting
    if durationStr:
        proto.duration = durationStr
    if useRTH:
        proto.useRTH = bool(useRTH)
    if whatToShow:
        proto.whatToShow = whatToShow
    if formatDate != UNSET_INTEGER:
        proto.formatDate = formatDate
    if keepUpToDate:
        proto.keepUpToDate = keepUpToDate
    fill_tag_value_map(chartOptions, proto.chartOptions)
    return proto


def createCancelHistoricalDataProto(
    reqId: int,
) -> CancelHistoricalData_pb2.CancelHistoricalData:
    proto = CancelHistoricalData_pb2.CancelHistoricalData()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto


def createRealTimeBarsRequestProto(
    reqId: int,
    contract: Contract,
    barSize: int,
    whatToShow: str,
    useRTH: bool,
    realTimeBarsOptions: list[TagValue] | None = None,
) -> RealTimeBarsRequest_pb2.RealTimeBarsRequest:
    proto = RealTimeBarsRequest_pb2.RealTimeBarsRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    if barSize != UNSET_INTEGER:
        proto.barSize = barSize
    if whatToShow:
        proto.whatToShow = whatToShow
    if useRTH:
        proto.useRTH = useRTH
    fill_tag_value_map(realTimeBarsOptions, proto.realTimeBarsOptions)
    return proto


def createCancelRealTimeBarsProto(
    reqId: int,
) -> CancelRealTimeBars_pb2.CancelRealTimeBars:
    proto = CancelRealTimeBars_pb2.CancelRealTimeBars()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto


def createHeadTimestampRequestProto(
    reqId: int, contract: Contract, useRTH: int, whatToShow: str, formatDate: int
) -> HeadTimestampRequest_pb2.HeadTimestampRequest:
    proto = HeadTimestampRequest_pb2.HeadTimestampRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    if useRTH:
        proto.useRTH = bool(useRTH)
    if whatToShow:
        proto.whatToShow = whatToShow
    if formatDate != UNSET_INTEGER:
        proto.formatDate = formatDate
    return proto


def createCancelHeadTimestampProto(
    reqId: int,
) -> CancelHeadTimestamp_pb2.CancelHeadTimestamp:
    proto = CancelHeadTimestamp_pb2.CancelHeadTimestamp()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto


def createHistogramDataRequestProto(
    reqId: int, contract: Contract, useRTH: bool, timePeriod: str
) -> HistogramDataRequest_pb2.HistogramDataRequest:
    proto = HistogramDataRequest_pb2.HistogramDataRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    if useRTH:
        proto.useRTH = useRTH
    if timePeriod:
        proto.timePeriod = timePeriod
    return proto


def createCancelHistogramDataProto(
    reqId: int,
) -> CancelHistogramData_pb2.CancelHistogramData:
    proto = CancelHistogramData_pb2.CancelHistogramData()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto


def createHistoricalTicksRequestProto(
    reqId: int,
    contract: Contract,
    startDateTime: str,
    endDateTime: str,
    numberOfTicks: int,
    whatToShow: str,
    useRTH: int,
    ignoreSize: bool,
    miscOptions: list[TagValue] | None = None,
) -> HistoricalTicksRequest_pb2.HistoricalTicksRequest:
    proto = HistoricalTicksRequest_pb2.HistoricalTicksRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    if startDateTime:
        proto.startDateTime = startDateTime
    if endDateTime:
        proto.endDateTime = endDateTime
    if numberOfTicks != UNSET_INTEGER:
        proto.numberOfTicks = numberOfTicks
    if whatToShow:
        proto.whatToShow = whatToShow
    if useRTH:
        proto.useRTH = bool(useRTH)
    if ignoreSize:
        proto.ignoreSize = ignoreSize
    fill_tag_value_map(miscOptions, proto.miscOptions)
    return proto


def createCancelHistoricalTicksProto(
    reqId: int,
) -> CancelHistoricalTicks_pb2.CancelHistoricalTicks:
    proto = CancelHistoricalTicks_pb2.CancelHistoricalTicks()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto


def createCancelContractDataProto(
    reqId: int,
) -> CancelContractData_pb2.CancelContractData:
    """Build a CancelContractData proto. Proto-only message family —
    the binary path has no equivalent. Mirrors IBKR's reference
    ``client_utils.createCancelContractDataProto``.
    """
    proto = CancelContractData_pb2.CancelContractData()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto
