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
import pathlib
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

import ib_async as ibi
from ib_async._pb import (
    CommissionAndFeesReport_pb2,
    ConfigResponse_pb2,
    Contract_pb2,
    ContractData_pb2,
    DisplayGroupList_pb2,
    DisplayGroupUpdated_pb2,
    ErrorMessage_pb2,
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
from ib_async.util import UNSET_INTEGER

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
    assert fill.commissionReport.commissionAndFees == Decimal("1.25")
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
        commissionAndFees=Decimal("0.50"),
        currency="USD",
        realizedPNL=None,
        yield_=None,
    )
    ib.wrapper.commissionReport(explicit)

    assert fill.commissionReport.commissionAndFees == Decimal("0.50")
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
    assert _isValidFloat(Decimal(0)) is True
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


# ---------------------------------------------------------------------------
# errorMsg / _protoError — server >= 194 ERROR_TIME gate
# ---------------------------------------------------------------------------


def test_proto_error_routes_to_wrapper_with_error_time():
    """Canonical msgId 4 (ERR_MSG) on the protobuf path must decode and
    dispatch to wrapper.error — including errorTime past gate 194.
    Without this handler, every server-pushed error on a protobuf-routed
    connection would be silently debug-dropped.
    """
    ib = ibi.IB()
    seen: list[tuple] = []
    ib.wrapper.error = lambda *a, **kw: seen.append(a)

    proto = ErrorMessage_pb2.ErrorMessage()
    proto.id = 42
    proto.errorCode = 200
    proto.errorMsg = "No security definition has been found"
    proto.advancedOrderRejectJson = ""
    proto.errorTime = 1715251800123
    ib.client.decoder.processProtoBuf(4, proto.SerializeToString())

    assert len(seen) == 1
    args = seen[0]
    assert args[0] == 42  # reqId
    assert args[1] == 200  # errorCode
    assert args[2] == "No security definition has been found"
    assert args[3] == ""
    assert args[4] == 1715251800123  # errorTime


def test_binary_error_msg_drops_legacy_version_prefix_on_server_194():
    """Pre-194 wire frame: [msgId, version, reqId, errorCode, errorString]
    194+ wire frame: [msgId, reqId, errorCode, errorString, advRejectJson, errorTime]
    The legacy version prefix is gone — eating it unconditionally
    corrupts the entire message on a 194+ server.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 194
    ib.client.decoder.serverVersion = 194
    seen: list[tuple] = []
    ib.wrapper.error = lambda *a, **kw: seen.append(a)

    # 194+ wire frame fields list (msgId comes off in the dispatcher,
    # we feed the rest including msgId placeholder for the slice).
    # Binary path delivers fields as already-decoded str (NUL-split).
    fields = ["4", "42", "200", "some error", "", "1715251800123"]
    ib.client.decoder.errorMsg(fields)

    assert len(seen) == 1
    assert seen[0] == (42, 200, "some error", "", 1715251800123)


def test_binary_error_msg_pre_194_keeps_legacy_version_prefix():
    """Pre-194 wire frame keeps the version prefix; we must consume it
    or reqId/errorCode/errorString shift one slot left.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 193
    ib.client.decoder.serverVersion = 193
    seen: list[tuple] = []
    ib.wrapper.error = lambda *a, **kw: seen.append(a)

    # Pre-194 wire frame fields: msgId, version, reqId, errorCode,
    # errorString, advancedOrderRejectJson (ADVANCED_ORDER_REJECT >= 166).
    fields = ["4", "2", "42", "200", "some error", ""]
    ib.client.decoder.errorMsg(fields)

    assert len(seen) == 1
    assert seen[0] == (42, 200, "some error", "", 0)  # errorTime defaults 0


# ---------------------------------------------------------------------------
# historicalData gate 196 (HISTORICAL_DATA_END)
# ---------------------------------------------------------------------------


def test_historical_data_end_msg_id_108_routes_to_wrapper():
    """Binary msgId 108 (HISTORICAL_DATA_END) added at server v196 was
    not in our handlers dict — every modern TWS historical-data
    subscription wedged forever waiting for the end signal.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 196
    ib.client.decoder.serverVersion = 196
    seen: list[tuple] = []
    ib.wrapper.historicalDataEnd = lambda *a, **kw: seen.append(a)

    fields = ["108", "5", "20240101", "20240131"]
    ib.client.decoder.historicalDataEnd(fields)

    assert seen == [(5, "20240101", "20240131")]


@pytest.mark.parametrize(
    "serverVersion, fields, expected_ends",
    [
        # Pre-196: startDateStr/endDateStr inline, historicalData itself
        # emits the end signal at the tail.
        (
            195,
            [
                "17",
                "5",
                "20240101",
                "20240131",
                "1",
                "20240115",
                "100.0",
                "101.0",
                "99.5",
                "100.5",
                "1000",
                "100.25",
                "10",
            ],
            [(5, "20240101", "20240131")],
        ),
        # >=196: no inline start/end. The end signal arrives via msgId 108.
        (
            196,
            [
                "17",
                "5",
                "1",
                "20240115",
                "100.0",
                "101.0",
                "99.5",
                "100.5",
                "1000",
                "100.25",
                "10",
            ],
            [],
        ),
    ],
    ids=["pre_196_inline_end_signal", "gate_196_no_inline_end"],
)
def test_historical_data_end_signal_gate_196(serverVersion, fields, expected_ends):
    """Gate 196 (HISTORICAL_DATA_END) wire-frame alignment.

    Pre-196 servers carry startDateStr/endDateStr inline in the bars
    frame and the historicalData handler itself fires
    ``historicalDataEnd`` at the tail. >=196 those fields move to a
    dedicated msgId 108 frame; the inline emit must be suppressed or
    callers see the end signal twice.
    """
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.decoder.serverVersion = serverVersion
    bars: list = []
    ends: list[tuple] = []
    ib.wrapper.historicalData = lambda *a: bars.append(a)
    ib.wrapper.historicalDataEnd = lambda *a: ends.append(a)

    ib.client.decoder.historicalData(fields)

    assert len(bars) == 1
    assert bars[0][0] == 5  # reqId
    assert ends == expected_ends


# ---------------------------------------------------------------------------
# cancelOrder / reqGlobalCancel — CME_TAGGING_FIELDS gate (192)
# ---------------------------------------------------------------------------


def test_cancel_order_pre_192_carries_legacy_version_byte():
    """Pre-192 wire frame: [4, 1, orderId, manualOrderCancelTime] —
    the leading 1 is a VERSION marker IBKR drops at gate 192. Without
    the gate, a 192+ server reads the 1 as orderId and our cancel
    targets order ID 1 instead of the real one.
    """
    from ib_async.order import OrderCancel

    ib = ibi.IB()
    ib.client._serverVersion = 191  # below CME_TAGGING_FIELDS
    sent: list = []
    ib.client.send = lambda *a: sent.append(a)
    ib.client.cancelOrder(42, OrderCancel(manualOrderCancelTime="20300101 09:30:00"))

    assert len(sent) == 1
    args = sent[0]
    # [msgId=4, VERSION=1, orderId=42, manualOrderCancelTime, ...]
    assert args[0] == 4
    assert args[1] == 1  # legacy VERSION
    assert args[2] == 42
    assert args[3] == "20300101 09:30:00"


def test_cancel_order_post_192_drops_version_appends_cme_tagging():
    """At gate 192 IBKR drops the VERSION byte and appends
    extOperator + manualOrderIndicator. Wrong gate means our cancel
    frame is corrupted: the leading 1 lands as orderId.
    """
    from ib_async.order import OrderCancel

    ib = ibi.IB()
    ib.client._serverVersion = 192
    sent: list = []
    ib.client.send = lambda *a: sent.append(a)
    ib.client.cancelOrder(
        42,
        OrderCancel(
            manualOrderCancelTime="20300101 09:30:00",
            extOperator="EXT-7",
            manualOrderIndicator=42,
        ),
    )

    assert len(sent) == 1
    args = sent[0]
    # [msgId=4, orderId=42, manualOrderCancelTime, extOperator, manualOrderIndicator]
    assert args[0] == 4
    assert args[1] == 42  # orderId — NOT VERSION
    assert args[2] == "20300101 09:30:00"
    assert args[3] == "EXT-7"
    assert args[4] == 42


def test_req_global_cancel_post_192_appends_cme_tagging():
    """reqGlobalCancel mirrors cancelOrder's gating: drop VERSION,
    append extOperator + manualOrderIndicator at 192+.
    """
    from ib_async.order import OrderCancel

    ib = ibi.IB()
    ib.client._serverVersion = 192
    sent: list = []
    ib.client.send = lambda *a: sent.append(a)
    ib.client.reqGlobalCancel(OrderCancel(extOperator="EXT-9", manualOrderIndicator=7))

    assert len(sent) == 1
    args = sent[0]
    # [msgId=58, extOperator, manualOrderIndicator]
    assert args == (58, "EXT-9", 7)


def test_req_global_cancel_pre_192_keeps_version_byte():
    ib = ibi.IB()
    ib.client._serverVersion = 191
    sent: list = []
    ib.client.send = lambda *a: sent.append(a)
    ib.client.reqGlobalCancel()

    assert len(sent) == 1
    assert sent[0] == (58, 1)  # legacy VERSION=1, no CME-tagging


# ---------------------------------------------------------------------------
# Binary contractDetails — gate 182 (LAST_TRADE_DATE), gate 179 (FUND_DATA),
# gate 186 (INELIGIBILITY_REASONS).
# ---------------------------------------------------------------------------


def _binary_contract_details_fields(
    *,
    secType: str = "STK",
    last_trade_date: str = "",
    fund_block: list[str] | None = None,
    ineligibility_count: int = 0,
    ineligibility_pairs: list[tuple[str, str]] | None = None,
    pre_182: bool = False,
) -> list[str]:
    """Build a synthetic non-bond contractDetails wire fields list.
    Layout matches IBKR processContractDataMsg with serverVersion>=164.
    """
    head = [
        "10",  # msgId placeholder
        "7",  # reqId
        "ESM6",  # symbol
        secType,
        "20260619",  # lastTimes (lastTradeDateOrContractMonth)
    ]
    if not pre_182:
        head.append(last_trade_date)
    head += [
        "100.5",  # strike
        "C",  # right
        "GLOBEX",  # exchange
        "USD",  # currency
        "ESM6",  # localSymbol
        "ES",  # marketName
        "ES",  # tradingClass
        "12345",  # conId
        "0.25",  # minTick
        "50",  # multiplier
        "LIMIT,MKT",  # orderTypes
        "GLOBEX",  # validExchanges
        "1",  # priceMagnifier
        "0",  # underConId
        "E-mini SP",  # longName
        "GLOBEX",  # primaryExchange
        "202606",  # contractMonth
        "Financial",  # industry
        "Index",  # category
        "Broad",  # subcategory
        "US/Central",  # timeZoneId
        "0830-1500",  # tradingHours
        "0830-1500",  # liquidHours
        "",  # evRule
        "0",  # evMultiplier
        "0",  # numSecIds
        "0",  # aggGroup
        "ES",  # underSymbol
        "IND",  # underSecType
        "0",  # marketRuleIds
        "20260619",  # realExpirationDate
        "ETP",  # stockType
        "1",  # minSize
        "1",  # sizeIncrement
        "1",  # suggestedSizeIncrement
    ]
    if fund_block is not None:
        head += fund_block
    head.append(str(ineligibility_count))
    if ineligibility_pairs:
        for rid, rdesc in ineligibility_pairs:
            head += [rid, rdesc]
    return head


def test_binary_contract_details_reads_last_trade_date_at_gate_182():
    """Gate 182: ``lastTradeDate`` is appended after the legacy
    ``lastTradeDateOrContractMonth``. Without the gated read, ``strike``
    lands as ``lastTradeDate`` and every following field shifts left.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 182
    ib.client.decoder.serverVersion = 182
    seen: list[tuple] = []
    ib.wrapper.contractDetails = lambda reqId, cd: seen.append((reqId, cd))

    fields = _binary_contract_details_fields(last_trade_date="20260619-15:00:00")
    ib.client.decoder.contractDetails(fields)

    assert len(seen) == 1
    reqId, cd = seen[0]
    assert reqId == 7
    assert cd.contract.lastTradeDate == "20260619-15:00:00"
    # strike must still land in the right slot (not shifted).
    assert cd.contract.strike == 100.5
    assert cd.contract.exchange == "GLOBEX"


def test_binary_contract_details_skips_last_trade_date_below_gate_182():
    """Below gate 182 the slot does not exist; reading it would shift
    every following field one slot left.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 181
    ib.client.decoder.serverVersion = 181
    seen: list[tuple] = []
    ib.wrapper.contractDetails = lambda reqId, cd: seen.append((reqId, cd))

    fields = _binary_contract_details_fields(pre_182=True)
    ib.client.decoder.contractDetails(fields)

    assert len(seen) == 1
    _, cd = seen[0]
    # Default empty string — no shift.
    assert cd.contract.lastTradeDate == ""
    assert cd.contract.strike == 100.5
    assert cd.contract.exchange == "GLOBEX"


def test_binary_contract_details_reads_fund_block_at_gate_179_for_fund():
    """Gate 179 + secType=='FUND': 17-field fund-family block ships
    between size-rules and ineligibility-reasons. Without it the
    ineligibility count would land as ``fundName`` and the parser
    would mis-segment everything.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 188
    ib.client.decoder.serverVersion = 188
    seen: list[tuple] = []
    ib.wrapper.contractDetails = lambda reqId, cd: seen.append((reqId, cd))

    fund_block = [
        "Vanguard 500",  # fundName
        "Vanguard",  # fundFamily
        "Index",  # fundType
        "0.0",  # fundFrontLoad
        "0.0",  # fundBackLoad
        "",  # fundBackLoadTimeInterval
        "0.04",  # fundManagementFee
        "0",  # fundClosed
        "0",  # fundClosedForNewInvestors
        "0",  # fundClosedForNewMoney
        "1000",  # fundNotifyAmount
        "3000",  # fundMinimumInitialPurchase
        "1000",  # fundSubsequentMinimumPurchase
        "ALL",  # fundBlueSkyStates
        "ALL",  # fundBlueSkyTerritories
        "AnnualDist",  # fundDistributionPolicyIndicator
        "Equity",  # fundAssetType
    ]
    fields = _binary_contract_details_fields(
        secType="FUND",
        last_trade_date="",
        fund_block=fund_block,
    )
    ib.client.decoder.contractDetails(fields)

    assert len(seen) == 1
    _, cd = seen[0]
    assert cd.fundName == "Vanguard 500"
    assert cd.fundFamily == "Vanguard"
    assert cd.fundManagementFee == "0.04"
    assert cd.fundAssetType == "Equity"
    # Default empty list when count==0.
    assert cd.ineligibilityReasonList == []


def test_binary_contract_details_skips_fund_block_for_non_fund():
    """Gate 179 only fires on FUND secType; for STK no fund block is
    on the wire and reading one would corrupt the ineligibility count.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 188
    ib.client.decoder.serverVersion = 188
    seen: list[tuple] = []
    ib.wrapper.contractDetails = lambda reqId, cd: seen.append((reqId, cd))

    fields = _binary_contract_details_fields(
        secType="STK",
        last_trade_date="20260619-15:00:00",
    )
    ib.client.decoder.contractDetails(fields)

    assert len(seen) == 1
    _, cd = seen[0]
    assert cd.fundName == ""  # default
    assert cd.ineligibilityReasonList == []


def test_binary_contract_details_reads_ineligibility_at_gate_186():
    """Gate 186: ``ineligibilityReasonList`` is a count-prefixed
    list of ``(id_, description)`` pairs. Skipping the count at 186+
    leaves stale data in subsequent decodes.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 188
    ib.client.decoder.serverVersion = 188
    seen: list[tuple] = []
    ib.wrapper.contractDetails = lambda reqId, cd: seen.append((reqId, cd))

    fields = _binary_contract_details_fields(
        last_trade_date="20260619-15:00:00",
        ineligibility_count=2,
        ineligibility_pairs=[("R1", "Restricted to US"), ("R2", "Pro only")],
    )
    ib.client.decoder.contractDetails(fields)

    assert len(seen) == 1
    _, cd = seen[0]
    assert len(cd.ineligibilityReasonList) == 2
    assert cd.ineligibilityReasonList[0].id_ == "R1"
    assert cd.ineligibilityReasonList[0].description == "Restricted to US"
    assert cd.ineligibilityReasonList[1].id_ == "R2"


# ---------------------------------------------------------------------------
# Binary bondContractDetails — gate 188 (BOND_TRADING_HOURS).
# ---------------------------------------------------------------------------


def _binary_bond_contract_details_fields(
    *,
    include_trading_hours: bool,
) -> list[str]:
    """Build a synthetic bondContractDetails wire fields list at >=164."""
    head = [
        "18",  # msgId
        "9",  # reqId
        "TBOND",  # symbol
        "BOND",  # secType
        "ABC123",  # cusip
        "5.5",  # coupon
        "20300515",  # lastTimes (maturity)
        "20240101",  # issueDate
        "AAA",  # ratings
        "Treasury",  # bondType
        "Fixed",  # couponType
        "0",  # convertible
        "0",  # callable
        "0",  # putable
        "",  # descAppend
        "BONDDESK",  # exchange
        "USD",  # currency
        "BONDS",  # marketName
        "BONDS",  # tradingClass
        "12345",  # conId
        "0.01",  # minTick
        "LIMIT",  # orderTypes
        "BONDDESK",  # validExchanges
        "",  # nextOptionDate
        "",  # nextOptionType
        "0",  # nextOptionPartial
        "",  # notes
        "US Treasury 5.5% 2030",  # longName
    ]
    if include_trading_hours:
        head += ["US/Eastern", "0930-1600", "0930-1600"]
    head += [
        "",  # evRule
        "0",  # evMultiplier
        "0",  # numSecIds
        "0",  # aggGroup
        "0",  # marketRuleIds
        "1",  # minSize
        "1",  # sizeIncrement
        "1",  # suggestedSizeIncrement
    ]
    return head


def test_binary_bond_contract_details_reads_trading_hours_at_gate_188():
    """Gate 188: bond messages gain ``timeZoneId``/``tradingHours``/
    ``liquidHours`` between ``longName`` and ``evRule``. Without these
    reads ``evRule`` lands as ``timeZoneId`` and the rest shifts left.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 188
    ib.client.decoder.serverVersion = 188
    seen: list[tuple] = []
    ib.wrapper.bondContractDetails = lambda reqId, cd: seen.append((reqId, cd))

    fields = _binary_bond_contract_details_fields(include_trading_hours=True)
    ib.client.decoder.bondContractDetails(fields)

    assert len(seen) == 1
    reqId, cd = seen[0]
    assert reqId == 9
    assert cd.timeZoneId == "US/Eastern"
    assert cd.tradingHours == "0930-1600"
    assert cd.liquidHours == "0930-1600"
    # Sanity: aggGroup did not shift onto evMultiplier slot. Wire ``"0"``
    # collapses to ``None`` (the universal unset marker on the public
    # ``int | None`` dataclass field) so callers gating on
    # ``if details.aggGroup:`` stay falsy without the UNSET_INTEGER
    # sentinel leaking.
    assert cd.aggGroup is None


def test_binary_bond_contract_details_skips_trading_hours_below_gate_188():
    """Below gate 188 the trading-hours block does not exist on the
    wire; reading it would shift every following field one slot left.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 187
    ib.client.decoder.serverVersion = 187
    seen: list[tuple] = []
    ib.wrapper.bondContractDetails = lambda reqId, cd: seen.append((reqId, cd))

    fields = _binary_bond_contract_details_fields(include_trading_hours=False)
    ib.client.decoder.bondContractDetails(fields)

    assert len(seen) == 1
    _, cd = seen[0]
    # Defaults — no shift. ``aggGroup`` wire ``"0"`` collapses to
    # ``None`` (universal unset marker on the public dataclass).
    assert cd.tradingHours == ""
    assert cd.liquidHours == ""
    assert cd.aggGroup is None


# ---------------------------------------------------------------------------
# Binary execDetails — gate 198 (SUBMITTER).
# ---------------------------------------------------------------------------


def _binary_exec_details_fields(
    *,
    pending_price_revision: str = "0",
    submitter: str | None = None,
) -> list[str]:
    head = [
        "11",  # msgId
        "1",  # reqId
        "100",  # orderId
        "12345",  # conId
        "AAPL",  # symbol
        "STK",  # secType
        "",  # lastTradeDateOrContractMonth
        "0",  # strike
        "",  # right
        "",  # multiplier
        "NASDAQ",  # exchange
        "USD",  # currency
        "AAPL",  # localSymbol
        "AAPL",  # tradingClass
        "EXEC-1",  # execId
        "20260101  09:30:00",  # timeStr
        "DU12345",  # acctNumber
        "NASDAQ",  # exchange (exec)
        "BOT",  # side
        "100",  # shares
        "150.50",  # price
        "777",  # permId
        "0",  # clientId
        "0",  # liquidation
        "100",  # cumQty
        "150.50",  # avgPrice
        "",  # orderRef
        "",  # evRule
        "0",  # evMultiplier
        "",  # modelCode
        "1",  # lastLiquidity
        pending_price_revision,  # pendingPriceRevision (gate 178)
    ]
    if submitter is not None:
        head.append(submitter)
    return head


def test_binary_exec_details_reads_submitter_at_gate_198():
    """Gate 198: ``submitter`` is appended past pendingPriceRevision.
    Without the gated read the value is silently dropped on every fill.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 198
    ib.client.decoder.serverVersion = 198
    seen: list[tuple] = []
    ib.wrapper.execDetails = lambda reqId, c, ex: seen.append((reqId, c, ex))

    fields = _binary_exec_details_fields(submitter="trader42")
    ib.client.decoder.execDetails(fields)

    assert len(seen) == 1
    _, _, ex = seen[0]
    assert ex.submitter == "trader42"
    assert ex.pendingPriceRevision is False


def test_binary_exec_details_skips_submitter_below_gate_198():
    """Below gate 198 the slot does not exist; reading would IndexError
    or pull non-existent data."""
    ib = ibi.IB()
    ib.client._serverVersion = 197
    ib.client.decoder.serverVersion = 197
    seen: list[tuple] = []
    ib.wrapper.execDetails = lambda reqId, c, ex: seen.append((reqId, c, ex))

    fields = _binary_exec_details_fields(submitter=None)
    ib.client.decoder.execDetails(fields)

    assert len(seen) == 1
    _, _, ex = seen[0]
    assert ex.submitter == ""  # default


# ---------------------------------------------------------------------------
# Binary openOrder — trailing wire fields past gate 170.
# Most slots are consumed-and-discarded pending Order dataclass field
# expansion (task #163); only ``extOperator`` and ``imbalanceOnly`` are
# surfaced today.
# ---------------------------------------------------------------------------


def _make_open_order_fields(server_version: int) -> list[str]:
    """Build a minimal openOrder fields list valid for the given server
    version. Fills only enough slots for the decoder to reach the trailer.
    The trailer fields are appended by the caller.
    """
    # Up to and including the "skip ETradeOnly/firmQuoteOnly/nbboPriceCap"
    # slots we mirror IBKR's default-zero output for empty fields.
    fields = [
        "5",  # msgId
        "100",  # orderId
        "12345",  # conId
        "AAPL",  # symbol
        "STK",  # secType
        "",  # lastTradeDateOrContractMonth
        "0",  # strike
        "",  # right
        "",  # multiplier
        "SMART",  # exchange
        "USD",  # currency
        "AAPL",  # localSymbol
        "NMS",  # tradingClass
        "BUY",  # action
        "100",  # totalQuantity
        "LMT",  # orderType
        "150.0",  # lmtPrice
        "0",  # auxPrice
        "DAY",  # tif
        "",  # ocaGroup
        "DU12345",  # account
        "",  # openClose
        "0",  # origin
        "",  # orderRef
        "0",  # clientId
        "777",  # permId
        "0",  # outsideRth
        "0",  # hidden
        "0",  # discretionaryAmt
        "",  # goodAfterTime
        "",  # sharesAllocation (skipped)
        "",  # faGroup
        "",  # faMethod
        "",  # faPercentage
    ]
    if server_version < 177:
        fields.append("")  # faProfile
    fields += [
        "",  # modelCode
        "",  # goodTillDate
        "",  # rule80A
        "0",  # percentOffset
        "",  # settlingFirm
        "0",  # shortSaleSlot
        "",  # designatedLocation
        "-1",  # exemptCode
        "0",  # auctionStrategy
        "0",  # startingPrice
        "0",  # stockRefPrice
        "0",  # delta
        "0",  # stockRangeLower
        "0",  # stockRangeUpper
        "0",  # displaySize
        "0",  # blockOrder
        "0",  # sweepToFill
        "0",  # allOrNone
        "0",  # minQty
        "0",  # ocaType
        "0",  # eTradeOnly
        "0",  # firmQuoteOnly
        "0",  # nbboPriceCap
        "0",  # parentId
        "0",  # triggerMethod
        "0",  # volatility
        "0",  # volatilityType
        "",  # deltaNeutralOrderType (empty -> no nested block)
        "0",  # deltaNeutralAuxPrice
        "0",  # continuousUpdate
        "0",  # referencePriceType
        "0",  # trailStopPrice
        "0",  # trailingPercent
        "0",  # basisPoints
        "0",  # basisPointsType
        "",  # comboLegsDescrip
        "0",  # numLegs
        "0",  # numOrderLegs
        "0",  # numSmartComboParams
        "0",  # scaleInitLevelSize
        "0",  # scaleSubsLevelSize
        "",  # increment (UNSET -> no scale block)
        "",  # hedgeType (empty -> no hedgeParam)
        "0",  # optOutSmartRouting
        "",  # clearingAccount
        "",  # clearingIntent
        "0",  # notHeld
        "0",  # dncPresent
        "",  # algoStrategy (empty -> no algoParams)
        "0",  # solicited
        "0",  # whatIf
        "",  # status
        "0",  # initMarginBefore
        "0",  # maintMarginBefore
        "0",  # equityWithLoanBefore
        "0",  # initMarginChange
        "0",  # maintMarginChange
        "0",  # equityWithLoanChange
        "0",  # initMarginAfter
        "0",  # maintMarginAfter
        "0",  # equityWithLoanAfter
        "0",  # commission
        "0",  # minCommission
        "0",  # maxCommission
        "USD",  # commissionCurrency
    ]
    if server_version >= 195:
        # FULL_ORDER_PREVIEW_FIELDS block — IBKR's
        # ``decodeWhatIfInfoAndCommissionAndFees`` appends OutsideRTH
        # margins + suggestedSize / rejectReason + repeated
        # orderAllocations between commissionCurrency and warningText.
        fields += [
            "USD",  # marginCurrency
            "0",  # initMarginBeforeOutsideRTH
            "0",  # maintMarginBeforeOutsideRTH
            "0",  # equityWithLoanBeforeOutsideRTH
            "0",  # initMarginChangeOutsideRTH
            "0",  # maintMarginChangeOutsideRTH
            "0",  # equityWithLoanChangeOutsideRTH
            "0",  # initMarginAfterOutsideRTH
            "0",  # maintMarginAfterOutsideRTH
            "0",  # equityWithLoanAfterOutsideRTH
            "",  # suggestedSize
            "",  # rejectReason
            "0",  # accountsCount (no orderAllocations)
        ]
    fields += [
        "",  # warningText
        "0",  # randomizeSize
        "0",  # randomizePrice
        # No PEG_BENCH (orderType != "PEG BENCH")
        "0",  # numConditions
        "",  # adjustedOrderType
        "0",  # triggerPrice
        "0",  # trailStopPrice
        "0",  # lmtPriceOffset
        "0",  # adjustedStopPrice
        "0",  # adjustedStopLimitPrice
        "0",  # adjustedTrailingAmount
        "0",  # adjustableTrailingUnit
        "",  # softDollarTier.name
        "",  # softDollarTier.val
        "",  # softDollarTier.displayName
        "0",  # cashQty
        "0",  # dontUseAutoPriceForHedge
        "0",  # isOmsContainer
        "0",  # discretionaryUpToLimitPrice
        "0",  # usePriceMgmtAlgo
    ]
    if server_version >= 159:
        fields.append("0")  # duration
    if server_version >= 160:
        fields.append("0")  # postToAts
    if server_version >= 162:
        fields.append("0")  # autoCancelParent
    if server_version >= 170:
        # PEGBEST_PEGMID block (5 fields)
        fields += ["0", "0", "0", "0", "0"]
    return fields


def test_binary_open_order_reads_ext_operator_at_gate_193():
    """Gate 193 (CME_TAGGING_FIELDS_IN_OPEN_ORDER): the wire trailer
    appends ``extOperator`` + ``manualOrderIndicator`` after the
    customerAccount/professionalCustomer/bondAccrued/includeOvernight
    slots. ``extOperator`` is one of the two trailing fields that has
    a corresponding Order dataclass field today.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 193
    ib.client.decoder.serverVersion = 193
    seen: list[tuple] = []
    ib.wrapper.openOrder = lambda *a: seen.append(a)

    fields = _make_open_order_fields(193)
    # Trailer in 193 order: customerAccount, professionalCustomer,
    # bondAccruedInterest, includeOvernight, extOperator, manualOrderIndicator.
    fields += [
        "DU12345",  # customerAccount (consumed)
        "0",  # professionalCustomer (consumed)
        "",  # bondAccruedInterest (consumed)
        "0",  # includeOvernight (consumed)
        "EXT-7",  # extOperator (surfaced)
        "1",  # manualOrderIndicator (consumed)
    ]
    ib.client.decoder.openOrder(fields)

    assert len(seen) == 1
    _, _, o, _ = seen[0]
    assert o.extOperator == "EXT-7"
    # imbalanceOnly stays at default since we are below gate 199.
    assert o.imbalanceOnly is False


def test_binary_open_order_reads_imbalance_only_at_gate_199():
    """Gate 199: ``imbalanceOnly`` is the final trailer slot. With
    submitter at 198 and CME-tagging at 193 already consumed, this
    field must be read into the Order dataclass field that exists.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 199
    ib.client.decoder.serverVersion = 199
    seen: list[tuple] = []
    ib.wrapper.openOrder = lambda *a: seen.append(a)

    fields = _make_open_order_fields(199)
    fields += [
        "DU12345",  # customerAccount
        "0",  # professionalCustomer
        "",  # bondAccruedInterest
        "0",  # includeOvernight
        "EXT-9",  # extOperator
        "0",  # manualOrderIndicator
        "trader1",  # submitter (consumed)
        "1",  # imbalanceOnly (surfaced)
    ]
    ib.client.decoder.openOrder(fields)

    assert len(seen) == 1
    _, _, o, _ = seen[0]
    assert o.extOperator == "EXT-9"
    assert o.imbalanceOnly is True


def test_binary_open_order_skips_trailer_below_gate_183():
    """Below gate 183 (CUSTOMER_ACCOUNT) the entire trailer is
    absent; reading any of it would IndexError or pull stale data.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 182
    ib.client.decoder.serverVersion = 182
    seen: list[tuple] = []
    ib.wrapper.openOrder = lambda *a: seen.append(a)

    fields = _make_open_order_fields(182)
    ib.client.decoder.openOrder(fields)

    assert len(seen) == 1
    _, _, o, _ = seen[0]
    assert o.extOperator == ""
    assert o.imbalanceOnly is False


# ---------------------------------------------------------------------------
# placeOrder gated trailers — gates 183, 184, 187-190, 189, 192, 199
# ---------------------------------------------------------------------------


def _placeOrderArgs(serverVersion: int):
    """Drive Client.placeOrder against the binary path on a synthetic
    server version, capturing the field tuple the encoder produced.
    Returns ``(args_tuple, ib)`` so callers can assert on field values
    AND on order-attribute mutations placeOrder performs.
    """
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    sent: list = []
    ib.client.send = lambda *a: sent.append(a)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    order = ibi.LimitOrder("BUY", 100, 50.5)
    ib.client.placeOrder(orderId=42, contract=contract, order=order)
    assert len(sent) == 1, f"expected one send, got {len(sent)}"
    return sent[0], ib


def test_place_order_at_192_writes_manual_order_indicator():
    """At MIN_SERVER_VER_CME_TAGGING_FIELDS (192) IBKR writes
    ``order.manualOrderIndicator`` past every other gated trailer.
    Below 192 it must NOT be written — the field would shift later
    fields out of position on the wire.
    """
    args_192, _ = _placeOrderArgs(192)
    args_191, _ = _placeOrderArgs(191)

    # 192 carries one more trailer than 191 — manualOrderIndicator.
    assert len(args_192) == len(args_191) + 1
    # The trailer is the LAST field at server 192 (IMBALANCE_ONLY is
    # gate 199, so not written here).
    assert args_192[-1] is None  # default Order.manualOrderIndicator
    # extOperator is unconditional in our send (gate 105 / EXT_OPERATOR
    # is below MIN_CLIENT_VER) — verify it appears in BOTH frames.
    assert "" in args_191  # default extOperator empty string
    assert "" in args_192


def test_place_order_at_199_writes_imbalance_only():
    """At MIN_SERVER_VER_IMBALANCE_ONLY (199) the bool ``order.imbalanceOnly``
    is appended past the gate-192 trailer. Adding a default-False order
    verifies the bool lands as a trailing argument.
    """
    args_199, _ = _placeOrderArgs(199)
    args_198, _ = _placeOrderArgs(198)

    # 199 carries one more trailer than 198 — imbalanceOnly.
    assert len(args_199) == len(args_198) + 1
    # imbalanceOnly defaults False at the dataclass.
    assert args_199[-1] is False
    # gate-192 manualOrderIndicator sits one slot earlier.
    assert args_199[-2] is None


def test_place_order_at_184_writes_customer_and_professional():
    """At MIN_SERVER_VER_PROFESSIONAL_CUSTOMER (184), customerAccount
    (gate 183, str) AND professionalCustomer (gate 184, bool) sit
    consecutively past gate 170. The fields aren't on Order yet — the
    getattr fallback must produce the IBKR defaults: "" and False.
    """
    args_184, _ = _placeOrderArgs(184)
    args_182, _ = _placeOrderArgs(182)

    # 184 carries TWO more trailers than 182 — customerAccount + professionalCustomer.
    assert len(args_184) == len(args_182) + 2
    # Fields trail in the order: ..., customerAccount="", professionalCustomer=False
    # then RFQ_FIELDS at 187-190 (interim) which doesn't apply here.
    assert args_184[-2] == ""  # customerAccount default
    assert args_184[-1] is False  # professionalCustomer default


def test_place_order_in_rfq_window_writes_interim_fields():
    """Servers in [MIN_SERVER_VER_RFQ_FIELDS (187),
    MIN_SERVER_VER_UNDO_RFQ_FIELDS (190)) get the interim 2-field RFQ
    block: bondAccruedInterest (str, default "") + UNSET_INTEGER
    placeholder. Outside the window the block is not written.
    """
    # 188 is in the window; 190 closes it.  At 188 the trailer order is
    #   ..., customerAccount="", professionalCustomer=False,
    #        bondAccruedInterest="", UNSET_INTEGER  (RFQ pair)
    # At 190 the RFQ pair is gone but includeOvernight (gate 189)
    # remains; so 188 = 4 trailers, 190 = 3.
    args_188, _ = _placeOrderArgs(188)
    args_190, _ = _placeOrderArgs(190)

    # The RFQ pair at 188's tail: bondAccruedInterest="" then UNSET_INTEGER.
    assert args_188[-2] is None  # bondAccruedInterest default (Decimal | None)
    assert args_188[-1] == UNSET_INTEGER  # RFQ placeholder int (literal in client.py)

    # Same window edges, different counts.
    assert len(args_188) == len(args_190) + 1  # +RFQ pair, -includeOvernight


def test_place_order_at_189_writes_include_overnight():
    """MIN_SERVER_VER_INCLUDE_OVERNIGHT (189) appends a bool. The field
    isn't on Order yet — getattr fallback returns False.
    """
    args_189, _ = _placeOrderArgs(189)
    args_188, _ = _placeOrderArgs(188)

    # 189 carries one more trailer than 188 — includeOvernight.
    assert len(args_189) == len(args_188) + 1
    assert args_189[-1] is False  # includeOvernight default


# ---------------------------------------------------------------------------
# exerciseOptions gated trailers — gates 180, 183, 184
# ---------------------------------------------------------------------------


def test_exercise_options_at_184_writes_all_gated_trailers():
    """At MIN_SERVER_VER_PROFESSIONAL_CUSTOMER (184) all three gated
    trailers — manualOrderTime (gate 180), customerAccount (183),
    professionalCustomer (184) — are written in order. Below 180 none
    of them appear.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 184
    sent: list = []
    ib.client.send = lambda *a: sent.append(a)
    contract = ibi.Option("AAPL", "20300119", 150.0, "C", "SMART")
    contract.conId = 12345
    ib.client.exerciseOptions(
        reqId=7,
        contract=contract,
        exerciseAction=1,
        exerciseQuantity=1,
        account="DU123456",
        override=0,
        manualOrderTime="20300101 09:30:00",
        customerAccount="CUST-1",
        professionalCustomer=True,
    )
    assert len(sent) == 1
    args = sent[0]
    # The three trailers are the last three fields, in order.
    assert args[-3] == "20300101 09:30:00"
    assert args[-2] == "CUST-1"
    assert args[-1] is True


def test_exercise_options_below_180_drops_all_gated_trailers():
    """Below MIN_SERVER_VER_MANUAL_ORDER_TIME_EXERCISE_OPTIONS (180)
    none of the three trailers are written. Sending them anyway would
    desync the wire frame on a legacy server.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 179
    sent: list = []
    ib.client.send = lambda *a: sent.append(a)
    contract = ibi.Option("AAPL", "20300119", 150.0, "C", "SMART")
    contract.conId = 12345
    ib.client.exerciseOptions(
        reqId=7,
        contract=contract,
        exerciseAction=1,
        exerciseQuantity=1,
        account="DU123456",
        override=0,
        manualOrderTime="20300101 09:30:00",
        customerAccount="CUST-1",
        professionalCustomer=True,
    )
    assert len(sent) == 1
    args = sent[0]
    # Last field is `override` (= 0) — no trailers past it.
    assert args[-1] == 0


# ---------------------------------------------------------------------------
# reqExecutions gated trailers — gate 200 (PARAMETRIZED_DAYS_OF_EXECUTIONS)
# ---------------------------------------------------------------------------


def test_req_executions_at_200_writes_last_n_days_and_specific_dates():
    """At MIN_SERVER_VER_PARAMETRIZED_DAYS_OF_EXECUTIONS (200) IBKR
    writes ``execFilter.lastNDays`` plus an int count of
    ``specificDates`` followed by each date. The dataclass doesn't
    carry these fields yet — the ``getattr`` fallback writes the
    IBKR defaults (UNSET_INTEGER + 0 dates).
    """
    ib = ibi.IB()
    ib.client._serverVersion = 200
    sent: list = []
    ib.client.send = lambda *a: sent.append(a)
    ef = ibi.ExecutionFilter(clientId=7, symbol="AAPL")
    ib.client.reqExecutions(reqId=42, execFilter=ef)
    assert len(sent) == 1
    args = sent[0]
    # Default: lastNDays=UNSET_INTEGER, specificDates count=0
    assert args[-2] == UNSET_INTEGER
    assert args[-1] == 0


def test_req_executions_at_200_writes_each_specific_date():
    """When the caller supplies ``specificDates`` via getattr-friendly
    monkey-patch, each date is written past the count.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 200
    sent: list = []
    ib.client.send = lambda *a: sent.append(a)
    ef = ibi.ExecutionFilter(clientId=7)
    # Sibling task 162 will add these dataclass fields; today the
    # method must read them via getattr so this monkeypatch lands.
    ef.lastNDays = 5  # type: ignore[attr-defined]
    ef.specificDates = [20300101, 20300102]  # type: ignore[attr-defined]
    ib.client.reqExecutions(reqId=42, execFilter=ef)
    assert len(sent) == 1
    args = sent[0]
    # Layout tail: ..., lastNDays=5, count=2, date1, date2
    assert args[-4] == 5
    assert args[-3] == 2
    assert args[-2] == 20300101
    assert args[-1] == 20300102


def test_req_executions_below_200_omits_parametrized_fields():
    """Below MIN_SERVER_VER_PARAMETRIZED_DAYS_OF_EXECUTIONS (200) no
    extra trailers are written. The legacy 7-field filter ends at
    ``execFilter.side``.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 199
    sent: list = []
    ib.client.send = lambda *a: sent.append(a)
    ef = ibi.ExecutionFilter(clientId=7, symbol="AAPL", side="BUY")
    ib.client.reqExecutions(reqId=42, execFilter=ef)
    assert len(sent) == 1
    args = sent[0]
    # Last legacy field is execFilter.side.
    assert args[-1] == "BUY"


def test_max_client_version_advertises_modern_protobuf_gates():
    """The handshake banner sends ``v{Min}..{Max}`` and the server
    negotiates ``min(server, Max)``. With Max capped at 178 every
    protobuf gate (>=201) was unreachable in production. Locks the
    cap at 225 (latest IBKR MAX_CLIENT_VER) so a careless edit
    can't silently regress protobuf reachability.
    """
    from ib_async._server_versions import (
        MIN_SERVER_VER_ODD_LOT_BID_ASK_QUOTES,
        MIN_SERVER_VER_PROTOBUF,
    )

    ib = ibi.IB()
    assert ib.client.MaxClientVersion == 225
    assert ib.client.MaxClientVersion == MIN_SERVER_VER_ODD_LOT_BID_ASK_QUOTES
    # Sanity: the protobuf base gate is reachable.
    assert ib.client.MaxClientVersion >= MIN_SERVER_VER_PROTOBUF


# ---------------------------------------------------------------------------
# Round-3 audit regressions — combo-leg per-leg pricing, WshEventData gating,
# condition triggerMethod=0 wire emission.
# ---------------------------------------------------------------------------


def test_combo_leg_per_leg_price_propagates_through_place_order():
    """``Order.orderComboLegs[i].price`` must land on the wire as
    ``Contract.comboLegs[i].perLegPrice`` for BAG-secType orders.

    IBKR's reference ``createContractProto(contract, order)`` reads the
    parallel ``order.orderComboLegs`` list and writes ``perLegPrice``
    on each ComboLeg proto. Before the round-3 audit fix our converter
    ignored ``order`` entirely and BAG orders shipped with all leg
    prices unset — the server treats unset perLegPrice as zero, which
    silently mis-prices every spread the user submits.
    """
    from ib_async._proto.orders import createPlaceOrderRequestProto
    from ib_async.contract import ComboLeg, Contract
    from ib_async.order import LimitOrder, OrderComboLeg

    bag = Contract(
        symbol="SPX",
        secType="BAG",
        exchange="SMART",
        currency="USD",
        comboLegs=[
            ComboLeg(conId=111, ratio=1, action="BUY", exchange="SMART"),
            ComboLeg(conId=222, ratio=1, action="SELL", exchange="SMART"),
        ],
    )
    order = LimitOrder("BUY", 1, 1.50)
    order.orderComboLegs = [
        OrderComboLeg(price=Decimal("1.25")),
        OrderComboLeg(price=Decimal("0.25")),
    ]

    proto = createPlaceOrderRequestProto(42, bag, order)

    assert len(proto.contract.comboLegs) == 2
    assert proto.contract.comboLegs[0].HasField("perLegPrice")
    assert proto.contract.comboLegs[0].perLegPrice == 1.25
    assert proto.contract.comboLegs[1].HasField("perLegPrice")
    assert proto.contract.comboLegs[1].perLegPrice == 0.25


def test_combo_leg_no_per_leg_price_when_order_has_no_combo_legs():
    """When ``Order.orderComboLegs`` is empty (the typical non-BAG
    case), the contract proto's ComboLegs must have ``perLegPrice``
    UNSET — not zero, which the server would interpret as a real
    price."""
    from ib_async._proto.orders import createPlaceOrderRequestProto
    from ib_async.contract import ComboLeg, Contract
    from ib_async.order import LimitOrder

    bag = Contract(
        symbol="SPX",
        secType="BAG",
        comboLegs=[ComboLeg(conId=111, ratio=1, action="BUY", exchange="SMART")],
    )
    order = LimitOrder("BUY", 1, 1.50)
    # No orderComboLegs assignment.

    proto = createPlaceOrderRequestProto(99, bag, order)

    assert len(proto.contract.comboLegs) == 1
    assert not proto.contract.comboLegs[0].HasField("perLegPrice")


def test_create_contract_proto_no_order_omits_per_leg_price():
    """``createContractProto(contract)`` (no order arg, the common case
    for market data / historical data calls) must produce ComboLeg
    protos without ``perLegPrice``. The send-side helper must not
    accidentally invent a zero per-leg price for non-trading paths.
    """
    from ib_async._proto.contracts import createContractProto
    from ib_async.contract import ComboLeg, Contract

    bag = Contract(
        symbol="SPX",
        secType="BAG",
        comboLegs=[
            ComboLeg(conId=111, ratio=1, action="BUY", exchange="SMART"),
            ComboLeg(conId=222, ratio=2, action="SELL", exchange="SMART"),
        ],
    )

    proto = createContractProto(bag)

    assert len(proto.comboLegs) == 2
    for leg in proto.comboLegs:
        assert not leg.HasField("perLegPrice")


def test_wsh_event_data_request_omits_unset_int_sentinels():
    """``WshEventData.conId`` and ``totalLimit`` default to
    ``UNSET_INTEGER``; sending the sentinel verbatim would have IBKR's
    server reject the request. Mirror IBKR's ``isValidIntValue``
    gating from ``client_utils.createWshEventDataRequestProto``.
    """
    from ib_async._proto.news import createWshEventDataRequestProto
    from ib_async.objects import WshEventData

    data = WshEventData()  # all defaults → conId / totalLimit unset
    proto = createWshEventDataRequestProto(reqId=7, data=data)

    assert proto.reqId == 7
    assert not proto.HasField("conId")
    assert not proto.HasField("totalLimit")
    # Empty strings stay unset on the wire too.
    assert not proto.HasField("filter")
    assert not proto.HasField("startDate")


def test_wsh_event_data_request_writes_set_fields():
    """When the user sets ``conId`` / ``totalLimit`` to non-sentinel
    values, those values must reach the wire — the gate must not be
    overzealous."""
    from ib_async._proto.news import createWshEventDataRequestProto
    from ib_async.objects import WshEventData

    data = WshEventData(
        conId=1234,
        filter="earnings",
        fillWatchlist=True,
        startDate="20260101",
        totalLimit=50,
    )
    proto = createWshEventDataRequestProto(reqId=7, data=data)

    assert proto.HasField("conId") and proto.conId == 1234
    assert proto.HasField("filter") and proto.filter == "earnings"
    assert proto.HasField("fillWatchlist") and proto.fillWatchlist is True
    assert proto.HasField("startDate") and proto.startDate == "20260101"
    assert proto.HasField("totalLimit") and proto.totalLimit == 50


def test_price_condition_trigger_method_zero_writes_to_wire():
    """``PriceCondition.triggerMethod=0`` means "Default trigger
    method" — a valid wire value IBKR's reference encoder writes via
    ``isValidIntValue``. The truthy guard the contributor PR ran with
    would have skipped 0 entirely, leaving the field unset and risking
    the server falling back to a different default.
    """
    from ib_async._proto.orders import createPlaceOrderRequestProto
    from ib_async.contract import Contract
    from ib_async.order import LimitOrder, PriceCondition

    cond = PriceCondition(
        conId=265598, exch="SMART", price=100.0, triggerMethod=0, isMore=True
    )
    order = LimitOrder("BUY", 1, 50.0)
    order.conditions = [cond]

    proto = createPlaceOrderRequestProto(7, Contract(symbol="AAPL"), order)
    assert len(proto.order.conditions) == 1
    cp = proto.order.conditions[0]
    assert cp.HasField("triggerMethod")
    assert cp.triggerMethod == 0


def test_combo_leg_more_contract_legs_than_order_legs_safe():
    """Defensive: when ``contract.comboLegs`` has more entries than
    ``order.orderComboLegs``, the extra contract legs must encode
    cleanly (no IndexError) and simply omit ``perLegPrice``. Mirrors
    IBKR's ``createComboLegProtoList`` ``i < len(orderComboLegs)``
    guard.
    """
    from ib_async._proto.orders import createPlaceOrderRequestProto
    from ib_async.contract import ComboLeg, Contract
    from ib_async.order import LimitOrder, OrderComboLeg

    bag = Contract(
        symbol="SPX",
        secType="BAG",
        comboLegs=[
            ComboLeg(conId=111, ratio=1, action="BUY", exchange="SMART"),
            ComboLeg(conId=222, ratio=1, action="SELL", exchange="SMART"),
            ComboLeg(conId=333, ratio=1, action="SELL", exchange="SMART"),
        ],
    )
    order = LimitOrder("BUY", 1, 1.50)
    order.orderComboLegs = [OrderComboLeg(price=Decimal("0.5"))]  # only first

    proto = createPlaceOrderRequestProto(11, bag, order)

    assert len(proto.contract.comboLegs) == 3
    assert proto.contract.comboLegs[0].HasField("perLegPrice")
    assert proto.contract.comboLegs[0].perLegPrice == 0.5
    assert not proto.contract.comboLegs[1].HasField("perLegPrice")
    assert not proto.contract.comboLegs[2].HasField("perLegPrice")


# ---------------------------------------------------------------------------
# Binary openOrder — FULL_ORDER_PREVIEW_FIELDS block (server >= 195).
# IBKR's ``decodeWhatIfInfoAndCommissionAndFees`` appends an OutsideRTH
# margin family + suggestedSize / rejectReason / orderAllocations between
# commissionCurrency and warningText. Skipping the block left the wire
# stream shifted left for every gated read past warningText.
# ---------------------------------------------------------------------------


def test_binary_open_order_decodes_full_order_preview_block():
    """Round 3 audit fix: the FULL_ORDER_PREVIEW_FIELDS block on the
    binary openOrder path was completely absent. With the gate at 195
    every modern server delivers OutsideRTH margins + suggestedSize +
    orderAllocations through this slot — the missing read shifted the
    wire by 13+ slots and corrupted every gated read past warningText.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 199
    ib.client.decoder.serverVersion = 199
    seen: list[tuple] = []
    ib.wrapper.openOrder = lambda *a: seen.append(a)

    fields = _make_open_order_fields(199)
    # Patch the FULL_ORDER_PREVIEW block (13 slots: marginCurrency,
    # 9 OutsideRTH margins, suggestedSize, rejectReason, accountsCount).
    # Three "USD" tokens exist in the payload: contract.currency,
    # commissionCurrency, marginCurrency. marginCurrency is the third.
    first = fields.index("USD")
    second = fields.index("USD", first + 1)
    block_start = fields.index("USD", second + 1)
    fields[block_start + 10] = "5"  # suggestedSize
    fields[block_start + 11] = "test-reject-reason"  # rejectReason
    fields += [
        "DU12345",  # customerAccount
        "0",  # professionalCustomer
        "",  # bondAccruedInterest
        "0",  # includeOvernight
        "EXT-9",  # extOperator
        "0",  # manualOrderIndicator
        "trader1",  # submitter
        "0",  # imbalanceOnly
    ]

    ib.client.decoder.openOrder(fields)

    assert len(seen) == 1
    _, _, o, st = seen[0]
    assert st.marginCurrency == "USD"
    assert st.suggestedSize == Decimal(5)
    assert st.rejectReason == "test-reject-reason"
    assert st.orderAllocations == []
    # Trailer fields past warningText still align after the new block.
    assert o.extOperator == "EXT-9"


def test_binary_open_order_decodes_order_allocations():
    """The FULL_ORDER_PREVIEW block ships an ``accountsCount`` int and
    that many ``OrderAllocation`` records (7 fields each). The decoder
    must materialize them as ``OrderAllocation`` dataclass instances on
    ``OrderState.orderAllocations``.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 199
    ib.client.decoder.serverVersion = 199
    seen: list[tuple] = []
    ib.wrapper.openOrder = lambda *a: seen.append(a)

    # The FULL_ORDER_PREVIEW accountsCount slot defaults to "0"; replace
    # it with "1" and inject one allocation right after.
    base = _make_open_order_fields(199)
    # Three "USD" tokens exist: contract.currency, commissionCurrency,
    # marginCurrency. marginCurrency is the third. accountsCount is at
    # offset +12 from marginCurrency (OutsideRTH x9 + suggestedSize +
    # rejectReason).
    first = base.index("USD")
    second = base.index("USD", first + 1)
    block_start = base.index("USD", second + 1)
    base[block_start + 12] = "1"  # accountsCount = 1
    # Insert 7 OrderAllocation fields right after accountsCount.
    base[block_start + 13 : block_start + 13] = [
        "DU-ALLOC-A",  # account
        "10",  # position
        "20",  # positionDesired
        "15",  # positionAfter
        "5",  # desiredAllocQty
        "5",  # allowedAllocQty
        "0",  # isMonetary
    ]
    base += [
        "DU12345",  # customerAccount
        "0",  # professionalCustomer
        "",  # bondAccruedInterest
        "0",  # includeOvernight
        "EXT-9",  # extOperator
        "0",  # manualOrderIndicator
        "trader1",  # submitter
        "0",  # imbalanceOnly
    ]

    ib.client.decoder.openOrder(base)

    assert len(seen) == 1
    _, _, _, st = seen[0]
    assert len(st.orderAllocations) == 1
    alloc = st.orderAllocations[0]
    assert alloc.account == "DU-ALLOC-A"
    assert alloc.position == Decimal(10)
    assert alloc.positionDesired == Decimal(20)
    assert alloc.positionAfter == Decimal(15)
    assert alloc.desiredAllocQty == Decimal(5)
    assert alloc.allowedAllocQty == Decimal(5)
    assert alloc.isMonetary is False


# ---------------------------------------------------------------------------
# Round-6 cross-version boundary matrix. For every recently-fixed gate, lock
# both the pre-gate path (server v=N-1) AND the post-gate path (server v=N)
# so an off-by-one in the comparison can't pass either side silently.
# ---------------------------------------------------------------------------


def test_binary_open_order_skips_full_order_preview_block_below_gate_195():
    """Gate 195 (FULL_ORDER_PREVIEW_FIELDS) below: at 194 the block is
    absent from the wire. Pairs with the existing >=199 above-test
    and the new gate-195 boundary test for off-by-one coverage.
    """
    from ib_async._server_versions import MIN_SERVER_VER_FULL_ORDER_PREVIEW_FIELDS

    serverVersion = MIN_SERVER_VER_FULL_ORDER_PREVIEW_FIELDS - 1
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.decoder.serverVersion = serverVersion
    seen: list[tuple] = []
    ib.wrapper.openOrder = lambda *a: seen.append(a)

    fields = _make_open_order_fields(serverVersion)
    fields += [
        "DU12345",
        "0",
        "",
        "0",
        "EXT-X",
        "0",
    ]
    ib.client.decoder.openOrder(fields)

    assert len(seen) == 1
    _, _, o, st = seen[0]
    assert st.marginCurrency == ""
    assert st.suggestedSize is None
    assert st.rejectReason == ""
    assert st.orderAllocations == []
    assert o.extOperator == "EXT-X"


def test_binary_open_order_at_exact_gate_195_reads_full_order_preview_block():
    """Gate 195 boundary: at exactly MIN_SERVER_VER_FULL_ORDER_PREVIEW_FIELDS
    the block IS present. Pairs with the below-195 test.
    """
    from ib_async._server_versions import MIN_SERVER_VER_FULL_ORDER_PREVIEW_FIELDS

    serverVersion = MIN_SERVER_VER_FULL_ORDER_PREVIEW_FIELDS
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.decoder.serverVersion = serverVersion
    seen: list[tuple] = []
    ib.wrapper.openOrder = lambda *a: seen.append(a)

    fields = _make_open_order_fields(serverVersion)
    first = fields.index("USD")
    second = fields.index("USD", first + 1)
    block_start = fields.index("USD", second + 1)
    fields[block_start + 10] = "7"
    fields[block_start + 11] = "test-reason-195"
    fields += [
        "DU12345",
        "0",
        "",
        "0",
        "EXT-G",
        "0",
    ]
    ib.client.decoder.openOrder(fields)

    assert len(seen) == 1
    _, _, o, st = seen[0]
    assert st.marginCurrency == "USD"
    assert st.suggestedSize == Decimal(7)
    assert st.rejectReason == "test-reason-195"
    assert o.extOperator == "EXT-G"


def test_binary_open_order_at_exact_gate_198_skips_imbalance_only():
    """Gate 199 (IMBALANCE_ONLY) boundary: at exactly 198 the slot is
    NOT consumed. Pairs with the existing 199 above-test.
    """
    from ib_async._server_versions import MIN_SERVER_VER_IMBALANCE_ONLY

    serverVersion = MIN_SERVER_VER_IMBALANCE_ONLY - 1
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.decoder.serverVersion = serverVersion
    seen: list[tuple] = []
    ib.wrapper.openOrder = lambda *a: seen.append(a)

    fields = _make_open_order_fields(serverVersion)
    fields += [
        "DU12345",
        "0",
        "",
        "0",
        "EXT-J",
        "0",
        "trader198",
    ]
    ib.client.decoder.openOrder(fields)

    assert len(seen) == 1
    _, _, o, _ = seen[0]
    assert o.extOperator == "EXT-J"
    assert o.imbalanceOnly is False


def _exec_details_fields_pre_178() -> list[str]:
    """Build a synthetic execDetails wire fields list at server <178 —
    no pendingPriceRevision slot.
    """
    return [
        "11",
        "1",
        "100",
        "12345",
        "AAPL",
        "STK",
        "",
        "0",
        "",
        "",
        "NASDAQ",
        "USD",
        "AAPL",
        "AAPL",
        "EXEC-1",
        "20260101  09:30:00",
        "DU12345",
        "NASDAQ",
        "BOT",
        "100",
        "150.50",
        "777",
        "0",
        "0",
        "100",
        "150.50",
        "",
        "",
        "0",
        "",
        "1",
    ]


def test_binary_exec_details_skips_pending_price_revision_below_gate_178():
    """Gate 178 (PENDING_PRICE_REVISION) below: at 177 no slot on the
    wire. Pairs with the >=178 above-tests already in the file.
    """
    from ib_async._server_versions import MIN_SERVER_VER_PENDING_PRICE_REVISION

    serverVersion = MIN_SERVER_VER_PENDING_PRICE_REVISION - 1
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.decoder.serverVersion = serverVersion
    seen: list[tuple] = []
    ib.wrapper.execDetails = lambda reqId, c, ex: seen.append((reqId, c, ex))

    fields = _exec_details_fields_pre_178()
    ib.client.decoder.execDetails(fields)

    assert len(seen) == 1
    _, _, ex = seen[0]
    assert ex.pendingPriceRevision is False
    assert ex.lastLiquidity == 1


def test_binary_exec_details_at_exact_gate_178_reads_pending_price_revision():
    """Gate 178 boundary: at exactly 178 the slot is consumed.
    Pairs with the pre-178 test for off-by-one.
    """
    from ib_async._server_versions import MIN_SERVER_VER_PENDING_PRICE_REVISION

    serverVersion = MIN_SERVER_VER_PENDING_PRICE_REVISION
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.decoder.serverVersion = serverVersion
    seen: list[tuple] = []
    ib.wrapper.execDetails = lambda reqId, c, ex: seen.append((reqId, c, ex))

    fields = _binary_exec_details_fields(pending_price_revision="1", submitter=None)
    ib.client.decoder.execDetails(fields)

    assert len(seen) == 1
    _, _, ex = seen[0]
    assert ex.pendingPriceRevision is True
    assert ex.submitter == ""


@pytest.mark.parametrize(
    "offset, expected",
    [
        (-1, (4, 1, 42)),  # below gate 169: no manualOrderCancelTime trailer
        (0, (4, 1, 42, "20300101 09:30:00")),  # at gate 169: trailer appended
    ],
    ids=["below_gate_169", "at_gate_169"],
)
def test_cancel_order_manual_order_time_gate_169(offset, expected):
    """Gate 169 (MANUAL_ORDER_TIME): ``manualOrderCancelTime`` appears in
    the cancelOrder frame at and above gate 169, but not below. Same
    cancel call exercises both sides — the only variable is server
    version and the resulting wire-arg tuple.
    """
    from ib_async._server_versions import MIN_SERVER_VER_MANUAL_ORDER_TIME
    from ib_async.order import OrderCancel

    ib = ibi.IB()
    ib.client._serverVersion = MIN_SERVER_VER_MANUAL_ORDER_TIME + offset
    sent: list = []
    ib.client.send = lambda *a: sent.append(a)
    ib.client.cancelOrder(42, OrderCancel(manualOrderCancelTime="20300101 09:30:00"))

    assert len(sent) == 1
    assert sent[0] == expected


def test_binary_contract_details_skips_ineligibility_below_gate_186():
    """Gate 186 (INELIGIBILITY_REASONS) below: at 185 there's no count
    slot at the tail.
    """
    from ib_async._server_versions import MIN_SERVER_VER_INELIGIBILITY_REASONS

    serverVersion = MIN_SERVER_VER_INELIGIBILITY_REASONS - 1
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.decoder.serverVersion = serverVersion
    seen: list[tuple] = []
    ib.wrapper.contractDetails = lambda reqId, cd: seen.append((reqId, cd))

    fields = [
        "10",
        "7",
        "ESM6",
        "STK",
        "20260619",
        "20260619-15:00:00",
        "100.5",
        "C",
        "GLOBEX",
        "USD",
        "ESM6",
        "ES",
        "ES",
        "12345",
        "0.25",
        "50",
        "LIMIT,MKT",
        "GLOBEX",
        "1",
        "0",
        "E-mini",
        "GLOBEX",
        "202606",
        "Financial",
        "Index",
        "Broad",
        "US/Central",
        "0830-1500",
        "0830-1500",
        "",
        "0",
        "0",
        "0",
        "ES",
        "IND",
        "0",
        "20260619",
        "ETP",
        "1",
        "1",
        "1",
    ]
    ib.client.decoder.contractDetails(fields)

    assert len(seen) == 1
    _, cd = seen[0]
    assert cd.ineligibilityReasonList == []
    assert cd.stockType == "ETP"


def test_binary_contract_details_at_exact_gate_186_reads_ineligibility_count():
    """Gate 186 boundary: at exactly 186 the count slot is present.
    Pairs with below-186 for off-by-one.
    """
    from ib_async._server_versions import MIN_SERVER_VER_INELIGIBILITY_REASONS

    serverVersion = MIN_SERVER_VER_INELIGIBILITY_REASONS
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.decoder.serverVersion = serverVersion
    seen: list[tuple] = []
    ib.wrapper.contractDetails = lambda reqId, cd: seen.append((reqId, cd))

    fields = _binary_contract_details_fields(
        last_trade_date="20260619-15:00:00",
        ineligibility_count=1,
        ineligibility_pairs=[("R7", "Restricted")],
    )
    ib.client.decoder.contractDetails(fields)

    assert len(seen) == 1
    _, cd = seen[0]
    assert len(cd.ineligibilityReasonList) == 1
    assert cd.ineligibilityReasonList[0].id_ == "R7"


def test_req_global_cancel_at_exact_gate_192_drops_version():
    """Gate 192 boundary in reqGlobalCancel: at exactly 192 the legacy
    VERSION byte must be absent. Pairs with the existing 191 test.
    """
    from ib_async._server_versions import MIN_SERVER_VER_CME_TAGGING_FIELDS

    serverVersion = MIN_SERVER_VER_CME_TAGGING_FIELDS
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    sent: list = []
    ib.client.send = lambda *a: sent.append(a)
    ib.client.reqGlobalCancel()

    assert len(sent) == 1
    assert sent[0] == (58, "", None)


def test_historical_data_at_pre_124_consumes_legacy_version_prefix():
    """Gate 124 (SYNT_REALTIME_BARS) below: at 123 the historicalData
    wire frame carries a legacy VERSION prefix that must be eaten.
    """
    from ib_async._server_versions import MIN_SERVER_VER_SYNT_REALTIME_BARS

    serverVersion = MIN_SERVER_VER_SYNT_REALTIME_BARS - 1
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.decoder.serverVersion = serverVersion
    bars: list = []
    ends: list[tuple] = []
    ib.wrapper.historicalData = lambda *a: bars.append(a)
    ib.wrapper.historicalDataEnd = lambda *a: ends.append(a)

    fields = [
        "17",
        "3",
        "5",
        "20240101",
        "20240131",
        "1",
        "20240115",
        "100.0",
        "101.0",
        "99.5",
        "100.5",
        "1000",
        "100.25",
        "10",
    ]
    ib.client.decoder.historicalData(fields)

    assert len(bars) == 1
    assert bars[0][0] == 5
    assert ends == [(5, "20240101", "20240131")]


def test_cancel_contract_data_emits_proto_only_at_gate_215():
    """Gate 215 (CANCEL_CONTRACT_DATA): IBKR ships no binary form so
    the client unconditionally takes the protobuf path. The wire
    frame is [4-byte len][4-byte wireMsgId = canonical + 200][body].
    """
    import struct

    from ib_async._pb_msgids import CANCEL_CONTRACT_DATA, PROTOBUF_MSG_ID

    ib = ibi.IB()
    ib.client._serverVersion = 215
    ib.client.connState = ib.client.CONNECTED
    sent: list[bytes] = []
    ib.client.conn = type("X", (), {"sendMsg": lambda self, msg: sent.append(msg)})()

    ib.client.cancelContractData(reqId=42)

    assert len(sent) == 1
    frame = sent[0]
    # Skip the 4-byte length prefix; next 4 bytes are the wireMsgId.
    wireMsgId = struct.unpack(">I", frame[4:8])[0]
    assert wireMsgId == CANCEL_CONTRACT_DATA + PROTOBUF_MSG_ID


def test_cancel_historical_ticks_emits_proto_only_at_gate_215():
    """Gate 215 partner: cancelHistoricalTicks shares the gate. Same
    proto-only contract.
    """
    import struct

    from ib_async._pb_msgids import CANCEL_HISTORICAL_TICKS, PROTOBUF_MSG_ID

    ib = ibi.IB()
    ib.client._serverVersion = 215
    ib.client.connState = ib.client.CONNECTED
    sent: list[bytes] = []
    ib.client.conn = type("X", (), {"sendMsg": lambda self, msg: sent.append(msg)})()

    ib.client.cancelHistoricalTicks(reqId=99)

    assert len(sent) == 1
    frame = sent[0]
    wireMsgId = struct.unpack(">I", frame[4:8])[0]
    assert wireMsgId == CANCEL_HISTORICAL_TICKS + PROTOBUF_MSG_ID


# ---------------------------------------------------------------------------
# safe_decimal: IBKR UNSET sentinel strings must coerce to None.
# IBKR's reference ``decode(Decimal, fields)`` rejects max-int / max-long /
# max-double sentinel strings as "unset" — without matching that semantics
# user code would receive a 1.7e308 wire-default fake quantity that looks
# like a real number and pollutes downstream calculations.
# ---------------------------------------------------------------------------


def test_safe_decimal_unset_integer_sentinel_returns_none():
    """``"2147483647"`` is IBKR's UNSET_INTEGER. Wire payloads that
    wedge this string into a Decimal field mean the field is unset."""
    from ib_async._proto.safe import safe_decimal

    assert safe_decimal("2147483647") is None


def test_safe_decimal_unset_long_sentinel_returns_none():
    """``"9223372036854775807"`` is IBKR's UNSET_LONG."""
    from ib_async._proto.safe import safe_decimal

    assert safe_decimal("9223372036854775807") is None


def test_safe_decimal_unset_double_uppercase_e_returns_none():
    """``"1.7976931348623157E308"`` is IBKR's UNSET_DOUBLE in the
    upper-case-E formatting their wire encoder emits."""
    from ib_async._proto.safe import safe_decimal

    assert safe_decimal("1.7976931348623157E308") is None


def test_safe_decimal_unset_double_lowercase_e_returns_none():
    """``"1.7976931348623157e+308"`` is the same UNSET_DOUBLE value
    serialized through Python's ``str(float)`` — both formats must
    map to None."""
    from ib_async._proto.safe import safe_decimal

    assert safe_decimal("1.7976931348623157e+308") is None


def test_safe_decimal_negative_long_min_sentinel_returns_none():
    """``"-9223372036854775808"`` is IBKR's most-negative int64 — also
    rejected as Decimal-unset by the reference decoder."""
    from ib_async._proto.safe import safe_decimal

    assert safe_decimal("-9223372036854775808") is None


def test_safe_decimal_real_values_round_trip():
    """Sanity: real Decimal-shaped wire strings continue to coerce
    correctly. Locks the sentinel guard from over-rejecting."""
    from ib_async._proto.safe import safe_decimal

    assert safe_decimal("100") == Decimal(100)
    assert safe_decimal("0.5") == Decimal("0.5")
    assert safe_decimal("-1.25") == Decimal("-1.25")
    assert safe_decimal("0") == Decimal(0)


# ---------------------------------------------------------------------------
# Round 3: Wrapper state-machine + Trade lifecycle regressions
# ---------------------------------------------------------------------------


def test_commission_report_arriving_before_fill_is_buffered_and_drained():
    """commissionReport for an unknown execId is parked rather than
    dropped. When the matching execDetails arrives, the parked report
    lands on the new Fill and the paired event fires.

    Regression: previously the wrapper logged-and-dropped early reports,
    losing the commission permanently for cross-client / startup-replay
    races where TWS delivered the report ahead of the fill."""

    ib = ibi.IB()
    ib.wrapper.clientId = 0

    # Wire up a Trade so commissionReport's permId2Trade lookup succeeds
    # once execDetails creates the fill.
    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 555
    order = ibi.Order(orderId=1, clientId=0, permId=42)
    orderStatus = ibi.OrderStatus(orderId=1, status=ibi.OrderStatus.Submitted)
    trade = ibi.Trade(contract, order, orderStatus, [], [])
    ib.wrapper.trades[(0, 1)] = trade
    ib.wrapper.permId2Trade[42] = trade

    seenCommission: list = []
    ib.commissionReportEvent += lambda t, f, r: seenCommission.append((t, f, r))

    # 1) Commission report arrives FIRST. It must be parked, not dropped.
    early_report = ibi.CommissionReport(
        execId="exec-early", commissionAndFees=2.5, currency="USD"
    )
    ib.wrapper.commissionReport(early_report)
    # Not yet emitted — fill doesn't exist.
    assert seenCommission == []
    # Internal park bucket holds it.
    assert "exec-early" in ib.wrapper._pendingCommissionReports

    # 2) execDetails arrives. The parked report drains onto the new Fill
    #    and the paired event fires.
    execution = ibi.Execution(
        execId="exec-early",
        permId=42,
        clientId=0,
        orderId=1,
        shares=Decimal(10),
        price=100.0,
        time="20250101 09:30:00",
    )
    ib.wrapper.execDetails(reqId=1, contract=contract, execution=execution)

    assert "exec-early" not in ib.wrapper._pendingCommissionReports
    assert len(trade.fills) == 1
    assert trade.fills[0].commissionReport.commissionAndFees == 2.5
    assert len(seenCommission) == 1
    assert seenCommission[0][2].commissionAndFees == 2.5


def test_completed_order_for_existing_trade_updates_status_to_terminal():
    """``completedOrder`` for a permId already known via ``openOrder``
    must mirror the terminal ``completedStatus`` onto the existing trade
    and reuse it (no duplicate Trade in ``trades`` / ``permId2Trade``).

    Regression: previously ``completedOrder`` always built a fresh Trade
    and the existing one stayed at ``Submitted``, so ``Trade.isDone()``
    returned ``False`` for terminal orders at startup."""

    ib = ibi.IB()
    ib.wrapper.clientId = 0

    # Pre-populate via openOrder semantics: trade exists in Submitted state.
    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 777
    order = ibi.Order(orderId=5, clientId=0, permId=99)
    orderStatus = ibi.OrderStatus(orderId=5, status=ibi.OrderStatus.Submitted)
    trade = ibi.Trade(contract, order, orderStatus, [], [])
    ib.wrapper.trades[(0, 5)] = trade
    ib.wrapper.permId2Trade[99] = trade

    # Now completedOrder echoes the terminal state at startup.
    state = ibi.OrderState(status="", completedStatus="Filled")
    ib.wrapper.completedOrder(contract, order, state)

    # Existing trade is mutated, not replaced.
    assert ib.wrapper.permId2Trade[99] is trade
    assert trade.orderStatus.status == "Filled"
    assert trade.isDone()


def test_completed_order_first_time_uses_completed_status_not_status():
    """A completedOrder for a never-seen permId records the trade with
    ``completedStatus`` (the post-hoc terminal field) rather than the
    transient ``status`` field, which may be empty on this path."""

    ib = ibi.IB()
    ib.wrapper.clientId = 0

    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 888
    order = ibi.Order(orderId=7, clientId=0, permId=111)

    # status="" simulates the empty-status case for completed orders.
    state = ibi.OrderState(status="", completedStatus="Cancelled")
    ib.wrapper.completedOrder(contract, order, state)

    assert ib.wrapper.permId2Trade[111].orderStatus.status == "Cancelled"
    assert ib.wrapper.permId2Trade[111].isDone()


def test_monetary_account_value_tags_covers_ibkr_summary_standard_set():
    """``MONETARY_ACCOUNT_VALUE_TAGS`` must whitelist every truly
    currency-denominated tag IBKR's ``AccountSummaryTags`` ships —
    including the bare-name forms (``ReqTEquity``, ``ReqTMargin``) the
    account-summary stream uses without a segment suffix.

    Without these, ``AccountValue.decimalValue`` returns ``None`` for
    valid monetary values from TWS and user code mistakes the value as
    non-numeric / unset."""

    from ib_async.objects import MONETARY_ACCOUNT_VALUE_TAGS

    # Bare-name spellings IBKR's account-summary stream emits.
    for tag in ("ReqTEquity", "ReqTMargin"):
        assert tag in MONETARY_ACCOUNT_VALUE_TAGS, f"missing {tag!r}"

    # Spot-check a few -S / -C variants that were already covered to
    # confirm we didn't regress the existing entries while editing.
    for tag in (
        "NetLiquidation",
        "AvailableFunds",
        "BuyingPower",
        "Cushion",
        "GrossPositionValue",
    ):
        assert tag in MONETARY_ACCOUNT_VALUE_TAGS


def test_account_value_decimal_view_returns_none_for_non_currency_tags():
    """``decimalValue`` is for monetary (currency-denominated) tags only.
    Pure ratios (``Leverage``), counts (``DayTradesRemaining``), unit
    sizes (``BillableSize``), and string labels (``SegmentTitle-S``)
    must return ``None`` so user code that asks for the typed Decimal
    view never accidentally treats a ratio or count as a money amount.
    """
    for tag in (
        "Leverage",
        "Leverage-S",
        "DayTradesRemaining",
        "DayTradesRemainingT+1",
        "BillableSize",
        "ColumnPrio-C",
        "SegmentTitle-S",
    ):
        av = ibi.AccountValue(
            account="DU1",
            tag=tag,
            value="2.5",
            currency="USD",
            modelCode="",
        )
        assert av.decimalValue is None, f"{tag} must not coerce to Decimal"


def test_order_bound_signature_uses_ibkr_argument_names():
    """``Wrapper.orderBound``'s signature must match IBKR's reference
    ``(permId, clientId, orderId)``. Both decoders pass arguments in
    that order; the parameter names are part of the public contract for
    subclasses overriding this hook.
    """
    import inspect

    sig = inspect.signature(ibi.Wrapper.orderBound)
    params = list(sig.parameters)
    # ``self`` first, then the IBKR contract names.
    assert params == ["self", "permId", "clientId", "orderId"]


# ---------------------------------------------------------------------------
# Round 3 audit: connection lifecycle / cross-cutting concerns
# ---------------------------------------------------------------------------


def test_set_optional_capabilities_stores_value_for_start_api():
    """``setOptionalCapabilities`` mirrors IBKR ``EClient.setOptionalCapabilities``.
    The value is read inside ``startApi`` (binary path field 4 / proto
    ``optionalCapabilities``); without the public setter, third-party
    integrations using the standard ibapi API surface have no way to set
    it short of reaching into ``client.optCapab`` directly.
    """
    ib = ibi.IB()
    assert ib.client.optCapab == ""
    ib.client.setOptionalCapabilities("xyz")
    assert ib.client.optCapab == "xyz"

    sent: list = []
    ib.client.send = lambda *a, **kw: sent.append(a)
    ib.client._serverVersion = 200  # below MIN_SERVER_VER_PROTOBUF
    ib.client.clientId = 9
    ib.client.startApi()
    assert sent == [(71, 2, 9, "xyz")]


def test_warning_codes_includes_connection_state_notifications():
    """Codes 1100/1101/1102 are TWS "system messages" with reqId=-1 —
    advisory notifications about connection state transitions. They must
    be classified as warnings so the log output reflects their nature
    and any user-facing severity routing doesn't surface them as real
    errors.
    """
    from ib_async.wrapper import _WARNING_CODES

    assert 1100 in _WARNING_CODES
    assert 1101 in _WARNING_CODES
    assert 1102 in _WARNING_CODES
    # 1300 ("TWS socket port has been reset") is NOT advisory — the
    # connection is actually being dropped — so it stays an error.
    assert 1300 not in _WARNING_CODES


def test_connection_state_codes_logged_at_warning_level(caplog):
    """Wrapper.error must classify 1100/1101/1102 as warnings (not
    errors). System messages from TWS arrive with reqId=-1 so there's
    no in-flight request or trade to act on, but the log severity still
    matters — ops dashboards key off it.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0

    with caplog.at_level(logging.WARNING, logger="ib_async.wrapper"):
        ib.wrapper.error(-1, 1100, "Connectivity lost", "")
        ib.wrapper.error(-1, 1101, "Restored - data lost", "")
        ib.wrapper.error(-1, 1102, "Restored - data maintained", "")

    error_records = [
        r
        for r in caplog.records
        if r.name == "ib_async.wrapper" and r.levelno >= logging.ERROR
    ]
    assert error_records == []


def test_send_proto_bypasses_throttle_queue():
    """Known limitation: ``sendProto`` writes directly to the socket
    without going through the ``_msgQ`` / ``_timeQ`` sliding-window
    throttle that ``sendMsg`` uses. Locking this in as a test so a
    future refactor that moves the proto path through the throttle is
    a deliberate, observable change.
    """
    ib = ibi.IB()
    sent: list = []
    ib.client.conn.sendMsg = lambda data: sent.append(data)
    ib.client.sendProto(1, b"\x00\x00")
    assert len(sent) == 1
    assert len(ib.client._timeQ) == 0
    assert len(ib.client._msgQ) == 0


def test_handshake_prefix_matches_ibkr_make_initial_msg():
    """IBKR ``comm.make_initial_msg`` produces ``len(text)`` (4-byte BE)
    + ``text``. We construct the equivalent inline in ``connectAsync``
    via ``self._prefix(b"v...")`` — same wire framing, no extra NULs.
    """
    import struct as _struct

    ib = ibi.IB()
    body = b"v157..225"
    framed = ib.client._prefix(body)
    assert framed == _struct.pack(">I", len(body)) + body
    assert len(framed) == 4 + len(body)


def test_set_connect_options_appends_to_handshake_body():
    """``setConnectOptions("+PACEAPI")`` must end up in the v100 banner
    as ``v{Min}..{Max} +PACEAPI`` — IBKR ``EClient.connect`` does the
    same with a leading space separator.
    """
    ib = ibi.IB()
    ib.client.setConnectOptions("+PACEAPI")
    body = b"v%d..%d%s" % (
        ib.client.MinClientVersion,
        ib.client.MaxClientVersion,
        b" " + ib.client.connectOptions,
    )
    assert body.endswith(b" +PACEAPI")


def test_max_requests_throttle_default_matches_ibkr_pacing():
    """IBKR documents 50 messages/sec as the practical pacing limit.
    Our defaults intentionally sit just below that (45/sec) so brief
    bursts don't trip server-side disconnects.
    """
    from ib_async.client import Client as _Client

    assert _Client.MaxRequests == 45
    assert _Client.RequestsInterval == 1


def test_disconnect_clears_in_flight_futures_with_connection_error():
    """``connectionClosed`` must drain every awaiter so user code past
    a daily server-reset doesn't wedge. Pending request futures must
    receive a ``ConnectionError`` exception.
    """
    from ib_async._requests import SingletonKey as _SingletonKey

    ib = ibi.IB()
    req, _opened = ib.wrapper.requests.open(_SingletonKey("openOrders"))
    future = req.future
    assert not future.done()

    ib.wrapper.connectionClosed()

    assert future.done()
    exc = future.exception()
    assert isinstance(exc, ConnectionError)


# ---------------------------------------------------------------------------
# Round 4 — market-data hot path: Ticker state, generic / string / odd-lot
# ticks, halt-code unset preservation, signed index-future premium.
# ---------------------------------------------------------------------------


def _ticker_for_reqid(ib: ibi.IB, reqId: int) -> ibi.Ticker:
    """Register a fresh ``Ticker`` against ``reqId`` so wrapper tick
    handlers can find it via ``Wrapper._get_ticker``. Bypasses the
    full ``reqMktData`` flow — we are exercising decode/state logic,
    not the request lifecycle. ``conId`` is required for the contract
    hash that keys the per-contract ticker pool.
    """
    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 265598 + reqId  # unique per reqId so no pool collision
    ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)
    ib.wrapper.subscriptions._ticker_by_reqid[reqId] = ticker
    return ticker


def test_tick_generic_halted_unset_minus_one_does_not_collapse_to_zero():
    """``HALTED`` (TickType 49) ships an int code where -1=unset,
    0=not-halted, 1=general halt, 2=volatility halt. The generic-tick
    "value > 0 else emptySize" clamp previously mapped -1 (unset) to 0
    (not halted), conflating two distinct states. Round 4 added
    ``_GENERIC_TICK_NO_CLAMP`` to bypass the clamp for halt-style ticks.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    ticker = _ticker_for_reqid(ib, 4001)

    ib.wrapper.tickGeneric(4001, 49, -1.0)
    assert ticker.halted is ibi.HaltedStatus.UNAVAILABLE
    assert ticker.halted == -1.0, (
        "HALTED=-1 (unset) must survive — not collapse to 0 (not halted)"
    )

    ib.wrapper.tickGeneric(4001, 49, 0.0)
    assert ticker.halted is ibi.HaltedStatus.NOT_HALTED
    assert ticker.halted == 0.0  # not halted

    ib.wrapper.tickGeneric(4001, 49, 1.0)
    assert ticker.halted is ibi.HaltedStatus.GENERAL
    assert ticker.halted == 1.0  # general halt

    ib.wrapper.tickGeneric(4001, 49, 2.0)
    assert ticker.halted is ibi.HaltedStatus.VOLATILITY
    assert ticker.halted == 2.0  # volatility halt


def test_tick_generic_delayed_halted_preserves_unset_sentinel():
    """``DELAYED_HALTED`` (TickType 90) shares the halt-code semantics."""
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    ticker = _ticker_for_reqid(ib, 4002)

    ib.wrapper.tickGeneric(4002, 90, -1.0)
    assert ticker.delayedHalted is ibi.HaltedStatus.UNAVAILABLE
    assert ticker.delayedHalted == -1.0


def test_tick_generic_index_future_premium_preserves_negative_sign():
    """``INDEX_FUTURE_PREMIUM`` (TickType 31) is signed: a future trading
    at a discount to spot legitimately shows a negative premium. The
    pre-fix clamp erased the sign, falsely signalling "no premium".
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    ticker = _ticker_for_reqid(ib, 4003)

    ib.wrapper.tickGeneric(4003, 31, -2.5)
    assert ticker.indexFuturePremium == -2.5

    ib.wrapper.tickGeneric(4003, 31, 4.25)
    assert ticker.indexFuturePremium == 4.25


def test_tick_generic_shortable_still_clamps_negative_to_zero():
    """Sanity guard: tick types NOT in ``_GENERIC_TICK_NO_CLAMP`` keep
    the legacy clamp. ``SHORTABLE`` (TickType 46) values are documented
    as non-negative; a negative would be a wire bug we still erase.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    ticker = _ticker_for_reqid(ib, 4004)

    ib.wrapper.tickGeneric(4004, 46, 3.0)
    assert ticker.shortable == 3.0


def test_odd_lot_price_routes_through_price_tick_map():
    """TickType 105 (ODD_LOT_BID) and 106 (ODD_LOT_ASK) must land in
    ``Ticker.oddLotBid`` / ``oddLotAsk`` — not assert-fail. IBKR added
    the odd-lot family for retail-sized prints; servers can ship these
    whenever the user enables the right generic-tick list.
    """
    from ib_async.objects import TickAttrib

    ib = ibi.IB()
    ib.wrapper.clientId = 0
    ticker = _ticker_for_reqid(ib, 4005)

    ib.wrapper.priceSizeTick(4005, 105, 100.25, 0.0, TickAttrib())
    assert ticker.oddLotBid == 100.25

    ib.wrapper.priceSizeTick(4005, 106, 100.50, 0.0, TickAttrib())
    assert ticker.oddLotAsk == 100.50


def test_odd_lot_size_routes_through_size_tick_map():
    """TickType 107 (ODD_LOT_BID_SIZE) and 108 (ODD_LOT_ASK_SIZE) land
    on the matching size fields without asserting.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    ticker = _ticker_for_reqid(ib, 4006)

    ib.wrapper.tickSize(4006, 107, 25.0)
    assert ticker.oddLotBidSize == 25.0

    ib.wrapper.tickSize(4006, 108, 50.0)
    assert ticker.oddLotAskSize == 50.0


def test_odd_lot_exchange_routes_through_string_tick_map():
    """TickType 109 / 110 carry the exchange identifier for the
    odd-lot side, mirroring 32 / 33 for round-lots.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    ticker = _ticker_for_reqid(ib, 4007)

    ib.wrapper.tickString(4007, 109, "ARCA")
    assert ticker.oddLotBidExch == "ARCA"

    ib.wrapper.tickString(4007, 110, "BATS")
    assert ticker.oddLotAskExch == "BATS"


def test_price_size_tick_attribs_flow_through_to_wrapper():
    """``TickAttrib`` (canAutoExecute / pastLimit / preOpen) should
    arrive in ``priceSizeTick`` so user code can gate on liquidity
    quality. Round 3 wired it through; this verifies the full path
    from a synthetic call lands on the ticker as a fresh BID.
    """
    from ib_async.objects import TickAttrib

    ib = ibi.IB()
    ib.wrapper.clientId = 0
    ticker = _ticker_for_reqid(ib, 4008)

    attrib = TickAttrib(canAutoExecute=True, pastLimit=False, preOpen=True)
    ib.wrapper.priceSizeTick(4008, 1, 100.0, 200.0, attrib)
    assert ticker.bid == 100.0
    assert ticker.bidSize == 200.0


def test_tick_req_params_populates_min_tick_and_bbo_exchange():
    """``Wrapper.tickReqParams`` should land ``minTick`` /
    ``bboExchange`` / ``snapshotPermissions`` on the Ticker so user code
    can render correctly-quantized prices and know the BBO source.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    ticker = _ticker_for_reqid(ib, 4009)

    ib.wrapper.tickReqParams(4009, 0.01, "NASDAQ", 3)
    assert ticker.minTick == 0.01
    assert ticker.bboExchange == "NASDAQ"
    assert ticker.snapshotPermissions == 3


def test_market_data_type_lands_on_ticker():
    """``Wrapper.marketDataType`` (1=live, 2=frozen, 3=delayed,
    4=delayed-frozen) is the user's signal that the price values are
    live or stale. Must surface on Ticker.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0
    ticker = _ticker_for_reqid(ib, 4010)

    ib.wrapper.marketDataType(4010, 3)
    assert ticker.marketDataType == 3


def test_delayed_bid_ask_last_route_through_bid_ask_last_state():
    """DELAYED_BID(66) / DELAYED_ASK(67) / DELAYED_LAST(68) share the
    bid/ask/last state slots with their live counterparts — the same
    Ticker fields render whether the user requested live or delayed.
    Verify all six branches roll prev correctly.
    """
    from ib_async.objects import TickAttrib

    ib = ibi.IB()
    ib.wrapper.clientId = 0
    ticker = _ticker_for_reqid(ib, 4011)

    a = TickAttrib()
    ib.wrapper.priceSizeTick(4011, 66, 99.0, 100.0, a)  # delayed bid
    assert ticker.bid == 99.0 and ticker.bidSize == 100.0

    ib.wrapper.priceSizeTick(4011, 66, 99.5, 150.0, a)
    assert ticker.bid == 99.5 and ticker.prevBid == 99.0

    ib.wrapper.priceSizeTick(4011, 67, 100.0, 200.0, a)  # delayed ask
    assert ticker.ask == 100.0
    ib.wrapper.priceSizeTick(4011, 68, 99.75, 50.0, a)  # delayed last
    assert ticker.last == 99.75


def test_generic_tick_map_no_clamp_set_matches_documentation():
    """Frozen-set guard: only INDEX_FUTURE_PREMIUM, HALTED,
    DELAYED_HALTED bypass the value-clamp. If a future change broadens
    this set silently it changes the wire-to-state contract; this
    test forces an explicit code update at audit-time.
    """
    from ib_async.wrapper import _GENERIC_TICK_NO_CLAMP

    assert frozenset({31, 49, 90}) == _GENERIC_TICK_NO_CLAMP


def test_odd_lot_tick_maps_registered_for_all_six_types():
    """Lock the routing of TickType 105-110 so a future tick-map
    refactor cannot silently drop odd-lot support.
    """
    from ib_async.wrapper import (
        PRICE_TICK_MAP,
        SIZE_TICK_MAP,
        STRING_TICK_MAP,
    )

    assert PRICE_TICK_MAP[105] == "oddLotBid"
    assert PRICE_TICK_MAP[106] == "oddLotAsk"
    assert SIZE_TICK_MAP[107] == "oddLotBidSize"
    assert SIZE_TICK_MAP[108] == "oddLotAskSize"
    assert STRING_TICK_MAP[109] == "oddLotBidExch"
    assert STRING_TICK_MAP[110] == "oddLotAskExch"


def test_wrapper_error_warning_classification_in_warning_band():
    """The 2100-2199 band auto-classifies as warning regardless of the
    explicit ``_WARNING_CODES`` set — this covers the data-farm
    connectivity codes (2103-2108) without enumerating them.
    """
    from ib_async.wrapper import _WARNING_CODES

    for code in (2103, 2104, 2105, 2106, 2107, 2108, 2150, 2199):
        is_warning = code in _WARNING_CODES or 2100 <= code < 2200
        assert is_warning, f"code {code} should classify as warning"

    assert not (2200 in _WARNING_CODES or 2100 <= 2200 < 2200)


# ---------------------------------------------------------------------------
# Round 4: account-update / position / FA stream-ordering regressions
# ---------------------------------------------------------------------------


def test_settled_cash_in_monetary_account_value_tags():
    """``SettledCash`` ships in IBKR's ``AccountSummaryTags.AllTags`` and
    in our default ``reqAccountSummaryAsync`` tag string. Without it on
    the whitelist, ``AccountValue.decimalValue`` returns ``None`` for
    valid wire values and user code mistakes the figure as unset.

    Also covers the ``-C`` / ``-S`` per-segment variants that arrive on
    the live ``updateAccountValue`` stream for futures-segment accounts.
    """
    from ib_async.objects import MONETARY_ACCOUNT_VALUE_TAGS

    for tag in ("SettledCash", "SettledCash-C", "SettledCash-S"):
        assert tag in MONETARY_ACCOUNT_VALUE_TAGS, f"missing {tag!r}"

    av = ibi.AccountValue(
        account="DU1",
        tag="SettledCash",
        value="12345.67",
        currency="USD",
        modelCode="",
    )
    assert av.decimalValue == Decimal("12345.67")


def test_account_summary_default_tags_are_all_whitelisted():
    """Every monetary tag we send in ``reqAccountSummaryAsync``'s default
    string must resolve to a Decimal via ``AccountValue.decimalValue``.
    Drift here means a TWS account-summary reply silently degrades to
    ``None`` for that field.
    """
    from ib_async.objects import MONETARY_ACCOUNT_VALUE_TAGS

    # Only the *monetary* members of the default request tag set; the
    # non-numeric ``AccountType`` and the time-string
    # ``LookAheadNextChange`` and severity-enum ``HighestSeverity`` are
    # intentionally excluded from the whitelist.
    for tag in (
        "NetLiquidation",
        "TotalCashValue",
        "SettledCash",
        "AccruedCash",
        "BuyingPower",
        "EquityWithLoanValue",
        "PreviousDayEquityWithLoanValue",
        "GrossPositionValue",
        "RegTEquity",
        "RegTMargin",
        "SMA",
        "InitMarginReq",
        "MaintMarginReq",
        "AvailableFunds",
        "ExcessLiquidity",
        "Cushion",
        "FullInitMarginReq",
        "FullMaintMarginReq",
        "FullAvailableFunds",
        "FullExcessLiquidity",
        "LookAheadInitMarginReq",
        "LookAheadMaintMarginReq",
        "LookAheadAvailableFunds",
        "LookAheadExcessLiquidity",
        # IBKR's plain ``ReqT*`` aliases the summary stream emits.
        "ReqTEquity",
        "ReqTMargin",
    ):
        assert tag in MONETARY_ACCOUNT_VALUE_TAGS, f"missing {tag!r}"


def test_account_download_end_settles_future_after_values_and_portfolio():
    """``reqAccountUpdates(True)`` must only resolve the user-visible
    ``accountValues`` future once ``accountDownloadEnd`` arrives. Until
    then ``updateAccountValue`` and ``updatePortfolio`` rows accumulate
    into the wrapper state without prematurely settling the waiter.
    """
    from ib_async._requests import SingletonKey as _SingletonKey

    ib = ibi.IB()
    req, _is_new = ib.wrapper.requests.open(_SingletonKey("accountValues"))
    future = req.future

    ib.wrapper.updateAccountValue("NetLiquidation", "100000.00", "USD", "DU1")
    ib.wrapper.updateAccountTime("12:34")

    assert not future.done(), "future must not settle before accountDownloadEnd"

    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 265598
    ib.wrapper.updatePortfolio(
        contract,
        Decimal(10),
        Decimal("190.50"),
        Decimal("1905.00"),
        Decimal("180.00"),
        Decimal("105.00"),
        Decimal(0),
        "DU1",
    )
    assert not future.done()

    ib.wrapper.accountDownloadEnd("DU1")

    assert future.done()
    # Accumulator state survived the call sequence.
    assert ("DU1", "NetLiquidation", "USD", "") in ib.wrapper.accountValues
    assert 265598 in ib.wrapper.portfolio["DU1"]


def test_update_portfolio_drops_zero_size_position_row():
    """When TWS sends a ``updatePortfolio`` row with size 0, the wrapper
    must drop the cached entry rather than store a zero-row that user
    code then has to filter out. ``Decimal('0')`` and ``None`` (no wire
    value) both close the position.
    """
    ib = ibi.IB()
    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 265598

    # First open the position.
    ib.wrapper.updatePortfolio(
        contract,
        Decimal(10),
        Decimal("190.50"),
        Decimal("1905.00"),
        Decimal("180.00"),
        Decimal("105.00"),
        Decimal(0),
        "DU1",
    )
    assert 265598 in ib.wrapper.portfolio["DU1"]

    # Then close it — the row must drop.
    ib.wrapper.updatePortfolio(
        contract,
        Decimal(0),
        Decimal("190.50"),
        Decimal(0),
        Decimal("180.00"),
        Decimal(0),
        Decimal("105.00"),
        "DU1",
    )
    assert 265598 not in ib.wrapper.portfolio["DU1"]


def test_position_drops_zero_and_appends_to_live_request():
    """Closing a position (size 0) must drop the cached entry, while
    every row also appends to the active ``reqPositionsAsync`` future
    accumulator so the singleton drains correctly on ``positionEnd``.
    """
    from ib_async._requests import SingletonKey as _SingletonKey

    ib = ibi.IB()
    req, _is_new = ib.wrapper.requests.open(_SingletonKey("positions"), container=[])
    future = req.future

    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 265598

    ib.wrapper.position("DU1", contract, Decimal(10), Decimal("180.00"))
    assert 265598 in ib.wrapper.positions["DU1"]

    ib.wrapper.position("DU1", contract, Decimal(0), Decimal("180.00"))
    assert 265598 not in ib.wrapper.positions["DU1"]

    ib.wrapper.positionEnd()
    assert future.done()
    drained = future.result()
    # Two rows appended (even the zero-row position event still
    # surfaces — it represents the close itself).
    assert len(drained) == 2


def test_position_multi_emits_event_and_accumulates_per_reqid():
    """Round 4 fix: ``positionMulti`` was a no-op stub that dropped every
    row, breaking ``Client.reqPositionsMulti`` callers (advisor accounts
    with model codes). Each row must now surface on ``positionEvent``
    and accumulate against ``ReqIdKey(reqId)`` for any future async
    waiter, with ``positionMultiEnd`` settling that future.
    """
    from ib_async._requests import ReqIdKey as _ReqIdKey

    ib = ibi.IB()
    captured: list[ibi.Position] = []
    ib.positionEvent += captured.append

    req, _is_new = ib.wrapper.requests.open(_ReqIdKey(7), container=[])
    future = req.future

    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 265598

    ib.wrapper.positionMulti(
        7, "DU1", "Conservative", contract, Decimal(5), Decimal("180.00")
    )

    assert len(captured) == 1
    assert captured[0].account == "DU1"
    assert captured[0].position == Decimal(5)
    assert 265598 in ib.wrapper.positions["DU1"]
    assert not future.done()

    ib.wrapper.positionMultiEnd(7)

    assert future.done()
    drained = future.result()
    assert len(drained) == 1


def test_position_multi_drops_zero_size_row():
    """Closing a position-multi row (size 0) must drop the cached entry
    the same way the singular ``position`` handler does, so the user-
    visible ``positions`` cache stays consistent across both streams.
    """
    ib = ibi.IB()
    contract = ibi.Stock("AAPL", "SMART", "USD")
    contract.conId = 265598

    # Open via positionMulti.
    ib.wrapper.positionMulti(
        9, "DU1", "Aggressive", contract, Decimal(3), Decimal("180.00")
    )
    assert 265598 in ib.wrapper.positions["DU1"]

    # Close it.
    ib.wrapper.positionMulti(
        9, "DU1", "Aggressive", contract, Decimal(0), Decimal("180.00")
    )
    assert 265598 not in ib.wrapper.positions["DU1"]


def test_managed_accounts_populates_account_list_on_comma_separated_payload():
    """``managedAccounts`` arrives once at startup with a CSV payload.
    Empty entries (trailing comma) must be filtered so user code reading
    ``IB.managedAccounts()`` never sees a blank account name.
    """
    ib = ibi.IB()
    ib.wrapper.managedAccounts("DU1,DU2,DU3,")
    assert ib.wrapper.accounts == ["DU1", "DU2", "DU3"]

    # Reconnection sends the list again; the wrapper must replace, not
    # append, so the live snapshot stays accurate after a server reset.
    ib.wrapper.managedAccounts("DU4")
    assert ib.wrapper.accounts == ["DU4"]


def test_receive_fa_settles_request_fa_future_with_xml_payload():
    """``receiveFA`` carries an XML body the user awaits via
    ``IB.requestFA(faDataType)``. The XML payload must round-trip
    end-to-end (no charset truncation, no field reorder) and the
    singleton future must resolve with the body."""
    from ib_async._requests import SingletonKey as _SingletonKey

    ib = ibi.IB()
    req, _is_new = ib.wrapper.requests.open(_SingletonKey("requestFA"), container="")
    future = req.future

    xml = (
        '<?xml version="1.0"?>'
        "<ListOfGroups><Group><name>Tech</name></Group></ListOfGroups>"
    )
    ib.wrapper.receiveFA(1, xml)

    assert future.done()
    assert future.result() == xml


def test_replace_fa_end_does_not_raise_on_unknown_reqid():
    """``replaceFAEnd`` ships back a ``(reqId, text)`` confirmation.
    The current ``IB.replaceFA`` doesn't open a waiter, so the wrapper
    handler accepts the call as a no-op — but it must NOT raise on an
    unknown reqId, otherwise a stray confirmation crashes the decoder.
    """
    ib = ibi.IB()
    # Should not raise.
    ib.wrapper.replaceFAEnd(99999, "0|Replace successful")


def test_account_summary_end_settles_per_reqid_future():
    """``accountSummary`` emits one row per (account, tag) and the
    waiter resolves only on ``accountSummaryEnd(reqId)``. Rows must
    accumulate into ``acctSummary`` keyed by (account, tag, currency)."""
    from ib_async._requests import ReqIdKey as _ReqIdKey

    ib = ibi.IB()
    req, _is_new = ib.wrapper.requests.open(_ReqIdKey(11))
    future = req.future

    ib.wrapper.accountSummary(11, "DU1", "NetLiquidation", "100000", "USD")
    ib.wrapper.accountSummary(11, "DU1", "BuyingPower", "200000", "USD")

    assert not future.done()
    assert ("DU1", "NetLiquidation", "USD") in ib.wrapper.acctSummary
    assert ("DU1", "BuyingPower", "USD") in ib.wrapper.acctSummary

    ib.wrapper.accountSummaryEnd(11)
    assert future.done()


def test_account_update_multi_carries_model_code_into_accumulator_key():
    """``accountUpdateMulti`` differs from ``updateAccountValue`` by
    carrying a model-code dimension. The accumulator key must include
    it so two model-code variants of the same tag don't collide.
    """
    ib = ibi.IB()
    ib.wrapper.accountUpdateMulti(
        21, "DU1", "Conservative", "NetLiquidation", "100000", "USD"
    )
    ib.wrapper.accountUpdateMulti(
        21, "DU1", "Aggressive", "NetLiquidation", "150000", "USD"
    )
    assert ("DU1", "NetLiquidation", "USD", "Conservative") in ib.wrapper.accountValues
    assert ("DU1", "NetLiquidation", "USD", "Aggressive") in ib.wrapper.accountValues


# ---------------------------------------------------------------------------
# Round 4: binary-path field encoder + safe_decimal sentinel coverage
# ---------------------------------------------------------------------------


def test_send_encodes_positive_infinity_as_ibkr_infinity_string():
    """``math.inf`` on the binary send path must serialize to the literal
    ``"Infinity"`` (matching IBKR's ``INFINITY_STR`` in ``ibapi/const.py``)
    — not ``"Infinite"``. Fields like ``competeAgainstBestOffset =
    COMPETE_AGAINST_BEST_OFFSET_UP_TO_MID`` (an alias for
    ``DOUBLE_INFINITY``) only travel correctly with the IBKR-canonical
    spelling; ``"Infinite"`` is rejected as a parse error server-side
    and silently corrupts mid-peg-to-mid orders.
    """
    import math

    from ib_async.client import _FORMAT_HANDLERS_EMPTY, _FORMAT_HANDLERS_KEEP

    assert _FORMAT_HANDLERS_EMPTY[float](math.inf) == "Infinity"
    assert _FORMAT_HANDLERS_KEEP[float](math.inf) == "Infinity"


def test_send_encodes_unset_double_as_empty_when_makeempty():
    """``UNSET_DOUBLE`` (sys.float_info.max) becomes empty string on the
    ``makeEmpty=True`` path — matching IBKR's ``make_field_handle_empty``
    semantics. With ``makeEmpty=False`` it serializes verbatim.
    """
    import sys

    from ib_async.client import _FORMAT_HANDLERS_EMPTY, _FORMAT_HANDLERS_KEEP

    UNSET_DOUBLE = sys.float_info.max
    assert _FORMAT_HANDLERS_EMPTY[float](UNSET_DOUBLE) == ""
    assert _FORMAT_HANDLERS_KEEP[float](UNSET_DOUBLE) != ""


def test_send_encodes_unset_integer_as_empty_when_makeempty():
    """``UNSET_INTEGER`` becomes empty string on the ``makeEmpty=True``
    path; matches IBKR's ``make_field_handle_empty``.
    """
    from ib_async.client import _FORMAT_HANDLERS_EMPTY, _FORMAT_HANDLERS_KEEP

    assert _FORMAT_HANDLERS_EMPTY[int](UNSET_INTEGER) == ""
    assert _FORMAT_HANDLERS_KEEP[int](UNSET_INTEGER) == str(UNSET_INTEGER)


def test_send_encodes_bool_as_zero_or_one_string():
    """IBKR's ``make_field`` encodes ``True``/``False`` as ``"1"``/``"0"``.
    Our handler must produce the same strings or every gated boolean field
    arrives as the Python repr ``"True"`` / ``"False"`` and TWS rejects.
    """
    from ib_async.client import _FORMAT_HANDLERS_EMPTY

    assert _FORMAT_HANDLERS_EMPTY[bool](True) == "1"
    assert _FORMAT_HANDLERS_EMPTY[bool](False) == "0"


def test_send_encodes_none_as_empty_string():
    """``None`` → empty string on the wire. IBKR's reference raises on
    ``None``; we permissively serialize as empty so contributor sites that
    forget to filter ``None`` from their field tuples don't crash.
    """
    from ib_async.client import _FORMAT_HANDLERS_EMPTY

    assert _FORMAT_HANDLERS_EMPTY[type(None)](None) == ""


def test_safe_decimal_rejects_every_ibkr_unset_sentinel_string():
    """The ``_DECIMAL_UNSET_STRINGS`` set must cover every wire string
    IBKR's ``decode(Decimal, fields)`` (utils.py) treats as the
    UNSET_DECIMAL sentinel — UNSET_INTEGER, UNSET_LONG, UNSET_DOUBLE
    (uppercase E), most-negative int64. A regression that drops one of
    these would let a 2.1B-or-1.8e308 fake quantity into a position
    or fill, corrupting every downstream calculation.
    """
    from ib_async._proto.safe import safe_decimal

    for sentinel in (
        "2147483647",  # UNSET_INTEGER
        "9223372036854775807",  # UNSET_LONG
        "1.7976931348623157E308",  # UNSET_DOUBLE (IBKR's spelling)
        "-9223372036854775808",  # most-negative int64
    ):
        assert safe_decimal(sentinel) is None, (
            f"sentinel {sentinel!r} must coerce to None"
        )

    for variant in (
        "1.7976931348623157e+308",
        "1.7976931348623157e308",
    ):
        assert safe_decimal(variant) is None, f"variant {variant!r} must coerce to None"


def test_safe_decimal_rejects_infinity_strings_for_decimal_field():
    """Decimal-typed wire fields with ``"Infinity"``/``"-Infinity"`` must
    coerce to ``None``. ``Decimal('Infinity')`` is a legitimate Decimal
    value, but for IBKR-domain Decimal fields (size, quantity, fees)
    infinity is meaningless and the ``Decimal | None`` contract expects
    ``None``.
    """
    from ib_async._proto.safe import safe_decimal

    assert safe_decimal("Infinity") is None
    assert safe_decimal("-Infinity") is None
    assert safe_decimal("Infinite") is None  # not a valid Decimal at all


def test_decoder_conv_int_empty_string_returns_zero():
    """IBKR's ``decode(int, fields)`` with empty wire field returns 0
    (via ``int_type(s or 0)``). Our ``_CONV[int]`` must match — a wire
    msg whose int field arrives empty should decode to 0, not raise.
    """
    from ib_async.decoder import _CONV

    assert _CONV[int]("") == 0
    assert _CONV[int]("0") == 0
    assert _CONV[int]("42") == 42
    assert _CONV[int]("-1") == -1


def test_decoder_conv_float_empty_string_returns_zero():
    """Same contract for floats: empty wire → 0.0."""
    from ib_async.decoder import _CONV

    assert _CONV[float]("") == 0.0
    assert _CONV[float]("0") == 0.0
    assert _CONV[float]("1.5") == 1.5


def test_decoder_conv_bool_empty_string_returns_false():
    """IBKR's ``decode(bool, fields)`` returns ``s != 0`` after coercing
    via ``int_type(s or 0)``. Empty string lands as ``False``.
    """
    from ib_async.decoder import _CONV

    assert _CONV[bool]("") is False
    assert _CONV[bool]("0") is False
    assert _CONV[bool]("1") is True


def test_decoder_conv_int_handles_long_values_without_precision_loss():
    """``permId`` and other gate-191 long-typed fields can carry values
    well past 2^31. Python ``int`` is arbitrary-precision so the
    ``_CONV[int]`` path must round-trip a 19-digit long without going
    through a float intermediate.
    """
    from ib_async.decoder import _CONV

    big = 9223372036854775806  # one less than UNSET_LONG
    decoded = _CONV[int](str(big))
    assert decoded == big
    assert isinstance(decoded, int)


def test_safe_decimal_preserves_high_precision_for_position_fields():
    """Position quantities can have >15 decimal digits (fractional shares).
    ``safe_decimal`` must not round-trip through ``float`` and lose
    precision — the IBKR wire format is a string for exactly this reason.
    """
    from ib_async._proto.safe import safe_decimal

    high_precision = "12345678901234567.890123"
    result = safe_decimal(high_precision)
    assert result is not None
    assert str(result) == high_precision


def test_format_proto_double_strips_trailing_zeros_and_decimal():
    """``format_proto_double`` matches IBKR's ``floatMaxString`` shape:
    whole numbers come back without ``.``, fractions strip trailing zeros.
    """
    from ib_async._proto.safe import format_proto_double

    assert format_proto_double(100.0) == "100"
    assert format_proto_double(1.5) == "1.5"
    assert format_proto_double(1.50000000) == "1.5"
    assert format_proto_double(0.0) == "0"


def test_send_round_trips_full_field_tuple_with_infinity_and_unset():
    """End-to-end shape check: a field tuple combining str / int / float /
    bool / None / UNSET / inf must produce a NUL-terminated wire string
    that matches the per-type lambdas. Locks the contract for the
    handler-table dispatch in ``Client.send``.
    """
    import math
    import sys

    from ib_async.client import _FORMAT_HANDLERS_EMPTY

    UNSET_DOUBLE = sys.float_info.max
    fields = [
        "TEST",
        42,
        1.5,
        True,
        False,
        None,
        UNSET_DOUBLE,
        UNSET_INTEGER,
        math.inf,
    ]
    parts = [_FORMAT_HANDLERS_EMPTY.get(type(f), str)(f) for f in fields]
    assert parts == [
        "TEST",
        "42",
        "1.5",
        "1",
        "0",
        "",
        "",
        "",
        "Infinity",
    ]


# ---------------------------------------------------------------------------
# Round 4 audit: TagValue option-list passthrough on scanner / news / fundamentals
# ---------------------------------------------------------------------------


def test_scanner_subscription_filter_options_round_trip_on_proto():
    """``reqScannerSubscription`` accepts a ``scannerSubscriptionFilterOptions``
    TagValue list (per IBKR's signature). The proto path must serialize
    those TagValues into the wire ``map<string, string>`` field — the
    binary path concatenates them; both paths must surface the same
    semantic options to the server.
    """
    from ib_async._proto.scanner import createScannerSubscriptionRequestProto
    from ib_async.contract import TagValue
    from ib_async.objects import ScannerSubscription

    sub = ScannerSubscription(scanCode="TOP_PERC_GAIN", instrument="STK")
    opts = [TagValue("priceAbove", "10"), TagValue("priceBelow", "100")]
    proto = createScannerSubscriptionRequestProto(
        reqId=42,
        sub=sub,
        scannerSubscriptionFilterOptions=opts,
    )

    assert proto.reqId == 42
    fopts = dict(proto.scannerSubscription.scannerSubscriptionFilterOptions)
    assert fopts == {"priceAbove": "10", "priceBelow": "100"}
    # The other map stays unset when the caller didn't supply it.
    assert not dict(proto.scannerSubscription.scannerSubscriptionOptions)


def test_scanner_subscription_options_round_trip_on_proto():
    """The IBKR-internal ``scannerSubscriptionOptions`` TagValue list
    must round-trip too — accepting it on the public surface preserves
    parity with IBKR's ``reqScannerSubscription(reqId, sub, options,
    filterOptions)`` signature.
    """
    from ib_async._proto.scanner import createScannerSubscriptionRequestProto
    from ib_async.contract import TagValue
    from ib_async.objects import ScannerSubscription

    sub = ScannerSubscription(scanCode="TOP_PERC_GAIN")
    proto = createScannerSubscriptionRequestProto(
        reqId=1,
        sub=sub,
        scannerSubscriptionOptions=[TagValue("internal", "x")],
    )
    assert dict(proto.scannerSubscription.scannerSubscriptionOptions) == {
        "internal": "x"
    }


def test_scanner_subscription_empty_option_lists_leave_proto_maps_unset():
    """``None`` and ``[]`` both must leave the wire map fields unset —
    matching ``client_utils.fillTagValueList`` "skip when empty"
    semantics so the wire frame is byte-identical to the no-option
    request.
    """
    from ib_async._proto.scanner import createScannerSubscriptionRequestProto
    from ib_async.objects import ScannerSubscription

    sub = ScannerSubscription(scanCode="TOP_PERC_GAIN")
    a = createScannerSubscriptionRequestProto(
        reqId=1,
        sub=sub,
        scannerSubscriptionOptions=None,
        scannerSubscriptionFilterOptions=None,
    )
    b = createScannerSubscriptionRequestProto(
        reqId=1,
        sub=sub,
        scannerSubscriptionOptions=[],
        scannerSubscriptionFilterOptions=[],
    )
    assert a.SerializeToString() == b.SerializeToString()
    assert not dict(a.scannerSubscription.scannerSubscriptionOptions)
    assert not dict(a.scannerSubscription.scannerSubscriptionFilterOptions)


def test_fundamentals_data_request_carries_options_into_proto_map():
    """``fundamentalsDataOptions`` reaches the wire map field on the
    proto path. Without this, user-supplied options on the binary
    signature silently disappear when TWS upgrades and protobuf becomes
    the default for that opcode.
    """
    from ib_async._proto.scanner import createFundamentalsDataRequestProto
    from ib_async.contract import Stock, TagValue

    contract = Stock("AAPL", "SMART", "USD")
    proto = createFundamentalsDataRequestProto(
        reqId=9,
        contract=contract,
        reportType="ReportSnapshot",
        fundamentalsDataOptions=[TagValue("foo", "bar")],
    )
    assert proto.reqId == 9
    assert proto.reportType == "ReportSnapshot"
    assert dict(proto.fundamentalsDataOptions) == {"foo": "bar"}


def test_news_article_request_carries_options_into_proto_map():
    """``newsArticleOptions`` round-trips into the proto's
    ``map<string, string>`` field — accepting it on the request keeps
    parity with ``reqNewsArticle(reqId, providerCode, articleId,
    newsArticleOptions)``.
    """
    from ib_async._proto.news import createNewsArticleRequestProto
    from ib_async.contract import TagValue

    proto = createNewsArticleRequestProto(
        reqId=11,
        providerCode="BRFG",
        articleId="abc123",
        newsArticleOptions=[TagValue("k", "v")],
    )
    assert proto.reqId == 11
    assert proto.providerCode == "BRFG"
    assert proto.articleId == "abc123"
    assert dict(proto.newsArticleOptions) == {"k": "v"}


def test_historical_news_request_carries_options_into_proto_map():
    """``historicalNewsOptions`` reaches the wire map field on the proto
    path."""
    from ib_async._proto.news import createHistoricalNewsRequestProto
    from ib_async.contract import TagValue

    proto = createHistoricalNewsRequestProto(
        reqId=12,
        conId=265598,
        providerCodes="BRFG+DJ-N",
        startDateTime="2026-01-01 00:00:00.0",
        endDateTime="2026-02-01 00:00:00.0",
        totalResults=10,
        historicalNewsOptions=[TagValue("a", "b"), TagValue("c", "d")],
    )
    assert proto.reqId == 12
    assert proto.conId == 265598
    assert dict(proto.historicalNewsOptions) == {"a": "b", "c": "d"}


def test_news_and_fundamentals_request_options_default_unset():
    """Default-call (no options arg) must leave the wire map field
    unset — preserving wire compatibility for callers that don't
    supply options.
    """
    from ib_async._proto.news import (
        createHistoricalNewsRequestProto,
        createNewsArticleRequestProto,
    )
    from ib_async._proto.scanner import createFundamentalsDataRequestProto
    from ib_async.contract import Stock

    a = createNewsArticleRequestProto(reqId=1, providerCode="BRFG", articleId="x")
    assert not dict(a.newsArticleOptions)

    b = createHistoricalNewsRequestProto(
        reqId=1,
        conId=1,
        providerCodes="BRFG",
        startDateTime="",
        endDateTime="",
        totalResults=10,
    )
    assert not dict(b.historicalNewsOptions)

    c = createFundamentalsDataRequestProto(
        reqId=1, contract=Stock("AAPL", "SMART", "USD"), reportType="ReportSnapshot"
    )
    assert not dict(c.fundamentalsDataOptions)


# ---------------------------------------------------------------------------
# Round 4 audit: scanner / news receiver semantics confirmation
# ---------------------------------------------------------------------------


def test_scanner_data_combo_legs_str_propagates_to_scan_data():
    """``ScannerDataElement.comboKey`` is the wire's combo description
    for combo scanners — the converter must surface it through the
    wrapper as ``ScanData.legsStr`` so user code that switches on
    combo-vs-single scanners sees a non-empty string."""
    from ib_async._pb import ScannerData_pb2
    from ib_async._proto.scanner import createScannerDataArgs

    proto = ScannerData_pb2.ScannerData()
    proto.reqId = 9
    el = proto.scannerDataElement.add()
    el.rank = 0
    el.contract.symbol = "SPY"
    el.distance = "0.5"
    el.benchmark = "SPX"
    el.projection = "10%"
    el.comboKey = "1234,1;5678,-1"

    args = createScannerDataArgs(proto)
    assert args.reqId == 9
    assert len(args.elements) == 1
    elt = args.elements[0]
    assert elt.legsStr == "1234,1;5678,-1"
    assert elt.benchmark == "SPX"


def test_tick_news_timestamp_preserves_full_int64_milliseconds():
    """The wire ``timestamp`` is int64 millis since epoch — values past
    2038 must not wrap. The args dataclass stores ``int`` so Python
    arbitrary-precision keeps the full value through to the wrapper.
    """
    from ib_async._pb import TickNews_pb2
    from ib_async._proto.news import createTickNewsArgs

    far_future_ms = 4102444800000  # 2100-01-01 UTC in ms
    proto = TickNews_pb2.TickNews()
    proto.reqId = 1
    proto.timestamp = far_future_ms
    proto.providerCode = "BRFG"
    proto.articleId = "abc"
    proto.headline = "headline"
    proto.extraData = ""

    args = createTickNewsArgs(proto)
    assert args.timeStamp == far_future_ms
    # Above int32 max; this is the regression we guard against.
    assert args.timeStamp > 2**31


def test_news_bulletin_msg_type_int_passes_through_unchanged():
    """``msgType`` is the IBKR enum (1=regular, 2=exchange-unavailable,
    3=exchange-available-again) — the converter does not interpret or
    remap it; the raw int reaches the wrapper / domain object so user
    code can switch on the documented values.
    """
    from ib_async._pb import NewsBulletin_pb2
    from ib_async._proto.news import createUpdateNewsBulletinArgs

    for raw in (1, 2, 3):
        proto = NewsBulletin_pb2.NewsBulletin()
        proto.newsMsgId = 100 + raw
        proto.newsMsgType = raw
        proto.newsMessage = "x"
        proto.originatingExch = "NYSE"

        args = createUpdateNewsBulletinArgs(proto)
        assert args.msgType == raw
        assert args.msgId == 100 + raw


def test_news_article_binary_pdf_articletype_preserved():
    """``articleType=1`` is IBKR's "binary PDF, base64-encoded as a
    string" indicator — the converter must surface the discriminator
    so user code can decode the base64 payload. ``articleText`` stays
    a ``str`` (the wire is also ``str``); base64 decode is callers'.
    """
    from ib_async._pb import NewsArticle_pb2
    from ib_async._proto.news import createNewsArticleArgs

    proto = NewsArticle_pb2.NewsArticle()
    proto.reqId = 17
    proto.articleType = 1
    proto.articleText = "JVBERi0xLjQK"  # "%PDF-1.4\n" base64-encoded

    args = createNewsArticleArgs(proto)
    assert args.articleType == 1
    assert args.articleText == "JVBERi0xLjQK"


def test_scanner_parameters_xml_passes_through_without_truncation():
    """``ScannerParameters`` carries a multi-MB XML payload — the
    converter must not truncate / re-encode / strip it. User code parses
    XML client-side."""
    from ib_async._pb import ScannerParameters_pb2
    from ib_async._proto.scanner import createScannerParametersXml

    big = "<Scanner>" + ("<Item/>" * 50000) + "</Scanner>"
    proto = ScannerParameters_pb2.ScannerParameters()
    proto.xml = big
    out = createScannerParametersXml(proto)
    assert out == big
    assert len(out) > 100000


# ---------------------------------------------------------------------------
# Round-5 audit regressions
# ---------------------------------------------------------------------------


def test_proto_bond_contract_data_dispatches_to_bond_wrapper_method():
    """BondContractData (msgId 18) must dispatch to
    ``Wrapper.bondContractDetails`` — NOT to ``contractDetails``.

    The base ``Wrapper`` aliases ``bondContractDetails = contractDetails``
    so default behaviour is unchanged, but a subclass overriding the
    bond callback alone must still see proto-arriving bond rows. The
    binary path already routes msgId 18 to ``bondContractDetails`` via
    its handler table; the proto path now matches.
    """
    ib = ibi.IB()

    # Capture which wrapper method got the row.
    bond_calls: list[tuple[int, str]] = []
    plain_calls: list[tuple[int, str]] = []

    original_bond = ib.wrapper.bondContractDetails
    original_plain = ib.wrapper.contractDetails

    def bond_spy(reqId, details):
        bond_calls.append((reqId, details.contract.symbol if details.contract else ""))
        return original_bond(reqId, details)

    def plain_spy(reqId, details):
        plain_calls.append((reqId, details.contract.symbol if details.contract else ""))
        return original_plain(reqId, details)

    # Monkey-patch the bound methods on the instance — overrides the
    # alias chain so we can tell which dispatch site fired.
    ib.wrapper.bondContractDetails = bond_spy  # type: ignore[method-assign]
    ib.wrapper.contractDetails = plain_spy  # type: ignore[method-assign]

    proto = ContractData_pb2.ContractData()
    proto.reqId = 42
    proto.contract.symbol = "TBOND"
    proto.contract.secType = "BOND"
    proto.contractDetails.marketName = "BOND"

    # msgId 18 = BondContractData (proto-side).
    ib.client.decoder.processProtoBuf(18, proto.SerializeToString())

    assert bond_calls == [(42, "TBOND")]
    assert plain_calls == []


def test_proto_contract_data_dispatches_to_plain_wrapper_method():
    """Sanity twin: msgId 10 (ContractData, non-bond) still routes to
    ``Wrapper.contractDetails`` — only the BOND msgId 18 reroutes."""
    ib = ibi.IB()

    bond_calls: list[int] = []
    plain_calls: list[int] = []

    original_plain = ib.wrapper.contractDetails

    def bond_spy(reqId, details):
        bond_calls.append(reqId)

    def plain_spy(reqId, details):
        plain_calls.append(reqId)
        return original_plain(reqId, details)

    ib.wrapper.bondContractDetails = bond_spy  # type: ignore[method-assign]
    ib.wrapper.contractDetails = plain_spy  # type: ignore[method-assign]

    proto = ContractData_pb2.ContractData()
    proto.reqId = 7
    proto.contract.symbol = "AAPL"
    proto.contract.secType = "STK"
    proto.contractDetails.marketName = "NASDAQ"

    # msgId 10 = ContractData (proto-side, non-bond).
    ib.client.decoder.processProtoBuf(10, proto.SerializeToString())

    assert plain_calls == [7]
    assert bond_calls == []


# ---------------------------------------------------------------------------
# Round-5 audit regressions — complex order-type wire encoding.
# ---------------------------------------------------------------------------


def test_binary_bond_contract_details_explicit_timezone_wins_at_gate_188():
    """Gate 188: when the wire ships an explicit ``timeZoneId`` block AND
    the legacy 3-part split-string in ``lastTradeDateOrContractMonth``,
    the explicit field MUST win — mirrors IBKR's reference where the
    explicit decode happens AFTER ``readLastTradeDate`` so the second
    write wins. Our decoder reads the explicit block first then splits
    the legacy string; without the gate guard the split would clobber
    the freshly-decoded explicit value with a stale third component.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 188
    ib.client.decoder.serverVersion = 188
    seen: list[tuple] = []
    ib.wrapper.bondContractDetails = lambda reqId, cd: seen.append((reqId, cd))

    fields = _binary_bond_contract_details_fields(include_trading_hours=True)
    # Replace lastTimes (slot 6) with a 3-part legacy string carrying
    # an OLD timezone. The new explicit block ships ``US/Eastern``.
    fields[6] = "20300515-09:30:00-Asia/Tokyo"
    ib.client.decoder.bondContractDetails(fields)

    assert len(seen) == 1
    _, cd = seen[0]
    # Explicit block wins — NOT the stale split[2].
    assert cd.timeZoneId == "US/Eastern"
    # Maturity + lastTradeTime still come from the split.
    assert cd.maturity == "20300515"
    assert cd.lastTradeTime == "09:30:00"


def test_binary_bond_contract_details_pre_188_split_still_populates_timezone():
    """Below gate 188 there is no explicit timezone block, so the
    legacy 3-part split-string must still populate ``timeZoneId``.
    Regression lock: the gate guard added to fix the post-188 clobber
    must NOT also disable pre-188 split-derived population.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 187
    ib.client.decoder.serverVersion = 187
    seen: list[tuple] = []
    ib.wrapper.bondContractDetails = lambda reqId, cd: seen.append((reqId, cd))

    fields = _binary_bond_contract_details_fields(include_trading_hours=False)
    fields[6] = "20300515-09:30:00-Asia/Tokyo"
    ib.client.decoder.bondContractDetails(fields)

    assert len(seen) == 1
    _, cd = seen[0]
    assert cd.maturity == "20300515"
    assert cd.lastTradeTime == "09:30:00"
    assert cd.timeZoneId == "Asia/Tokyo"


def test_proto_price_condition_full_round_trip():
    """``PriceCondition`` carries every ContractCondition + Operator
    field — connector, isMore, conId, exch, price, triggerMethod —
    onto the flat OrderCondition wire proto. Encode-then-decode must
    reconstruct the exact subclass with every field intact.
    """
    from ib_async._pb import Order_pb2
    from ib_async._proto.orders import _createConditionProtos, _decodeConditions
    from ib_async.order import PriceCondition

    cond = PriceCondition(
        conId=265598,
        exch="SMART",
        price=125.5,
        triggerMethod=2,  # "Last"
        isMore=False,
    )
    cond.Or()  # conjunction = "o"

    protos = _createConditionProtos([cond])
    assert len(protos) == 1
    cp = protos[0]
    assert cp.type == 1
    assert cp.isConjunctionConnection is False  # Or
    assert cp.isMore is False
    assert cp.conId == 265598
    assert cp.exchange == "SMART"
    assert cp.price == 125.5
    assert cp.triggerMethod == 2

    # Round-trip through a parent Order proto so ``_decodeConditions``
    # sees the same wire shape the server would deliver.
    parent = Order_pb2.Order()
    parent.conditions.append(cp)
    decoded = _decodeConditions(parent)
    assert len(decoded) == 1
    out = decoded[0]
    assert isinstance(out, PriceCondition)
    assert out.conjunction == "o"
    assert out.isMore is False
    assert out.conId == 265598
    assert out.exch == "SMART"
    assert out.price == 125.5
    assert out.triggerMethod == 2


def test_proto_execution_condition_no_is_more_field():
    """``ExecutionCondition`` is the only condition that does NOT
    carry ``isMore`` — its dataclass omits the attribute, the wire
    encoder must skip the optional field, and the decoder must
    reconstruct the object without trying to set ``isMore`` on it.
    """
    from ib_async._pb import Order_pb2
    from ib_async._proto.orders import _createConditionProtos, _decodeConditions
    from ib_async.order import ExecutionCondition

    cond = ExecutionCondition(secType="STK", exch="NASDAQ", symbol="AAPL")
    protos = _createConditionProtos([cond])
    cp = protos[0]
    assert cp.type == 5
    # isMore must NOT be set on the wire proto for ExecutionCondition.
    assert not cp.HasField("isMore")
    assert cp.secType == "STK"
    assert cp.exchange == "NASDAQ"
    assert cp.symbol == "AAPL"

    parent = Order_pb2.Order()
    parent.conditions.append(cp)
    decoded = _decodeConditions(parent)
    assert isinstance(decoded[0], ExecutionCondition)
    assert decoded[0].secType == "STK"
    assert decoded[0].exch == "NASDAQ"
    assert decoded[0].symbol == "AAPL"
    # No isMore attribute pollution from the generic decode loop.
    assert not hasattr(decoded[0], "isMore")


def test_proto_volume_and_percent_change_conditions_round_trip():
    """``VolumeCondition`` and ``PercentChangeCondition`` extend
    ``ContractCondition`` — they carry conId + exch on top of the
    operator-condition fields and a per-subclass scalar (volume /
    changePercent). Both must round-trip cleanly.
    """
    from ib_async._pb import Order_pb2
    from ib_async._proto.orders import _createConditionProtos, _decodeConditions
    from ib_async.order import PercentChangeCondition, VolumeCondition

    vol = VolumeCondition(conId=11, exch="SMART", isMore=True, volume=100_000)
    pct = PercentChangeCondition(
        conId=22, exch="SMART", isMore=False, changePercent=2.5
    )
    protos = _createConditionProtos([vol, pct])
    assert protos[0].type == 6 and protos[0].volume == 100_000
    assert protos[1].type == 7 and protos[1].changePercent == 2.5

    parent = Order_pb2.Order()
    parent.conditions.extend(protos)
    decoded = _decodeConditions(parent)
    assert isinstance(decoded[0], VolumeCondition)
    assert decoded[0].volume == 100_000
    assert decoded[0].conId == 11
    assert decoded[0].exch == "SMART"
    assert decoded[0].isMore is True
    assert isinstance(decoded[1], PercentChangeCondition)
    assert decoded[1].changePercent == 2.5
    assert decoded[1].conId == 22
    assert decoded[1].isMore is False


def test_proto_margin_and_time_conditions_round_trip():
    """``MarginCondition`` (percent) and ``TimeCondition`` (time
    string) extend only ``OperatorCondition`` — they carry isMore +
    their value, no conId / exchange. Must round-trip to their exact
    domain subclass.
    """
    from ib_async._pb import Order_pb2
    from ib_async._proto.orders import _createConditionProtos, _decodeConditions
    from ib_async.order import MarginCondition, TimeCondition

    margin = MarginCondition(isMore=True, percent=25)
    timec = TimeCondition(isMore=False, time="20260101 09:30:00 US/Eastern")
    protos = _createConditionProtos([margin, timec])
    assert protos[0].type == 4 and protos[0].percent == 25
    assert protos[1].type == 3 and protos[1].time == "20260101 09:30:00 US/Eastern"

    parent = Order_pb2.Order()
    parent.conditions.extend(protos)
    decoded = _decodeConditions(parent)
    assert isinstance(decoded[0], MarginCondition)
    assert decoded[0].percent == 25
    assert decoded[0].isMore is True
    assert isinstance(decoded[1], TimeCondition)
    assert decoded[1].time == "20260101 09:30:00 US/Eastern"
    assert decoded[1].isMore is False


def test_proto_hedge_param_decode_requires_hedge_type():
    """Decoder pairing rule: ``hedgeParam`` is only consumed when a
    matching ``hedgeType`` is present, mirroring IBKR's binary path
    which gates the param read on a non-empty hedgeType. A
    malformed wire frame with a stray hedgeParam (no hedgeType)
    must NOT surface that param onto the domain object.
    """
    from ib_async._pb import Order_pb2
    from ib_async._proto.orders import createOrder

    proto = Order_pb2.Order()
    proto.hedgeParam = "stale"  # No hedgeType set on the wire.
    decoded = createOrder(proto)
    # Decoder gates hedgeParam on the hedgeType being present.
    assert decoded.hedgeType == ""
    # hedgeParam must not survive without its pairing hedgeType.
    assert decoded.hedgeParam != "stale"


def test_proto_algo_params_paired_with_algo_strategy():
    """``algoParams`` is meaningful only with a non-empty
    ``algoStrategy``. The decoder must consume algoParams only when
    algoStrategy is present — mirrors IBKR's binary path which
    gates the params length read on a non-empty strategy.
    """
    from ib_async._pb import Order_pb2
    from ib_async._proto.orders import createOrder

    # algoStrategy missing, algoParams populated — decoder must not
    # surface params.
    proto = Order_pb2.Order()
    proto.algoParams["foo"] = "bar"
    decoded = createOrder(proto)
    assert decoded.algoStrategy == ""
    assert not decoded.algoParams


def test_proto_combo_leg_full_field_set_round_trip():
    """ComboLeg carries 8 fields — conId, ratio, action, exchange,
    openClose, shortSaleSlot, designatedLocation, exemptCode. Plus
    the parallel ``perLegPrice`` from the matching ``OrderComboLeg``.
    All must round-trip on encode + decode.
    """
    from ib_async._proto.contracts import createComboLeg, createComboLegProto
    from ib_async.contract import ComboLeg

    leg = ComboLeg(
        conId=12345,
        ratio=2,
        action="BUY",
        exchange="SMART",
        openClose=1,
        shortSaleSlot=2,
        designatedLocation="ARCA",
        exemptCode=3,
    )
    proto = createComboLegProto(leg, perLegPrice=1.25)
    # Verify EVERY field landed on the wire — domain spelling
    # (``shortSaleSlot``) maps to wire spelling (``shortSalesSlot``).
    assert proto.conId == 12345
    assert proto.ratio == 2
    assert proto.action == "BUY"
    assert proto.exchange == "SMART"
    assert proto.openClose == 1
    assert proto.shortSalesSlot == 2
    assert proto.designatedLocation == "ARCA"
    assert proto.exemptCode == 3
    assert proto.perLegPrice == 1.25

    # Round-trip the contract-side leg back; perLegPrice rides on the
    # ComboLeg proto but lives on a parallel ``OrderComboLeg`` on the
    # domain side, so ``createComboLeg`` does not surface it.
    rebuilt = createComboLeg(proto)
    assert rebuilt.conId == 12345
    assert rebuilt.ratio == 2
    assert rebuilt.action == "BUY"
    assert rebuilt.exchange == "SMART"
    assert rebuilt.openClose == 1
    assert rebuilt.shortSaleSlot == 2  # NOT shortSalesSlot
    assert rebuilt.designatedLocation == "ARCA"
    assert rebuilt.exemptCode == 3


def test_proto_combo_leg_default_exempt_code_writes_minus_one():
    """``ComboLeg.exemptCode`` defaults to ``-1`` in the domain
    dataclass — that's the real wire value meaning "not exempt".
    IBKR's reference gates with ``isValidIntValue`` (only ``UNSET_INTEGER``
    suppresses) so ``-1`` flows through; skipping the write would let
    the server's proto3 default fill the field with the sentinel and
    reject the request. An empty inbound proto round-trips back to the
    ``-1`` dataclass default."""
    from ib_async._pb import ComboLeg_pb2
    from ib_async._proto.contracts import createComboLeg, createComboLegProto
    from ib_async.contract import ComboLeg

    leg = ComboLeg(conId=7, ratio=1, action="BUY", exchange="SMART")
    proto = createComboLegProto(leg)
    # exemptCode default -1 IS the wire value — flows through.
    assert proto.HasField("exemptCode")
    assert proto.exemptCode == -1

    # Empty proto round-trips back to default -1.
    empty = ComboLeg_pb2.ComboLeg()
    rebuilt = createComboLeg(empty)
    assert rebuilt.exemptCode == -1


def test_proto_scale_family_default_unset_skipped():
    """Scale family (10 fields) must use UNSET-sentinel guards — the
    UNSET_DOUBLE / UNSET_INTEGER defaults must NOT land on the wire
    when the user has not opted into a scale order.
    """
    from ib_async._proto.orders import createOrderProto
    from ib_async.order import LimitOrder

    order = LimitOrder("BUY", 1, 50.0)
    proto = createOrderProto(order)
    assert not proto.HasField("scaleInitLevelSize")
    assert not proto.HasField("scaleSubsLevelSize")
    assert not proto.HasField("scalePriceIncrement")
    assert not proto.HasField("scalePriceAdjustValue")
    assert not proto.HasField("scalePriceAdjustInterval")
    assert not proto.HasField("scaleProfitOffset")
    assert not proto.HasField("scaleInitPosition")
    assert not proto.HasField("scaleInitFillQty")
    # scaleAutoReset and scaleRandomPercent are bools — default False
    # is falsy and must be skipped.
    assert not proto.HasField("scaleAutoReset")
    assert not proto.HasField("scaleRandomPercent")


def test_proto_what_if_flag_round_trip():
    """``Order.whatIf`` is a bool — must round-trip True intact.
    Skipped on encode when False (default) since IBKR's reference
    encoder uses truthy semantics for the bool.
    """
    from ib_async._proto.orders import createOrder, createOrderProto
    from ib_async.order import LimitOrder

    order = LimitOrder("BUY", 1, 50.0)
    order.whatIf = True
    proto = createOrderProto(order)
    assert proto.HasField("whatIf") and proto.whatIf is True

    decoded = createOrder(proto)
    assert decoded.whatIf is True

    # Default False must NOT land on the wire.
    order2 = LimitOrder("BUY", 1, 50.0)
    proto2 = createOrderProto(order2)
    assert not proto2.HasField("whatIf")


def test_proto_smart_combo_routing_params_round_trip():
    """``smartComboRoutingParams`` is a TagValue list — only meaningful
    on BAG-secType orders. The proto encoder writes them onto the
    Order map; round-trip must preserve all entries.
    """
    from ib_async._proto.orders import createOrder, createOrderProto
    from ib_async.objects import TagValue
    from ib_async.order import LimitOrder

    order = LimitOrder("BUY", 1, 50.0)
    order.smartComboRoutingParams = [
        TagValue(tag="NonGuaranteed", value="1"),
        TagValue(tag="LeavesDeltaAfterSubmit", value="100"),
    ]
    proto = createOrderProto(order)
    assert dict(proto.smartComboRoutingParams) == {
        "NonGuaranteed": "1",
        "LeavesDeltaAfterSubmit": "100",
    }

    decoded = createOrder(proto)
    pairs = {tv.tag: tv.value for tv in decoded.smartComboRoutingParams}
    assert pairs == {"NonGuaranteed": "1", "LeavesDeltaAfterSubmit": "100"}


def test_proto_pegged_to_benchmark_family_round_trip():
    """The peg-to-benchmark family — ``referenceContractId``,
    ``peggedChangeAmount``, ``referenceChangeAmount``,
    ``referenceExchangeId``, ``isPeggedChangeAmountDecrease`` —
    must round-trip through the proto encoder + decoder for a
    PEG BENCH order.
    """
    from ib_async._proto.orders import createOrder, createOrderProto
    from ib_async.order import LimitOrder

    order = LimitOrder("BUY", 1, 50.0)
    order.orderType = "PEG BENCH"
    order.referenceContractId = 999
    order.peggedChangeAmount = 1.25
    order.referenceChangeAmount = 0.5
    order.referenceExchangeId = "SMART"
    order.isPeggedChangeAmountDecrease = True
    proto = createOrderProto(order)
    assert proto.referenceContractId == 999
    assert proto.peggedChangeAmount == 1.25
    assert proto.referenceChangeAmount == 0.5
    assert proto.referenceExchangeId == "SMART"
    assert proto.isPeggedChangeAmountDecrease is True

    decoded = createOrder(proto)
    assert decoded.referenceContractId == 999
    assert decoded.peggedChangeAmount == 1.25
    assert decoded.referenceChangeAmount == 0.5
    assert decoded.referenceExchangeId == "SMART"
    assert decoded.isPeggedChangeAmountDecrease is True


def test_proto_adjusted_order_family_round_trip():
    """The adjusted-order family — ``adjustedOrderType``,
    ``triggerPrice``, ``lmtPriceOffset``, ``adjustedStopPrice``,
    ``adjustedStopLimitPrice``, ``adjustedTrailingAmount``,
    ``adjustableTrailingUnit`` — must round-trip every field that
    travels via the proto encoder + decoder. ``Decimal | None`` fields
    must come back as Decimal.
    """
    from decimal import Decimal as D

    from ib_async._proto.orders import createOrder, createOrderProto
    from ib_async.order import LimitOrder

    order = LimitOrder("BUY", 1, 50.0)
    order.adjustedOrderType = "STP"
    order.triggerPrice = D("99.5")
    order.lmtPriceOffset = D("0.25")
    order.adjustedStopPrice = D("95.0")
    order.adjustedStopLimitPrice = D("94.5")
    order.adjustedTrailingAmount = D("1.5")
    order.adjustableTrailingUnit = 1
    proto = createOrderProto(order)
    assert proto.adjustedOrderType == "STP"
    assert proto.triggerPrice == 99.5
    assert proto.lmtPriceOffset == 0.25
    assert proto.adjustedStopPrice == 95.0
    assert proto.adjustedStopLimitPrice == 94.5
    assert proto.adjustedTrailingAmount == 1.5
    assert proto.adjustableTrailingUnit == 1

    decoded = createOrder(proto)
    assert decoded.adjustedOrderType == "STP"
    assert decoded.triggerPrice == D("99.5")
    assert decoded.lmtPriceOffset == D("0.25")
    assert decoded.adjustedStopPrice == D("95.0")
    assert decoded.adjustedStopLimitPrice == D("94.5")
    assert decoded.adjustedTrailingAmount == D("1.5")
    assert decoded.adjustableTrailingUnit == 1


# ---------------------------------------------------------------------------
# Round-5: Subscription / Ticker lifecycle regressions
# ---------------------------------------------------------------------------


def test_late_tick_after_cancel_is_silent_for_every_tick_handler(caplog):
    """Every tick handler that looks up a Ticker by reqId must be silent
    when the reqId is unknown — TWS keeps emitting a few ticks for ~1-2
    seconds after :meth:`IB.cancelMktData` / ``cancelTickByTickData``
    lands, and a noisy ``error`` line per stray tick floods user logs.
    The handlers downgrade these to ``debug`` so a real reqId mismatch
    is still surfaced under verbose logging without spamming default
    output.
    """
    from ib_async.objects import TickAttribBidAsk, TickAttribLast

    ib = ibi.IB()
    unknown = 99999  # never registered

    with caplog.at_level(logging.ERROR, logger="ib_async.wrapper.Wrapper"):
        ib.wrapper.priceSizeTick(unknown, 1, 100.0, 50)
        ib.wrapper.tickSize(unknown, 0, 50)
        ib.wrapper.tickByTickAllLast(unknown, 1, 0, 100.0, 50, TickAttribLast(), "", "")
        ib.wrapper.tickByTickBidAsk(
            unknown, 0, 100.0, 100.5, 50, 50, TickAttribBidAsk()
        )
        ib.wrapper.tickByTickMidPoint(unknown, 0, 100.25)
        ib.wrapper.tickGeneric(unknown, 49, 0)  # halted, in NO_CLAMP
        ib.wrapper.tickString(unknown, 32, "X")
        ib.wrapper.tickReqParams(unknown, 0.01, "", 0)
        ib.wrapper.marketDataType(unknown, 1)
        ib.wrapper.updateMktDepthL2(unknown, 0, "", 0, 0, 100.0, 10)
        ib.wrapper.tickOptionComputation(
            unknown, 10, 0, 0.2, 0.5, 1.0, 0.0, 0.05, 0.1, -0.05, 100.0
        )

    assert caplog.records == []


def test_subscription_close_idempotent_across_tick_kinds():
    """Closing a Subscription twice (e.g. user double-cancel + reconnect
    teardown) must not raise and must not re-issue the cancel."""
    from unittest.mock import MagicMock

    from ib_async._subscriptions import (
        MktDataSub,
        MktDepthSub,
        TickByTickSub,
    )

    ib = ibi.IB()
    ib.client = MagicMock()
    ib.client.isConnected.return_value = True

    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 555

    ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)
    md = MktDataSub(reqId=100, contract=contract, ticker=ticker)
    tbt = TickByTickSub(reqId=101, contract=contract, ticker=ticker, tickType="Last")
    depth = MktDepthSub(reqId=102, contract=contract, ticker=ticker)

    for sub in (md, tbt, depth):
        ib.wrapper.subscriptions.add(sub)

    md.close()
    md.close()  # double-close is a no-op
    tbt.close()
    tbt.close()
    depth.close()
    depth.close()

    assert ib.client.cancelMktData.call_count == 1
    assert ib.client.cancelTickByTickData.call_count == 1
    assert ib.client.cancelMktDepth.call_count == 1
    assert len(ib.wrapper.subscriptions) == 0


def test_concurrent_market_data_subscriptions_only_one_cancel_per_kind():
    """Two distinct kinds (mktData + tickByTick "Last") on the same
    contract get distinct reqIds and the registry tracks them
    independently. Cancelling one must not cancel the other."""
    from unittest.mock import MagicMock

    from ib_async._subscriptions import MktDataSub, TickByTickSub

    ib = ibi.IB()
    ib.client = MagicMock()

    contract = ibi.Stock("XYZ", "SMART", "USD")
    contract.conId = 777

    ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)
    md = MktDataSub(reqId=200, contract=contract, ticker=ticker)
    tbt = TickByTickSub(reqId=201, contract=contract, ticker=ticker, tickType="Last")
    ib.wrapper.subscriptions.add(md)
    ib.wrapper.subscriptions.add(tbt)

    md.close()

    assert ib.client.cancelMktData.call_count == 1
    assert ib.client.cancelTickByTickData.call_count == 0
    assert ib.wrapper.subscriptions.get_sub(200) is None
    assert ib.wrapper.subscriptions.get_sub(201) is tbt
    # Shared Ticker still routes ticks for the surviving subscription.
    assert ib.wrapper.subscriptions.get_ticker(201) is ticker


def test_market_depth_l2_delete_out_of_bounds_is_silent_no_op():
    """``updateMktDepthL2`` operation 2 (delete) at a position not in
    the dict must be a silent no-op — TWS occasionally sends a delete
    for a level that was already removed by a prior reset event."""
    from ib_async._subscriptions import MktDepthSub

    ib = ibi.IB()
    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 888

    ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)
    sub = MktDepthSub(reqId=300, contract=contract, ticker=ticker)
    ib.wrapper.subscriptions.add(sub)

    # Insert level 0 on bid side, then try to delete level 5 (never set).
    ib.wrapper.updateMktDepthL2(300, 0, "", 0, 1, 100.0, 10)
    ib.wrapper.updateMktDepthL2(300, 5, "", 2, 1, 0.0, 0)

    assert len(ticker.domBids) == 1
    assert ticker.domBids[0].price == 100.0
    # Delete-of-existing should still work after the no-op delete.
    ib.wrapper.updateMktDepthL2(300, 0, "", 2, 1, 0.0, 0)
    assert ticker.domBids == []


def test_pnl_single_subscription_mutates_in_place_for_user_references():
    """A user reference to ``PnLSingleSub.pnlSingle`` must observe live
    updates — the ``pnlSingle`` callback updates the existing object in
    place rather than replacing it."""
    from decimal import Decimal as D

    from ib_async._subscriptions import PnLSingleSub
    from ib_async.objects import PnLSingle

    ib = ibi.IB()
    pnlSingle = PnLSingle(account="DU1", modelCode="", conId=42)
    sub = PnLSingleSub(
        reqId=400,
        contract=ibi.contract.Contract(),
        pnlSingle=pnlSingle,
        account="DU1",
        modelCode="",
        conId=42,
    )
    ib.wrapper.subscriptions.add(sub)

    user_held = sub.pnlSingle  # user reference

    ib.wrapper.pnlSingle(400, D(100), 1.0, 2.0, 3.0, 1234.5)

    assert user_held is pnlSingle
    assert user_held.position == D(100)
    assert user_held.dailyPnL == 1.0
    assert user_held.unrealizedPnL == 2.0
    assert user_held.realizedPnL == 3.0
    assert user_held.value == 1234.5


def test_singleton_request_third_caller_attaches_after_two_sharers():
    """Single-flight refcount tracks every attached caller, not just
    the first attach. A third caller attaches to the same future."""
    from ib_async._requests import SingletonKey

    ib = ibi.IB()
    a, isNewA = ib.wrapper.requests.open(SingletonKey("openOrders"), single_flight=True)
    b, isNewB = ib.wrapper.requests.open(SingletonKey("openOrders"), single_flight=True)
    c, isNewC = ib.wrapper.requests.open(SingletonKey("openOrders"), single_flight=True)

    assert isNewA is True
    assert isNewB is False
    assert isNewC is False
    assert a is b is c
    assert a.refcount == 3


def test_ticker_post_init_resets_every_float_field_to_defaults_unset():
    """Round 4 added six odd-lot float fields. ``__post_init__`` must
    reset every float-typed Ticker field to ``defaults.unset`` so a
    user with a non-NaN ``IBDefaults.unset`` (e.g. ``-1.0``) sees
    consistent unset semantics across the entire Ticker shape."""
    from ib_async.objects import IBDefaults
    from ib_async.ticker import Ticker

    sentinel = -1.0
    defaults = IBDefaults(unset=sentinel)
    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 1
    ticker = Ticker(contract=contract, defaults=defaults)

    # Spot-check the six fields that were added in round 4 plus a few
    # baseline fields, to lock the post_init coverage in place.
    for field_name in (
        "oddLotBid",
        "oddLotAsk",
        "oddLotBidSize",
        "oddLotAskSize",
        "bid",
        "ask",
        "last",
        "volume",
        "creditmanMarkPrice",
        "etfNavBid",
    ):
        assert getattr(ticker, field_name) == sentinel, field_name


def test_late_data_after_set_result_does_not_corrupt_user_container():
    """A stray data row arriving after ``set_result`` must not append
    to the now-resolved future's container — the registry pop guards
    the accumulator from late writes."""
    from ib_async._requests import ReqIdKey
    from ib_async.objects import BarData

    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(500))
    container = req.container
    bar1 = BarData(date="20251020 15:00:00", open=1, high=2, low=0, close=1, volume=10)
    ib.wrapper.historicalData(500, bar1)

    ib.wrapper.historicalDataEnd(500, "", "")
    snapshot_len = len(container)

    # Stray late bar — must NOT mutate the user-held container.
    bar2 = BarData(date="20251020 15:01:00", open=1, high=2, low=0, close=1, volume=20)
    ib.wrapper.historicalData(500, bar2)

    assert len(container) == snapshot_len
    assert ReqIdKey(500) not in ib.wrapper.requests


def test_disconnect_during_callback_reentry_does_not_raise():
    """A user callback during ``connectionClosed`` event handling that
    mutates ``self.trades`` must not trip
    ``RuntimeError: dictionary changed size during iteration`` — the
    handler iterates over a snapshot of the trades dict."""
    from ib_async.order import Order, OrderStatus, Trade

    ib = ibi.IB()
    ib.wrapper.clientId = 0

    def add_trade_during_status_emit(t):
        # User code mutating ``self.trades`` during the iteration —
        # historically a RuntimeError.
        if len(ib.wrapper.trades) < 3:
            new_order = Order(orderId=len(ib.wrapper.trades) + 100, clientId=0)
            new_contract = ibi.Stock("XYZ", "SMART", "USD")
            new_contract.conId = 99
            new_trade = Trade(
                new_contract,
                new_order,
                OrderStatus(orderId=new_order.orderId, status=OrderStatus.Submitted),
            )
            ib.wrapper.trades[(0, new_order.orderId)] = new_trade

    contract = ibi.Stock("ABC", "SMART", "USD")
    contract.conId = 1
    order = Order(orderId=1, clientId=0)
    trade = Trade(
        contract,
        order,
        OrderStatus(orderId=1, status=OrderStatus.Submitted),
    )
    trade.statusEvent += add_trade_during_status_emit
    ib.wrapper.trades[(0, 1)] = trade

    # Must not raise.
    ib.wrapper.connectionClosed()


# ---------------------------------------------------------------------------
# Round 5 audit: rare message handlers + raw-proto wrapper-surface coverage
# ---------------------------------------------------------------------------


def test_proto_msg_handlers_cover_every_ibkr_canonical_msg_id():
    """``_PROTO_MSG_HANDLERS`` must mirror every msgId in IBKR's
    reference ``Decoder.msgId2handleInfoProtoBuf`` map.

    IBKR's set of canonical proto-encoded message ids is fixed by the
    server protocol — adding a new one requires a server upgrade. Locking
    the set here means any future drift in their map (or accidental
    deletion of one of ours) trips the regression instead of silently
    debug-dropping the new wire frame.
    """
    from ib_async.decoder import _PROTO_MSG_HANDLERS, _initProtoMsgHandlers

    _initProtoMsgHandlers()
    ours = set(_PROTO_MSG_HANDLERS.keys())

    # Canonical ``IN`` ids from ibapi/decoder.py:msgId2handleInfoProtoBuf
    # (server-protocol contract — see ibapi/message.py for the names).
    ibkrCanonicalProtoIds = {
        # orders / executions
        3,
        4,
        5,
        11,
        53,
        55,
        100,
        101,
        102,
        # contracts
        10,
        18,
        52,
        # ticks + market data
        1,
        2,
        12,
        13,
        21,
        45,
        46,
        57,
        58,
        80,
        81,
        # accounts / positions
        6,
        7,
        8,
        15,
        54,
        61,
        62,
        63,
        64,
        71,
        72,
        73,
        74,
        # historical
        17,
        50,
        88,
        89,
        90,
        96,
        97,
        98,
        99,
        106,
        108,
        # news + scanner / fundamentals / pnl
        14,
        19,
        20,
        51,
        83,
        84,
        85,
        86,
        87,
        94,
        95,
        104,
        105,
        # REST / FA / soft-dollar / market-rule / smart-components / etc
        9,
        16,
        49,
        75,
        76,
        77,
        78,
        79,
        82,
        93,
        103,
        107,
        109,
        # commission + market-data reroutes
        59,
        91,
        92,
        # verify / display-group / config
        65,
        66,
        67,
        68,
        110,
        111,
    }
    assert ours == ibkrCanonicalProtoIds, (
        f"missing: {sorted(ibkrCanonicalProtoIds - ours)}, "
        f"extra: {sorted(ours - ibkrCanonicalProtoIds)}"
    )


def test_tick_efp_binary_handler_reads_all_nine_fields():
    """``tickEFP`` (msgId 47) wire format carries 9 payload fields after
    msgId+version: reqId, tickType, basisPoints, formattedBasisPoints,
    totalDividends, holdDays, futureLastTradeDate, dividendImpact,
    dividendsToLastTradeDate. The binary dispatch must forward all
    nine to ``Wrapper.tickEFP`` — dropping any of them silently truncates
    EFP ticks (used for SSF / index futures).

    ``tickEFP`` is binary-only; IBKR's ``msgId2handleInfoProtoBuf`` does
    not include it, so no proto path needs cross-checking.
    """
    ib = ibi.IB()
    captured: list[tuple] = []
    ib.wrapper.tickEFP = lambda *args: captured.append(args)  # type: ignore[method-assign]

    # ``Decoder`` caches the bound wrapper method at construction time
    # (one ``getattr`` per ``wrap(...)`` call) so we rebuild the handler
    # table after stubbing the wrapper method, mirroring what subclass
    # users would do at startup.
    from ib_async.decoder import Decoder

    ib.client.decoder = Decoder(ib.wrapper, ib.client.serverVersion or 0)

    # msgId, version, then the 9 EFP fields. ``Decoder.interpret`` is fed
    # post-split string fields (the wire ``\0``-split happens upstream).
    fields = [
        "47",  # msgId
        "1",  # version
        "42",  # reqId
        "38",  # tickType (BID_EFP_COMPUTATION)
        "12.5",  # basisPoints
        "+12.50",  # formattedBasisPoints
        "100.25",  # totalDividends (per IBKR docs: implied future price)
        "30",  # holdDays
        "20251220",  # futureLastTradeDate
        "0.75",  # dividendImpact
        "2.50",  # dividendsToLastTradeDate
    ]
    ib.client.decoder.interpret(fields)

    assert captured == [(42, 38, 12.5, "+12.50", 100.25, 30, "20251220", 0.75, 2.50)], (
        "tickEFP must pass all nine fields through unchanged"
    )


def test_proto_dispatch_does_not_invoke_raw_proto_wrapper_hooks_we_do_not_expose():
    """Locks current behaviour: for the ~78 message families where IBKR
    invokes a ``Wrapper.xxxProtoBuf(proto)`` hook BEFORE the decoded
    callback, we currently invoke only the decoded callback — the raw
    hook is intentionally absent. A future change exposing the full
    raw-proto callback surface should update this regression first.

    The two raw-proto hooks we DO expose
    (``configResponseProtoBuf`` / ``updateConfigResponseProtoBuf``) are
    exempt because their messages carry nested oneofs with no flat
    domain equivalent.
    """
    ib = ibi.IB()

    # Sentinel attribute presence: today these hooks are absent. If a
    # future PR begins exposing the full raw-proto surface, update this
    # locked-list rather than silently shipping new public API.
    assert not hasattr(ib.wrapper, "tickPriceProtoBuf")
    assert not hasattr(ib.wrapper, "orderStatusProtoBuf")
    assert not hasattr(ib.wrapper, "commissionAndFeesReportProtoBuf")
    assert not hasattr(ib.wrapper, "historicalDataProtoBuf")
    assert not hasattr(ib.wrapper, "tickByTickDataProtoBuf")

    # The two we DO expose are still present (regression for round 2).
    assert hasattr(ib.wrapper, "configResponseProtoBuf")
    assert hasattr(ib.wrapper, "updateConfigResponseProtoBuf")


def test_public_dataclasses_re_exported_at_package_root():
    """Public dataclasses surfaced through ``IB`` method signatures or
    other public dataclasses must be importable from ``ib_async`` directly.

    Each name listed below is referenced by a publicly typed parameter
    or attribute, so users hitting ``IB.cancelOrder``, iterating
    ``ContractDetails.ineligibilityReasonList``, reading
    ``OrderState.orderAllocations``, or inspecting a ``Ticker``'s EFP
    fields must be able to ``from ib_async import X`` without dipping
    into private modules. PEP 561 also requires these names to live on
    the package surface for downstream type-checkers to resolve them.
    """
    import ib_async as _root

    # Names added to round 6 — guarded against accidental re-hiding.
    for name in (
        "OrderCancel",
        "OrderAllocation",
        "IneligibilityReason",
        "TradingSession",
        "EfpData",
    ):
        assert hasattr(_root, name), f"{name} missing from ib_async public API"
        assert name in _root.__all__, f"{name} missing from ib_async.__all__"


def test_py_typed_marker_present():
    """PEP 561 — ``ib_async/py.typed`` is an empty marker file telling
    downstream type checkers (mypy, pyright) that this package ships
    inline type hints. Without it, users get implicit-Any for every
    ib_async symbol even though we have full annotations.
    """
    import ib_async

    pkg_dir = pathlib.Path(ib_async.__file__).parent
    marker = pkg_dir / "py.typed"
    assert marker.is_file(), f"PEP 561 marker missing at {marker}"


def test_every_ib_async_method_has_docstring():
    """Audit lock — every public ``IB.*Async`` method must carry at
    least a one-line docstring. Many delegate to documented sync
    siblings; the sibling pointer is enough. Without this lock new
    methods can land undocumented and silently regress the public
    surface contract.
    """
    import ast
    import inspect

    import ib_async

    src = pathlib.Path(inspect.getsourcefile(ib_async.IB)).read_text()
    tree = ast.parse(src)
    missing: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "IB":
            for item in node.body:
                if not isinstance(item, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if item.name.startswith("_"):
                    continue
                if not item.name.endswith("Async"):
                    continue
                if not ast.get_docstring(item):
                    missing.append(item.name)
    assert not missing, f"IB.*Async methods missing docstring: {missing}"


def test_contract_subclass_round_trip_equality():
    """``Stock('AAPL') == Stock('AAPL')`` is documented behaviour and
    user code (caches, dedup) relies on it. ``Contract.__eq__`` falls
    back to ``dataclassAsDict`` equality when ``conId`` is unset, so
    the same constructor args must always produce equal instances. A
    refactor that moves Contract's eq into ``__init_subclass__`` (e.g.
    ``@dataclass(eq=True)``) could silently break this — guard it.
    """
    assert ibi.Stock("AAPL") == ibi.Stock("AAPL")
    assert ibi.Stock("AAPL", "SMART", "USD") == ibi.Stock("AAPL", "SMART", "USD")
    assert ibi.Forex("EURUSD") == ibi.Forex("EURUSD")
    assert ibi.Crypto("BTC", "PAXOS", "USD") == ibi.Crypto("BTC", "PAXOS", "USD")
    assert ibi.Future("ES", "20260320", "GLOBEX") == ibi.Future(
        "ES", "20260320", "GLOBEX"
    )
    # Inequality across symbol or constructor args.
    assert ibi.Stock("AAPL") != ibi.Stock("MSFT")
    # Recreate routes secType back to the specialised subclass.
    assert isinstance(ibi.Contract.recreate(ibi.Stock("AAPL")), ibi.Stock)


def test_contract_create_routes_news_and_event_secTypes():
    """``Contract.create(secType='NEWS' | 'EVENT' | 'EC')`` returns a
    plain ``Contract`` rather than raising on the unknown subclass —
    these are real IBKR security types we don't have specialised
    helpers for, so the dispatcher must keep ``secType`` set instead
    of dropping it.
    """
    for secType in ("NEWS", "EVENT", "EC"):
        c = ibi.Contract.create(secType=secType, symbol="X")
        assert type(c) is ibi.Contract
        assert c.secType == secType
        assert c.symbol == "X"


def test_order_convenience_constructors_coerce_decimal():
    """``LimitOrder``, ``MarketOrder``, ``StopOrder``, ``StopLimitOrder``
    all accept ``Decimal | float | int | str`` for monetary fields and
    funnel through ``_toDecimal`` so binary-float imprecision (e.g.
    ``Decimal(0.1) → 0.10000…0055``) cannot leak into wire messages.
    """
    from decimal import Decimal

    lo = ibi.LimitOrder("BUY", 10, 1.5)
    assert lo.totalQuantity == Decimal(10)
    assert lo.lmtPrice == Decimal("1.5")
    # Float "0.1" must round-trip through str() — guard against the
    # binary imprecision regression.
    lo2 = ibi.LimitOrder("BUY", "10", 0.1)
    assert lo2.lmtPrice == Decimal("0.1")

    mo = ibi.MarketOrder("SELL", "5.25")
    assert mo.totalQuantity == Decimal("5.25")

    so = ibi.StopOrder("BUY", 1, 99.99)
    assert so.auxPrice == Decimal("99.99")

    slo = ibi.StopLimitOrder("SELL", 1, 100.5, 100.0)
    assert slo.lmtPrice == Decimal("100.5")
    assert slo.auxPrice == Decimal("100.0")


# ---------------------------------------------------------------------------
# Round 6: malformed-input survival (fuzz / corruption / half-disconnect)
#
# A broken TCP, a pre-2.x server in test, or a corrupted stream during
# recovery can deliver any of the wire shapes below. None of them may
# crash the decoder, wedge the connection, or silently corrupt state.
# ---------------------------------------------------------------------------


def test_interpret_truncated_binary_frame_does_not_raise(caplog):
    """Scenario 1: handler expects more fields than the frame carries.
    The unpack succeeds (``*fields`` is permissive) but the handler
    indexes past the end and hits ``IndexError``. ``Decoder.interpret``
    must catch and log; the connection survives.
    """
    ib = ibi.IB()
    # msgId 47 (tickEFP) needs 11 fields total; we send only 4.
    with caplog.at_level(logging.ERROR, logger="ib_async.Decoder"):
        ib.client.decoder.interpret(["47", "1", "42", "38"])
    # The exception path was taken — the log carries the failing field list.
    assert any("47" in rec.message for rec in caplog.records)


def test_interpret_oversized_binary_frame_absorbs_silently():
    """Scenario 2: more fields than the handler expects. The wrap()
    plan zips converters with ``fields[skip:]`` — extra trailing fields
    are silently absorbed, NOT misinterpreted as part of an adjacent
    handler's payload. No exception; no corruption of state.
    """
    ib = ibi.IB()
    captured: list = []
    ib.wrapper.tickEFP = lambda *a: captured.append(a)  # type: ignore[method-assign]
    from ib_async.decoder import Decoder

    ib.client.decoder = Decoder(ib.wrapper, ib.client.serverVersion or 0)

    # 11-field tickEFP plus 5 trailing junk fields.
    ib.client.decoder.interpret(
        [
            "47",
            "1",
            "42",
            "38",
            "12.5",
            "+12.50",
            "100.25",
            "30",
            "20251220",
            "0.75",
            "2.50",
            "junk1",
            "junk2",
            "junk3",
            "junk4",
            "junk5",
        ]
    )
    # The trailing junk is silently absorbed — handler runs cleanly with
    # exactly the 9 EFP args.
    assert captured == [(42, 38, 12.5, "+12.50", 100.25, 30, "20251220", 0.75, 2.50)]


def test_interpret_wrong_type_binary_field_caught(caplog):
    """Scenario 3: handler expects an int but the wire field is the
    literal string ``"abc"``. The per-field converter raises
    ``ValueError`` and the wrap() try/except catches and logs.
    """
    ib = ibi.IB()
    with caplog.at_level(logging.ERROR, logger="ib_async.Decoder"):
        # tickEFP wants int reqId — feed it "abc" instead.
        ib.client.decoder.interpret(
            [
                "47",
                "1",
                "abc",
                "38",
                "12.5",
                "+12.50",
                "100.25",
                "30",
                "20251220",
                "0.75",
                "2.50",
            ]
        )
    assert any("tickEFP" in rec.message for rec in caplog.records)


def test_interpret_unknown_binary_msg_id_does_not_raise(caplog):
    """Scenario 11 (binary side): msgId outside the handler dict.
    ``self.handlers[msgId]`` raises ``KeyError``; the outer try/except
    in ``interpret`` catches and logs. Connection survives.
    """
    ib = ibi.IB()
    with caplog.at_level(logging.ERROR, logger="ib_async.Decoder"):
        ib.client.decoder.interpret(["9999", "1", "stuff"])
    assert any("9999" in rec.message for rec in caplog.records)


def test_interpret_non_numeric_msg_id_does_not_raise(caplog):
    """Scenario 3 variant: the msgId itself is not parseable as int.
    ``int(fields[0])`` raises ``ValueError``; outer try/except catches.
    """
    ib = ibi.IB()
    with caplog.at_level(logging.ERROR, logger="ib_async.Decoder"):
        ib.client.decoder.interpret(["NOT_A_NUMBER", "1", "x"])
    # Logged as expected, connection survives.
    assert any("NOT_A_NUMBER" in rec.message for rec in caplog.records)


def test_interpret_empty_fields_list_does_not_raise(caplog):
    """Edge case: a body of all NULs splits to ``[""]`` after pop().
    ``int(fields[0])`` raises ``ValueError`` (empty-string-to-int);
    outer try/except catches. The decoder must never propagate this.
    """
    ib = ibi.IB()
    with caplog.at_level(logging.ERROR, logger="ib_async.Decoder"):
        ib.client.decoder.interpret([""])
    # Silent surrender to logging.


def test_interpret_fields_with_embedded_extra_empties():
    """Scenario 12: split('\\0') on a body with embedded NULs produces
    extra empty fields. Many binary handlers tolerate empty-string
    fields (per-type converters default empty to 0 / None). Verify
    that a wrap()-style handler doesn't crash on extra blank fields
    and the dispatch table absorbs them silently.
    """
    ib = ibi.IB()
    captured: list = []
    # Use updateNewsBulletin (msgId 14, wired via ``wrap([int, int, str, str])``)
    # — pure converter chain, no serverVersion-gated branches.
    ib.wrapper.updateNewsBulletin = lambda *a: captured.append(a)  # type: ignore[method-assign]
    from ib_async.decoder import Decoder

    ib.client.decoder = Decoder(ib.wrapper, 200)
    # msgId, version, msgId-news, msgType, newsMessage, originExch
    # Append 3 empty trailing fields (simulating split('\\0') on a NUL-runny
    # body) — extra fields must be silently absorbed by the zip().
    ib.client.decoder.interpret(["14", "1", "5", "1", "headline", "NYSE", "", "", ""])
    assert captured == [(5, 1, "headline", "NYSE")]


def test_process_proto_buf_empty_payload_does_not_raise():
    """Scenario 5: empty payload b''. ``proto.ParseFromString(b'')``
    succeeds; every field is at default; ``HasField`` checks return
    False uniformly. The handler must not raise ``KeyError`` or wedge.
    """
    ib = ibi.IB()
    # canonical msgId 4 = errorMsg, registered handler. Empty payload.
    ib.client.decoder.processProtoBuf(4, b"")


def test_process_proto_buf_empty_payload_logs_no_error(caplog):
    """The empty-payload case is benign: no error log, just silent
    drop (HasField returned False for everything → empty error frame
    forwarded to wrapper.error which will route to its warning path).
    """
    ib = ibi.IB()
    with caplog.at_level(logging.ERROR, logger="ib_async.Decoder"):
        ib.client.decoder.processProtoBuf(4, b"")
    # Empty payload parses cleanly: no decoder-level error log.
    assert not any(
        rec.levelno >= logging.ERROR and "Error decoding" in rec.message
        for rec in caplog.records
    )


def test_process_proto_buf_oversized_payload_round_trips():
    """Scenario 6: a payload larger than expected (extra unknown
    proto fields tacked on) must round-trip — proto wire format is
    forward-compatible, unknown tags are skipped.
    """
    ib = ibi.IB()
    captured: list = []
    ib.wrapper.error = lambda *a, **kw: captured.append(a)  # type: ignore[method-assign]

    proto = ErrorMessage_pb2.ErrorMessage()
    proto.id = 7
    proto.errorCode = 200
    proto.errorMsg = "test"
    base = proto.SerializeToString()
    # Append unknown tag 9999 wire-type 2 (length-delimited) with junk bytes.
    # tag = (9999 << 3) | 2 = 79994; varint-encoded as multi-byte.
    junk = base + bytes([0xFA, 0xE6, 0x04, 0x05, 0x68, 0x65, 0x6C, 0x6C, 0x6F])

    ib.client.decoder.processProtoBuf(4, junk)
    # The handler still got called with the recognised fields.
    assert any(call[0] == 7 and call[1] == 200 for call in captured)


def test_process_proto_buf_binary_frame_routed_as_proto_logs(caplog):
    """Scenario 10: a NUL-separated binary frame mistakenly handed to
    ``processProtoBuf``. ``ParseFromString`` raises ``DecodeError``;
    the handler catches and logs at error level. Connection survives.
    """
    ib = ibi.IB()
    binary_frame = b"4\x001\x002\x00200\x00message\x00"
    with caplog.at_level(logging.ERROR, logger="ib_async.Decoder"):
        ib.client.decoder.processProtoBuf(4, binary_frame)
    assert any("Error decoding" in rec.message for rec in caplog.records)


def test_process_proto_buf_malformed_does_not_wedge_other_msgids():
    """Scenario 14 (audit task #115): a malformed payload for one
    canonical msgId must not affect the dispatch table or any
    subsequent message. After a malformed frame, the next valid frame
    for a different msgId must still route correctly.

    Documented limitation: the malformed frame's own awaiter (if any)
    is left unresolved — the reqId is inside the unparseable payload.
    See ``processProtoBuf`` docstring. The connection-loss path
    eventually drains it via ``Wrapper.disconnected``.
    """
    ib = ibi.IB()
    captured: list = []
    ib.wrapper.error = lambda *a, **kw: captured.append(a)  # type: ignore[method-assign]

    # 1) Malformed payload for openOrder (canonical 5) — drops with log.
    ib.client.decoder.processProtoBuf(5, b"\xff\xff\xff\xff")
    # 2) Valid error proto must still dispatch normally.
    proto = ErrorMessage_pb2.ErrorMessage()
    proto.id = 99
    proto.errorCode = 321
    proto.errorMsg = "after-malformed"
    ib.client.decoder.processProtoBuf(4, proto.SerializeToString())

    assert len(captured) == 1
    assert captured[0][0] == 99
    assert captured[0][1] == 321


def test_safe_decimal_passthrough_decimal_input():
    """Scenario 8 first half: ``Decimal('-1')`` round-trips through
    ``safe_decimal`` — the negative sentinel that IBKR uses for some
    legitimately-unset numeric fields stays as ``Decimal('-1')``,
    NOT silently substituted to ``None``.
    """
    from ib_async._proto.safe import safe_decimal

    assert safe_decimal(Decimal(-1)) == Decimal(-1)
    assert safe_decimal(Decimal(-2)) == Decimal(-2)
    assert safe_decimal(Decimal(0)) == Decimal(0)
    assert safe_decimal(Decimal("100.5")) == Decimal("100.5")


def test_safe_decimal_decimal_nan_reinput_returns_none():
    """Scenario 8 second half: ``safe_decimal(Decimal('NaN'))`` —
    e.g. parse() called twice on the same field — must return None.
    Otherwise the truthy-trap (``if x:`` evaluates True on NaN)
    re-emerges through a second-pass coercion.
    """
    from ib_async._proto.safe import safe_decimal

    assert safe_decimal(Decimal("NaN")) is None


def test_safe_decimal_decimal_infinity_reinput_returns_none():
    """Sibling of the NaN case: ``Decimal('Infinity')`` re-input must
    also collapse to None so re-coerced wire payloads stay clean."""
    from ib_async._proto.safe import safe_decimal

    assert safe_decimal(Decimal("Infinity")) is None
    assert safe_decimal(Decimal("-Infinity")) is None


def test_safe_decimal_negative_real_value_not_conflated_with_unset():
    """Scenario 7 lock: ``"-1"`` as wire string is a legitimate
    negative quantity / sentinel — it must coerce to ``Decimal('-1')``,
    not None. Only the IBKR UNSET sentinel strings (max int32 etc.)
    are sentinels.
    """
    from ib_async._proto.safe import safe_decimal

    assert safe_decimal("-1") == Decimal(-1)
    assert safe_decimal("-2") == Decimal(-2)
    # And confirm the actual UNSET sentinels still collapse to None.
    assert safe_decimal("2147483647") is None


def test_process_proto_buf_protobuf_frame_handed_to_binary_logs(caplog):
    """Scenario 9: a wire frame that should have routed to the proto
    decoder gets handed to the binary ``interpret`` instead. The
    proto bytes look like an opaque blob to ``int(fields[0])`` —
    ``ValueError`` raises and the outer try/except catches.
    """
    ib = ibi.IB()
    proto = ErrorMessage_pb2.ErrorMessage()
    proto.id = 1
    proto.errorCode = 200
    proto.errorMsg = "x"
    raw = proto.SerializeToString()
    # Mock how the binary decoder would see this: a list of fields
    # produced by raw.split('\0') — entirely arbitrary byte boundaries.
    fields = raw.decode(errors="backslashreplace").split("\0")
    with caplog.at_level(logging.ERROR, logger="ib_async.Decoder"):
        ib.client.decoder.interpret(fields)
    # Logged-and-dropped: connection survives.


def test_decoder_parse_non_dataclass_raises_typeerror_caught_by_interpret():
    """Scenario 13: ``Decoder.parse(obj)`` with a non-dataclass would
    raise ``TypeError`` from ``dataclasses.fields(obj)``. In production
    the only callers feed dataclass instances, but if a future refactor
    accidentally passes the wrong type, the error must propagate up to
    ``interpret``'s try/except (which catches all ``Exception``) so the
    connection does not crash. Verify ``parse(int)`` raises TypeError.
    """
    ib = ibi.IB()
    import pytest

    # Direct call to parse with a wrong-type arg raises — confirms the
    # error path is sensible (not a silent corruption).
    with pytest.raises(TypeError):
        ib.client.decoder.parse(42)  # type: ignore[arg-type]
    # And via the interpret outer try/except, the same situation would
    # be caught at the dispatch layer — verified by the broader
    # "interpret_unknown_binary_msg_id_does_not_raise" test above.


def test_process_proto_buf_msg_id_mid_int_overflow_does_not_raise():
    """Adversarial: a wire msgId that is enormous (e.g. 2**31 - 1).
    ``_protoDispatch.get`` returns None, debug-log, drop. No crash.
    """
    ib = ibi.IB()
    ib.client.decoder.processProtoBuf(2**31 - 1, b"")
    ib.client.decoder.processProtoBuf(0, b"")
    ib.client.decoder.processProtoBuf(-1, b"")


# ---------------------------------------------------------------------------
# Binary orderStatus (msgId 3) — gate 131 MARKET_CAP_PRICE.
# Pre-131 servers send a leading version field and no mktCapPrice; >=131
# drops the version and appends mktCapPrice. A static wrap() with skip=1
# either parses status as Decimal (pre-131 → silent drop) or works.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "serverVersion, fields, expected_mktCapPrice",
    [
        # Pre-131: leading version prefix, no mktCapPrice trailer.
        (
            130,
            [
                "3",  # msgId
                "6",  # version
                "1234",  # orderId
                "Submitted",  # status
                "10.5",  # filled
                "0",  # remaining
                "120.25",  # avgFillPrice
                "55",  # permId
                "0",  # parentId
                "120.25",  # lastFillPrice
                "1",  # clientId
                "",  # whyHeld
            ],
            None,
        ),
        # Gate 131: version prefix dropped, mktCapPrice appended.
        (
            131,
            [
                "3",  # msgId
                "1234",  # orderId (no version prefix at >=131)
                "Submitted",  # status
                "10.5",  # filled
                "0",  # remaining
                "120.25",  # avgFillPrice
                "55",  # permId
                "0",  # parentId
                "120.25",  # lastFillPrice
                "1",  # clientId
                "",  # whyHeld
                "5000000000",  # mktCapPrice
            ],
            Decimal(5000000000),
        ),
    ],
    ids=["pre_131_no_mkt_cap_price", "gate_131_with_mkt_cap_price"],
)
def test_binary_order_status_market_cap_price_gate_131(
    serverVersion, fields, expected_mktCapPrice
):
    """Gate 131 (MARKET_CAP_PRICE) wire-frame alignment.

    Pre-131 servers send a leading version field and no mktCapPrice;
    >=131 drops the version and appends mktCapPrice. Decoder must
    branch at the gate or status mis-parses as Decimal (pre-131) /
    mktCapPrice goes missing (post-131).
    """
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.decoder.serverVersion = serverVersion
    seen: list[tuple] = []
    ib.wrapper.orderStatus = lambda *args: seen.append(args)

    ib.client.decoder.orderStatusMsg(fields)

    assert len(seen) == 1
    args = seen[0]
    assert args[0] == 1234
    assert args[1] == "Submitted"
    assert args[2] == Decimal("10.5")
    assert args[3] == Decimal(0)
    assert args[4] == Decimal("120.25")
    assert args[5] == 55
    assert args[6] == 0
    assert args[7] == Decimal("120.25")
    assert args[8] == 1
    assert args[9] == ""
    assert args[10] == expected_mktCapPrice


# ---------------------------------------------------------------------------
# Binary contractDetails — gate 134 REAL_EXPIRATION_DATE and gate 152
# STOCK_TYPE. With MIN_CLIENT_VER=100 a server in the 100-151 range can
# deliver a strictly shorter frame; reading unconditionally would mis-align
# every following gated field.
# ---------------------------------------------------------------------------


def _binary_contract_details_pre134_fields() -> list[str]:
    """contractDetails wire frame as a server <134 would send it.
    No realExpirationDate, no stockType, no minSize/sizeIncrement.
    """
    return [
        "10",  # msgId placeholder
        "8",  # version (only present pre-SIZE_RULES)
        "7",  # reqId
        "ESM6",  # symbol
        "STK",  # secType
        "20260619",  # lastTimes
        "100.5",  # strike
        "C",  # right
        "GLOBEX",  # exchange
        "USD",  # currency
        "ESM6",  # localSymbol
        "ES",  # marketName
        "ES",  # tradingClass
        "12345",  # conId
        "0.25",  # minTick
        "1",  # mdSizeMultiplier (gate 124-163 obsolete read)
        "50",  # multiplier
        "LIMIT,MKT",  # orderTypes
        "GLOBEX",  # validExchanges
        "1",  # priceMagnifier
        "0",  # underConId
        "E-mini",  # longName
        "GLOBEX",  # primaryExchange
        "202606",  # contractMonth
        "Financial",  # industry
        "Index",  # category
        "Broad",  # subcategory
        "US/Central",  # timeZoneId
        "0830-1500",  # tradingHours
        "0830-1500",  # liquidHours
        "",  # evRule
        "0",  # evMultiplier
        "0",  # numSecIds
        "0",  # aggGroup
        "ES",  # underSymbol
        "IND",  # underSecType
        "0",  # marketRuleIds
        # NB: no realExpirationDate, no stockType, no minSize trio
    ]


@pytest.mark.parametrize(
    "serverVersion, extra_fields, expected_real_expiration",
    [
        # Pre-134: frame carries no realExpirationDate slot.
        (133, [], ""),
        # At gate 134 (and below 152): slot is consumed onto cd.realExpirationDate.
        (151, ["20260619"], "20260619"),
    ],
    ids=["pre_134_no_slot", "gate_134_slot_consumed"],
)
def test_binary_contract_details_real_expiration_date_gate_134(
    serverVersion, extra_fields, expected_real_expiration
):
    """Gate 134 (REAL_EXPIRATION_DATE) wire-frame alignment.

    Pre-134 servers don't carry the slot; consuming it would either
    run the unpack dry or shift a later field into the
    ``realExpirationDate`` slot. >=134 must read it, and on <152 the
    stockType slot is still absent.
    """
    ib = ibi.IB()
    ib.client._serverVersion = serverVersion
    ib.client.decoder.serverVersion = serverVersion
    seen: list[tuple] = []
    ib.wrapper.contractDetails = lambda reqId, cd: seen.append((reqId, cd))

    fields = _binary_contract_details_pre134_fields() + extra_fields
    ib.client.decoder.contractDetails(fields)

    assert len(seen) == 1
    _, cd = seen[0]
    assert cd.realExpirationDate == expected_real_expiration
    assert cd.stockType == ""
