import pytest
from ib_async.contract import Contract, TagValue
from ib_async.objects import (
    OptionComputation,
    TickAttrib,
    TickComputationData,
    TickGenericData,
    TickParams,
    TickPriceData,
    TickSizeData,
    TickStringData,
    TickType,
)
from ib_async.protobuf.MarketDataTypeRequest_pb2 import (
    MarketDataTypeRequest as MarketDataTypeRequestProto,
)
from ib_async.protobuf.MarketDataRequest_pb2 import (
    MarketDataRequest as MarketDataRequestProto,
)
from ib_async.protobuf.CancelMarketData_pb2 import CancelMarketData as CancelMarketDataProto
from ib_async.protobuf.TickByTickRequest_pb2 import TickByTickRequest as TickByTickRequestProto
from ib_async.protobuf.TickReqParams_pb2 import TickReqParams as TickReqParamsProto
from ib_async.protobuf.TickPrice_pb2 import TickPrice as TickPriceProto
from ib_async.protobuf.TickSize_pb2 import TickSize as TickSizeProto
from ib_async.protobuf.TickString_pb2 import TickString as TickStringProto
from ib_async.protobuf.TickGeneric_pb2 import TickGeneric as TickGenericProto
from ib_async.protobuf.TickOptionComputation_pb2 import (
    TickOptionComputation as TickOptionComputationProto,
)
from ib_async.protobuf.CalculateImpliedVolatilityRequest_pb2 import (
    CalculateImpliedVolatilityRequest as CalculateImpliedVolatilityRequestProto,
)
from ib_async.protobuf.CalculateOptionPriceRequest_pb2 import (
    CalculateOptionPriceRequest as CalculateOptionPriceRequestProto,
)
from ib_async.protobuf.CancelCalculateImpliedVolatility_pb2 import (
    CancelCalculateImpliedVolatility as CancelCalculateImpliedVolatilityProto,
)
from ib_async.protobuf.CancelCalculateOptionPrice_pb2 import (
    CancelCalculateOptionPrice as CancelCalculateOptionPriceProto,
)
from ib_async.protobuf_converters.market_data_converters import (
    createMarketDataTypeRequestProto,
    createMarketDataRequestProto,
    cancelMarketDataProto,
    createTickByTickRequestProto,
    createTickParams,
    createTickPriceData,
    createTickSizeData,
    createTickStringData,
    createTickGenericData,
    createTickOptionComputation,
    createCalculateImpliedVolatilityRequestProto,
    createCalculateOptionPriceRequestProto,
    createCancelCalculateImpliedVolatilityProto,
    createCancelCalculateOptionPriceProto,
)

class TestMarketDataConverters:

    def test_createMarketDataTypeRequestProto(self):
        proto = createMarketDataTypeRequestProto(1)
        assert isinstance(proto, MarketDataTypeRequestProto)
        assert proto.marketDataType == 1

    def test_createMarketDataRequestProto(self):
        contract = Contract(symbol="SPY", secType="STK")
        proto = createMarketDataRequestProto(1, contract, "100,101", True, False, [])
        assert isinstance(proto, MarketDataRequestProto)
        assert proto.reqId == 1
        assert proto.contract.symbol == "SPY"
        assert proto.genericTickList == "100,101"
        assert proto.snapshot is True
        assert proto.regulatorySnapshot is False

    def test_cancelMarketDataProto(self):
        proto = cancelMarketDataProto(1)
        assert isinstance(proto, CancelMarketDataProto)
        assert proto.reqId == 1

    def test_createTickByTickRequestProto(self):
        contract = Contract(symbol="EURUSD", secType="CASH")
        proto = createTickByTickRequestProto(2, contract, "Last", 0, False)
        assert isinstance(proto, TickByTickRequestProto)
        assert proto.reqId == 2
        assert proto.contract.symbol == "EURUSD"
        assert proto.tickType == "Last"
        assert proto.numberOfTicks == 0
        assert proto.ignoreSize is False

    def test_createTickParams(self):
        proto = TickReqParamsProto(reqId=1, minTick="0.01", bboExchange="ISLAND", snapshotPermissions=3)
        params = createTickParams(proto)
        assert isinstance(params, TickParams)
        assert params.reqId == 1
        assert params.minTick == 0.01
        assert params.bboExchange == "ISLAND"
        assert params.snapshotPermissions == 3

    def test_createTickPriceData(self):
        proto = TickPriceProto(reqId=1, tickType=TickType.BID.value, price=1.2, size="100", attrMask=1)
        price_data, size_data = createTickPriceData(proto)
        
        assert isinstance(price_data, TickPriceData)
        assert price_data.reqId == 1
        assert price_data.tickType == TickType.BID
        assert price_data.price == 1.2
        assert price_data.size == 100
        assert price_data.attribs.canAutoExecute is True

        assert isinstance(size_data, TickSizeData)
        assert size_data.tickType == TickType.BID_SIZE
        assert size_data.size == 100

    def test_createTickSizeData(self):
        proto = TickSizeProto(reqId=1, tickType=TickType.ASK_SIZE.value, size="200")
        size_data = createTickSizeData(proto)
        assert isinstance(size_data, TickSizeData)
        assert size_data.reqId == 1
        assert size_data.tickType == TickType.ASK_SIZE
        assert size_data.size == 200

    def test_createTickStringData(self):
        proto = TickStringProto(reqId=1, tickType=TickType.LAST_TIMESTAMP.value, value="1672531200")
        string_data = createTickStringData(proto)
        assert isinstance(string_data, TickStringData)
        assert string_data.reqId == 1
        assert string_data.tickType == TickType.LAST_TIMESTAMP
        assert string_data.value == "1672531200"

    def test_createTickGenericData(self):
        proto = TickGenericProto(reqId=1, tickType=TickType.OPTION_IMPLIED_VOL.value, value=0.5)
        generic_data = createTickGenericData(proto)
        assert isinstance(generic_data, TickGenericData)
        assert generic_data.reqId == 1
        assert generic_data.tickType == TickType.OPTION_IMPLIED_VOL
        assert generic_data.value == 0.5

    def test_createTickOptionComputation(self):
        proto = TickOptionComputationProto(
            reqId=1, tickType=TickType.BID_OPTION_COMPUTATION.value, impliedVol=0.25, delta=0.6
        )
        comp_data = createTickOptionComputation(proto)
        assert isinstance(comp_data, TickComputationData)
        assert comp_data.reqId == 1
        assert comp_data.tickType == TickType.BID_OPTION_COMPUTATION
        assert isinstance(comp_data.computation, OptionComputation)
        assert comp_data.computation.impliedVol == 0.25
        assert comp_data.computation.delta == 0.6

    def test_createCalculateImpliedVolatilityRequestProto(self):
        contract = Contract(symbol="AAPL", secType="OPT", right="C", strike=150)
        proto = createCalculateImpliedVolatilityRequestProto(1, contract, 2.5, 145.0, [])
        assert isinstance(proto, CalculateImpliedVolatilityRequestProto)
        assert proto.reqId == 1
        assert proto.contract.symbol == "AAPL"
        assert proto.optionPrice == 2.5
        assert proto.underPrice == 145.0

    def test_createCalculateOptionPriceRequestProto(self):
        contract = Contract(symbol="AAPL", secType="OPT", right="P", strike=140)
        proto = createCalculateOptionPriceRequestProto(1, contract, 0.3, 145.0, [])
        assert isinstance(proto, CalculateOptionPriceRequestProto)
        assert proto.reqId == 1
        assert proto.contract.symbol == "AAPL"
        assert proto.volatility == 0.3
        assert proto.underPrice == 145.0

    def test_createCancelCalculateImpliedVolatilityProto(self):
        proto = createCancelCalculateImpliedVolatilityProto(1)
        assert isinstance(proto, CancelCalculateImpliedVolatilityProto)
        assert proto.reqId == 1

    def test_createCancelCalculateOptionPriceProto(self):
        proto = createCancelCalculateOptionPriceProto(1)
        assert isinstance(proto, CancelCalculateOptionPriceProto)
        assert proto.reqId == 1
