"""Regression locks for the P6 audit fixes and dispatch robustness.

These tests guard the corner-case behaviour that the final audit pass
fixed and that future refactors could silently break:

* ``Wrapper.commissionReport`` must NOT substitute ``defaults.unset``
  (a ``float('nan')``) for the ``Decimal | None`` fields. Doing so
  would (a) violate the field type and (b) reintroduce the
  ``Decimal('NaN')`` truthy-trap (``if report.realizedPNL:`` is True
  on NaN but False on None).

* ``Decoder._normalizeExecutionTime`` is shared between the binary
  ``execDetails`` decoder and the protobuf ``_protoExecutionDetails``
  handler. Both paths must produce equivalent tz-aware datetimes for
  the same wire string so executions round-trip identically across
  wire formats.

* ``Decoder.processProtoBuf`` must survive an unknown msgId, malformed
  bytes, and an empty discriminated-union (oneof) payload — none of
  these may raise out of the decoder. A single bad wire frame must
  not kill the long-running connection.
"""

from __future__ import annotations

import logging
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import ib_async as ibi
from ib_async._pb import (
    CommissionAndFeesReport_pb2,
    ConfigResponse_pb2,
    Contract_pb2,
    ContractData_pb2,
    DisplayGroupList_pb2,
    DisplayGroupUpdated_pb2,
    ExecutionDetails_pb2,
    OpenOrder_pb2,
    TickByTickData_pb2,
    UpdateConfigResponse_pb2,
    VerifyCompleted_pb2,
    VerifyMessageApi_pb2,
)
from ib_async._proto.contracts import (
    createContract,
    createContractDetailsFromContractData,
)

# ---------------------------------------------------------------------------
# CommissionReport: None must survive the dispatch path without becoming NaN
# ---------------------------------------------------------------------------


def test_commission_report_unset_realized_pnl_stays_none_not_nan():
    """Wire CommissionAndFeesReport without ``realizedPNL`` and ``bondYield``
    must land on the fill with those fields still ``None`` — never ``NaN``.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0

    fill = ibi.Fill(
        contract=ibi.Stock("AAPL"),
        execution=ibi.Execution(execId="exec-nan-guard", permId=1),
        commissionReport=ibi.CommissionReport(),
        time=ibi.util.EPOCH,
    )
    ib.wrapper.fills["exec-nan-guard"] = fill

    proto = CommissionAndFeesReport_pb2.CommissionAndFeesReport()
    proto.execId = "exec-nan-guard"
    proto.commissionAndFees = 1.25
    proto.currency = "USD"
    # realizedPNL and bondYield deliberately not set.
    ib.client.decoder.processProtoBuf(59, proto.SerializeToString())

    # commission did flow.
    assert fill.commissionReport.commission == Decimal("1.25")
    # realizedPNL / yield_ stay None — NOT Decimal('NaN'), NOT 0.
    assert fill.commissionReport.realizedPNL is None
    assert fill.commissionReport.yield_ is None


def test_commission_report_none_is_falsy_no_nan_truthy_trap():
    """Direct guard against the ``Decimal('NaN')`` truthy trap.

    With ``Decimal | None`` fields and ``None`` as the unset sentinel,
    ``if report.realizedPNL:`` must evaluate False when unset. If a
    refactor reintroduces ``Decimal('NaN')`` as the sentinel, this
    flips to True and user code that gates on these fields breaks.
    """
    report = ibi.CommissionReport()
    assert report.realizedPNL is None
    assert report.yield_ is None
    assert not report.realizedPNL  # falsy on None
    assert not report.yield_  # falsy on None


def test_commission_report_explicit_none_survives_wrapper_dispatch():
    """``Wrapper.commissionReport`` must NOT substitute ``defaults.unset``
    (a NaN) when the wire report's Decimal-typed fields are ``None``.

    This is the direct regression lock: prior to the P6 fix,
    ``dataclassNonDefaults`` + ``defaults.unset`` could re-introduce
    ``Decimal('NaN')`` for the unset fields. We feed an explicit
    None-valued wire report and assert nothing morphs to NaN.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0

    fill = ibi.Fill(
        contract=ibi.Stock("AAPL"),
        execution=ibi.Execution(execId="exec-explicit-none", permId=1),
        commissionReport=ibi.CommissionReport(),
        time=ibi.util.EPOCH,
    )
    ib.wrapper.fills["exec-explicit-none"] = fill

    explicit = ibi.CommissionReport(
        execId="exec-explicit-none",
        commission=Decimal("0.50"),
        currency="USD",
        realizedPNL=None,
        yield_=None,
    )
    ib.wrapper.commissionReport(explicit)

    assert fill.commissionReport.commission == Decimal("0.50")
    assert fill.commissionReport.realizedPNL is None
    assert fill.commissionReport.yield_ is None
    # Direct NaN guard: nothing morphed silently into a NaN sentinel.
    assert not (fill.commissionReport.realizedPNL or False)
    assert not (fill.commissionReport.yield_ or False)


# ---------------------------------------------------------------------------
# _normalizeExecutionTime: binary and proto paths must agree
# ---------------------------------------------------------------------------


def test_normalize_execution_time_returns_tz_aware_datetime():
    """The helper must always return a tz-aware datetime in the
    wrapper's default timezone, regardless of input format.
    """
    ib = ibi.IB()
    ib.TimezoneTWS = "US/Eastern"

    result = ib.client.decoder._normalizeExecutionTime("20260509  09:30:00")
    assert isinstance(result, datetime)
    assert result.tzinfo is not None
    # Default timezone is the wrapper's; the value carries it.
    assert result.tzinfo == ib.wrapper.defaultTimezone


def test_normalize_execution_time_explicit_tz_in_string():
    """Wire form ``YYYYmmdd HH:MM:SS US/Eastern`` carries the tz inline;
    the helper preserves it as the source-of-truth then converts.
    """
    ib = ibi.IB()

    result = ib.client.decoder._normalizeExecutionTime("20260509 09:30:00 US/Eastern")
    assert isinstance(result, datetime)
    assert result.tzinfo is not None
    # Sanity: the moment-in-time must equal 13:30 UTC for 09:30 US/Eastern in May.
    utc = result.astimezone(ZoneInfo("UTC"))
    assert utc.hour == 13
    assert utc.minute == 30


def test_normalize_execution_time_date_only_combines_with_midnight():
    """An 8-char ``YYYYmmdd`` wire string lacks time-of-day. The
    helper combines with midnight rather than raising.
    """
    ib = ibi.IB()
    ib.TimezoneTWS = "US/Eastern"

    result = ib.client.decoder._normalizeExecutionTime("20260509")
    assert isinstance(result, datetime)
    assert result.tzinfo is not None


def test_normalize_execution_time_binary_proto_equivalence():
    """The binary execDetails path and the protobuf
    ``_protoExecutionDetails`` path must land *equivalent* ex.time
    values for the same wire string. They share the helper, so a
    refactor that changes one path must touch the other.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    ib.TimezoneTWS = "US/Eastern"

    wire_time = "20260509  09:30:00"

    # --- proto path ----------------------------------------------------
    open_proto = OpenOrder_pb2.OpenOrder()
    open_proto.orderId = 5
    open_proto.contract.symbol = "AAPL"
    open_proto.contract.secType = "STK"
    open_proto.order.orderId = 5
    open_proto.order.clientId = 0
    open_proto.order.permId = 999
    open_proto.order.action = "BUY"
    open_proto.order.totalQuantity = "100"
    open_proto.orderState.status = "Submitted"
    ib.client.decoder.processProtoBuf(5, open_proto.SerializeToString())

    exec_proto = ExecutionDetails_pb2.ExecutionDetails()
    exec_proto.reqId = -1
    exec_proto.contract.symbol = "AAPL"
    exec_proto.contract.secType = "STK"
    exec_proto.execution.execId = "exec-equiv"
    exec_proto.execution.orderId = 5
    exec_proto.execution.clientId = 0
    exec_proto.execution.permId = 999
    exec_proto.execution.shares = "100"
    exec_proto.execution.price = 50.5
    exec_proto.execution.cumQty = "100"
    exec_proto.execution.avgPrice = 50.5
    exec_proto.execution.side = "BOT"
    exec_proto.execution.time = wire_time
    ib.client.decoder.processProtoBuf(11, exec_proto.SerializeToString())

    proto_fill = ib.wrapper.fills["exec-equiv"]
    proto_time = proto_fill.execution.time

    # --- direct helper call (the same code the binary path reaches) ----
    direct_time = ib.client.decoder._normalizeExecutionTime(wire_time)

    # Same instant, same tz — the proto path must not have drifted.
    assert proto_time == direct_time
    assert proto_time.tzinfo == direct_time.tzinfo


# ---------------------------------------------------------------------------
# Dispatch robustness: unknown msgId, malformed bytes, empty oneof
# ---------------------------------------------------------------------------


def test_process_proto_buf_unknown_msg_id_dropped_silently():
    """An unknown canonical msgId must be logged at debug and dropped —
    NOT raised. The connection must survive a future protobuf message
    family the client doesn't yet handle.
    """
    ib = ibi.IB()
    # 999 is well outside the IBKR canonical IN msgId space.
    # No registry exists, no exception, no side effect.
    ib.client.decoder.processProtoBuf(999, b"\x00\x01\x02")


def test_process_proto_buf_unknown_msg_id_emits_debug_log(caplog):
    """The drop is observable: a debug log entry names the unknown
    msgId and payload size so an operator can diagnose protocol drift.
    """
    ib = ibi.IB()
    with caplog.at_level(logging.DEBUG, logger="ib_async.Decoder"):
        ib.client.decoder.processProtoBuf(999, b"abc")
    assert any("999" in rec.message for rec in caplog.records)


def test_process_proto_buf_malformed_bytes_does_not_raise():
    """A registered handler that hits ``ParseFromString`` failure
    must not propagate the exception. The protobuf parser raises
    on garbage input; we catch and log so a single bad frame can't
    take down the long-running connection.
    """
    ib = ibi.IB()
    # canonical msgId 5 = OPEN_ORDER, registered handler. Garbage payload.
    ib.client.decoder.processProtoBuf(5, b"\xff\xff\xff\xff\xff\xff\xff\xff")


def test_process_proto_buf_malformed_bytes_logs_exception(caplog):
    """The exception path is observable: the exception trace is
    logged at error level naming the offending msgId.
    """
    ib = ibi.IB()
    with caplog.at_level(logging.ERROR, logger="ib_async.Decoder"):
        ib.client.decoder.processProtoBuf(5, b"\xff\xff\xff\xff\xff\xff\xff\xff")
    assert any("5" in rec.message for rec in caplog.records)


def test_proto_tick_by_tick_empty_oneof_is_dropped():
    """``TickByTickData`` with no oneof variant set decodes via the
    discriminated-union dispatch — the dispatcher returns ``None``
    and the handler must drop silently. No wrapper method is called.
    Mirrors the binary path's ``tickType=0`` no-op branch.
    """
    ib = ibi.IB()
    seen: list[tuple] = []

    # Spy on every tickByTick* wrapper method to catch a stray dispatch.
    ib.wrapper.tickByTickAllLast = lambda *a, **kw: seen.append(("allLast", a))
    ib.wrapper.tickByTickBidAsk = lambda *a, **kw: seen.append(("bidAsk", a))
    ib.wrapper.tickByTickMidPoint = lambda *a, **kw: seen.append(("midPoint", a))

    proto = TickByTickData_pb2.TickByTickData()
    proto.reqId = 7
    proto.tickType = 0
    # No historicalTickLast / historicalTickBidAsk / historicalTickMidPoint set.
    ib.client.decoder.processProtoBuf(99, proto.SerializeToString())

    assert seen == []


# ---------------------------------------------------------------------------
# Contract / ContractDetails: parity with IBKR ground truth
# ---------------------------------------------------------------------------


def test_create_contract_reads_last_trade_date():
    """IBKR's reference reads ``contractProto.lastTradeDate`` separately
    from ``lastTradeDateOrContractMonth``. Our converter must too —
    silently dropping the field would lose post-2024 IBKR contracts'
    actual expiry date.
    """
    proto = Contract_pb2.Contract()
    proto.symbol = "ESM6"
    proto.secType = "FUT"
    proto.lastTradeDateOrContractMonth = "20260619"
    proto.lastTradeDate = "20260619-15:00:00"

    contract = createContract(proto)
    assert contract.lastTradeDateOrContractMonth == "20260619"
    assert contract.lastTradeDate == "20260619-15:00:00"


def test_contract_details_splits_last_trade_date_for_non_bond():
    """ContractDetails wire packs date+time as a single string in
    ``contract.lastTradeDateOrContractMonth``. The binary path
    splits into separate ``lastTradeTime`` (and bond ``maturity``,
    ``timeZoneId``) fields. The proto path must do the same split.
    """
    proto = ContractData_pb2.ContractData()
    proto.contract.symbol = "ESM6"
    proto.contract.secType = "FUT"
    # Hyphen-separated form: date-time
    proto.contract.lastTradeDateOrContractMonth = "20260619-15:00:00"
    proto.contractDetails.marketName = "ES"

    details = createContractDetailsFromContractData(proto)
    assert details.contract.lastTradeDateOrContractMonth == "20260619"
    assert details.lastTradeTime == "15:00:00"
    # Non-bond: maturity and timeZoneId stay empty.
    assert details.maturity == ""
    assert details.timeZoneId == ""


def test_contract_details_splits_last_trade_date_for_bond():
    """For ``secType == 'BOND'``, the wire string carries
    ``maturity time tz``. The split populates bond ``maturity`` and
    bond ``timeZoneId`` rather than overwriting
    ``lastTradeDateOrContractMonth``.
    """
    proto = ContractData_pb2.ContractData()
    proto.contract.symbol = "TBOND"
    proto.contract.secType = "BOND"
    proto.contract.lastTradeDateOrContractMonth = "20300515 16:00:00 US/Eastern"
    # Ensure the contractDetails sub-message is present on the wire so
    # the populated path runs (where the post-process split lives).
    proto.contractDetails.marketName = "BOND"

    details = createContractDetailsFromContractData(proto)
    assert details.maturity == "20300515"
    assert details.lastTradeTime == "16:00:00"
    assert details.timeZoneId == "US/Eastern"


def test_open_order_missing_contract_drops_silently():
    """OpenOrder wire frame with no ``contract`` field must NOT
    deliver a half-formed openOrder to user code. IBKR's reference
    returns silently in this case (decoder.py:406-418); we now do
    the same. Prior behavior built an empty Contract()/Order() and
    polluted the trade registry.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0

    proto = OpenOrder_pb2.OpenOrder()
    proto.orderId = 999
    # No contract / order / orderState set.
    ib.client.decoder.processProtoBuf(5, proto.SerializeToString())

    # No trade landed in the registry.
    assert (0, 999) not in ib.wrapper.trades


def test_open_order_missing_order_drops_silently():
    """Same gate: missing ``order`` field also drops."""
    ib = ibi.IB()
    ib.wrapper.clientId = 0

    proto = OpenOrder_pb2.OpenOrder()
    proto.orderId = 999
    proto.contract.symbol = "AAPL"
    proto.contract.secType = "STK"
    # No order / orderState.
    ib.client.decoder.processProtoBuf(5, proto.SerializeToString())

    assert (0, 999) not in ib.wrapper.trades


def test_contract_details_split_skipped_when_field_empty():
    """No split when wire ``lastTradeDateOrContractMonth`` is empty —
    domain fields stay at their defaults rather than crashing on a
    missing-field split.
    """
    proto = ContractData_pb2.ContractData()
    proto.contract.symbol = "AAPL"
    proto.contract.secType = "STK"
    # No lastTradeDateOrContractMonth set.
    proto.contractDetails.marketName = "NMS"

    details = createContractDetailsFromContractData(proto)
    assert details.contract.lastTradeDateOrContractMonth == ""
    assert details.lastTradeTime == ""


# ---------------------------------------------------------------------------
# Verify / DisplayGroup / Config handlers — IBKR ground-truth dispatch parity
# ---------------------------------------------------------------------------


def test_verify_message_api_proto_routes_to_wrapper_method():
    """canonical msgId 65 (VERIFY_MESSAGE_API) — IBKR registers a
    protobuf handler; we used to silently drop. Route to
    wrapper.verifyMessageAPI(apiData) when present.
    """
    ib = ibi.IB()
    seen: list[str] = []
    ib.wrapper.verifyMessageAPI = lambda apiData: seen.append(apiData)

    proto = VerifyMessageApi_pb2.VerifyMessageApi()
    proto.apiData = "hello-from-tws"
    ib.client.decoder.processProtoBuf(65, proto.SerializeToString())

    assert seen == ["hello-from-tws"]


def test_verify_message_api_drops_when_method_missing():
    """No wrapper method → silent drop, no exception."""
    ib = ibi.IB()
    proto = VerifyMessageApi_pb2.VerifyMessageApi()
    proto.apiData = "x"
    ib.client.decoder.processProtoBuf(65, proto.SerializeToString())


def test_verify_completed_proto_routes_to_wrapper_method():
    ib = ibi.IB()
    seen: list[tuple[bool, str]] = []
    ib.wrapper.verifyCompleted = lambda ok, err: seen.append((ok, err))

    proto = VerifyCompleted_pb2.VerifyCompleted()
    proto.isSuccessful = True
    proto.errorText = "ok"
    ib.client.decoder.processProtoBuf(66, proto.SerializeToString())

    assert seen == [(True, "ok")]


def test_display_group_list_proto_routes_to_wrapper_method():
    ib = ibi.IB()
    seen: list[tuple[int, str]] = []
    ib.wrapper.displayGroupList = lambda reqId, groups: seen.append((reqId, groups))

    proto = DisplayGroupList_pb2.DisplayGroupList()
    proto.reqId = 7
    proto.groups = "1|2|3"
    ib.client.decoder.processProtoBuf(67, proto.SerializeToString())

    assert seen == [(7, "1|2|3")]


def test_display_group_updated_proto_routes_to_wrapper_method():
    ib = ibi.IB()
    seen: list[tuple[int, str]] = []
    ib.wrapper.displayGroupUpdated = lambda reqId, info: seen.append((reqId, info))

    proto = DisplayGroupUpdated_pb2.DisplayGroupUpdated()
    proto.reqId = 7
    proto.contractInfo = "AAPL@SMART"
    ib.client.decoder.processProtoBuf(68, proto.SerializeToString())

    assert seen == [(7, "AAPL@SMART")]


def test_config_response_proto_routes_to_wrapper_proto_method():
    """ConfigResponse carries nested config sub-messages with no flat
    equivalent. The handler delivers the raw proto to a
    ``configResponseProtoBuf`` wrapper hook, mirroring IBKR's
    reference behaviour.
    """
    ib = ibi.IB()
    seen: list[object] = []
    ib.wrapper.configResponseProtoBuf = lambda p: seen.append(p)

    proto = ConfigResponse_pb2.ConfigResponse()
    proto.reqId = 1
    ib.client.decoder.processProtoBuf(110, proto.SerializeToString())

    assert len(seen) == 1
    assert seen[0].reqId == 1


def test_update_config_response_proto_routes_to_wrapper_proto_method():
    ib = ibi.IB()
    seen: list[object] = []
    ib.wrapper.updateConfigResponseProtoBuf = lambda p: seen.append(p)

    proto = UpdateConfigResponse_pb2.UpdateConfigResponse()
    proto.reqId = 2
    proto.status = "OK"
    ib.client.decoder.processProtoBuf(111, proto.SerializeToString())

    assert len(seen) == 1
    assert seen[0].status == "OK"


# ---------------------------------------------------------------------------
# UNSET sentinel guards (_isValidFloat / _isValidInt)
# ---------------------------------------------------------------------------


def test_is_valid_float_rejects_unset_sentinel():
    """The UNSET_DOUBLE sentinel must NOT pass through into the wire
    encoding; ``createOrderProto`` and friends gate every optional
    double field on ``_isValidFloat`` to skip the sentinel.
    """
    from sys import float_info

    from ib_async._proto.orders import _isValidFloat

    UNSET_DOUBLE = float_info.max
    assert _isValidFloat(UNSET_DOUBLE) is False
    assert _isValidFloat(0.0) is True
    assert _isValidFloat(-0.0) is True
    assert _isValidFloat(1.5) is True
    assert _isValidFloat(-1.5) is True
    # Decimal compares cleanly against the float sentinel.
    assert _isValidFloat(Decimal("0")) is True
    assert _isValidFloat(Decimal("1.5")) is True


def test_is_valid_int_rejects_unset_sentinel():
    """The UNSET_INTEGER sentinel (2**31 - 1) must be skipped by
    ``createOrderProto`` and friends so wire frames don't carry it.
    """
    from ib_async._proto.orders import _isValidInt

    UNSET_INTEGER = 2**31 - 1
    assert _isValidInt(UNSET_INTEGER) is False
    assert _isValidInt(0) is True
    assert _isValidInt(-1) is True
    assert _isValidInt(1) is True
    assert _isValidInt(2**31 - 2) is True  # one less than sentinel
    assert _isValidInt(-(2**31)) is True


def test_req_current_time_in_millis_async_end_to_end():
    """The new v3.0 public method round-trips the proto receive
    handler back to the future the caller awaits. Tests:
    1. Calling the IB method opens a singleton request + sends a
       protobuf REQ_CURRENT_TIME_IN_MILLIS frame.
    2. Receiving a proto CurrentTimeInMillis settles the future
       with the raw millisecond value.
    """
    from ib_async._pb import CurrentTimeInMillis_pb2

    ib = ibi.IB()
    ib.client._serverVersion = 213
    ib.client.connState = ib.client.CONNECTED
    sent: list[bytes] = []
    ib.client.conn = type("X", (), {"sendMsg": lambda self, msg: sent.append(msg)})()

    fut = ib.reqCurrentTimeInMillisAsync()
    assert not fut.done()
    assert sent  # the request frame went out

    # Server replies with CurrentTimeInMillis carrying the timestamp.
    proto = CurrentTimeInMillis_pb2.CurrentTimeInMillis()
    proto.currentTimeInMillis = 1715251800123  # ~2024-05-09T13:30:00.123Z
    ib.client.decoder.processProtoBuf(109, proto.SerializeToString())

    # processProtoBuf settles the future synchronously (the wrapper
    # method calls set_result directly), so it's already done — no
    # event loop spin needed.
    assert fut.done()
    assert fut.result() == 1715251800123


def test_is_valid_float_handles_nan_safely():
    """Float NaN compares != to anything including itself, so the
    sentinel guard returns True for NaN. This is the correct
    behaviour: we want NaN values to be rejected at the
    safe_decimal layer, not at the sentinel guard. Lock the
    contract so a future "fix" doesn't accidentally reverse it.
    """
    from ib_async._proto.orders import _isValidFloat

    nan = float("nan")
    assert _isValidFloat(nan) is True  # NaN != UNSET_DOUBLE (NaN != anything)
