import pytest
from unittest.mock import Mock

from ib_async.objects import AccountValue, Position, PortfolioItem
from ib_async.contract import Contract
from ib_async.protobuf.AccountDataRequest_pb2 import (
    AccountDataRequest as AccountDataRequestProto,
)
from ib_async.protobuf.AccountUpdatesMultiRequest_pb2 import (
    AccountUpdatesMultiRequest as AccountUpdatesMultiRequestProto,
)
from ib_async.protobuf.AccountUpdateMulti_pb2 import (
    AccountUpdateMulti as AccountUpdateMultiProto,
)
from ib_async.protobuf.AccountSummary_pb2 import AccountSummary as AccountSummaryProto
from ib_async.protobuf.AccountValue_pb2 import AccountValue as AccountValueProto
from ib_async.protobuf.CancelAccountUpdatesMulti_pb2 import (
    CancelAccountUpdatesMulti as CancelAccountUpdatesMultiProto,
)
from ib_async.protobuf.Position_pb2 import Position as PositionProto
from ib_async.protobuf.PortfolioValue_pb2 import PortfolioValue as PortfolioValueProto
from ib_async.protobuf.Contract_pb2 import Contract as ContractProto
from ib_async.protobuf.IdsRequest_pb2 import IdsRequest as IdsRequestProto

from ib_async.protobuf_converters.account_converters import (
    createPosition,
    createAccountDataRequestProto,
    createAccountMultiRequestProto,
    createCancelAccMultiRequestProto,
    createAccountValueFromUpdateMulti,
    createAccountValue,
    createAccountSummary,
    createPortfolioItem,
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
        assert portfolio_item.position == 50.0
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
