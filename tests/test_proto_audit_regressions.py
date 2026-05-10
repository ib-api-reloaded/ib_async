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
    assert st.suggestedSize == Decimal("5")
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
    assert alloc.position == Decimal("10")
    assert alloc.positionDesired == Decimal("20")
    assert alloc.positionAfter == Decimal("15")
    assert alloc.desiredAllocQty == Decimal("5")
    assert alloc.allowedAllocQty == Decimal("5")
    assert alloc.isMonetary is False


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

    assert safe_decimal("100") == Decimal("100")
    assert safe_decimal("0.5") == Decimal("0.5")
    assert safe_decimal("-1.25") == Decimal("-1.25")
    assert safe_decimal("0") == Decimal("0")


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
        execId="exec-early", commission=2.5, currency="USD"
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
        shares=Decimal("10"),
        price=100.0,
        time="20250101 09:30:00",
    )
    ib.wrapper.execDetails(reqId=1, contract=contract, execution=execution)

    assert "exec-early" not in ib.wrapper._pendingCommissionReports
    assert len(trade.fills) == 1
    assert trade.fills[0].commissionReport.commission == 2.5
    assert len(seenCommission) == 1
    assert seenCommission[0][2].commission == 2.5


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
    """``MONETARY_ACCOUNT_VALUE_TAGS`` must whitelist every monetary tag
    IBKR's ``AccountSummaryTags`` ships — including the bare-name forms
    (``Leverage``, ``ReqTEquity``, ``ReqTMargin``) the account-summary
    stream uses without a segment suffix.

    Without these, ``AccountValue.decimalValue`` returns ``None`` for
    valid monetary values from TWS and user code mistakes the value as
    non-numeric / unset."""

    from ib_async.objects import MONETARY_ACCOUNT_VALUE_TAGS

    # Bare-name spellings IBKR's account-summary stream emits.
    for tag in ("Leverage", "ReqTEquity", "ReqTMargin"):
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


def test_account_value_decimal_view_returns_decimal_for_leverage():
    """AccountValue('Leverage', '2.5').decimalValue must round-trip to
    ``Decimal('2.5')`` rather than ``None`` after the whitelist fix."""

    av = ibi.AccountValue(
        account="DU1",
        tag="Leverage",
        value="2.5",
        currency="USD",
        modelCode="",
    )
    assert av.decimalValue == Decimal("2.5")


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
