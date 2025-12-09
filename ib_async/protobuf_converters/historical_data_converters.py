"""Historical data protobuf converters"""

from datetime import tzinfo
from typing import TypeAlias

from ..contract import Contract, TagValue
from ..objects import (
    BarData,
    HistogramData,
    HistoricalSchedule,
    HistoricalSession,
    HistoricalTick,
    HistoricalTickBidAsk,
    HistoricalTickLast,
    HistoricalTickType,
    IBDefaults,
    RealTimeBar,
    TickAttribBidAsk,
    TickAttribLast,
)
from ..protobuf.CancelHistoricalData_pb2 import (
    CancelHistoricalData as CancelHistoricalDataProto,
)
from ..protobuf.FundamentalsDataRequest_pb2 import (
    FundamentalsDataRequest as FundamentalsDataRequestProto,
)
from ..protobuf.HeadTimestampRequest_pb2 import (
    HeadTimestampRequest as HeadTimestampRequestProto,
)
from ..protobuf.HistogramDataEntry_pb2 import (
    HistogramDataEntry as HistogramDataEntryProto,
)
from ..protobuf.HistogramDataRequest_pb2 import (
    HistogramDataRequest as HistogramDataRequestProto,
)
from ..protobuf.HistoricalDataBar_pb2 import (
    HistoricalDataBar as HistoricalDataBarProto,
)
from ..protobuf.HistoricalDataRequest_pb2 import (
    HistoricalDataRequest as HistoricalDataRequestProto,
)
from ..protobuf.HistoricalSchedule_pb2 import (
    HistoricalSchedule as HistoricalScheduleProto,
)
from ..protobuf.HistoricalTick_pb2 import HistoricalTick as HistoricalTickProto
from ..protobuf.HistoricalTickBidAsk_pb2 import (
    HistoricalTickBidAsk as HistoricalTickBidAskProto,
)
from ..protobuf.HistoricalTickLast_pb2 import (
    HistoricalTickLast as HistoricalTickLastProto,
)
from ..protobuf.HistoricalTicks_pb2 import HistoricalTicks as HistoricalTicksProto
from ..protobuf.HistoricalTicksBidAsk_pb2 import (
    HistoricalTicksBidAsk as HistoricalTicksBidAskProto,
)
from ..protobuf.HistoricalTicksLast_pb2 import (
    HistoricalTicksLast as HistoricalTicksLastProto,
)
from ..protobuf.HistoricalTicksRequest_pb2 import (
    HistoricalTicksRequest as HistoricalTicksRequestProto,
)
from ..protobuf.RealTimeBarsRequest_pb2 import (
    RealTimeBarsRequest as RealTimeBarsRequestProto,
)
from ..protobuf.RealTimeBarTick_pb2 import RealTimeBarTick as RealTimeBarTickProto
from ..protobuf.TickByTickData_pb2 import TickByTickData as TickByTickDataProto
from ..util import (
    EPOCH,
    UNSET_DOUBLE,
    isValidIntValue,
    parseIBDatetime,
    parseIBTimeStamp,
)
from .contract_converters import createContractProto
from .base_converters import ClientException, fillTagValueList


def createHeadTimestampRequestProto(
    reqId: int, contract: Contract, whatToShow: str, useRTH: bool, formatDate: int
) -> HeadTimestampRequestProto:
    headTimestampRequestProto = HeadTimestampRequestProto()
    if isValidIntValue(reqId):
        headTimestampRequestProto.reqId = reqId
    contractProto = createContractProto(contract, None)
    if contractProto is not None:
        headTimestampRequestProto.contract.CopyFrom(contractProto)
    if whatToShow:
        headTimestampRequestProto.whatToShow = whatToShow
    if useRTH:
        headTimestampRequestProto.useRTH = useRTH
    if isValidIntValue(formatDate):
        headTimestampRequestProto.formatDate = formatDate
    return headTimestampRequestProto


def createHistoricalDataRequestProto(
    reqId: int,
    contract: Contract,
    endDateTime: str,
    duration: str,
    barSizeSetting: str,
    whatToShow: str,
    useRTH: bool,
    formatDate: int,
    keepUpToDate: bool,
    chartOptionsList: list[TagValue],
) -> HistoricalDataRequestProto:
    historicalDataRequestProto = HistoricalDataRequestProto()
    if isValidIntValue(reqId):
        historicalDataRequestProto.reqId = reqId
    contractProto = createContractProto(contract, None)
    if contractProto is not None:
        historicalDataRequestProto.contract.CopyFrom(contractProto)
    if endDateTime:
        historicalDataRequestProto.endDateTime = endDateTime
    if duration:
        historicalDataRequestProto.duration = duration
    if barSizeSetting:
        historicalDataRequestProto.barSizeSetting = barSizeSetting
    if whatToShow:
        historicalDataRequestProto.whatToShow = whatToShow
    if useRTH:
        historicalDataRequestProto.useRTH = useRTH
    if isValidIntValue(formatDate):
        historicalDataRequestProto.formatDate = formatDate
    if keepUpToDate:
        historicalDataRequestProto.keepUpToDate = keepUpToDate
    fillTagValueList(chartOptionsList, historicalDataRequestProto.chartOptions)
    return historicalDataRequestProto


def createCancelHistoricalDataProto(reqId: int) -> CancelHistoricalDataProto:
    cancelHistoricalDataProto = CancelHistoricalDataProto()
    if isValidIntValue(reqId):
        cancelHistoricalDataProto.reqId = reqId
    return cancelHistoricalDataProto


def createRealTimeBarsRequestProto(
    reqId: int,
    contract: Contract,
    barSize: int,
    whatToShow: str,
    useRTH: bool,
    realTimeBarsOptionsList: list[TagValue],
) -> RealTimeBarsRequestProto:
    realTimeBarsRequestProto = RealTimeBarsRequestProto()
    if isValidIntValue(reqId):
        realTimeBarsRequestProto.reqId = reqId
    contractProto = createContractProto(contract, None)
    if contractProto is not None:
        realTimeBarsRequestProto.contract.CopyFrom(contractProto)
    if isValidIntValue(barSize):
        realTimeBarsRequestProto.barSize = barSize
    if whatToShow:
        realTimeBarsRequestProto.whatToShow = whatToShow
    if useRTH:
        realTimeBarsRequestProto.useRTH = useRTH
    fillTagValueList(
        realTimeBarsOptionsList, realTimeBarsRequestProto.realTimeBarsOptions
    )
    return realTimeBarsRequestProto


def createBarDataList(
    historicalDataBarsProto: list[HistoricalDataBarProto],
) -> list[BarData]:
    bars = []
    for barProto in historicalDataBarsProto:
        bar = createBarData(barProto)
        bars.append(bar)
    return bars


def createBarData(historicalDataBarProto: HistoricalDataBarProto) -> BarData:
    if historicalDataBarProto.HasField("date"):
        date = parseIBDatetime(historicalDataBarProto.date)
    if historicalDataBarProto.HasField("open"):
        open_ = historicalDataBarProto.open
    if historicalDataBarProto.HasField("high"):
        high = historicalDataBarProto.high
    if historicalDataBarProto.HasField("low"):
        low = historicalDataBarProto.low
    if historicalDataBarProto.HasField("close"):
        close = historicalDataBarProto.close
    if historicalDataBarProto.HasField("volume"):
        volume = float(historicalDataBarProto.volume)
    if historicalDataBarProto.HasField("WAP"):
        average = float(historicalDataBarProto.WAP)
    if historicalDataBarProto.HasField("barCount"):
        barCount = historicalDataBarProto.barCount
    bar = BarData(date, open_, high, low, close, volume, average, barCount)
    return bar


def createHistoricalTicksRequestProto(
    reqId: int,
    contract: Contract,
    startDateTime: str,
    endDateTime: str,
    numberOfTicks: int,
    whatToShow: str,
    useRTH: bool,
    ignoreSize: bool,
    miscOptionsList: list[TagValue],
) -> HistoricalTicksRequestProto:
    historicalTicksRequestProto = HistoricalTicksRequestProto()
    if isValidIntValue(reqId):
        historicalTicksRequestProto.reqId = reqId
    contractProto = createContractProto(contract, None)
    if contractProto is not None:
        historicalTicksRequestProto.contract.CopyFrom(contractProto)
    if startDateTime:
        historicalTicksRequestProto.startDateTime = startDateTime
    if endDateTime:
        historicalTicksRequestProto.endDateTime = endDateTime
    if isValidIntValue(numberOfTicks):
        historicalTicksRequestProto.numberOfTicks = numberOfTicks
    if whatToShow:
        historicalTicksRequestProto.whatToShow = whatToShow
    if useRTH:
        historicalTicksRequestProto.useRTH = useRTH
    if ignoreSize:
        historicalTicksRequestProto.ignoreSize = ignoreSize
    fillTagValueList(miscOptionsList, historicalTicksRequestProto.miscOptions)
    return historicalTicksRequestProto


def createHistoricalTick(
    historicalTickProto: HistoricalTickProto, tz: tzinfo
) -> HistoricalTick:
    time = parseIBTimeStamp(historicalTickProto.time, tz)
    price = historicalTickProto.price
    size = (
        float(historicalTickProto.size)
        if historicalTickProto.size
        else IBDefaults.emptySize
    )
    historicalTick = HistoricalTick(time, price, size)
    return historicalTick


def createHistoricalTickBidAsk(
    historicalTickBidAskProto: HistoricalTickBidAskProto, tz: tzinfo
) -> HistoricalTickBidAsk:
    time = parseIBTimeStamp(historicalTickBidAskProto.time, tz)

    tickAttribBidAskProto = historicalTickBidAskProto.tickAttribBidAsk
    bidPastLow = tickAttribBidAskProto.bidPastLow
    askPastHigh = tickAttribBidAskProto.askPastHigh
    tickAttribBidAsk = TickAttribBidAsk(bidPastLow, askPastHigh)

    priceBid = historicalTickBidAskProto.priceBid
    priceAsk = historicalTickBidAskProto.priceAsk
    sizeBid = float(historicalTickBidAskProto.sizeBid)
    sizeAsk = float(historicalTickBidAskProto.sizeAsk)

    historicalTickBidAsk = HistoricalTickBidAsk(
        time, tickAttribBidAsk, priceBid, priceAsk, sizeBid, sizeAsk
    )

    return historicalTickBidAsk


def createHistoricalTickLast(
    historicalTickLastProto: HistoricalTickLastProto, tz: tzinfo
) -> HistoricalTickLast:
    time = parseIBTimeStamp(historicalTickLastProto.time, tz)
    tickAttribLastProto = historicalTickLastProto.tickAttribLast
    pastLimit = tickAttribLastProto.pastLimit
    unreported = tickAttribLastProto.unreported
    tickAttribLast = TickAttribLast(pastLimit, unreported)

    price = historicalTickLastProto.price
    size = float(historicalTickLastProto.size)
    exchange = historicalTickLastProto.exchange
    specialConditions = historicalTickLastProto.specialConditions

    historicalTickLast = HistoricalTickLast(
        time, tickAttribLast, price, size, exchange, specialConditions
    )

    return historicalTickLast


HistoricalTicksProtoType: TypeAlias = (
    HistoricalTicksProto | HistoricalTicksBidAskProto | HistoricalTicksLastProto
)


def createHistoricalTickShim(
    historicalTicksProto: HistoricalTicksProtoType, tz: tzinfo
) -> list[HistoricalTickType]:
    historicalTicks: list[HistoricalTickType] = []
    if isinstance(historicalTicksProto, HistoricalTicksProto):
        for tick_proto in historicalTicksProto.historicalTicks:
            historicalTicks.append(createHistoricalTick(tick_proto, tz))
    elif isinstance(historicalTicksProto, HistoricalTicksBidAskProto):
        for tick_proto in historicalTicksProto.historicalTicksBidAsk:
            historicalTicks.append(createHistoricalTickBidAsk(tick_proto, tz))
    elif isinstance(historicalTicksProto, HistoricalTicksLastProto):
        for tick_proto in historicalTicksProto.historicalTicksLast:
            historicalTicks.append(createHistoricalTickLast(tick_proto, tz))
    else:
        raise ClientException(575, "Unknown historical ticks type", "")
    return historicalTicks


def createTickByTick(
    tickByTickData: TickByTickDataProto, tz: tzinfo
) -> HistoricalTickType|None:
    tickType = tickByTickData.tickType if tickByTickData.HasField("tickType") else 0
    if tickType == 0:
        raise ValueError("%s: Invalid tick type: %r",__name__,tickByTickData)
    elif tickType == 1 or tickType == 2:
        # Last or AllLast
        if tickByTickData.HasField("historicalTickLast"):
            tick_last = createHistoricalTickLast(tickByTickData.historicalTickLast, tz)
            return tick_last
    elif tickType == 3:
        # BidAsk
        if tickByTickData.HasField("historicalTickBidAsk"):
            tick_bid_ask = createHistoricalTickBidAsk(
                tickByTickData.historicalTickBidAsk, tz
            )
            return tick_bid_ask
    elif tickType == 4:
        # MidPoint
        if tickByTickData.HasField("historicalTickMidPoint"):
            tick_mid = createHistoricalTick(tickByTickData.historicalTickMidPoint, tz)
            return tick_mid
    return None

def createHistogramDataRequestProto(
    reqId: int, contract: Contract, useRTH: bool, timePeriod: str
) -> HistogramDataRequestProto:
    histogramDataRequestProto = HistogramDataRequestProto()
    if isValidIntValue(reqId):
        histogramDataRequestProto.reqId = reqId
    contractProto = createContractProto(contract, None)
    if contractProto is not None:
        histogramDataRequestProto.contract.CopyFrom(contractProto)
    if useRTH:
        histogramDataRequestProto.useRTH = useRTH
    if timePeriod:
        histogramDataRequestProto.timePeriod = timePeriod
    return histogramDataRequestProto


def createHistogramDataEntry(
    histogramDataEntryProto: HistogramDataEntryProto,
) -> HistogramData:
    price = (
        histogramDataEntryProto.price
        if histogramDataEntryProto.HasField("price")
        else 0
    )
    count = (
        int(histogramDataEntryProto.size)
        if histogramDataEntryProto.HasField("size")
        else 0
    )
    return HistogramData(price, count)


def createHistoricalSchedule(
    historicalScheduleProto: HistoricalScheduleProto,
) -> HistoricalSchedule:
    _startDateTime = (
        historicalScheduleProto.startDateTime
        if historicalScheduleProto.HasField("startDateTime")
        else ""
    )
    _endDateTime = (
        historicalScheduleProto.endDateTime
        if historicalScheduleProto.HasField("endDateTime")
        else ""
    )
    _timeZone = (
        historicalScheduleProto.timeZone
        if historicalScheduleProto.HasField("timeZone")
        else ""
    )

    sessions = []
    if historicalScheduleProto.historicalSessions:
        for historicalSessionProto in historicalScheduleProto.historicalSessions:
            startDateTime = (
                historicalSessionProto.startDateTime
                if historicalSessionProto.HasField("startDateTime")
                else ""
            )
            endDateTime = (
                historicalSessionProto.endDateTime
                if historicalSessionProto.HasField("endDateTime")
                else ""
            )
            refDate = (
                historicalSessionProto.refDate
                if historicalSessionProto.HasField("refDate")
                else ""
            )
            historicalSession = HistoricalSession(
                startDateTime,
                endDateTime,
                refDate,
            )
            sessions.append(historicalSession)

    historicalSchedule = HistoricalSchedule(
        _startDateTime, _endDateTime, _timeZone, sessions
    )
    return historicalSchedule


def createRealTimeBarTick(
    realTimeBarTickProto: RealTimeBarTickProto, tz: tzinfo
) -> RealTimeBar:
    time = (
        parseIBTimeStamp(realTimeBarTickProto.time, tz)
        if realTimeBarTickProto.HasField("time")
        else EPOCH
    )
    open_ = realTimeBarTickProto.open if realTimeBarTickProto.HasField("open") else 0.0
    high = realTimeBarTickProto.high if realTimeBarTickProto.HasField("high") else 0.0
    low = realTimeBarTickProto.low if realTimeBarTickProto.HasField("low") else 0.0
    close = (
        realTimeBarTickProto.close if realTimeBarTickProto.HasField("close") else 0.0
    )
    volume = (
        float(realTimeBarTickProto.volume)
        if realTimeBarTickProto.HasField("volume")
        else UNSET_DOUBLE
    )
    wap = (
        float(realTimeBarTickProto.WAP)
        if realTimeBarTickProto.HasField("WAP")
        else UNSET_DOUBLE
    )
    count = realTimeBarTickProto.count if realTimeBarTickProto.HasField("count") else 0
    realTimeBar = RealTimeBar(time, -1, open_, high, low, close, volume, wap, count)
    return realTimeBar


def createFundamentalsDataRequestProto(
    reqId: int,
    contract: Contract,
    reportType: str,
    fundamentalsDataOptionsList: list[TagValue],
) -> FundamentalsDataRequestProto:
    fundamentalsDataRequestProto = FundamentalsDataRequestProto()
    if isValidIntValue(reqId):
        fundamentalsDataRequestProto.reqId = reqId
    contractProto = createContractProto(contract, None)
    if contractProto is not None:
        fundamentalsDataRequestProto.contract.CopyFrom(contractProto)
    if reportType:
        fundamentalsDataRequestProto.reportType = reportType
    fillTagValueList(
        fundamentalsDataOptionsList,
        fundamentalsDataRequestProto.fundamentalsDataOptions,
    )
    return fundamentalsDataRequestProto
