from ib_async.contract import ContractDetails
from ib_async.objects import ScanData, ScannerSubscription, TagValue
from ib_async.protobuf.CancelPnL_pb2 import CancelPnL as CancelPnLProto
from ib_async.protobuf.CancelPnLSingle_pb2 import (
    CancelPnLSingle as CancelPnLSingleProto,
)
from ib_async.protobuf.CancelScannerSubscription_pb2 import (
    CancelScannerSubscription as CancelScannerSubscriptionProto,
)
from ib_async.protobuf.PnLRequest_pb2 import PnLRequest as PnLRequestProto
from ib_async.protobuf.PnLSingleRequest_pb2 import (
    PnLSingleRequest as PnLSingleRequestProto,
)
from ib_async.protobuf.ScannerData_pb2 import ScannerData as ScannerDataProto
from ib_async.protobuf.ScannerParametersRequest_pb2 import (
    ScannerParametersRequest as ScannerParametersRequestProto,
)
from ib_async.protobuf.ScannerSubscription_pb2 import (
    ScannerSubscription as ScannerSubscriptionProto,
)
from ib_async.protobuf.ScannerSubscriptionRequest_pb2 import (
    ScannerSubscriptionRequest as ScannerSubscriptionRequestProto,
)
from ib_async.protobuf_converters.subscription_converters import (
    createCancelPnLProto,
    createCancelPnLSingleProto,
    createCancelScannerSubscriptionProto,
    createPnLRequestProto,
    createPnLSingleRequestProto,
    createScannerDataList,
    createScannerParametersRequestProto,
    createScannerSubscriptionProto,
    createScannerSubscriptionRequestProto,
)


class TestSubscriptionConverters:
    def test_createScannerParametersRequestProto(self):
        proto = createScannerParametersRequestProto()
        assert isinstance(proto, ScannerParametersRequestProto)

    def test_createScannerSubscriptionRequestProto(self):
        sub = ScannerSubscription(instrument="STK", locationCode="STK.US.MAJOR")
        options = [TagValue("tag1", "val1")]
        filters = [TagValue("tag2", "val2")]
        proto = createScannerSubscriptionRequestProto(1, sub, options, filters)

        assert isinstance(proto, ScannerSubscriptionRequestProto)
        assert proto.reqId == 1
        assert proto.scannerSubscription.instrument == "STK"
        assert proto.scannerSubscription.locationCode == "STK.US.MAJOR"
        assert "tag1" in proto.scannerSubscription.scannerSubscriptionOptions
        assert "tag2" in proto.scannerSubscription.scannerSubscriptionFilterOptions

    def test_createScannerSubscriptionProto(self):
        sub = ScannerSubscription(
            instrument="STK",
            locationCode="STK.US",
            scanCode="TOP_PERC_GAIN",
            abovePrice=10.0,
            belowPrice=100.0,
            aboveVolume=10000,
            marketCapAbove=1e9,
            marketCapBelow=1e11,
            stockTypeFilter="ALL",
        )
        options = [TagValue("opt1", "val1")]
        filters: list = []
        proto = createScannerSubscriptionProto(sub, options, filters)

        assert isinstance(proto, ScannerSubscriptionProto)
        assert proto.instrument == "STK"
        assert proto.locationCode == "STK.US"
        assert proto.scanCode == "TOP_PERC_GAIN"
        assert proto.abovePrice == 10.0
        assert proto.belowPrice == 100.0
        assert proto.aboveVolume == 10000
        assert proto.marketCapAbove == 1e9
        assert proto.marketCapBelow == 1e11
        assert proto.stockTypeFilter == "ALL"
        assert "opt1" in proto.scannerSubscriptionOptions
        assert len(proto.scannerSubscriptionFilterOptions) == 0

    def test_createScannerSubscriptionProto_none(self):
        proto = createScannerSubscriptionProto(None, [], [])  # type: ignore
        assert proto is None

    def test_createCancelScannerSubscriptionProto(self):
        proto = createCancelScannerSubscriptionProto(1)
        assert isinstance(proto, CancelScannerSubscriptionProto)
        assert proto.reqId == 1

    def test_createPnLRequestProto(self):
        proto = createPnLRequestProto(2, "DU12345", "MyModel")
        assert isinstance(proto, PnLRequestProto)
        assert proto.reqId == 2
        assert proto.account == "DU12345"
        assert proto.modelCode == "MyModel"

    def test_createCancelPnLProto(self):
        proto = createCancelPnLProto(2)
        assert isinstance(proto, CancelPnLProto)
        assert proto.reqId == 2

    def test_createPnLSingleRequestProto(self):
        proto = createPnLSingleRequestProto(3, "DU12345", "MyModel", 12345)
        assert isinstance(proto, PnLSingleRequestProto)
        assert proto.reqId == 3
        assert proto.account == "DU12345"
        assert proto.modelCode == "MyModel"
        assert proto.conId == 12345

    def test_createCancelPnLSingleProto(self):
        proto = createCancelPnLSingleProto(3)
        assert isinstance(proto, CancelPnLSingleProto)
        assert proto.reqId == 3

    def test_createScannerDataList(self):
        scanner_data_proto = ScannerDataProto()

        # Element 1
        elem1 = scanner_data_proto.scannerDataElement.add()
        elem1.rank = 1
        elem1.contract.symbol = "AAPL"
        elem1.contract.secType = "STK"
        elem1.marketName = "NASDAQ"
        elem1.distance = "dist1"
        elem1.benchmark = "bench1"
        elem1.projection = "proj1"
        elem1.comboKey = "key1"

        # Element 2
        elem2 = scanner_data_proto.scannerDataElement.add()
        elem2.rank = 2
        elem2.contract.symbol = "GOOG"
        elem2.contract.secType = "STK"
        elem2.marketName = "NASDAQ"

        data_list = createScannerDataList(scanner_data_proto)

        assert isinstance(data_list, list)
        assert len(data_list) == 2

        # Check item 1
        item1 = data_list[0]
        assert isinstance(item1, ScanData)
        assert item1.rank == 1
        assert isinstance(item1.contractDetails, ContractDetails)
        assert item1.contractDetails.contract.symbol == "AAPL"  # type: ignore
        assert item1.contractDetails.marketName == "NASDAQ"
        assert item1.distance == "dist1"
        assert item1.benchmark == "bench1"
        assert item1.projection == "proj1"
        assert item1.legsStr == "key1"

        # Check item 2
        item2 = data_list[1]
        assert isinstance(item2, ScanData)
        assert item2.rank == 2
        assert item2.contractDetails.contract.symbol == "GOOG"  # type: ignore
        assert item2.distance == ""

    def test_createScannerDataList_empty(self):
        scanner_data_proto = ScannerDataProto()
        data_list = createScannerDataList(scanner_data_proto)
        assert isinstance(data_list, list)
        assert len(data_list) == 0
