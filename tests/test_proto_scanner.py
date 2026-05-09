"""Negative-path-first tests for the scanner / fundamentals / PnL converter.

Coverage strategy:

* Empty / partial protos must produce safe-default args without
  crashing — exercises ``HasField`` discipline.
* ``PnLSingle.position`` is wire ``string`` but the wrapper takes
  ``pos: int``: garbage / fractional / nan / empty inputs must
  coerce to ``0`` instead of raising.
* ``ScannerData`` with no repeated elements must yield an empty list
  — the decoder relies on iteration semantics.
* The full ~21-field ``ScannerSubscription`` must round-trip through
  ``SerializeToString`` — proto3 boolean defaults silently swallow
  ``True`` if the encoder forgets to set them, so
  ``excludeConvertible=True`` is exercised explicitly.
* Wire-level field-name mismatches (``comboKey`` → ``legsStr``) must
  resolve.
"""

from __future__ import annotations

import pytest

from ib_async._pb import (
    CancelFundamentalsData_pb2,
    CancelPnL_pb2,
    CancelPnLSingle_pb2,
    CancelScannerSubscription_pb2,
    FundamentalsData_pb2,
    FundamentalsDataRequest_pb2,
    PnL_pb2,
    PnLRequest_pb2,
    PnLSingle_pb2,
    PnLSingleRequest_pb2,
    ScannerData_pb2,
    ScannerDataElement_pb2,
    ScannerParameters_pb2,
    ScannerSubscription_pb2,
    ScannerSubscriptionRequest_pb2,
)
from ib_async._proto.scanner import (
    createCancelFundamentalsDataProto,
    createCancelPnLProto,
    createCancelPnLSingleProto,
    createCancelScannerSubscriptionProto,
    createFundamentalDataArgs,
    createFundamentalsDataRequestProto,
    createPnLArgs,
    createPnLRequestProto,
    createPnLSingleArgs,
    createPnLSingleRequestProto,
    createScannerDataElementArgs,
    createScannerParametersRequestProto,
    createScannerParametersXml,
    createScannerSubscriptionProto,
    createScannerSubscriptionRequestProto,
    iterScannerData,
)
from ib_async.contract import Contract
from ib_async.objects import ScannerSubscription
from ib_async.util import UNSET_DOUBLE, UNSET_INTEGER

# ---------------------------------------------------------------------------
# ScannerData / element decode
# ---------------------------------------------------------------------------


def test_scanner_data_empty_proto_yields_zero_reqId_and_empty_elements():
    args = iterScannerData(ScannerData_pb2.ScannerData())
    assert args.reqId == 0
    assert args.elements == []


def test_scanner_data_with_zero_elements_returns_empty_list():
    """reqId set, no repeated elements — the decoder will only emit
    ``scannerDataEnd`` and we must not synthesise a ghost element."""
    proto = ScannerData_pb2.ScannerData(reqId=42)
    args = iterScannerData(proto)
    assert args.reqId == 42
    assert args.elements == []


def test_scanner_data_element_empty_yields_safe_defaults():
    """Bare element with no fields set must produce empty strings, rank=0,
    and a ContractDetails wrapping an empty Contract."""
    args = createScannerDataElementArgs(7, ScannerDataElement_pb2.ScannerDataElement())
    assert args.reqId == 7
    assert args.rank == 0
    assert args.distance == ""
    assert args.benchmark == ""
    assert args.projection == ""
    assert args.legsStr == ""
    assert args.contractDetails.marketName == ""
    assert args.contractDetails.contract is not None
    assert args.contractDetails.contract.symbol == ""


def test_scanner_data_element_wire_comboKey_maps_to_legsStr():
    """The wire field is named ``comboKey``; the wrapper signature
    calls it ``legsStr``. Mapping is mandatory or every combo scan
    drops its leg description on the floor."""
    proto = ScannerDataElement_pb2.ScannerDataElement(comboKey="leg-a/leg-b")
    args = createScannerDataElementArgs(7, proto)
    assert args.legsStr == "leg-a/leg-b"


def test_scanner_data_element_wire_marketName_lands_on_contractDetails():
    """``marketName`` lives on ``ContractDetails``, not on ``Contract``.
    Routing it onto ``contractDetails.marketName`` is what makes the
    wrapper's ScanData carry the value."""
    proto = ScannerDataElement_pb2.ScannerDataElement(marketName="NASDAQ.NMS")
    args = createScannerDataElementArgs(7, proto)
    assert args.contractDetails.marketName == "NASDAQ.NMS"


def test_scanner_data_full_round_trip_with_one_element():
    proto = ScannerData_pb2.ScannerData(reqId=42)
    el = proto.scannerDataElement.add()
    el.rank = 3
    el.distance = "0.5"
    el.benchmark = "SPX"
    el.projection = "future"
    el.comboKey = ""
    el.marketName = "NYSE"
    el.contract.symbol = "AAPL"
    el.contract.secType = "STK"

    args = iterScannerData(proto)
    assert args.reqId == 42
    assert len(args.elements) == 1
    only = args.elements[0]
    assert only.reqId == 42
    assert only.rank == 3
    assert only.distance == "0.5"
    assert only.benchmark == "SPX"
    assert only.projection == "future"
    assert only.legsStr == ""
    assert only.contractDetails.marketName == "NYSE"
    assert only.contractDetails.contract is not None
    assert only.contractDetails.contract.symbol == "AAPL"
    assert only.contractDetails.contract.secType == "STK"


def test_scanner_data_multiple_elements_decode_independently():
    proto = ScannerData_pb2.ScannerData(reqId=11)
    a = proto.scannerDataElement.add()
    a.rank = 0
    a.contract.symbol = "AAPL"
    b = proto.scannerDataElement.add()
    b.rank = 1
    b.contract.symbol = "MSFT"
    args = iterScannerData(proto)
    assert [
        e.contractDetails.contract.symbol
        for e in args.elements
        if e.contractDetails.contract is not None
    ] == ["AAPL", "MSFT"]
    assert [e.rank for e in args.elements] == [0, 1]


# ---------------------------------------------------------------------------
# ScannerParameters
# ---------------------------------------------------------------------------


def test_scanner_parameters_empty_proto_returns_empty_string():
    assert createScannerParametersXml(ScannerParameters_pb2.ScannerParameters()) == ""


def test_scanner_parameters_xml_round_trip():
    proto = ScannerParameters_pb2.ScannerParameters(xml="<ScanParameterResponse/>")
    assert createScannerParametersXml(proto) == "<ScanParameterResponse/>"


def test_scanner_parameters_request_proto_serializes_empty():
    assert createScannerParametersRequestProto().SerializeToString() == b""


# ---------------------------------------------------------------------------
# FundamentalsData
# ---------------------------------------------------------------------------


def test_fundamental_data_empty_proto():
    args = createFundamentalDataArgs(FundamentalsData_pb2.FundamentalsData())
    assert args.reqId == 0
    assert args.data == ""


def test_fundamental_data_full_round_trip():
    proto = FundamentalsData_pb2.FundamentalsData(reqId=7, data="<xml/>")
    args = createFundamentalDataArgs(proto)
    assert args.reqId == 7
    assert args.data == "<xml/>"


def test_fundamentals_data_request_proto_carries_every_field():
    contract = Contract(symbol="IBM", secType="STK", exchange="SMART", currency="USD")
    proto = createFundamentalsDataRequestProto(7, contract, "ReportsFinSummary")
    decoded = FundamentalsDataRequest_pb2.FundamentalsDataRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.reportType == "ReportsFinSummary"
    assert decoded.contract.symbol == "IBM"
    assert decoded.contract.secType == "STK"
    assert decoded.contract.exchange == "SMART"
    assert decoded.contract.currency == "USD"


def test_cancel_fundamentals_data_carries_reqId():
    proto = createCancelFundamentalsDataProto(7)
    decoded = CancelFundamentalsData_pb2.CancelFundamentalsData()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


# ---------------------------------------------------------------------------
# PnL (msgId 94)
# ---------------------------------------------------------------------------


def test_pnl_empty_proto_yields_zero_floats():
    args = createPnLArgs(PnL_pb2.PnL())
    assert args.reqId == 0
    assert args.dailyPnL == 0.0
    assert args.unrealizedPnL == 0.0
    assert args.realizedPnL == 0.0


def test_pnl_full_round_trip():
    proto = PnL_pb2.PnL(reqId=42, dailyPnL=100.5, unrealizedPnL=-25.0, realizedPnL=15.0)
    args = createPnLArgs(proto)
    assert args.reqId == 42
    assert args.dailyPnL == 100.5
    assert args.unrealizedPnL == -25.0
    assert args.realizedPnL == 15.0


def test_pnl_negative_values_round_trip():
    """Defensive — losses are negative; ensure no truthiness traps drop them."""
    proto = PnL_pb2.PnL(reqId=42, dailyPnL=-1.0, unrealizedPnL=-2.0, realizedPnL=-3.0)
    args = createPnLArgs(proto)
    assert args.dailyPnL == -1.0
    assert args.unrealizedPnL == -2.0
    assert args.realizedPnL == -3.0


def test_pnl_request_proto_carries_every_field():
    proto = createPnLRequestProto(7, "DU1", "MODEL_A")
    decoded = PnLRequest_pb2.PnLRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.account == "DU1"
    assert decoded.modelCode == "MODEL_A"


def test_cancel_pnl_carries_reqId():
    proto = createCancelPnLProto(7)
    decoded = CancelPnL_pb2.CancelPnL()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


# ---------------------------------------------------------------------------
# PnLSingle (msgId 95) — Decimal-precision string position coerced to int
# ---------------------------------------------------------------------------


def test_pnl_single_empty_proto_yields_zero_position():
    args = createPnLSingleArgs(PnLSingle_pb2.PnLSingle())
    assert args.reqId == 0
    assert args.pos == 0
    assert args.dailyPnL == 0.0
    assert args.unrealizedPnL == 0.0
    assert args.realizedPnL == 0.0
    assert args.value == 0.0


def test_pnl_single_garbage_position_string_coerces_to_zero():
    """Wire ``position`` is string; if upstream sends garbage we must
    not raise — wrapper expects ``int``, so we collapse to 0."""
    proto = PnLSingle_pb2.PnLSingle(reqId=42, position="not-a-number")
    args = createPnLSingleArgs(proto)
    assert args.pos == 0


def test_pnl_single_empty_position_string_coerces_to_zero():
    proto = PnLSingle_pb2.PnLSingle(reqId=42, position="")
    args = createPnLSingleArgs(proto)
    assert args.pos == 0


def test_pnl_single_nan_position_coerces_to_zero():
    proto = PnLSingle_pb2.PnLSingle(reqId=42, position="nan")
    args = createPnLSingleArgs(proto)
    assert args.pos == 0


def test_pnl_single_fractional_position_truncates():
    """The wrapper's ``pos: int`` typing means fractional positions
    are not representable. Truncation (not rounding) is the
    documented coercion."""
    proto = PnLSingle_pb2.PnLSingle(reqId=42, position="100.7")
    args = createPnLSingleArgs(proto)
    assert args.pos == 100


def test_pnl_single_negative_position_round_trips():
    proto = PnLSingle_pb2.PnLSingle(reqId=42, position="-50")
    args = createPnLSingleArgs(proto)
    assert args.pos == -50


def test_pnl_single_full_round_trip():
    proto = PnLSingle_pb2.PnLSingle(
        reqId=42,
        position="100",
        dailyPnL=10.5,
        unrealizedPnL=-2.5,
        realizedPnL=1.0,
        value=10000.0,
    )
    args = createPnLSingleArgs(proto)
    assert args.reqId == 42
    assert args.pos == 100
    assert args.dailyPnL == 10.5
    assert args.unrealizedPnL == -2.5
    assert args.realizedPnL == 1.0
    assert args.value == 10000.0


def test_pnl_single_request_proto_carries_every_field():
    proto = createPnLSingleRequestProto(7, "DU1", "MODEL_A", 12345)
    decoded = PnLSingleRequest_pb2.PnLSingleRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.account == "DU1"
    assert decoded.modelCode == "MODEL_A"
    assert decoded.conId == 12345


def test_cancel_pnl_single_carries_reqId():
    proto = createCancelPnLSingleProto(7)
    decoded = CancelPnLSingle_pb2.CancelPnLSingle()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


# ---------------------------------------------------------------------------
# ScannerSubscription send-side — every domain field must wire through
# ---------------------------------------------------------------------------


def test_scanner_subscription_proto_default_subscription_round_trips():
    """Default ScannerSubscription uses sentinel UNSET values; verify
    the proto carries them (as proto3 ints/floats they're not ``HasField``-
    tracked, but the round-trip value is preserved)."""
    sub = ScannerSubscription()
    proto = createScannerSubscriptionProto(sub)
    decoded = ScannerSubscription_pb2.ScannerSubscription()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.numberOfRows == -1
    # excludeConvertible defaults False, which is the proto3 zero, so
    # round-trips by absence — we check for False not raise.
    assert decoded.excludeConvertible is False


def test_scanner_subscription_proto_carries_every_string_field():
    sub = ScannerSubscription(
        instrument="STK",
        locationCode="STK.US.MAJOR",
        scanCode="TOP_PERC_GAIN",
        moodyRatingAbove="A",
        moodyRatingBelow="C",
        spRatingAbove="AA",
        spRatingBelow="BB",
        maturityDateAbove="20300101",
        maturityDateBelow="20990101",
        scannerSettingPairs="Annual,true",
        stockTypeFilter="ALL",
    )
    proto = createScannerSubscriptionProto(sub)
    decoded = ScannerSubscription_pb2.ScannerSubscription()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.instrument == "STK"
    assert decoded.locationCode == "STK.US.MAJOR"
    assert decoded.scanCode == "TOP_PERC_GAIN"
    assert decoded.moodyRatingAbove == "A"
    assert decoded.moodyRatingBelow == "C"
    assert decoded.spRatingAbove == "AA"
    assert decoded.spRatingBelow == "BB"
    assert decoded.maturityDateAbove == "20300101"
    assert decoded.maturityDateBelow == "20990101"
    assert decoded.scannerSettingPairs == "Annual,true"
    assert decoded.stockTypeFilter == "ALL"


def test_scanner_subscription_proto_carries_excludeConvertible_true():
    """proto3 silently drops ``False`` bools as zero-value defaults; if
    we forgot to set the True case it would round-trip as False and
    every convertible-excluding scan would silently include them.
    This is the explicit guard."""
    sub = ScannerSubscription(excludeConvertible=True)
    proto = createScannerSubscriptionProto(sub)
    decoded = ScannerSubscription_pb2.ScannerSubscription()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.excludeConvertible is True


def test_scanner_subscription_proto_carries_numeric_filters():
    sub = ScannerSubscription(
        numberOfRows=20,
        abovePrice=10.0,
        belowPrice=200.0,
        aboveVolume=10000,
        marketCapAbove=1_000_000.0,
        marketCapBelow=1_000_000_000.0,
        couponRateAbove=2.5,
        couponRateBelow=10.0,
        averageOptionVolumeAbove=100,
    )
    proto = createScannerSubscriptionProto(sub)
    decoded = ScannerSubscription_pb2.ScannerSubscription()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.numberOfRows == 20
    assert decoded.abovePrice == 10.0
    assert decoded.belowPrice == 200.0
    assert decoded.aboveVolume == 10000
    assert decoded.marketCapAbove == 1_000_000.0
    assert decoded.marketCapBelow == 1_000_000_000.0
    assert decoded.couponRateAbove == 2.5
    assert decoded.couponRateBelow == 10.0
    assert decoded.averageOptionVolumeAbove == 100


def test_scanner_subscription_request_envelope_carries_reqId_and_nested_sub():
    sub = ScannerSubscription(
        instrument="STK", locationCode="STK.US", scanCode="TOP_PERC_GAIN"
    )
    proto = createScannerSubscriptionRequestProto(7, sub)
    decoded = ScannerSubscriptionRequest_pb2.ScannerSubscriptionRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7
    assert decoded.scannerSubscription.instrument == "STK"
    assert decoded.scannerSubscription.locationCode == "STK.US"
    assert decoded.scannerSubscription.scanCode == "TOP_PERC_GAIN"


def test_scanner_subscription_request_default_sub_round_trips_sentinels():
    """Defensive — the UNSET sentinel ints/floats from objects.py must
    survive proto round-trip without truncation. They're large but
    fit ``int32`` / ``double`` ranges."""
    sub = ScannerSubscription()
    proto = createScannerSubscriptionRequestProto(1, sub)
    decoded = ScannerSubscriptionRequest_pb2.ScannerSubscriptionRequest()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 1
    # The proto declares numberOfRows int32; UNSET_INTEGER = 2**31-1 fits.
    assert decoded.scannerSubscription.aboveVolume == UNSET_INTEGER
    assert decoded.scannerSubscription.abovePrice == UNSET_DOUBLE


def test_cancel_scanner_subscription_carries_reqId():
    proto = createCancelScannerSubscriptionProto(7)
    decoded = CancelScannerSubscription_pb2.CancelScannerSubscription()
    decoded.ParseFromString(proto.SerializeToString())
    assert decoded.reqId == 7


# ---------------------------------------------------------------------------
# Cross-cutting: empty-body request envelopes serialize to empty bytes
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "factory",
    [createScannerParametersRequestProto],
)
def test_empty_body_request_envelopes_serialize_to_empty_bytes(factory):
    """The framing layer wraps the serialized bytes in the +200 envelope.
    Empty body must be truly empty so the wire is just the 4-byte
    msgId with no trailing payload."""
    assert factory().SerializeToString() == b""
