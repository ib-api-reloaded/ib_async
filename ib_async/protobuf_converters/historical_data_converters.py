"""Historical data protobuf converters"""

from ib_async.objects import BarData
from ..util import isValidIntValue, parseIBDatetime

from ..contract import Contract, TagValue
from ..protobuf.HeadTimestampRequest_pb2 import (
    HeadTimestampRequest as HeadTimestampRequestProto,
)
from ..protobuf.HistoricalDataRequest_pb2 import (
    HistoricalDataRequest as HistoricalDataRequestProto,
)
from ..protobuf.HistoricalDataBar_pb2 import (
    HistoricalDataBar as HistoricalDataBarProto,
)
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
