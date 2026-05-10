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


def test_historical_data_pre_196_emits_inline_end_signal():
    """Pre-196 servers carry startDateStr/endDateStr inline in the
    bars frame and historicalData itself fires historicalDataEnd at
    the tail. This must keep working on legacy servers.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 195
    ib.client.decoder.serverVersion = 195
    bars: list = []
    ends: list[tuple] = []
    ib.wrapper.historicalData = lambda *a: bars.append(a)
    ib.wrapper.historicalDataEnd = lambda *a: ends.append(a)

    # msgId, reqId, startDateStr, endDateStr, numBars, [date,o,h,l,c,vol,wap,barCount]*
    fields = [
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
    ]
    ib.client.decoder.historicalData(fields)

    assert len(bars) == 1
    assert bars[0][0] == 5  # reqId
    assert ends == [(5, "20240101", "20240131")]


def test_historical_data_post_196_does_not_emit_inline_end():
    """On 196+ servers the inline start/end fields are gone and the
    end signal arrives via msgId 108. historicalData must NOT emit
    historicalDataEnd or callers receive the signal twice.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 196
    ib.client.decoder.serverVersion = 196
    bars: list = []
    ends: list[tuple] = []
    ib.wrapper.historicalData = lambda *a: bars.append(a)
    ib.wrapper.historicalDataEnd = lambda *a: ends.append(a)

    # msgId, reqId, numBars, [date,o,h,l,c,vol,wap,barCount]*
    fields = [
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
    ]
    ib.client.decoder.historicalData(fields)

    assert len(bars) == 1
    assert ends == []  # end signal comes from separate msgId 108 frame


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
    # Sanity: aggGroup did not shift onto evMultiplier slot.
    assert cd.aggGroup == 0


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
    # Defaults — no shift.
    assert cd.tradingHours == ""
    assert cd.liquidHours == ""
    assert cd.aggGroup == 0


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
    assert args_192[-1] == UNSET_INTEGER  # default Order.manualOrderIndicator
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
    assert args_199[-2] == UNSET_INTEGER


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
    assert args_188[-2] == ""  # bondAccruedInterest default
    assert args_188[-1] == UNSET_INTEGER  # RFQ placeholder int

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
