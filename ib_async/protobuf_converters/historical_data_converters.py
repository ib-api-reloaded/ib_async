"""Historical data protobuf converters"""

from datetime import datetime, tzinfo

from ..contract import Contract, TagValue
from ..objects import (
    BarData,
    HistogramData,
    HistoricalSchedule,
    HistoricalSession,
    HistoricalTick,
    HistoricalTickBidAsk,
    HistoricalTickLast,
    TickAttribBidAsk,
    TickAttribLast,
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
from ..protobuf.HistoricalSession_pb2 import HistoricalSession as HistoricalSessionProto
from ..protobuf.HistoricalTick_pb2 import HistoricalTick as HistoricalTickProto
from ..protobuf.HistoricalTickBidAsk_pb2 import (
    HistoricalTickBidAsk as HistoricalTickBidAskProto,
)
from ..protobuf.HistoricalTickLast_pb2 import (
    HistoricalTickLast as HistoricalTickLastProto,
)
from ..protobuf.HistoricalTicksRequest_pb2 import (
    HistoricalTicksRequest as HistoricalTicksRequestProto,
)
from ..protobuf.TickAttribBidAsk_pb2 import TickAttribBidAsk as TickAttribBidAskProto
from ..protobuf.TickAttribLast_pb2 import TickAttribLast as TickAttribLastProto
from ..util import NO_VALID_ID, isValidIntValue, parseIBDatetime
from .contract_converters import createContractProto


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


def fillTagValueList(tagValueList: list[TagValue], orderProtoMap: dict):
    if tagValueList is not None and tagValueList:
        for tagValue in tagValueList:
            orderProtoMap[tagValue.tag] = tagValue.value


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


def createBarDataList(
    historicalDataBarsProto: list[HistoricalDataBarProto],
) -> list[BarData]:
    bars = []
    for barProto in historicalDataBarsProto:
        bar = BarData()
        if barProto.HasField("date"):
            bar.date = parseIBDatetime(barProto.date)
        if barProto.HasField("open"):
            bar.open = barProto.open
        if barProto.HasField("high"):
            bar.high = barProto.high
        if barProto.HasField("low"):
            bar.low = barProto.low
        if barProto.HasField("close"):
            bar.close = barProto.close
        if barProto.HasField("volume"):
            bar.volume = float(barProto.volume)
        if barProto.HasField("WAP"):
            bar.average = float(barProto.WAP)
        if barProto.HasField("barCount"):
            bar.barCount = barProto.barCount
        bars.append(bar)
    return bars


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
    time = datetime.fromtimestamp(historicalTickProto.time, tz)
    price = historicalTickProto.price
    size = float(historicalTickProto.size)
    historicalTick = HistoricalTick(time, price, size)
    return historicalTick


def createHistoricalTickBidAsk(
    historicalTickBidAskProto: HistoricalTickBidAskProto, tz: tzinfo
) -> HistoricalTickBidAsk:
    time = datetime.fromtimestamp(historicalTickBidAskProto.time, tz)

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
    time = datetime.fromtimestamp(historicalTickLastProto.time, tz)

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
    histogramData = HistogramData()
    if histogramDataEntryProto.HasField("price"):
        histogramData.price = histogramDataEntryProto.price
    if histogramDataEntryProto.HasField("size"):
        histogramData.count = int(histogramDataEntryProto.size)
    return histogramData


def createHistoricalSchedule(
    historicalScheduleProto: HistoricalScheduleProto,
) -> HistoricalSchedule:
    startDateTime = (
        historicalScheduleProto.startDateTime
        if historicalScheduleProto.HasField("startDateTime")
        else ""
    )
    endDateTime = (
        historicalScheduleProto.endDateTime
        if historicalScheduleProto.HasField("endDateTime")
        else ""
    )
    timeZone = (
        historicalScheduleProto.timeZone
        if historicalScheduleProto.HasField("timeZone")
        else ""
    )

    sessions = []
    if historicalScheduleProto.historicalSessions:
        for historicalSessionProto in historicalScheduleProto.historicalSessions:
            historicalSession = HistoricalSession()
            historicalSession.startDateTime = (
                historicalSessionProto.startDateTime
                if historicalSessionProto.HasField("startDateTime")
                else ""
            )
            historicalSession.endDateTime = (
                historicalSessionProto.endDateTime
                if historicalSessionProto.HasField("endDateTime")
                else ""
            )
            historicalSession.refDate = (
                historicalSessionProto.refDate
                if historicalSessionProto.HasField("refDate")
                else ""
            )
            sessions.append(historicalSession)

    historicalSchedule = HistoricalSchedule(
        startDateTime, endDateTime, timeZone, sessions
    )
    return historicalSchedule
