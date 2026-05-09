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

from .._pb import (
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
from ..contract import Contract
from ..objects import (
    BarData,
    HistogramData,
    HistoricalSchedule,
    HistoricalSession,
    HistoricalTick,
    HistoricalTickBidAsk,
    HistoricalTickLast,
)
from .contracts import createContractProto
from .market_data import createTickAttribBidAsk, createTickAttribLast
from .safe import safe_decimal

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
        open=safe_decimal(str(proto.open)) if proto.HasField("open") else None,
        high=safe_decimal(str(proto.high)) if proto.HasField("high") else None,
        low=safe_decimal(str(proto.low)) if proto.HasField("low") else None,
        close=safe_decimal(str(proto.close)) if proto.HasField("close") else None,
        volume=safe_decimal(proto.volume) if proto.HasField("volume") else None,
        average=safe_decimal(proto.WAP) if proto.HasField("WAP") else None,
        barCount=proto.barCount if proto.HasField("barCount") else 0,
    )


# ---------------------------------------------------------------------------
# HistoricalData (msgId 17 receive) + End (msgId 19 receive)
# ---------------------------------------------------------------------------


def iterHistoricalDataBars(
    proto: HistoricalData_pb2.HistoricalData,
) -> tuple[int, list[BarData]]:
    """Decode a HistoricalData proto into ``(reqId, [BarData])``.

    The wrapper's ``historicalData(reqId, bar)`` is called per-bar by
    the binary path; the protobuf path delivers all bars in a single
    repeated field. Caller iterates and dispatches.
    """
    reqId = proto.reqId if proto.HasField("reqId") else -1
    bars = [createBarData(b) for b in proto.historicalDataBars]
    return reqId, bars


def createHistoricalDataEndArgs(
    proto: HistoricalDataEnd_pb2.HistoricalDataEnd,
) -> tuple[int, str, str]:
    """``Wrapper.historicalDataEnd(reqId, start, end)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    start = proto.startDateStr if proto.HasField("startDateStr") else ""
    end = proto.endDateStr if proto.HasField("endDateStr") else ""
    return reqId, start, end


# ---------------------------------------------------------------------------
# HistoricalDataUpdate (msgId 90 receive)
# ---------------------------------------------------------------------------


def createHistoricalDataUpdateArgs(
    proto: HistoricalDataUpdate_pb2.HistoricalDataUpdate,
) -> tuple[int, BarData]:
    """``Wrapper.historicalDataUpdate(reqId, bar)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    if proto.HasField("historicalDataBar"):
        bar = createBarData(proto.historicalDataBar)
    else:
        bar = BarData()
    return reqId, bar


# ---------------------------------------------------------------------------
# RealTimeBarTick (msgId 50 receive) — wire name for live real-time bars
# ---------------------------------------------------------------------------


def createRealtimeBarArgs(
    proto: RealTimeBarTick_pb2.RealTimeBarTick,
) -> tuple[int, int, object, object, object, object, object, object, int]:
    """``Wrapper.realtimeBar(reqId, time, open_, high, low, close, volume, wap, count)`` args.

    OHLC fields route through ``safe_decimal(str(...))`` to match the
    Decimal-native ``RealTimeBar`` shape; wrapper signature accepts
    ``Decimal | None``.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    time_ = int(proto.time) if proto.HasField("time") else 0
    open_ = safe_decimal(str(proto.open)) if proto.HasField("open") else None
    high = safe_decimal(str(proto.high)) if proto.HasField("high") else None
    low = safe_decimal(str(proto.low)) if proto.HasField("low") else None
    close = safe_decimal(str(proto.close)) if proto.HasField("close") else None
    volume = safe_decimal(proto.volume) if proto.HasField("volume") else None
    wap = safe_decimal(proto.WAP) if proto.HasField("WAP") else None
    count = proto.count if proto.HasField("count") else 0
    return reqId, time_, open_, high, low, close, volume, wap, count


# ---------------------------------------------------------------------------
# HeadTimestamp (msgId 88 receive)
# ---------------------------------------------------------------------------


def createHeadTimestampArgs(
    proto: HeadTimestamp_pb2.HeadTimestamp,
) -> tuple[int, str]:
    """``Wrapper.headTimestamp(reqId, headTimestamp)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    head = proto.headTimestamp if proto.HasField("headTimestamp") else ""
    return reqId, head


# ---------------------------------------------------------------------------
# HistogramData (msgId 89 receive)
# ---------------------------------------------------------------------------


def createHistogramDataEntry(
    proto: HistogramDataEntry_pb2.HistogramDataEntry,
) -> HistogramData:
    """The proto's nested entry maps onto the domain ``HistogramData``
    dataclass directly (the domain does not distinguish container vs
    entry — each entry IS a ``HistogramData`` row)."""
    price = float(proto.price) if proto.HasField("price") else 0.0
    size_d = safe_decimal(proto.size) if proto.HasField("size") else None
    size = float(size_d) if size_d is not None else 0.0
    return HistogramData(price=price, count=int(size))


def createHistogramDataArgs(
    proto: HistogramData_pb2.HistogramData,
) -> tuple[int, list[HistogramData]]:
    """``Wrapper.histogramData(reqId, items)`` args.

    Note ``size`` on the wire is a string (Decimal precision); we coerce
    to an int count on the way out because the domain field is
    ``HistogramData.count: int``. (Fractional histogram counts have no
    semantics in the IBKR API.)
    """
    reqId = proto.reqId if proto.HasField("reqId") else -1
    items = [createHistogramDataEntry(e) for e in proto.histogramDataEntries]
    return reqId, items


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
) -> tuple[int, HistoricalSchedule]:
    """``Wrapper.historicalSchedule(reqId, schedule)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    schedule = HistoricalSchedule(
        startDateTime=proto.startDateTime if proto.HasField("startDateTime") else "",
        endDateTime=proto.endDateTime if proto.HasField("endDateTime") else "",
        timeZone=proto.timeZone if proto.HasField("timeZone") else "",
        sessions=[createHistoricalSession(s) for s in proto.historicalSessions],
    )
    return reqId, schedule


# ---------------------------------------------------------------------------
# HistoricalTick / HistoricalTickBidAsk / HistoricalTickLast (per-tick)
# ---------------------------------------------------------------------------


def _wireSizeToFloat(s: str) -> float:
    """Parallel to ``market_data._wireSizeToFloat`` — wire string → float
    via ``safe_decimal``. Sizes are float-typed on these tick records
    pending the Ticker hot-path benchmark."""
    d = safe_decimal(s)
    return float(d) if d is not None else 0.0


def createHistoricalTick(
    proto: HistoricalTick_pb2.HistoricalTick,
) -> HistoricalTick:
    return HistoricalTick(
        time=proto.time if proto.HasField("time") else 0,  # type: ignore[arg-type]
        price=float(proto.price) if proto.HasField("price") else 0.0,
        size=_wireSizeToFloat(proto.size) if proto.HasField("size") else 0.0,
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
        sizeBid=_wireSizeToFloat(proto.sizeBid) if proto.HasField("sizeBid") else 0.0,
        sizeAsk=_wireSizeToFloat(proto.sizeAsk) if proto.HasField("sizeAsk") else 0.0,
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
        size=_wireSizeToFloat(proto.size) if proto.HasField("size") else 0.0,
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
) -> tuple[int, list[HistoricalTick], bool]:
    """``Wrapper.historicalTicks(reqId, ticks, done)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    ticks = [createHistoricalTick(t) for t in proto.historicalTicks]
    done = proto.isDone if proto.HasField("isDone") else False
    return reqId, ticks, done


def createHistoricalTicksBidAskArgs(
    proto: HistoricalTicksBidAsk_pb2.HistoricalTicksBidAsk,
) -> tuple[int, list[HistoricalTickBidAsk], bool]:
    """``Wrapper.historicalTicksBidAsk(reqId, ticks, done)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    ticks = [createHistoricalTickBidAsk(t) for t in proto.historicalTicksBidAsk]
    done = proto.isDone if proto.HasField("isDone") else False
    return reqId, ticks, done


def createHistoricalTicksLastArgs(
    proto: HistoricalTicksLast_pb2.HistoricalTicksLast,
) -> tuple[int, list[HistoricalTickLast], bool]:
    """``Wrapper.historicalTicksLast(reqId, ticks, done)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else -1
    ticks = [createHistoricalTickLast(t) for t in proto.historicalTicksLast]
    done = proto.isDone if proto.HasField("isDone") else False
    return reqId, ticks, done


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
) -> HistoricalDataRequest_pb2.HistoricalDataRequest:
    proto = HistoricalDataRequest_pb2.HistoricalDataRequest()
    proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    proto.endDateTime = endDateTime
    proto.barSizeSetting = barSizeSetting
    proto.duration = durationStr
    proto.useRTH = bool(useRTH)
    proto.whatToShow = whatToShow
    proto.formatDate = formatDate
    proto.keepUpToDate = keepUpToDate
    return proto


def createCancelHistoricalDataProto(
    reqId: int,
) -> CancelHistoricalData_pb2.CancelHistoricalData:
    proto = CancelHistoricalData_pb2.CancelHistoricalData()
    proto.reqId = reqId
    return proto


def createRealTimeBarsRequestProto(
    reqId: int, contract: Contract, barSize: int, whatToShow: str, useRTH: bool
) -> RealTimeBarsRequest_pb2.RealTimeBarsRequest:
    proto = RealTimeBarsRequest_pb2.RealTimeBarsRequest()
    proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    proto.barSize = barSize
    proto.whatToShow = whatToShow
    proto.useRTH = useRTH
    return proto


def createCancelRealTimeBarsProto(
    reqId: int,
) -> CancelRealTimeBars_pb2.CancelRealTimeBars:
    proto = CancelRealTimeBars_pb2.CancelRealTimeBars()
    proto.reqId = reqId
    return proto


def createHeadTimestampRequestProto(
    reqId: int, contract: Contract, useRTH: int, whatToShow: str, formatDate: int
) -> HeadTimestampRequest_pb2.HeadTimestampRequest:
    proto = HeadTimestampRequest_pb2.HeadTimestampRequest()
    proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    proto.useRTH = bool(useRTH)
    proto.whatToShow = whatToShow
    proto.formatDate = formatDate
    return proto


def createCancelHeadTimestampProto(
    reqId: int,
) -> CancelHeadTimestamp_pb2.CancelHeadTimestamp:
    proto = CancelHeadTimestamp_pb2.CancelHeadTimestamp()
    proto.reqId = reqId
    return proto


def createHistogramDataRequestProto(
    reqId: int, contract: Contract, useRTH: bool, timePeriod: str
) -> HistogramDataRequest_pb2.HistogramDataRequest:
    proto = HistogramDataRequest_pb2.HistogramDataRequest()
    proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    proto.useRTH = useRTH
    proto.timePeriod = timePeriod
    return proto


def createCancelHistogramDataProto(
    reqId: int,
) -> CancelHistogramData_pb2.CancelHistogramData:
    proto = CancelHistogramData_pb2.CancelHistogramData()
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
) -> HistoricalTicksRequest_pb2.HistoricalTicksRequest:
    proto = HistoricalTicksRequest_pb2.HistoricalTicksRequest()
    proto.reqId = reqId
    proto.contract.MergeFrom(createContractProto(contract))
    proto.startDateTime = startDateTime
    proto.endDateTime = endDateTime
    proto.numberOfTicks = numberOfTicks
    proto.whatToShow = whatToShow
    proto.useRTH = bool(useRTH)
    proto.ignoreSize = ignoreSize
    return proto


def createCancelHistoricalTicksProto(
    reqId: int,
) -> CancelHistoricalTicks_pb2.CancelHistoricalTicks:
    proto = CancelHistoricalTicks_pb2.CancelHistoricalTicks()
    proto.reqId = reqId
    return proto
