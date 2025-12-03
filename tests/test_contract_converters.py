import pytest
from unittest.mock import Mock
from ib_async.contract import (
    ComboLeg,
    Contract,
    ContractDescription,
    ContractDetails,
    DeltaNeutralContract,
    IneligibilityReason,
)
from ib_async.objects import OptionChain, SmartComponent
from ib_async.order import Order
from ib_async.protobuf.ComboLeg_pb2 import ComboLeg as ComboLegProto
from ib_async.protobuf.Contract_pb2 import Contract as ContractProto
from ib_async.protobuf.ContractData_pb2 import ContractData as ContractDataProto
from ib_async.protobuf.ContractDescription_pb2 import (
    ContractDescription as ContractDescriptionProto,
)
from ib_async.protobuf.ContractDetails_pb2 import (
    ContractDetails as ContractDetailsProto,
)
from ib_async.protobuf.DeltaNeutralContract_pb2 import (
    DeltaNeutralContract as DeltaNeutralContractProto,
)
from ib_async.protobuf.MarketRuleRequest_pb2 import (
    MarketRuleRequest as MarketRuleRequestProto,
)
from ib_async.protobuf.MatchingSymbolsRequest_pb2 import (
    MatchingSymbolsRequest as MatchingSymbolsRequestProto,
)
from ib_async.protobuf.SecDefOptParameter_pb2 import (
    SecDefOptParameter as SecDefOptParameterProto,
)
from ib_async.protobuf.SecDefOptParamsRequest_pb2 import (
    SecDefOptParamsRequest as SecDefOptParamsRequestProto,
)
from ib_async.protobuf.SmartComponentsRequest_pb2 import (
    SmartComponentsRequest as SmartComponentsRequestProto,
)
from ib_async.protobuf.SmartComponents_pb2 import (
    SmartComponents as SmartComponentsProto,
)
from ib_async.protobuf_converters.contract_converters import (
    createSecDefOptParamsRequestProto,
    createOptionChain,
    createContract,
    createComboLegs,
    createDeltaNeutralContract,
    createIneligibilityReasonList,
    setLastTradeDate,
    createContractDetails,
    createContractDescription,
    createMatchingSymbolsRequestProto,
    createMarketRuleRequestProto,
    createContractProto,
    createDeltaNeutralContractProto,
    createComboLegProtoList,
    createComboLegProto,
    createSmartComponentsRequestProto,
    createSmartComponents,
)


class TestContractConverters:
    def test_createSecDefOptParamsRequestProto(self):
        proto = createSecDefOptParamsRequestProto(1, "SPX", "SMART", "IND", 123)
        assert isinstance(proto, SecDefOptParamsRequestProto)
        assert proto.reqId == 1
        assert proto.underlyingSymbol == "SPX"
        assert proto.futFopExchange == "SMART"
        assert proto.underlyingSecType == "IND"
        assert proto.underlyingConId == 123

    def test_createOptionChain(self):
        proto = SecDefOptParameterProto(
            exchange="CBOE",
            underlyingConId=456,
            tradingClass="SPXW",
            multiplier="100",
            expirations=["202512", "202603"],
            strikes=[4000.0, 4100.0],
        )
        option_chain = createOptionChain(proto)
        assert isinstance(option_chain, OptionChain)
        assert option_chain.exchange == "CBOE"
        assert option_chain.underlyingConId == 456
        assert option_chain.tradingClass == "SPXW"
        assert option_chain.multiplier == "100"
        assert option_chain.expirations == ["202512", "202603"]
        assert option_chain.strikes == [4000.0, 4100.0]

    def test_createContract(self):
        proto = ContractProto(
            conId=1, symbol="AAPL", secType="STK", exchange="SMART", currency="USD"
        )
        contract = createContract(proto)
        assert isinstance(contract, Contract)
        assert contract.conId == 1
        assert contract.symbol == "AAPL"
        assert contract.secType == "STK"
        assert contract.exchange == "SMART"
        assert contract.currency == "USD"

    def test_createComboLegs(self):
        proto = ContractProto()
        leg1 = proto.comboLegs.add()
        leg1.conId = 1
        leg1.ratio = 1
        leg1.action = "BUY"
        leg1.exchange = "SMART"

        combo_legs = createComboLegs(proto)
        assert len(combo_legs) == 1
        leg = combo_legs[0]
        assert isinstance(leg, ComboLeg)
        assert leg.conId == 1
        assert leg.ratio == 1
        assert leg.action == "BUY"
        assert leg.exchange == "SMART"

    def test_createDeltaNeutralContract(self):
        proto = ContractProto()
        dn_proto = proto.deltaNeutralContract
        dn_proto.conId = 123
        dn_proto.delta = 0.5
        dn_proto.price = 10.0

        dn_contract = createDeltaNeutralContract(proto)
        assert isinstance(dn_contract, DeltaNeutralContract)
        assert dn_contract.conId == 123
        assert dn_contract.delta == 0.5
        assert dn_contract.price == 10.0

    def test_createIneligibilityReasonList(self):
        proto = ContractDetailsProto()
        reason1 = proto.ineligibilityReasonList.add()
        reason1.id = "1"
        reason1.description = "Reason 1"

        reasons = createIneligibilityReasonList(proto)
        assert len(reasons) == 1
        reason = reasons[0]
        assert isinstance(reason, IneligibilityReason)
        assert reason.id_ == "1"
        assert reason.description == "Reason 1"

    def test_setLastTradeDate(self):
        cd = ContractDetails(contract=Contract())
        setLastTradeDate("20251219", cd, isBond=False)
        assert cd.contract.lastTradeDateOrContractMonth == "20251219"

        cd_bond = ContractDetails(contract=Contract())
        setLastTradeDate("20300101", cd_bond, isBond=True)
        assert cd_bond.maturity == "20300101"

    def test_createContractDetails(self):
        contract_proto = ContractProto(symbol="TSLA", secType="STK")
        details_proto = ContractDetailsProto(marketName="Tesla", longName="Tesla Inc.")
        msg = ContractDataProto(contract=contract_proto, contractDetails=details_proto)

        cd = createContractDetails(msg)
        assert isinstance(cd, ContractDetails)
        assert cd.contract.symbol == "TSLA"
        assert cd.marketName == "Tesla"
        assert cd.longName == "Tesla Inc."

    def test_createContractDescription(self):
        contract_proto = ContractProto(symbol="GOOG", secType="STK")
        desc_proto = ContractDescriptionProto(contract=contract_proto)
        desc_proto.derivativeSecTypes.extend(["OPT", "FUT"])

        desc = createContractDescription(desc_proto)
        assert isinstance(desc, ContractDescription)
        assert desc.contract.symbol == "GOOG"
        assert desc.derivativeSecTypes == ["OPT", "FUT"]

    def test_createMatchingSymbolsRequestProto(self):
        proto = createMatchingSymbolsRequestProto(1, "IBKR")
        assert isinstance(proto, MatchingSymbolsRequestProto)
        assert proto.reqId == 1
        assert proto.pattern == "IBKR"

    def test_createMarketRuleRequestProto(self):
        proto = createMarketRuleRequestProto(123)
        assert isinstance(proto, MarketRuleRequestProto)
        assert proto.marketRuleId == 123

    def test_createContractProto(self):
        contract = Contract(
            symbol="MSFT", secType="STK", exchange="SMART", currency="USD"
        )
        proto = createContractProto(contract, None)
        assert isinstance(proto, ContractProto)
        assert proto.symbol == "MSFT"
        assert proto.secType == "STK"
        assert proto.exchange == "SMART"
        assert proto.currency == "USD"

    def test_createDeltaNeutralContractProto(self):
        dn_contract = DeltaNeutralContract(conId=456, delta=0.8, price=20.0)
        contract = Contract(deltaNeutralContract=dn_contract)
        proto = createDeltaNeutralContractProto(contract)
        assert isinstance(proto, DeltaNeutralContractProto)
        assert proto.conId == 456
        assert proto.delta == 0.8
        assert proto.price == 20.0

    def test_createComboLegProtoList(self):
        leg1 = ComboLeg(conId=1, ratio=1, action="BUY")
        leg2 = ComboLeg(conId=2, ratio=2, action="SELL")
        contract = Contract(comboLegs=[leg1, leg2])
        order = Order(orderComboLegs=[Mock(price=10.0), Mock(price=20.0)])

        proto_list = createComboLegProtoList(contract, order)
        assert len(proto_list) == 2
        assert proto_list[0].conId == 1
        assert proto_list[0].ratio == 1
        assert proto_list[0].perLegPrice == 10.0
        assert proto_list[1].conId == 2
        assert proto_list[1].ratio == 2
        assert proto_list[1].perLegPrice == 20.0

    def test_createComboLegProto(self):
        leg = ComboLeg(conId=1, ratio=1, action="BUY", exchange="SMART")
        proto = createComboLegProto(leg, 15.0)
        assert isinstance(proto, ComboLegProto)
        assert proto.conId == 1
        assert proto.ratio == 1
        assert proto.action == "BUY"
        assert proto.exchange == "SMART"
        assert proto.perLegPrice == 15.0

    def test_createSmartComponentsRequestProto(self):
        proto = createSmartComponentsRequestProto(1, "SMART")
        assert isinstance(proto, SmartComponentsRequestProto)
        assert proto.reqId == 1
        assert proto.bboExchange == "SMART"

    def test_createSmartComponents(self):
        smart_components_proto = SmartComponentsProto()
        comp1 = smart_components_proto.smartComponents.add()
        comp1.bitNumber = 1
        comp1.exchange = "SMART"
        comp1.exchangeLetter = "A"

        comp2 = smart_components_proto.smartComponents.add()
        comp2.bitNumber = 2
        comp2.exchange = "NYSE"
        comp2.exchangeLetter = "B"

        smart_components = createSmartComponents(smart_components_proto)
        assert isinstance(smart_components, list)
        assert len(smart_components) == 2

        assert isinstance(smart_components[0], SmartComponent)
        assert smart_components[0].bitNumber == 1
        assert smart_components[0].exchange == "SMART"
        assert smart_components[0].exchangeLetter == "A"

        assert isinstance(smart_components[1], SmartComponent)
        assert smart_components[1].bitNumber == 2
        assert smart_components[1].exchange == "NYSE"
        assert smart_components[1].exchangeLetter == "B"

    def test_createSmartComponents_empty(self):
        smart_components_proto = SmartComponentsProto()
        smart_components = createSmartComponents(smart_components_proto)
        assert isinstance(smart_components, list)
        assert len(smart_components) == 0
