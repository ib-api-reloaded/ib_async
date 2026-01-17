"""Test for acount protobuf converters."""

from decimal import Decimal
from ib_async.objects import (
    AccountValue,
    FamilyCode,
    PortfolioItem,
    Position,
    PositionMulti,
    SoftDollarTier,
)
from ib_async.protobuf.AccountDataRequest_pb2 import (
    AccountDataRequest as AccountDataRequestProto,
)
from ib_async.protobuf.AccountSummary_pb2 import AccountSummary as AccountSummaryProto
from ib_async.protobuf.AccountUpdateMulti_pb2 import (
    AccountUpdateMulti as AccountUpdateMultiProto,
)
from ib_async.protobuf.AccountUpdatesMultiRequest_pb2 import (
    AccountUpdatesMultiRequest as AccountUpdatesMultiRequestProto,
)
from ib_async.protobuf.AccountValue_pb2 import AccountValue as AccountValueProto
from ib_async.protobuf.CancelAccountUpdatesMulti_pb2 import (
    CancelAccountUpdatesMulti as CancelAccountUpdatesMultiProto,
)
from ib_async.protobuf.CancelPositionsMulti_pb2 import (
    CancelPositionsMulti as CancelPositionsMultiProto,
)
from ib_async.protobuf.Contract_pb2 import Contract as ContractProto
from ib_async.protobuf.FamilyCode_pb2 import FamilyCode as FamilyCodeProto
from ib_async.protobuf.FamilyCodes_pb2 import FamilyCodes as FamilyCodesProto
from ib_async.protobuf.FamilyCodesRequest_pb2 import (
    FamilyCodesRequest as FamilyCodesRequestProto,
)
from ib_async.protobuf.FAReplace_pb2 import FAReplace as FAReplaceProto
from ib_async.protobuf.FARequest_pb2 import FARequest as FARequestProto
from ib_async.protobuf.IdsRequest_pb2 import IdsRequest as IdsRequestProto
from ib_async.protobuf.PortfolioValue_pb2 import PortfolioValue as PortfolioValueProto
from ib_async.protobuf.Position_pb2 import Position as PositionProto
from ib_async.protobuf.PositionMulti_pb2 import PositionMulti as PositionMultiProto
from ib_async.protobuf.PositionsMultiRequest_pb2 import (
    PositionsMultiRequest as PositionsMultiRequestProto,
)
from ib_async.protobuf.ReceiveFA_pb2 import ReceiveFA as ReceiveFAProto
from ib_async.protobuf.ReplaceFAEnd_pb2 import ReplaceFAEnd as ReplaceFAEndProto
from ib_async.protobuf.SoftDollarTier_pb2 import SoftDollarTier as SoftDollarTierProto
from ib_async.protobuf.SoftDollarTiersRequest_pb2 import (
    SoftDollarTiersRequest as SoftDollarTiersRequestProto,
)
from ib_async.protobuf_converters.account_converters import (
    createAccountDataRequestProto,
    createAccountMultiRequestProto,
    createAccountSummary,
    createAccountValue,
    createAccountValueFromUpdateMulti,
    createCancelAccMultiRequestProto,
    createCancelPositionsMultiRequestProto,
    createFamilyCode,
    createFamilyCodes,
    createFamilyCodesRequestProto,
    createFAmsg,
    createFAReplaceProto,
    createFARequestProto,
    createPortfolioItem,
    createPosition,
    createPositionMulti,
    createPositionsMultiRequestProto,
    createReplaceFAEnd,
    createSoftDollarTier,
    createSoftDollarTiers,
    createSoftDollarTiersRequestProto,
    createUserInfoRequestProto,
)


class TestAccountConverters:
    def test_createPosition(self):
        mock_contract_proto = ContractProto(conId=123, symbol="SPY")
        position_proto = PositionProto(
            account="DU12345",
            contract=mock_contract_proto,
            position="100.0",
            avgCost=150.0,
        )
        position = createPosition(position_proto)

        assert isinstance(position, Position)
        assert position.account == "DU12345"
        assert position.contract.conId == 123
        assert position.contract.symbol == "SPY"
        assert position.position == 100.0
        assert position.avgCost == 150.0

    def test_createAccountDataRequestProto(self):
        proto = createAccountDataRequestProto(True, "U12345")
        assert isinstance(proto, AccountDataRequestProto)
        assert proto.subscribe is True
        assert proto.acctCode == "U12345"

    def test_createAccountMultiRequestProto(self):
        proto = createAccountMultiRequestProto(1, "U12345", "Cash", True)
        assert isinstance(proto, AccountUpdatesMultiRequestProto)
        assert proto.reqId == 1
        assert proto.account == "U12345"
        assert proto.modelCode == "Cash"
        assert proto.ledgerAndNLV is True

        proto_minimal = createAccountMultiRequestProto(2, "", "", False)
        assert proto_minimal.reqId == 2
        assert not proto_minimal.HasField("account")
        assert not proto_minimal.HasField("modelCode")
        assert not proto_minimal.HasField("ledgerAndNLV")

    def test_createCancelAccMultiRequestProto(self):
        proto = createCancelAccMultiRequestProto(1)
        assert isinstance(proto, CancelAccountUpdatesMultiProto)
        assert proto.reqId == 1

    def test_createAccountValueFromUpdateMulti(self):
        account_update_multi_proto = AccountUpdateMultiProto(
            account="DU12345", key="NetLiquidation", value="100000.00", currency="USD"
        )
        account_value = createAccountValueFromUpdateMulti(account_update_multi_proto)

        assert isinstance(account_value, AccountValue)
        assert account_value.account == "DU12345"
        assert account_value.tag == "NetLiquidation"
        assert account_value.value == "100000.00"
        assert account_value.currency == "USD"
        assert account_value.modelCode == ""

        # Test with missing fields
        account_update_multi_proto_minimal = AccountUpdateMultiProto()
        account_value_minimal = createAccountValueFromUpdateMulti(
            account_update_multi_proto_minimal
        )
        assert account_value_minimal.account == ""
        assert account_value_minimal.tag == ""
        assert account_value_minimal.value == ""
        assert account_value_minimal.currency == ""

    def test_createAccountValue(self):
        account_value_proto = AccountValueProto(
            accountName="DU12345", key="CashBalance", value="50000.00", currency="USD"
        )
        account_value = createAccountValue(account_value_proto)

        assert isinstance(account_value, AccountValue)
        assert account_value.account == "DU12345"
        assert account_value.tag == "CashBalance"
        assert account_value.value == "50000.00"
        assert account_value.currency == "USD"
        assert account_value.modelCode == ""

        # Test with missing fields
        account_value_proto_minimal = AccountValueProto()
        account_value_minimal = createAccountValue(account_value_proto_minimal)
        assert account_value_minimal.account == ""
        assert account_value_minimal.tag == ""
        assert account_value_minimal.value == ""
        assert account_value_minimal.currency == ""

    def test_createAccountSummary(self):
        account_summary_proto = AccountSummaryProto(
            account="DU12345", tag="TotalCashValue", value="150000.00", currency="USD"
        )
        account_value = createAccountSummary(account_summary_proto)

        assert isinstance(account_value, AccountValue)
        assert account_value.account == "DU12345"
        assert account_value.tag == "TotalCashValue"
        assert account_value.value == "150000.00"
        assert account_value.currency == "USD"
        assert account_value.modelCode == ""

        # Test with missing fields
        account_summary_proto_minimal = AccountSummaryProto()
        account_value_minimal = createAccountSummary(account_summary_proto_minimal)
        assert account_value_minimal.account == ""
        assert account_value_minimal.tag == ""
        assert account_value_minimal.value == ""
        assert account_value_minimal.currency == ""

    def test_createPortfolioItem(self):
        mock_contract_proto = ContractProto(conId=456, symbol="AAPL")
        portfolio_value_proto = PortfolioValueProto(
            contract=mock_contract_proto,
            position="50.0",
            marketPrice=170.0,
            marketValue=8500.0,
            averageCost=160.0,
            unrealizedPNL=500.0,
            realizedPNL=100.0,
            accountName="DU12345",
        )
        portfolio_item = createPortfolioItem(portfolio_value_proto)

        assert isinstance(portfolio_item, PortfolioItem)
        assert portfolio_item.contract.conId == 456
        assert portfolio_item.contract.symbol == "AAPL"
        assert portfolio_item.position == Decimal("50.0")
        assert portfolio_item.marketPrice == 170.0
        assert portfolio_item.marketValue == 8500.0
        assert portfolio_item.averageCost == 160.0
        assert portfolio_item.unrealizedPNL == 500.0
        assert portfolio_item.realizedPNL == 100.0
        assert portfolio_item.account == "DU12345"

        # Test with zero position
        portfolio_value_proto_zero_pos = PortfolioValueProto(
            contract=mock_contract_proto,
            position="0.0",
            marketPrice=170.0,
            marketValue=0.0,
            averageCost=0.0,
            unrealizedPNL=0.0,
            realizedPNL=0.0,
            accountName="DU12345",
        )
        portfolio_item_zero_pos = createPortfolioItem(portfolio_value_proto_zero_pos)
        assert portfolio_item_zero_pos.position == 0.0

    def test_createUserInfoRequestProto(self):
        proto = createUserInfoRequestProto(10)
        assert isinstance(proto, IdsRequestProto)
        assert proto.numIds == 10

    def test_createFARequestProto(self):
        proto = createFARequestProto(1)
        assert isinstance(proto, FARequestProto)
        assert proto.faDataType == 1

    def test_createFAReplaceProto(self):
        proto = createFAReplaceProto(2, 1, "<xml>data</xml>")
        assert isinstance(proto, FAReplaceProto)
        assert proto.reqId == 2
        assert proto.faDataType == 1
        assert proto.xml == "<xml>data</xml>"

    def test_createFAmsg(self):
        msg = ReceiveFAProto(faDataType=1, xml="<xml>fa data</xml>")
        fa_data_type, xml = createFAmsg(msg)
        assert fa_data_type == 1
        assert xml == "<xml>fa data</xml>"

    def test_createReplaceFAEnd(self):
        msg = ReplaceFAEndProto(text="FA data replaced")
        text = createReplaceFAEnd(msg)
        assert text == "FA data replaced"

    def test_createPositionsMultiRequestProto(self):
        proto = createPositionsMultiRequestProto(3, "U123", "MyModel")
        assert isinstance(proto, PositionsMultiRequestProto)
        assert proto.reqId == 3
        assert proto.account == "U123"
        assert proto.modelCode == "MyModel"

    def test_createCancelPositionsMultiRequestProto(self):
        proto = createCancelPositionsMultiRequestProto(4)
        assert isinstance(proto, CancelPositionsMultiProto)
        assert proto.reqId == 4

    def test_createPositionMulti(self):
        contract_proto = ContractProto(symbol="TSLA", secType="STK")
        pos_multi_proto = PositionMultiProto(
            account="U456",
            modelCode="MyModel",
            contract=contract_proto,
            position="200.0",
            avgCost=300.0,
        )
        pos_multi = createPositionMulti(pos_multi_proto)
        assert isinstance(pos_multi, PositionMulti)
        assert pos_multi.account == "U456"
        assert pos_multi.modelCode == "MyModel"
        assert pos_multi.contract.symbol == "TSLA"
        assert pos_multi.position == 200.0
        assert pos_multi.avgCost == 300.0

    def test_createFamilyCodesRequestProto(self):
        proto = createFamilyCodesRequestProto()
        assert isinstance(proto, FamilyCodesRequestProto)

    def test_createFamilyCode(self):
        family_code_proto = FamilyCodeProto(accountId="F123", familyCode="FAM1")
        family_code = createFamilyCode(family_code_proto)
        assert isinstance(family_code, FamilyCode)
        assert family_code.accountID == "F123"
        assert family_code.familyCodeStr == "FAM1"

    def test_createFamilyCodes(self):
        family_codes_proto = FamilyCodesProto()
        fc1 = family_codes_proto.familyCodes.add()
        fc1.accountId = "F1"
        fc1.familyCode = "FC1"
        fc2 = family_codes_proto.familyCodes.add()
        fc2.accountId = "F2"
        fc2.familyCode = "FC2"

        family_codes = createFamilyCodes(family_codes_proto)
        assert len(family_codes) == 2
        assert family_codes[0].accountID == "F1"
        assert family_codes[1].familyCodeStr == "FC2"

    def test_createSoftDollarTiersRequestProto(self):
        proto = createSoftDollarTiersRequestProto(5)
        assert isinstance(proto, SoftDollarTiersRequestProto)
        assert proto.reqId == 5

    def test_createSoftDollarTier(self):
        tier_proto = SoftDollarTierProto(
            name="TierA", value="ValA", displayName="Display A"
        )
        tier = createSoftDollarTier(tier_proto)
        assert isinstance(tier, SoftDollarTier)
        assert tier.name == "TierA"
        assert tier.val == "ValA"
        assert tier.displayName == "Display A"

    def test_createSoftDollarTiers(self):
        # The function createSoftDollarTiers seems to have a wrong type hint.
        # It expects a proto message with a 'softDollarTiers' field.
        # SoftDollarTiersRequestProto does not have this field.
        # We use a mock object to simulate the correct response proto.
        class MockSoftDollarTiersResponseProto:
            def __init__(self):
                self.softDollarTiers = []

        tiers_proto = MockSoftDollarTiersResponseProto()
        tiers_proto.softDollarTiers.append(SoftDollarTierProto(name="T1", value="V1"))
        tiers_proto.softDollarTiers.append(
            SoftDollarTierProto(name="T2", displayName="D2")
        )

        tiers = createSoftDollarTiers(tiers_proto)  # type: ignore
        assert len(tiers) == 2
        assert tiers[0].name == "T1"
        assert tiers[0].val == "V1"
        assert tiers[1].name == "T2"
        assert tiers[1].displayName == "D2"
