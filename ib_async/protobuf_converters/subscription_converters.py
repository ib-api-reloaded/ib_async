import logging
from ib_async.objects import ScannerSubscription, TagValue
from ib_async.util import UNSET_DOUBLE, isValidIntValue
from ib_async.contract import ScanData, ContractDetails

from ..protobuf.CancelPnL_pb2 import CancelPnL as CancelPnLProto
from ..protobuf.CancelPnLSingle_pb2 import CancelPnLSingle as CancelPnLSingleProto
from ..protobuf.CancelScannerSubscription_pb2 import (
    CancelScannerSubscription as CancelScannerSubscriptionProto,
)
from ..protobuf.PnLRequest_pb2 import PnLRequest as PnLRequestProto
from ..protobuf.PnLSingleRequest_pb2 import PnLSingleRequest as PnLSingleRequestProto
from ..protobuf.ScannerParametersRequest_pb2 import (
    ScannerParametersRequest as ScannerParametersRequestProto,
)
from ..protobuf.ScannerSubscription_pb2 import (
    ScannerSubscription as ScannerSubscriptionProto,
)
from ..protobuf.ScannerData_pb2 import ScannerData as ScannerDataProto
from ..protobuf.ScannerSubscriptionRequest_pb2 import (
    ScannerSubscriptionRequest as ScannerSubscriptionRequestProto,
)
from .historical_data_converters import fillTagValueList
from .contract_converters import createContract


def createScannerParametersRequestProto() -> ScannerParametersRequestProto:
    scannerParametersRequestProto = ScannerParametersRequestProto()
    return scannerParametersRequestProto


def createScannerSubscriptionRequestProto(
    reqId: int,
    subscription: ScannerSubscription,
    scannerSubscriptionOptionsList: list[TagValue],
    scannerSubscriptionFilterOptionsList: list[TagValue],
) -> ScannerSubscriptionRequestProto:
    scannerSubscriptionRequestProto = ScannerSubscriptionRequestProto()
    if isValidIntValue(reqId):
        scannerSubscriptionRequestProto.reqId = reqId
    scannerSubscriptionProto = createScannerSubscriptionProto(
        subscription,
        scannerSubscriptionOptionsList,
        scannerSubscriptionFilterOptionsList,
    )
    if scannerSubscriptionProto is not None:
        scannerSubscriptionRequestProto.scannerSubscription.CopyFrom(
            scannerSubscriptionProto
        )
    return scannerSubscriptionRequestProto


def createScannerSubscriptionProto(
    subscription: ScannerSubscription,
    scannerSubscriptionOptionsList: list[TagValue],
    scannerSubscriptionFilterOptionsList: list[TagValue],
) -> ScannerSubscriptionProto:
    if subscription is None:
        return None
    scannerSubscriptionProto = ScannerSubscriptionProto()
    if isValidIntValue(subscription.numberOfRows):
        scannerSubscriptionProto.numberOfRows = subscription.numberOfRows
    if subscription.instrument:
        scannerSubscriptionProto.instrument = subscription.instrument
    if subscription.locationCode:
        scannerSubscriptionProto.locationCode = subscription.locationCode
    if subscription.scanCode:
        scannerSubscriptionProto.scanCode = subscription.scanCode
    if subscription.abovePrice != UNSET_DOUBLE:
        scannerSubscriptionProto.abovePrice = subscription.abovePrice
    if subscription.belowPrice != UNSET_DOUBLE:
        scannerSubscriptionProto.belowPrice = subscription.belowPrice
    if isValidIntValue(subscription.aboveVolume):
        scannerSubscriptionProto.aboveVolume = subscription.aboveVolume
    if isValidIntValue(subscription.averageOptionVolumeAbove):
        scannerSubscriptionProto.averageOptionVolumeAbove = (
            subscription.averageOptionVolumeAbove
        )
    if subscription.marketCapAbove != UNSET_DOUBLE:
        scannerSubscriptionProto.marketCapAbove = subscription.marketCapAbove
    if subscription.marketCapBelow != UNSET_DOUBLE:
        scannerSubscriptionProto.marketCapBelow = subscription.marketCapBelow
    if subscription.moodyRatingAbove:
        scannerSubscriptionProto.moodyRatingAbove = subscription.moodyRatingAbove
    if subscription.moodyRatingBelow:
        scannerSubscriptionProto.moodyRatingBelow = subscription.moodyRatingBelow
    if subscription.spRatingAbove:
        scannerSubscriptionProto.spRatingAbove = subscription.spRatingAbove
    if subscription.spRatingBelow:
        scannerSubscriptionProto.spRatingBelow = subscription.spRatingBelow
    if subscription.maturityDateAbove:
        scannerSubscriptionProto.maturityDateAbove = subscription.maturityDateAbove
    if subscription.maturityDateBelow:
        scannerSubscriptionProto.maturityDateBelow = subscription.maturityDateBelow
    if subscription.couponRateAbove != UNSET_DOUBLE:
        scannerSubscriptionProto.couponRateAbove = subscription.couponRateAbove
    if subscription.couponRateBelow != UNSET_DOUBLE:
        scannerSubscriptionProto.couponRateBelow = subscription.couponRateBelow
    if subscription.excludeConvertible:
        scannerSubscriptionProto.excludeConvertible = subscription.excludeConvertible
    if subscription.scannerSettingPairs:
        scannerSubscriptionProto.scannerSettingPairs = subscription.scannerSettingPairs
    if subscription.stockTypeFilter:
        scannerSubscriptionProto.stockTypeFilter = subscription.stockTypeFilter
    fillTagValueList(
        scannerSubscriptionOptionsList,
        scannerSubscriptionProto.scannerSubscriptionOptions,
    )
    fillTagValueList(
        scannerSubscriptionFilterOptionsList,
        scannerSubscriptionProto.scannerSubscriptionFilterOptions,
    )
    return scannerSubscriptionProto


def createCancelScannerSubscriptionProto(reqId: int) -> CancelScannerSubscriptionProto:
    cancelScannerSubscriptionProto = CancelScannerSubscriptionProto()
    if isValidIntValue(reqId):
        cancelScannerSubscriptionProto.reqId = reqId
    return cancelScannerSubscriptionProto


def createPnLRequestProto(reqId: int, account: str, modelCode: str) -> PnLRequestProto:
    pnlRequestProto = PnLRequestProto()
    if isValidIntValue(reqId):
        pnlRequestProto.reqId = reqId
    if account:
        pnlRequestProto.account = account
    if modelCode:
        pnlRequestProto.modelCode = modelCode
    return pnlRequestProto


def createCancelPnLProto(reqId: int) -> CancelPnLProto:
    cancelPnLProto = CancelPnLProto()
    if isValidIntValue(reqId):
        cancelPnLProto.reqId = reqId
    return cancelPnLProto


def createPnLSingleRequestProto(
    reqId: int, account: str, modelCode: str, conId: int
) -> PnLSingleRequestProto:
    pnlSingleRequestProto = PnLSingleRequestProto()
    if isValidIntValue(reqId):
        pnlSingleRequestProto.reqId = reqId
    if account:
        pnlSingleRequestProto.account = account
    if modelCode:
        pnlSingleRequestProto.modelCode = modelCode
    if isValidIntValue(conId):
        pnlSingleRequestProto.conId = conId
    return pnlSingleRequestProto


def createCancelPnLSingleProto(reqId: int) -> CancelPnLSingleProto:
    cancelPnLSingleProto = CancelPnLSingleProto()
    if isValidIntValue(reqId):
        cancelPnLSingleProto.reqId = reqId
    return cancelPnLSingleProto


def createScannerDataList(scannerDataProto: ScannerDataProto) -> list[ScanData]:
    dataList = []
    if scannerDataProto.scannerDataElement:
        for element in scannerDataProto.scannerDataElement:
            rank = element.rank if element.HasField("rank") else 0

            # Set contract details
            if element.HasField("contract"):
                contract = createContract(element.contract)
                marketName = (
                    element.marketName if element.HasField("marketName") else ""
                )
                contractDetails = ContractDetails(
                    contract=contract, marketName=marketName
                )

            distance = element.distance if element.HasField("distance") else ""
            benchmark = element.benchmark if element.HasField("benchmark") else ""
            projection = element.projection if element.HasField("projection") else ""
            comboKey = element.comboKey if element.HasField("comboKey") else ""
            scanData = ScanData(
                rank=rank,
                contractDetails=contractDetails,
                distance=distance,
                benchmark=benchmark,
                projection=projection,
                legsStr=comboKey,
            )
            dataList.append(scanData)
    return dataList

