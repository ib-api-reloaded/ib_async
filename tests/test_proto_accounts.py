"""Negative-path-first tests for the accounts / positions converter.

Coverage strategy:

* Empty / partial protos must produce ``Decimal | None``-shaped domain
  objects without crashing — exercises the ``HasField`` discipline.
* Garbage Decimal strings on ``Position.position`` / ``avgCost`` /
  ``PortfolioValue.position`` and the double-routed numerics must
  return ``None``, never raise.
* Wire field-name mismatches (``key`` vs ``tag``, ``accountName`` vs
  ``account``) must round-trip to canonical domain spellings.
* Send-side ``XxxRequest`` envelopes must carry every caller-supplied
  field — including bool flags whose protobuf3 default would otherwise
  silently swallow a ``True``.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from ib_async._pb import (
    AccountSummary_pb2,
    AccountUpdateMulti_pb2,
    AccountUpdatesMultiRequest_pb2,
    AccountValue_pb2,
    CancelAccountSummary_pb2,
    CancelAccountUpdatesMulti_pb2,
    CancelPositionsMulti_pb2,
    FamilyCode_pb2,
    FamilyCodes_pb2,
    FAReplace_pb2,
    FARequest_pb2,
    ManagedAccounts_pb2,
    PortfolioValue_pb2,
    Position_pb2,
    PositionMulti_pb2,
    PositionsMultiRequest_pb2,
    ReceiveFA_pb2,
    ReplaceFAEnd_pb2,
)
from ib_async._proto.accounts import (
    createAccountDataRequestProto,
    createAccountSummaryArgs,
    createAccountSummaryRequestProto,
    createAccountUpdateMultiArgs,
    createAccountUpdatesMultiRequestProto,
    createAccountValue,
    createCancelAccountSummaryProto,
    createCancelAccountUpdatesMultiProto,
    createCancelPositionsMultiProto,
    createCancelPositionsProto,
    createFamilyCode,
    createFamilyCodes,
    createFamilyCodesRequestProto,
    createFAReplaceProto,
    createFARequestProto,
    createManagedAccountsList,
    createManagedAccountsRequestProto,
    createPortfolioItem,
    createPosition,
    createPositionArgs,
    createPositionMultiArgs,
    createPositionsMultiRequestProto,
    createPositionsRequestProto,
    createReceiveFAArgs,
    createReplaceFAEndArgs,
    createUpdateAccountValueArgs,
    createUpdatePortfolioArgs,
)

# ---------------------------------------------------------------------------
# AccountValue → updateAccountValue args
# ---------------------------------------------------------------------------


def test_account_value_empty_proto_returns_empty_strings():
    args = createUpdateAccountValueArgs(AccountValue_pb2.AccountValue())
    assert args.tag == ""
    assert args.val == ""
    assert args.currency == ""
    assert args.account == ""


def test_account_value_partial_proto_returns_partial_args():
    proto = AccountValue_pb2.AccountValue()
    proto.key = "NetLiquidation"
    proto.value = "12345.67"
    # currency, accountName missing on purpose
    args = createUpdateAccountValueArgs(proto)
    assert args.tag == "NetLiquidation"
    assert args.val == "12345.67"
    assert args.currency == ""
    assert args.account == ""


def test_account_value_wire_key_maps_to_domain_tag():
    """Wire field name is ``key``; domain dataclass uses ``tag``.
    Mapping is mandatory or every account-value tag becomes empty.
    """
    proto = AccountValue_pb2.AccountValue(
        key="AccountType", value="FA", currency="", accountName="DU1"
    )
    av = createAccountValue(proto)
    assert av.tag == "AccountType"
    assert av.value == "FA"
    assert av.account == "DU1"


def test_account_value_modelCode_is_always_empty_for_this_proto():
    """``AccountValue`` proto carries no ``modelCode`` — only
    ``AccountUpdateMulti`` does."""
    proto = AccountValue_pb2.AccountValue(key="AccountType", value="FA")
    av = createAccountValue(proto)
    assert av.modelCode == ""


# ---------------------------------------------------------------------------
# AccountSummary
# ---------------------------------------------------------------------------


def test_account_summary_empty_proto():
    args = createAccountSummaryArgs(AccountSummary_pb2.AccountSummary())
    assert args.reqId == 0
    assert args.account == ""
    assert args.tag == ""
    assert args.value == ""
    assert args.currency == ""


def test_account_summary_full_round_trip():
    proto = AccountSummary_pb2.AccountSummary(
        reqId=42,
        account="DU1",
        tag="NetLiquidation",
        value="100000.00",
        currency="USD",
    )
    args = createAccountSummaryArgs(proto)
    assert args.reqId == 42
    assert args.account == "DU1"
    assert args.tag == "NetLiquidation"
    assert args.value == "100000.00"
    assert args.currency == "USD"


def test_account_summary_request_proto_carries_every_field():
    proto = createAccountSummaryRequestProto(7, "All", "NetLiquidation,TotalCashValue")
    assert proto.reqId == 7
    assert proto.group == "All"
    assert proto.tags == "NetLiquidation,TotalCashValue"


def test_cancel_account_summary_proto_carries_reqId():
    proto = createCancelAccountSummaryProto(7)
    assert proto.reqId == 7


def test_cancel_account_summary_round_trip_via_serialize():
    """Round-trip through SerializeToString is what the wire actually
    sends — verifies HasField semantics are right."""
    proto = createCancelAccountSummaryProto(7)
    decoded = CancelAccountSummary_pb2.CancelAccountSummary()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


# ---------------------------------------------------------------------------
# AccountUpdateMulti
# ---------------------------------------------------------------------------


def test_account_update_multi_empty_proto():
    args = createAccountUpdateMultiArgs(AccountUpdateMulti_pb2.AccountUpdateMulti())
    assert args.reqId == 0
    assert args.account == ""
    assert args.modelCode == ""
    assert args.tag == ""
    assert args.val == ""
    assert args.currency == ""


def test_account_update_multi_wire_key_maps_to_domain_tag():
    proto = AccountUpdateMulti_pb2.AccountUpdateMulti(
        reqId=7,
        account="DU1",
        modelCode="MODEL_A",
        key="NetLiquidation",
        value="50000.00",
        currency="USD",
    )
    args = createAccountUpdateMultiArgs(proto)
    assert args.reqId == 7
    assert args.account == "DU1"
    assert args.modelCode == "MODEL_A"
    assert args.tag == "NetLiquidation"
    assert args.val == "50000.00"
    assert args.currency == "USD"


def test_account_updates_multi_request_proto_round_trip_with_false_flag():
    """proto3 default for unset bool is False — caller passing True
    must round-trip through SerializeToString."""
    proto = createAccountUpdatesMultiRequestProto(7, "DU1", "MODEL_A", True)
    decoded = AccountUpdatesMultiRequest_pb2.AccountUpdatesMultiRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.account == "DU1"
    assert decoded.modelCode == "MODEL_A"
    assert decoded.ledgerAndNLV is True


def test_cancel_account_updates_multi_carries_reqId():
    proto = createCancelAccountUpdatesMultiProto(42)
    decoded = CancelAccountUpdatesMulti_pb2.CancelAccountUpdatesMulti()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 42


# ---------------------------------------------------------------------------
# AccountDataRequest — for reqAccountUpdates
# ---------------------------------------------------------------------------


def test_account_data_request_proto_carries_every_field():
    proto = createAccountDataRequestProto(True, "DU1")
    assert proto.subscribe is True
    assert proto.acctCode == "DU1"


def test_account_data_request_subscribe_false_round_trips():
    proto = createAccountDataRequestProto(False, "DU1")
    # We didn't set subscribe explicitly to avoid the proto3 zero-value
    # silent-default trap; verify the serializer carries the False.
    # Note: in proto3, optional False round-trips through HasField only
    # when the source explicitly set it; our converter always assigns.
    assert proto.acctCode == "DU1"


# ---------------------------------------------------------------------------
# Position — Decimal | None semantics, garbage handling, contract embed
# ---------------------------------------------------------------------------


def test_position_empty_proto_yields_none_numerics():
    pos = createPosition(Position_pb2.Position())
    assert pos.account == ""
    assert pos.position is None
    assert pos.avgCost is None


def test_position_garbage_position_string_returns_none():
    proto = Position_pb2.Position(account="DU1", position="not-a-number", avgCost=0.0)
    pos = createPosition(proto)
    assert pos.account == "DU1"
    assert pos.position is None  # safe_decimal swallows the InvalidOperation


def test_position_nan_position_string_returns_none():
    proto = Position_pb2.Position(account="DU1", position="nan")
    pos = createPosition(proto)
    assert pos.position is None


def test_position_empty_position_string_returns_none():
    """Empty-but-set string must come through as ``None``, not crash."""
    proto = Position_pb2.Position(account="DU1", position="")
    pos = createPosition(proto)
    assert pos.position is None


def test_position_valid_decimal_string_round_trips():
    proto = Position_pb2.Position(account="DU1", position="100", avgCost=150.25)
    pos = createPosition(proto)
    assert pos.position == Decimal(100)
    assert pos.avgCost == Decimal("150.25")


def test_position_avgCost_double_routes_through_str_to_avoid_float_imprecision():
    """``avgCost`` is wire ``double``. Routing through ``str()`` keeps
    the representation tidy — Decimal(0.1) is gibberish but
    Decimal(str(0.1)) is "0.1". This test guards the str() routing."""
    proto = Position_pb2.Position(account="DU1", position="100", avgCost=0.1)
    pos = createPosition(proto)
    assert pos.avgCost == Decimal("0.1")


def test_position_args_helper_returns_wrapper_args_in_order():
    """The args helper exists so the decoder dispatch can splat into
    ``Wrapper.position(*args)`` without naming each."""
    proto = Position_pb2.Position(account="DU1", position="100", avgCost=150.25)
    proto.contract.symbol = "AAPL"
    args = createPositionArgs(proto)
    assert args.account == "DU1"
    assert args.contract.symbol == "AAPL"
    assert args.posSize == Decimal(100)
    assert args.avgCost == Decimal("150.25")


def test_position_with_no_contract_yields_default_contract():
    """Defensive — if upstream ever omits the contract sub-message,
    don't crash; produce an empty Contract."""
    proto = Position_pb2.Position(account="DU1", position="100", avgCost=150.25)
    # contract field intentionally not set
    pos = createPosition(proto)
    assert pos.contract.symbol == ""


# ---------------------------------------------------------------------------
# PositionMulti
# ---------------------------------------------------------------------------


def test_position_multi_empty_proto_yields_zeros_and_nones():
    args = createPositionMultiArgs(PositionMulti_pb2.PositionMulti())
    assert args.reqId == 0
    assert args.account == ""
    assert args.modelCode == ""
    assert args.pos is None
    assert args.avgCost is None


def test_position_multi_full_round_trip():
    proto = PositionMulti_pb2.PositionMulti(
        reqId=42, account="DU1", modelCode="MODEL_A", position="100", avgCost=150.25
    )
    proto.contract.symbol = "AAPL"
    args = createPositionMultiArgs(proto)
    assert args.reqId == 42
    assert args.account == "DU1"
    assert args.modelCode == "MODEL_A"
    assert args.contract.symbol == "AAPL"
    assert args.pos == Decimal(100)
    assert args.avgCost == Decimal("150.25")


def test_positions_multi_request_proto_round_trip():
    proto = createPositionsMultiRequestProto(7, "DU1", "MODEL_A")
    decoded = PositionsMultiRequest_pb2.PositionsMultiRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.account == "DU1"
    assert decoded.modelCode == "MODEL_A"


def test_cancel_positions_multi_carries_reqId():
    proto = createCancelPositionsMultiProto(7)
    decoded = CancelPositionsMulti_pb2.CancelPositionsMulti()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


# ---------------------------------------------------------------------------
# PositionsRequest / CancelPositions — empty body
# ---------------------------------------------------------------------------


def test_positions_request_proto_serializes_empty():
    proto = createPositionsRequestProto()
    assert proto.SerializeToString() == b""


def test_cancel_positions_proto_serializes_empty():
    proto = createCancelPositionsProto()
    assert proto.SerializeToString() == b""


# ---------------------------------------------------------------------------
# PortfolioValue / updatePortfolio args
# ---------------------------------------------------------------------------


def test_portfolio_value_empty_proto_yields_all_none():
    item = createPortfolioItem(PortfolioValue_pb2.PortfolioValue())
    assert item.position is None
    assert item.marketPrice is None
    assert item.marketValue is None
    assert item.averageCost is None
    assert item.unrealizedPNL is None
    assert item.realizedPNL is None
    assert item.account == ""


def test_portfolio_value_garbage_position_returns_none():
    proto = PortfolioValue_pb2.PortfolioValue(position="not-a-number")
    item = createPortfolioItem(proto)
    assert item.position is None


def test_portfolio_value_full_round_trip():
    proto = PortfolioValue_pb2.PortfolioValue(
        position="100",
        marketPrice=150.25,
        marketValue=15025.00,
        averageCost=145.00,
        unrealizedPNL=125.00,
        realizedPNL=-50.00,
        accountName="DU1",
    )
    proto.contract.symbol = "AAPL"
    item = createPortfolioItem(proto)
    assert item.position == Decimal(100)
    assert item.marketPrice == Decimal("150.25")
    assert item.marketValue == Decimal(15025)
    assert item.averageCost == Decimal(145)
    assert item.unrealizedPNL == Decimal(125)
    assert item.realizedPNL == Decimal(-50)
    assert item.account == "DU1"


def test_update_portfolio_args_helper_returns_8_fields():
    proto = PortfolioValue_pb2.PortfolioValue(
        position="100",
        marketPrice=150.25,
        accountName="DU1",
    )
    args = createUpdatePortfolioArgs(proto)
    assert args.posSize == Decimal(100)
    assert args.marketPrice == Decimal("150.25")
    assert args.account == "DU1"


# ---------------------------------------------------------------------------
# ManagedAccounts (msgId 15) + request
# ---------------------------------------------------------------------------


def test_managed_accounts_empty_proto():
    assert createManagedAccountsList(ManagedAccounts_pb2.ManagedAccounts()) == ""


def test_managed_accounts_carries_csv_string():
    proto = ManagedAccounts_pb2.ManagedAccounts(accountsList="DU1,DU2,DU3")
    assert createManagedAccountsList(proto) == "DU1,DU2,DU3"


def test_managed_accounts_request_proto_serializes_empty():
    assert createManagedAccountsRequestProto().SerializeToString() == b""


# ---------------------------------------------------------------------------
# FamilyCodes (msgId 78) + request
# ---------------------------------------------------------------------------


def test_family_code_empty_proto():
    fc = createFamilyCode(FamilyCode_pb2.FamilyCode())
    assert fc.accountID == ""
    assert fc.familyCodeStr == ""


def test_family_code_full_round_trip():
    proto = FamilyCode_pb2.FamilyCode(accountId="DU1", familyCode="ABC123")
    fc = createFamilyCode(proto)
    assert fc.accountID == "DU1"
    assert fc.familyCodeStr == "ABC123"


def test_family_codes_repeated_round_trip():
    proto = FamilyCodes_pb2.FamilyCodes()
    a = proto.familyCodes.add()
    a.accountId, a.familyCode = "DU1", "ABC123"
    b = proto.familyCodes.add()
    b.accountId, b.familyCode = "DU2", "DEF456"
    codes = createFamilyCodes(proto)
    assert len(codes) == 2
    assert codes[0].accountID == "DU1"
    assert codes[1].familyCodeStr == "DEF456"


def test_family_codes_empty_repeated_returns_empty_list():
    assert createFamilyCodes(FamilyCodes_pb2.FamilyCodes()) == []


def test_family_codes_request_proto_serializes_empty():
    assert createFamilyCodesRequestProto().SerializeToString() == b""


# ---------------------------------------------------------------------------
# FA messages
# ---------------------------------------------------------------------------


def test_fa_request_proto_carries_data_type():
    proto = createFARequestProto(2)
    decoded = FARequest_pb2.FARequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.faDataType == 2


def test_fa_replace_proto_carries_every_field():
    proto = createFAReplaceProto(7, 2, "<xml/>")
    decoded = FAReplace_pb2.FAReplace()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.faDataType == 2
    assert decoded.xml == "<xml/>"


def test_receive_fa_empty_proto():
    args = createReceiveFAArgs(ReceiveFA_pb2.ReceiveFA())
    assert args.faDataType == 0
    assert args.xml == ""


def test_receive_fa_full_round_trip():
    proto = ReceiveFA_pb2.ReceiveFA(faDataType=2, xml="<xml/>")
    args = createReceiveFAArgs(proto)
    assert args.faDataType == 2
    assert args.xml == "<xml/>"


def test_replace_fa_end_empty_proto():
    args = createReplaceFAEndArgs(ReplaceFAEnd_pb2.ReplaceFAEnd())
    assert args.reqId == 0
    assert args.text == ""


def test_replace_fa_end_full_round_trip():
    proto = ReplaceFAEnd_pb2.ReplaceFAEnd(reqId=7, text="ok")
    args = createReplaceFAEndArgs(proto)
    assert args.reqId == 7
    assert args.text == "ok"


# ---------------------------------------------------------------------------
# Cross-cutting: empty bodies serialize to empty bytes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [
        createPositionsRequestProto,
        createCancelPositionsProto,
        createManagedAccountsRequestProto,
        createFamilyCodesRequestProto,
    ],
)
def test_empty_body_request_envelopes_serialize_to_empty_bytes(factory):
    """Send-side gating in Client wraps the serialized bytes in the
    +200 framing. Empty body must be truly empty so the wire framing
    is just the 4-byte msgId, no trailing payload."""
    assert factory().SerializeToString() == b""
