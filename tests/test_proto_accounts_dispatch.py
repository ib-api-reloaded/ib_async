"""End-to-end dispatch + gating tests for accounts / positions protobuf.

Mirrors the orders / contracts equivalents (test_proto_decoder_dispatch
and test_proto_client_gating) for the account / position message
families. Receive side: a synthetic proto payload routes through
``processProtoBuf`` and lands the same wrapper state the binary path
produces. Send side: per ``useProtoBuf(canonicalMsgId)`` boolean, a
server below the family gate keeps NUL-separated text framing while a
server at or above the gate emits a 4-byte BE protobuf frame.

Both directions guard against the standard converter bug-prevention
checklist: source-to-target writes, HasField guards, no module
globals, malformed input lands as ``None``.
"""

from __future__ import annotations

from decimal import Decimal

import ib_async as ibi
from ib_async._pb import (
    AccountDataEnd_pb2,
    AccountDataRequest_pb2,
    AccountSummary_pb2,
    AccountSummaryEnd_pb2,
    AccountSummaryRequest_pb2,
    AccountUpdateMulti_pb2,
    AccountUpdateMultiEnd_pb2,
    AccountUpdatesMultiRequest_pb2,
    AccountUpdateTime_pb2,
    AccountValue_pb2,
    CancelAccountSummary_pb2,
    CancelAccountUpdatesMulti_pb2,
    CancelPositionsMulti_pb2,
    ManagedAccounts_pb2,
    PortfolioValue_pb2,
    Position_pb2,
    PositionEnd_pb2,
    PositionMulti_pb2,
    PositionMultiEnd_pb2,
    PositionsMultiRequest_pb2,
)
from ib_async._pb_msgids import (
    CANCEL_ACCOUNT_SUMMARY,
    CANCEL_ACCOUNT_UPDATES_MULTI,
    CANCEL_POSITIONS,
    CANCEL_POSITIONS_MULTI,
    REQ_ACCOUNT_SUMMARY,
    REQ_ACCOUNT_UPDATES_MULTI,
    REQ_ACCT_DATA,
    REQ_MANAGED_ACCTS,
    REQ_POSITIONS,
    REQ_POSITIONS_MULTI,
)
from ib_async._requests import ReqIdKey, SingletonKey
from tests._helpers import _captureSend, _decodeProtoFrame, _ibAtVersion

# ===========================================================================
# RECEIVE SIDE — Decoder.processProtoBuf dispatch lands wrapper state
# ===========================================================================


# ---------- updateAccountValue (msgId 6) ---------------------------------


def test_account_value_proto_lands_in_account_values_dict():
    ib = ibi.IB()
    proto = AccountValue_pb2.AccountValue(
        key="NetLiquidation", value="100000.00", currency="USD", accountName="DU1"
    )
    ib.client.decoder.processProtoBuf(6, proto.SerializeToString())
    key = ("DU1", "NetLiquidation", "USD", "")
    av = ib.wrapper.accountValues[key]
    assert av.value == "100000.00"
    # Typed view is the v3.0 ergonomic surface.
    assert av.decimalValue == Decimal("100000")


# ---------- updatePortfolio (msgId 7) ------------------------------------


def test_portfolio_value_proto_lands_in_portfolio_dict():
    ib = ibi.IB()
    proto = PortfolioValue_pb2.PortfolioValue(
        position="100",
        marketPrice=150.25,
        marketValue=15025.0,
        averageCost=145.0,
        unrealizedPNL=125.0,
        realizedPNL=-50.0,
        accountName="DU1",
    )
    proto.contract.conId = 7
    proto.contract.symbol = "AAPL"
    ib.client.decoder.processProtoBuf(7, proto.SerializeToString())
    item = ib.wrapper.portfolio["DU1"][7]
    assert item.position == Decimal("100")
    assert item.marketPrice == Decimal("150.25")
    assert item.realizedPNL == Decimal("-50")


def test_portfolio_value_zero_position_drops_cached_entry():
    """A zero-position portfolio update must remove the cached entry,
    matching the wire-binary path's drop-on-close semantics."""
    ib = ibi.IB()

    # Seed a position first.
    proto = PortfolioValue_pb2.PortfolioValue(
        position="100", marketPrice=150.25, accountName="DU1"
    )
    proto.contract.conId = 7
    ib.client.decoder.processProtoBuf(7, proto.SerializeToString())
    assert 7 in ib.wrapper.portfolio["DU1"]

    # Then zero it out.
    proto.position = "0"
    ib.client.decoder.processProtoBuf(7, proto.SerializeToString())
    assert 7 not in ib.wrapper.portfolio["DU1"]


# ---------- accountUpdateTime (msgId 8) ----------------------------------


def test_account_update_time_proto_does_not_raise():
    """``Wrapper.updateAccountTime`` is a no-op pass; smoke-test only."""
    ib = ibi.IB()
    proto = AccountUpdateTime_pb2.AccountUpdateTime(timeStamp="09:30:00")
    ib.client.decoder.processProtoBuf(8, proto.SerializeToString())


# ---------- managedAccounts (msgId 15) -----------------------------------


def test_managed_accounts_proto_populates_accounts_list():
    ib = ibi.IB()
    proto = ManagedAccounts_pb2.ManagedAccounts(accountsList="DU1,DU2,DU3")
    ib.client.decoder.processProtoBuf(15, proto.SerializeToString())
    assert ib.wrapper.accounts == ["DU1", "DU2", "DU3"]


# ---------- accountDownloadEnd (msgId 54) --------------------------------


def test_account_download_end_proto_settles_singleton_request():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(SingletonKey("accountValues"), container=[])
    assert not req.future.done()

    proto = AccountDataEnd_pb2.AccountDataEnd(accountName="DU1")
    ib.client.decoder.processProtoBuf(54, proto.SerializeToString())

    assert req.future.done()


# ---------- position (msgId 61) + positionEnd (msgId 62) -----------------


def test_position_proto_lands_in_positions_dict():
    ib = ibi.IB()
    proto = Position_pb2.Position(account="DU1", position="100", avgCost=150.25)
    proto.contract.conId = 7
    proto.contract.symbol = "AAPL"
    ib.client.decoder.processProtoBuf(61, proto.SerializeToString())
    pos = ib.wrapper.positions["DU1"][7]
    assert pos.position == Decimal("100")
    assert pos.avgCost == Decimal("150.25")


def test_position_proto_zero_quantity_drops_cached_entry():
    ib = ibi.IB()
    proto = Position_pb2.Position(account="DU1", position="100", avgCost=150.25)
    proto.contract.conId = 7
    ib.client.decoder.processProtoBuf(61, proto.SerializeToString())
    assert 7 in ib.wrapper.positions["DU1"]

    proto.position = "0"
    ib.client.decoder.processProtoBuf(61, proto.SerializeToString())
    assert 7 not in ib.wrapper.positions["DU1"]


def test_position_end_proto_settles_singleton_request():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(SingletonKey("positions"), container=[])
    assert not req.future.done()

    ib.client.decoder.processProtoBuf(
        62, PositionEnd_pb2.PositionEnd().SerializeToString()
    )
    assert req.future.done()


# ---------- accountSummary (msgId 63) + end (msgId 64) -------------------


def test_account_summary_proto_lands_in_acct_summary_dict():
    ib = ibi.IB()
    proto = AccountSummary_pb2.AccountSummary(
        reqId=42,
        account="DU1",
        tag="NetLiquidation",
        value="100000.00",
        currency="USD",
    )
    ib.client.decoder.processProtoBuf(63, proto.SerializeToString())
    av = ib.wrapper.acctSummary[("DU1", "NetLiquidation", "USD")]
    assert av.value == "100000.00"
    assert av.decimalValue == Decimal("100000")


def test_account_summary_end_proto_settles_reqId():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(42), container=[])
    assert not req.future.done()

    proto = AccountSummaryEnd_pb2.AccountSummaryEnd(reqId=42)
    ib.client.decoder.processProtoBuf(64, proto.SerializeToString())

    assert req.future.done()


# ---------- positionMulti (msgId 71) + end (msgId 72) --------------------


def test_position_multi_proto_does_not_raise():
    """``Wrapper.positionMulti`` is a no-op (model-portfolio updates
    aren't routed to a default container); smoke-test only."""
    ib = ibi.IB()
    proto = PositionMulti_pb2.PositionMulti(
        reqId=7, account="DU1", modelCode="MODEL_A", position="100", avgCost=150.25
    )
    proto.contract.symbol = "AAPL"
    ib.client.decoder.processProtoBuf(71, proto.SerializeToString())


def test_position_multi_end_proto_does_not_raise():
    ib = ibi.IB()
    proto = PositionMultiEnd_pb2.PositionMultiEnd(reqId=7)
    ib.client.decoder.processProtoBuf(72, proto.SerializeToString())


# ---------- accountUpdateMulti (msgId 73) + end (msgId 74) ---------------


def test_account_update_multi_proto_lands_with_modelCode():
    ib = ibi.IB()
    proto = AccountUpdateMulti_pb2.AccountUpdateMulti(
        reqId=7,
        account="DU1",
        modelCode="MODEL_A",
        key="NetLiquidation",
        value="50000.00",
        currency="USD",
    )
    ib.client.decoder.processProtoBuf(73, proto.SerializeToString())
    key = ("DU1", "NetLiquidation", "USD", "MODEL_A")
    av = ib.wrapper.accountValues[key]
    assert av.value == "50000.00"
    assert av.modelCode == "MODEL_A"


def test_account_update_multi_end_proto_settles_reqId():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    assert not req.future.done()

    proto = AccountUpdateMultiEnd_pb2.AccountUpdateMultiEnd(reqId=7)
    ib.client.decoder.processProtoBuf(74, proto.SerializeToString())

    assert req.future.done()


# ===========================================================================
# SEND SIDE — useProtoBuf gating per canonical msgId at gate 207
# ===========================================================================


# ---------- reqAccountUpdates → REQ_ACCT_DATA ---------------------------


def test_req_account_updates_uses_binary_below_gate():
    ib = _ibAtVersion(206)
    sent = _captureSend(ib)
    ib.client.reqAccountUpdates(True, "DU1")
    assert sent[0][4:].startswith(b"\x00\x00\x00\x06")  # REQ_ACCT_DATA=6, raw int (server>=201)


def test_req_account_updates_uses_protobuf_at_gate():
    ib = _ibAtVersion(207)
    sent = _captureSend(ib)
    ib.client.reqAccountUpdates(True, "DU1")
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_ACCT_DATA
    proto = AccountDataRequest_pb2.AccountDataRequest()
    proto.ParseFromString(body)
    assert proto.subscribe is True
    assert proto.acctCode == "DU1"


# ---------- reqManagedAccts → REQ_MANAGED_ACCTS -------------------------


def test_req_managed_accts_uses_protobuf_at_gate():
    ib = _ibAtVersion(207)
    sent = _captureSend(ib)
    ib.client.reqManagedAccts()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_MANAGED_ACCTS
    assert body == b""


# ---------- reqPositions / cancelPositions ------------------------------


def test_req_positions_uses_protobuf_at_gate():
    ib = _ibAtVersion(207)
    sent = _captureSend(ib)
    ib.client.reqPositions()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_POSITIONS
    assert body == b""


def test_cancel_positions_uses_protobuf_at_gate():
    ib = _ibAtVersion(207)
    sent = _captureSend(ib)
    ib.client.cancelPositions()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_POSITIONS
    assert body == b""


def test_req_positions_uses_binary_below_gate():
    ib = _ibAtVersion(206)
    sent = _captureSend(ib)
    ib.client.reqPositions()
    assert sent[0][4:].startswith(b"\x00\x00\x00\x3d")  # REQ_POSITIONS=61, raw int (server>=201)


# ---------- reqAccountSummary / cancelAccountSummary --------------------


def test_req_account_summary_uses_protobuf_at_gate_and_round_trips_fields():
    ib = _ibAtVersion(207)
    sent = _captureSend(ib)
    ib.client.reqAccountSummary(7, "All", "NetLiquidation,TotalCashValue")
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_ACCOUNT_SUMMARY
    proto = AccountSummaryRequest_pb2.AccountSummaryRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.group == "All"
    assert proto.tags == "NetLiquidation,TotalCashValue"


def test_cancel_account_summary_uses_protobuf_at_gate():
    ib = _ibAtVersion(207)
    sent = _captureSend(ib)
    ib.client.cancelAccountSummary(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_ACCOUNT_SUMMARY
    proto = CancelAccountSummary_pb2.CancelAccountSummary()
    proto.ParseFromString(body)
    assert proto.reqId == 7


# ---------- reqPositionsMulti / cancelPositionsMulti --------------------


def test_req_positions_multi_uses_protobuf_at_gate_and_round_trips_fields():
    ib = _ibAtVersion(207)
    sent = _captureSend(ib)
    ib.client.reqPositionsMulti(7, "DU1", "MODEL_A")
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_POSITIONS_MULTI
    proto = PositionsMultiRequest_pb2.PositionsMultiRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.account == "DU1"
    assert proto.modelCode == "MODEL_A"


def test_cancel_positions_multi_uses_protobuf_at_gate():
    ib = _ibAtVersion(207)
    sent = _captureSend(ib)
    ib.client.cancelPositionsMulti(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_POSITIONS_MULTI
    proto = CancelPositionsMulti_pb2.CancelPositionsMulti()
    proto.ParseFromString(body)
    assert proto.reqId == 7


# ---------- reqAccountUpdatesMulti / cancelAccountUpdatesMulti ----------


def test_req_account_updates_multi_round_trips_bool_flag():
    """proto3 default bool is False — caller passing True must come
    through after SerializeToString round-trip."""
    ib = _ibAtVersion(207)
    sent = _captureSend(ib)
    ib.client.reqAccountUpdatesMulti(7, "DU1", "MODEL_A", True)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_ACCOUNT_UPDATES_MULTI
    proto = AccountUpdatesMultiRequest_pb2.AccountUpdatesMultiRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.account == "DU1"
    assert proto.modelCode == "MODEL_A"
    assert proto.ledgerAndNLV is True


def test_cancel_account_updates_multi_uses_protobuf_at_gate():
    ib = _ibAtVersion(207)
    sent = _captureSend(ib)
    ib.client.cancelAccountUpdatesMulti(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_ACCOUNT_UPDATES_MULTI
    proto = CancelAccountUpdatesMulti_pb2.CancelAccountUpdatesMulti()
    proto.ParseFromString(body)
    assert proto.reqId == 7
