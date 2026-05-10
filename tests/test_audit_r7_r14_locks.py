"""Regression locks for the R7-R14 audit fixes.

Each test pins one specific behaviour that an audit round caught and
fixed. The tests are intentionally small, standalone, and worded so a
future refactor that unfixes the issue surfaces a clearly-named failure
rather than a cascade.

The companion ``test_proto_audit_regressions.py`` covers R1-R6; this
file covers R7-R14. R15 reached convergence (zero findings), so no
new locks come from it.
"""

from __future__ import annotations

import asyncio
import math
import struct
from collections import OrderedDict
from decimal import Decimal

import pytest

import ib_async as ibi
from ib_async._requests import ReqIdKey
from ib_async._server_versions import (
    MIN_SERVER_VER_DURATION,
    MIN_SERVER_VER_FA_PROFILE_DESUPPORT,
    MIN_SERVER_VER_PROTOBUF,
    MIN_SERVER_VER_REPLACE_FA_END,
)
from ib_async.ibcontroller import Watchdog
from ib_async.objects import (
    MONETARY_ACCOUNT_VALUE_TAGS,
    AccountValue,
    OptionComputation,
)
from ib_async.order import Order, OrderState, _toDecimal
from ib_async.util import UNSET_DOUBLE
from ib_async.wrapper import _MAX_PENDING_COMMISSION_REPORTS

# ---------------------------------------------------------------------------
# R9 — AccountValue.decimalValue rejects IBKR UNSET sentinels (#198)
# ---------------------------------------------------------------------------

# IBKR sentinels that show up in real wire payloads for unset numeric
# fields. ``decimalValue`` must coerce each to ``None`` rather than
# materialising a 1.8e308-shaped Decimal that user code mistakes for a
# legitimate value.
_IBKR_UNSET_SENTINEL_STRINGS = (
    "2147483647",  # UNSET_INTEGER (2**31 - 1)
    "9223372036854775807",  # UNSET_LONG (2**63 - 1)
    "1.7976931348623157E308",  # UNSET_DOUBLE upper-case
    "1.7976931348623157e+308",  # UNSET_DOUBLE lower-case
    "-9223372036854775808",  # MIN_INT64
    "NaN",
    "Infinity",
    "-Infinity",
)


@pytest.mark.parametrize("sentinel", _IBKR_UNSET_SENTINEL_STRINGS)
def test_account_value_decimal_value_rejects_unset_sentinel(sentinel: str):
    """AccountValue.decimalValue on a monetary tag must NOT coerce IBKR's
    UNSET / NaN / Infinity sentinel strings into a Decimal. Otherwise
    a 1.7976931348623157e+308 NetLiquidation lands on the user's
    portfolio summary and corrupts every downstream "if cash:" guard.
    """
    av = AccountValue(
        account="DU111111",
        tag="NetLiquidation",  # a real monetary tag
        value=sentinel,
        currency="USD",
        modelCode="",
    )
    assert av.decimalValue is None, f"sentinel {sentinel!r} must coerce to None"


def test_account_value_decimal_value_passes_through_real_amount():
    """The companion positive path — a real currency string still
    survives the sentinel filter and lands as a Decimal."""
    av = AccountValue(
        account="DU111111",
        tag="NetLiquidation",
        value="123456.78",
        currency="USD",
        modelCode="",
    )
    assert av.decimalValue == Decimal("123456.78")


def test_account_value_decimal_value_none_for_non_monetary_tag():
    """Non-monetary tags (e.g. ``AccountType``, ``Leverage``) return
    None from ``decimalValue`` even when the value parses as a number.
    The whitelist ``MONETARY_ACCOUNT_VALUE_TAGS`` is the single source
    of truth for what's currency-denominated.
    """
    assert "AccountType" not in MONETARY_ACCOUNT_VALUE_TAGS
    av = AccountValue(
        account="DU111111",
        tag="AccountType",
        value="123.45",
        currency="",
        modelCode="",
    )
    assert av.decimalValue is None


# ---------------------------------------------------------------------------
# R9 — Order._toDecimal filters NaN / Infinity from float and Decimal (#199)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "bad",
    [
        float("nan"),
        float("inf"),
        -float("inf"),
        Decimal("NaN"),
        Decimal("Infinity"),
        Decimal("-Infinity"),
    ],
)
def test_to_decimal_filters_nan_and_infinity(bad):
    """``_toDecimal`` must coerce NaN / Infinity to None on both the
    float and Decimal input branches. The trap is ``Decimal('NaN')``
    being silently truthy — ``if order.lmtPrice:`` returns True on NaN
    but False on None.
    """
    assert _toDecimal(bad) is None


def test_to_decimal_real_float_still_passes_via_str():
    """The companion positive path — a real float still goes through
    ``str()`` so binary-float imprecision is bounded.
    """
    assert _toDecimal(0.1) == Decimal("0.1")
    assert _toDecimal(50.5) == Decimal("50.5")


def test_order_post_init_filters_decimal_nan_input():
    """An ``Order`` constructed with ``Decimal('NaN')`` on a Decimal
    field must NOT keep the NaN — ``__post_init__`` re-runs
    ``_toDecimal`` even on pre-coerced Decimal inputs so a stray NaN
    from user code lands as ``None``.
    """
    order = Order(orderType="LMT", lmtPrice=Decimal("NaN"))
    assert order.lmtPrice is None


def test_order_post_init_filters_float_nan_input():
    """Same trap from the float side. ``Order(lmtPrice=float('nan'))``
    must produce ``lmtPrice is None``, not ``Decimal('NaN')``.
    """
    order = Order(orderType="LMT", lmtPrice=float("nan"))
    assert order.lmtPrice is None


def test_order_post_init_filters_float_infinity_input():
    """``float('inf')`` is the third trap variant; same expected outcome."""
    order = Order(orderType="LMT", trailingPercent=float("inf"))
    assert order.trailingPercent is None


# ---------------------------------------------------------------------------
# R9 — _pendingCommissionReports bounded FIFO eviction (#202)
# ---------------------------------------------------------------------------


def test_pending_commission_reports_evicts_oldest_at_cap():
    """``_pendingCommissionReports`` caps at ``_MAX_PENDING_COMMISSION_REPORTS``
    with FIFO eviction. An unbounded stream of orphan commission
    reports (cross-client / startup-replay) must not grow the map
    without limit.
    """
    ib = ibi.IB()
    ib.wrapper.clientId = 0

    # Fill to exactly the cap.
    for i in range(_MAX_PENDING_COMMISSION_REPORTS):
        ib.wrapper.commissionReport(
            ibi.CommissionReport(execId=f"orphan-{i}", commissionAndFees=Decimal("1.0"))
        )
    assert len(ib.wrapper._pendingCommissionReports) == _MAX_PENDING_COMMISSION_REPORTS
    assert "orphan-0" in ib.wrapper._pendingCommissionReports

    # One more push evicts the oldest (orphan-0) and admits the newest.
    ib.wrapper.commissionReport(
        ibi.CommissionReport(execId="orphan-new", commissionAndFees=Decimal("1.0"))
    )
    assert len(ib.wrapper._pendingCommissionReports) == _MAX_PENDING_COMMISSION_REPORTS
    assert "orphan-0" not in ib.wrapper._pendingCommissionReports
    assert "orphan-new" in ib.wrapper._pendingCommissionReports


def test_pending_commission_reports_is_ordered_dict():
    """The eviction order depends on insertion-order semantics.
    ``OrderedDict`` is the contract; a future refactor swapping to
    ``dict`` would still preserve insertion order but silently lose
    ``popitem(last=False)`` semantics.
    """
    ib = ibi.IB()
    assert isinstance(ib.wrapper._pendingCommissionReports, OrderedDict)


# ---------------------------------------------------------------------------
# R9 — OrderState.transform covers all 9 OutsideRTH margin variants (#203)
# ---------------------------------------------------------------------------

# The full set of fields that ``transform`` must funnel through the
# transformer callable. If a future audit adds a new margin variant
# and forgets the corresponding ``transformer(...)`` call site,
# ``state.numeric()`` and ``state.formatted()`` silently leave the new
# field as a raw wire string while its siblings convert — a subtle bug
# that breaks every "iterate margin fields" caller.
_TRANSFORMED_FIELDS = (
    # 9 regular margin variants
    "initMarginBefore",
    "maintMarginBefore",
    "equityWithLoanBefore",
    "initMarginChange",
    "maintMarginChange",
    "equityWithLoanChange",
    "initMarginAfter",
    "maintMarginAfter",
    "equityWithLoanAfter",
    # 9 OutsideRTH variants (the R9 fix added these — were silently dropped)
    "initMarginBeforeOutsideRTH",
    "maintMarginBeforeOutsideRTH",
    "equityWithLoanBeforeOutsideRTH",
    "initMarginChangeOutsideRTH",
    "maintMarginChangeOutsideRTH",
    "equityWithLoanChangeOutsideRTH",
    "initMarginAfterOutsideRTH",
    "maintMarginAfterOutsideRTH",
    "equityWithLoanAfterOutsideRTH",
    # 3 commission monetary fields (canonical v3.0 name)
    "commissionAndFees",
    "minCommission",
    "maxCommission",
)


def test_order_state_transform_covers_outsidertch_variants():
    """``OrderState.transform`` must touch every margin field — the
    9 regular + 9 OutsideRTH + 3 commission variants. We pass a
    transformer that tags each input with its position, then assert
    every expected field landed in the output with a tag.
    """
    seen: list[str] = []

    def tagging_transformer(value):
        seen.append("touched")
        return f"T<{value}>"

    state = OrderState(
        status="PreSubmitted",
        initMarginBefore="100",
        maintMarginBefore="100",
        equityWithLoanBefore="100",
        initMarginChange="0",
        maintMarginChange="0",
        equityWithLoanChange="0",
        initMarginAfter="100",
        maintMarginAfter="100",
        equityWithLoanAfter="100",
        initMarginBeforeOutsideRTH="200",
        maintMarginBeforeOutsideRTH="200",
        equityWithLoanBeforeOutsideRTH="200",
        initMarginChangeOutsideRTH="0",
        maintMarginChangeOutsideRTH="0",
        equityWithLoanChangeOutsideRTH="0",
        initMarginAfterOutsideRTH="200",
        maintMarginAfterOutsideRTH="200",
        equityWithLoanAfterOutsideRTH="200",
        commissionAndFees=Decimal("1.5"),
        minCommission=Decimal("1.0"),
        maxCommission=Decimal("2.0"),
    )

    transformed = state.transform(tagging_transformer)

    # Every expected field must carry the transformer's tag.
    for fieldName in _TRANSFORMED_FIELDS:
        value = getattr(transformed, fieldName)
        assert isinstance(value, str), (
            f"{fieldName} must be transformer output (str), got {value!r}"
        )
        assert value.startswith("T<"), f"{fieldName} skipped the transformer"

    # The transformer fired exactly once per field — no silent gaps,
    # no double-applies.
    assert len(seen) == len(_TRANSFORMED_FIELDS)


def test_order_state_numeric_converts_outsidertch_margins():
    """End-to-end: ``state.numeric()`` must convert OutsideRTH margins
    to floats just like the regular margins. Prior to R9 the
    OutsideRTH fields silently stayed as raw wire strings.
    """
    state = OrderState(
        initMarginBeforeOutsideRTH="200.5",
        equityWithLoanChangeOutsideRTH="-50.25",
        maintMarginAfterOutsideRTH="300.75",
    )
    numeric = state.numeric(digits=2)
    assert numeric.initMarginBeforeOutsideRTH == 200.5
    assert numeric.equityWithLoanChangeOutsideRTH == -50.25
    assert numeric.maintMarginAfterOutsideRTH == 300.75


# ---------------------------------------------------------------------------
# R13 — tickOptionComputation vega/theta sentinel maps to None (#206)
# ---------------------------------------------------------------------------


def test_tick_option_computation_vega_theta_sentinel_maps_to_none():
    """IBKR uses ``-2`` to mark "not yet computed" for vega and theta.
    Prior to the R13 fix the wrapper had a tautology ``vega if vega
    != -2 else -2`` so the sentinel leaked into ``OptionComputation``
    where user code mistook -2 for a real greek.
    """
    ib = ibi.IB()
    reqId = 42
    # Pre-register an in-flight request so the wrapper's
    # "reply from calculateImpliedVolatility / calculateOptionPrice"
    # branch fires and we can inspect the produced OptionComputation.
    request, _isNew = ib.wrapper.requests.open(ReqIdKey(reqId))

    ib.wrapper.tickOptionComputation(
        reqId,
        tickType=53,  # tickAttrib (any value — not used in non-ticker branch)
        tickAttrib=0,
        impliedVol=0.25,
        delta=0.5,
        optPrice=1.5,
        pvDividend=0.0,
        gamma=0.05,
        vega=-2,  # sentinel
        theta=-2,  # sentinel
        undPrice=100.0,
    )

    # ``set_result`` pops the settled request from the registry, so the
    # future on the original ``Request`` is the source of truth.
    assert request.settled
    comp: OptionComputation = request.future.result()
    assert comp.vega is None, f"vega sentinel must map to None, got {comp.vega!r}"
    assert comp.theta is None, f"theta sentinel must map to None, got {comp.theta!r}"
    # Sanity — non-sentinel greeks survived.
    assert comp.delta == 0.5
    assert comp.gamma == 0.05


def test_tick_option_computation_other_sentinels_still_map_to_none():
    """The other sentinels on this callback — ``-1`` for impliedVol /
    optPrice / pvDividend / undPrice and ``-2`` for delta / gamma —
    were correct before R13 but we lock them here too so a regression
    that re-introduces the tautology pattern on any of them surfaces.
    """
    ib = ibi.IB()
    reqId = 43
    request, _isNew = ib.wrapper.requests.open(ReqIdKey(reqId))

    ib.wrapper.tickOptionComputation(
        reqId,
        tickType=53,
        tickAttrib=0,
        impliedVol=-1,
        delta=-2,
        optPrice=-1,
        pvDividend=-1,
        gamma=-2,
        vega=0.1,
        theta=-0.05,
        undPrice=-1,
    )

    comp: OptionComputation = request.future.result()
    assert comp.impliedVol is None
    assert comp.delta is None
    assert comp.optPrice is None
    assert comp.pvDividend is None
    assert comp.gamma is None
    assert comp.undPrice is None
    # vega / theta carried real values this time.
    assert comp.vega == 0.1
    assert comp.theta == -0.05


# ---------------------------------------------------------------------------
# R13 — Watchdog.probeContract is per-instance (not shared mutable) (#216)
# ---------------------------------------------------------------------------


def test_watchdog_probe_contract_is_per_instance():
    """``Watchdog.probeContract`` uses ``field(default_factory=...)``
    after R13. Prior to that it was a class-level mutable default —
    every Watchdog instance shared the same Forex object, so mutating
    probeContract on one watchdog (e.g. user changes the symbol)
    silently affected every other live watchdog.
    """
    ib = ibi.IB()  # not connected — Watchdog only checks isConnected()
    controller = object()
    w1 = Watchdog(controller=controller, ib=ib)  # type: ignore[arg-type]
    w2 = Watchdog(controller=controller, ib=ib)  # type: ignore[arg-type]
    assert w1.probeContract is not w2.probeContract, (
        "probeContract must be a fresh instance per Watchdog"
    )
    # Mutating one must not affect the other.
    w1.probeContract.symbol = "GBPUSD"
    assert w2.probeContract.symbol == "EUR"


def test_watchdog_probe_contract_defaults_to_eurusd_forex():
    """The default probeContract is still the conventional ``EUR/USD``
    Forex — a high-liquidity, always-on instrument that's safe to use
    as a TWS liveness probe.
    """
    ib = ibi.IB()
    controller = object()
    w = Watchdog(controller=controller, ib=ib)  # type: ignore[arg-type]
    assert isinstance(w.probeContract, ibi.Forex)
    assert w.probeContract.pair() == "EURUSD"


# ---------------------------------------------------------------------------
# R11 — headTimestamp catches ZoneInfoNotFoundError (#218)
# ---------------------------------------------------------------------------


def test_head_timestamp_zone_info_not_found_surfaces_as_request_error():
    """``parseIBDatetime`` raises ``ZoneInfoNotFoundError`` (a subclass
    of ``KeyError``, NOT of ``ValueError``) when IBKR ships a timezone
    the host doesn't know. Prior to R11 the wrapper caught only
    ``ValueError`` so the awaiter on ``reqHeadTimeStampAsync`` hung
    forever instead of seeing the error.
    """
    ib = ibi.IB()
    reqId = 77
    request, _isNew = ib.wrapper.requests.open(ReqIdKey(reqId))

    # An unknown-timezone wire string — IBKR's ``YYYYmmdd HH:MM:SS Tz``
    # shape with a TZ name not in the host's tzdata. ``ZoneInfo`` raises
    # ``ZoneInfoNotFoundError``.
    ib.wrapper.headTimestamp(reqId, "20221125 10:00:00 Mars/Olympus")

    assert request.future.done()
    with pytest.raises(Exception):
        request.future.result()


def test_head_timestamp_value_error_still_surfaces_as_request_error():
    """The pre-R11 ``ValueError`` branch still works — malformed
    datetimes that ``parseIBDatetime`` rejects with ``ValueError``
    must continue to wake the awaiter with the error.
    """
    ib = ibi.IB()
    reqId = 78
    request, _isNew = ib.wrapper.requests.open(ReqIdKey(reqId))

    ib.wrapper.headTimestamp(reqId, "not-a-date")

    assert request.future.done()
    with pytest.raises(Exception):
        request.future.result()


def test_head_timestamp_success_path_resolves_with_datetime():
    """The success path stays intact — a parsable wire string lands
    the resolved datetime on the awaiter's future.
    """
    ib = ibi.IB()
    reqId = 79
    request, _isNew = ib.wrapper.requests.open(ReqIdKey(reqId))

    ib.wrapper.headTimestamp(reqId, "20221125 10:00:00 US/Eastern")

    assert request.future.done()
    result = request.future.result()
    # ``_normalizeDatetime`` returns a tz-aware datetime.
    assert result.year == 2022
    assert result.month == 11
    assert result.day == 25


# ---------------------------------------------------------------------------
# R11 cross-check — math.nan handling on _toDecimal vs Decimal('NaN')
# ---------------------------------------------------------------------------


def test_to_decimal_math_nan_vs_decimal_nan_equivalent():
    """Both ``math.nan`` and ``Decimal('NaN')`` are NaN-shaped; both
    must coerce to None. Locks the symmetry between the two input
    branches of ``_toDecimal``.
    """
    assert _toDecimal(math.nan) is None
    assert _toDecimal(Decimal("NaN")) is None
    # They are NOT equal — Decimal('NaN') != float('nan') in Python —
    # but ``_toDecimal``'s contract is the same: both unset.


# ---------------------------------------------------------------------------
# Send-side test scaffolding (mirrors test_proto_client_gating.py)
# ---------------------------------------------------------------------------


def _ibAtVersion(version: int) -> ibi.IB:
    ib = ibi.IB()
    ib.client._serverVersion = version
    ib.client.connState = ib.client.CONNECTED
    return ib


def _captureSend(ib: ibi.IB) -> list[bytes]:
    sent: list[bytes] = []
    ib.client.conn.sendMsg = sent.append  # type: ignore[method-assign]
    return sent


# ---------------------------------------------------------------------------
# R14 — Client.replaceFA reqId trailing field gated at server 157 (#207)
# ---------------------------------------------------------------------------


def test_replace_fa_omits_reqid_below_gate_157():
    """At server 156 (< MIN_SERVER_VER_REPLACE_FA_END=157) the trailing
    ``reqId`` field must NOT be appended. Sending it to a pre-157
    server desyncs the frame on the IBKR side.
    """
    assert MIN_SERVER_VER_REPLACE_FA_END == 157
    ib = _ibAtVersion(156)
    sent = _captureSend(ib)

    ib.client.replaceFA(reqId=99, faData=1, cxml="<xml/>")

    # Frame body (after 4-byte length prefix) is NUL-separated text on
    # this pre-201 server. Fields in order: msgId="19", version="1",
    # faData="1", cxml="<xml/>" — reqId NOT appended.
    body = sent[0][4:]
    fields = body.split(b"\x00")
    # Fields: ["19", "1", "1", "<xml/>", ""] (trailing empty from final NUL)
    assert fields[:4] == [b"19", b"1", b"1", b"<xml/>"]
    # The 5th field would be the reqId if appended. Confirm it's the
    # trailing empty (last NUL of the frame), not "99".
    assert b"99" not in fields


def test_replace_fa_appends_reqid_at_gate_157():
    """At exactly server 157, the trailing ``reqId`` field IS written.
    This is the threshold where IBKR began acknowledging the reqId on
    replaceFAEnd; the gate is exact.
    """
    ib = _ibAtVersion(MIN_SERVER_VER_REPLACE_FA_END)  # 157
    sent = _captureSend(ib)

    ib.client.replaceFA(reqId=99, faData=1, cxml="<xml/>")

    body = sent[0][4:]
    fields = body.split(b"\x00")
    # reqId="99" lands as the 5th field at and above gate 157.
    assert fields[:5] == [b"19", b"1", b"1", b"<xml/>", b"99"]


# ---------------------------------------------------------------------------
# R14 — requestFA / replaceFA reject faData=2 (Profiles) at gate 177 (#208)
# ---------------------------------------------------------------------------


def test_request_fa_rejects_profile_faData_at_gate_177():
    """faData=2 (Profiles) was de-supported at server gate 177
    (FA_PROFILE_DESUPPORT). ``requestFA`` must reject the request
    locally without putting anything on the wire — mirrors IBKR's
    reference client behaviour and avoids a server bounce.
    """
    assert MIN_SERVER_VER_FA_PROFILE_DESUPPORT == 177
    ib = _ibAtVersion(MIN_SERVER_VER_FA_PROFILE_DESUPPORT)
    sent = _captureSend(ib)

    ib.client.requestFA(faData=2)
    assert sent == []


def test_replace_fa_rejects_profile_faData_at_gate_177():
    """Same rule on the replaceFA path."""
    ib = _ibAtVersion(MIN_SERVER_VER_FA_PROFILE_DESUPPORT)
    sent = _captureSend(ib)

    ib.client.replaceFA(reqId=1, faData=2, cxml="<xml/>")
    assert sent == []


def test_request_fa_still_accepts_groups_faData_at_gate_177():
    """The companion positive path — ``faData=1`` (Groups) still flows
    through at gate 177. Only Profiles (2) was de-supported.
    """
    ib = _ibAtVersion(MIN_SERVER_VER_FA_PROFILE_DESUPPORT)
    sent = _captureSend(ib)

    ib.client.requestFA(faData=1)
    # On server 177 (>= MIN_SERVER_VER_PROTOBUF=201? no, 177 < 201), the
    # binary path fires. The frame body starts with "18\x00" (msgId=18,
    # legacy NUL-text since serverVersion < 201).
    assert sent[0][4:].startswith(b"18\x00")


def test_request_fa_below_gate_177_accepts_profile():
    """Pre-177 the Profile rejection doesn't apply — the request flows
    through verbatim. Locks the gate behaviour at exact boundaries.
    """
    ib = _ibAtVersion(176)
    sent = _captureSend(ib)

    ib.client.requestFA(faData=2)
    # Frame still fires; gate-177 rejection only kicks in at 177+.
    assert sent
    assert sent[0][4:].startswith(b"18\x00")


# ---------------------------------------------------------------------------
# R14 — placeOrder volatility-clear hoisted above proto branch (#209)
# ---------------------------------------------------------------------------


def test_place_order_volatility_clear_applies_on_proto_path():
    """For a non-VOL order, ``placeOrder`` must reset ``order.volatility``
    to ``UNSET_DOUBLE`` BEFORE the protobuf-gated branch — so the proto
    converter's ``_isValidFloat`` guard skips the field. Prior to R14,
    the clear lived after the proto-branch return, so a TWS-populated
    volatility echoed back out on every modify and the server rejected
    the order.
    """
    ib = _ibAtVersion(203)  # MIN_SERVER_VER_PROTOBUF_PLACE_ORDER
    _captureSend(ib)

    contract = ibi.Stock("AAPL", "SMART", "USD")
    order = ibi.LimitOrder("BUY", 100, 50.5)
    # IBKR back-populated this on a prior open-orders snapshot.
    order.volatility = 0.42
    assert order.orderType == "LMT"  # not a VOL order

    ib.client.placeOrder(orderId=42, contract=contract, order=order)
    # The volatility-clear ran — verifies the fix is hoisted above the
    # proto branch.
    assert order.volatility == UNSET_DOUBLE


def test_place_order_volatility_preserved_for_vol_orders():
    """The companion path: VOL-family order types KEEP their volatility
    field. The clear is conditioned on ``not orderType.startswith("VOL")``.
    """
    ib = _ibAtVersion(203)
    _captureSend(ib)

    contract = ibi.Stock("AAPL", "SMART", "USD")
    order = ibi.LimitOrder("BUY", 100, 50.5)
    order.orderType = "VOL"
    order.volatility = 0.42

    ib.client.placeOrder(orderId=42, contract=contract, order=order)
    assert order.volatility == 0.42  # preserved


# ---------------------------------------------------------------------------
# R12 — binary openOrder duration gate at exact server 158 (#210)
# ---------------------------------------------------------------------------


def test_min_server_ver_duration_constant_is_158():
    """The duration field on binary ``openOrder`` is gated at exactly
    server 158 (``MIN_SERVER_VER_DURATION``). The R12 audit replaced a
    literal ``159`` (off-by-one — duration would never read on a 158
    server, silently shifting every subsequent field by one position
    and corrupting OpenOrder for that server) with this named constant.
    """
    assert MIN_SERVER_VER_DURATION == 158


def test_decoder_uses_named_constant_for_duration_gate():
    """Source-level lock: ``decoder.py`` must reference the named
    constant, not a literal. A future refactor that hardcodes ``158``
    or ``159`` would lose the off-by-one safety the constant provides.
    """
    import pathlib

    decoder_src = pathlib.Path("ib_async/decoder.py").read_text()
    # The constant import + usage at the openOrder gate.
    assert "MIN_SERVER_VER_DURATION" in decoder_src, (
        "decoder.py must import + use the named constant for the duration gate"
    )
    # Defensive: no stray ``>= 159`` literal that could shadow the
    # intended gate. ``159`` may appear in unrelated contexts but never
    # adjacent to ``serverVersion`` and ``duration``.
    assert ">= 159" not in decoder_src or "MIN_SERVER_VER_DURATION" in decoder_src


# ---------------------------------------------------------------------------
# R8 — Client.send raw-int msgId framing at server >= 201 (#219)
# ---------------------------------------------------------------------------


def test_send_uses_raw_int_msg_id_at_protobuf_gate():
    """At server >= MIN_SERVER_VER_PROTOBUF (201), the binary ``Client.send``
    emits a 4-byte big-endian raw msgId prefix followed by NUL-terminated
    body bytes. Mirrors IBKR's ``comm.make_msg(msgId, useRawIntMsgId=True,
    text)``. Sending the legacy NUL-text msgId to a 201+ server makes the
    server fail to decode and silently drop the connection.
    """
    assert MIN_SERVER_VER_PROTOBUF == 201
    ib = _ibAtVersion(MIN_SERVER_VER_PROTOBUF)
    sent = _captureSend(ib)

    # Use a benign send — cancelOrder of a non-existent reqId. msgId
    # for cancelOrder is 4.
    ib.client.cancelOrder(orderId=99999)

    body = sent[0][4:]  # strip outer length prefix
    # First 4 bytes are the big-endian raw msgId (4 == CANCEL_ORDER).
    assert body[:4] == struct.pack(">I", 4)


def test_send_uses_legacy_text_msg_id_below_protobuf_gate():
    """At server < 201, ``Client.send`` keeps the legacy NUL-separated
    text msgId framing. ``"4\\x00"`` precedes the body bytes.
    """
    ib = _ibAtVersion(200)
    sent = _captureSend(ib)

    ib.client.cancelOrder(orderId=99999)

    body = sent[0][4:]
    assert body.startswith(b"4\x00")


# ---------------------------------------------------------------------------
# R10 — IB.disconnect fires wrapper.connectionClosed exactly once (#204)
# ---------------------------------------------------------------------------


def test_ib_disconnect_fires_connection_closed_exactly_once():
    """``IB.disconnect`` delegates to ``client.disconnect``, which is the
    single voluntary teardown path. Prior to R10, ``IB.disconnect`` ALSO
    called ``wrapper.connectionClosed`` directly, so the callback fired
    twice — once from the client, once again from IB. The duplicate
    fire double-failed in-flight request futures (raising
    ``InvalidStateError`` on the second attempt) and emitted
    ``globalErrorEvent`` twice for every disconnect.
    """
    ib = _ibAtVersion(MIN_SERVER_VER_PROTOBUF)
    ib.client._apiReady = True  # pretend the API handshake completed

    calls: list[None] = []
    original = ib.wrapper.connectionClosed

    def counter():
        calls.append(None)
        original()

    ib.wrapper.connectionClosed = counter  # type: ignore[method-assign]

    ib.disconnect()
    assert len(calls) == 1, f"connectionClosed must fire exactly once, got {len(calls)}"


def test_ib_disconnect_no_op_when_already_disconnected():
    """``IB.disconnect`` returns early when ``client.isConnected()`` is
    False. No teardown side effects, no callback fires.
    """
    ib = ibi.IB()
    # Not connected to start with.
    calls: list[None] = []
    ib.wrapper.connectionClosed = lambda: calls.append(None)  # type: ignore[method-assign]

    result = ib.disconnect()
    assert result is None
    assert calls == []


# ---------------------------------------------------------------------------
# R10 — IB._backgroundTasks holds reconnect resync task strongly (#205)
# ---------------------------------------------------------------------------


def test_background_tasks_strongly_references_reconnect_resync():
    """When IBKR fires error code 1101 or 1102 ("Connectivity has been
    restored..."), ``IB._onError`` spawns ``reqAccountSummaryAsync`` as
    a background resync. Asyncio holds tasks only weakly via the loop,
    so storing the task in ``_backgroundTasks`` is the explicit strong
    reference that keeps it from being GC'd mid-run.
    """

    async def _run():
        ib = ibi.IB()
        assert isinstance(ib._backgroundTasks, set)
        assert ib._backgroundTasks == set()

        # Pre-set _apiReady so any internal "isConnected" gate stays
        # quiet on the resync helper. We monkey-patch the helper to a
        # no-op coroutine so we don't need a real wire.
        async def fake_summary(*a, **kw):
            return []

        ib.reqAccountSummaryAsync = fake_summary  # type: ignore[method-assign]

        ib._onError(
            reqId=-1, errorCode=1101, errorString="conn restored", contract=None
        )

        # A single resync task landed in the set.
        assert len(ib._backgroundTasks) == 1
        task = next(iter(ib._backgroundTasks))
        assert isinstance(task, asyncio.Task)

        # The done-callback removes the task once it settles, so after
        # awaiting the set goes back to empty.
        await task
        assert ib._backgroundTasks == set()

    asyncio.run(_run())


def test_background_tasks_no_op_on_unrelated_error_codes():
    """Only 1101 / 1102 spawn the resync task. Other error codes (e.g.
    321 "Server error validating an API client request") must NOT.
    """
    ib = ibi.IB()
    ib._onError(reqId=-1, errorCode=321, errorString="benign", contract=None)
    assert ib._backgroundTasks == set()


# ---------------------------------------------------------------------------
# R9 — cancel-async methods settle in-flight futures (#200)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "cancel_name",
    [
        "cancelHeadTimeStamp",
        "cancelHistogramData",
        "cancelContractData",
        "cancelHistoricalTicks",
    ],
)
def test_cancel_async_method_settles_in_flight_future(cancel_name: str):
    """Each cancel-async method must call ``requests.cancel(ReqIdKey(...))``
    so the matching ``reqXxxAsync`` future raises ``CancelledError``
    instead of hanging forever. Prior to R9 the cancel sent the wire
    frame and returned, never waking the awaiter — TWS does not echo
    an End frame on cancel for any of these four request families.
    """
    ib = ibi.IB()

    # Pre-open the in-flight registry entry the cancel must settle.
    reqId = 12345
    request, _isNew = ib.wrapper.requests.open(ReqIdKey(reqId))

    # Stub the wire-side cancel so we don't need a real connection.
    setattr(ib.client, cancel_name, lambda _reqId: None)

    getattr(ib, cancel_name)(reqId)

    assert request.future.done()
    with pytest.raises(asyncio.CancelledError):
        request.future.result()
    # The registry entry is removed once settled.
    assert ReqIdKey(reqId) not in ib.wrapper.requests


def test_cancel_async_on_unknown_req_id_is_idempotent():
    """``requests.cancel`` is idempotent — a cancel for a reqId that
    was never opened (or has already settled) must not raise.
    """
    ib = ibi.IB()
    ib.client.cancelHeadTimeStamp = lambda _reqId: None  # type: ignore[method-assign]
    # Should not raise — no in-flight request for this reqId.
    ib.cancelHeadTimeStamp(99999)


# ---------------------------------------------------------------------------
# R9 — reqTickersAsync try/finally cleanup on gather raise (#201)
# ---------------------------------------------------------------------------


async def test_req_tickers_async_closes_subs_on_gather_raise():
    """``reqTickersAsync`` runs ``await gather(*futures)`` inside a
    ``try`` block; the ``finally`` closes every snapshot subscription
    that was registered for the call. Prior to R9 the cleanup lived
    inline after gather and a per-future failure leaked the other
    in-flight snapshot subs in the SubscriptionRegistry's reqId index.
    """
    ib = ibi.IB()
    ib.client._serverVersion = MIN_SERVER_VER_PROTOBUF
    ib.client.connState = ib.client.CONNECTED
    ib.client._apiReady = True  # getReqId / isReady gates
    # Stub the wire send so reqMktData doesn't try to hit a real socket.
    ib.client.conn.sendMsg = lambda _msg: None  # type: ignore[method-assign]

    contracts = [ibi.Stock("AAPL"), ibi.Stock("MSFT"), ibi.Stock("GOOG")]
    for c in contracts:
        c.conId = abs(hash(c.symbol))  # synthetic but deterministic

    # Fire reqTickersAsync as a background task so we can interrupt one
    # of its in-flight futures mid-flight.
    fut = asyncio.ensure_future(ib.reqTickersAsync(*contracts))
    # Let reqTickersAsync register the subs and reach the gather.
    await asyncio.sleep(0)

    # Snapshot the three reqIds the call registered.
    reqIds = [sub.reqId for sub in ib.wrapper.subscriptions]
    assert len(reqIds) == 3, f"expected 3 snapshot subs, got {reqIds!r}"

    # Trigger a wire-level error on the first ticker so gather raises
    # via the registry's ``set_error``.
    ib.wrapper.requests.set_error(
        ReqIdKey(reqIds[0]), ConnectionError("simulated wire failure")
    )

    with pytest.raises(BaseException):
        await fut

    # The finally clause must have closed every snapshot sub, even
    # though gather raised on the first one.
    leftover = list(ib.wrapper.subscriptions)
    assert leftover == [], f"reqTickersAsync leaked subs on gather raise: {leftover!r}"


# ---------------------------------------------------------------------------
# R13 — IBC monitorAsync survives stdout read exceptions (#215)
# ---------------------------------------------------------------------------


async def test_ibc_monitor_async_breaks_on_stdout_read_exception():
    """``IBC.monitorAsync`` must catch arbitrary stdout-read failures
    and exit the loop cleanly. Prior to R13 a transient stdout transport
    failure (e.g. a decode raising on garbled bytes) propagated out and
    silently killed the monitor task — the IBC process owner never knew.
    """
    from ib_async.ibcontroller import IBC

    ibc = IBC(twsVersion=974, gateway=True)

    class FlakyStdout:
        async def readline(self):
            raise OSError("simulated transport read failure")

    class FlakyProc:
        stdout = FlakyStdout()
        pid = 12345

        async def wait(self):
            return 0

        def terminate(self):
            pass

        def kill(self):
            pass

    ibc._proc = FlakyProc()  # type: ignore[assignment]

    # monitorAsync must complete (not raise) within a reasonable time.
    await asyncio.wait_for(ibc.monitorAsync(), timeout=2)


async def test_ibc_monitor_async_drains_garbled_bytes_with_replace_decode():
    """The decode in ``monitorAsync`` uses ``errors="replace"`` so
    garbled bytes flow through as replacement characters instead of
    crashing the loop on a UnicodeDecodeError.
    """
    from ib_async.ibcontroller import IBC

    ibc = IBC(twsVersion=974, gateway=True)

    class _GarbledStdout:
        _lines = [b"\xff\xfe garbled \x80\x81 bytes\n", b""]  # second is EOF

        async def readline(self):
            if self._lines:
                return self._lines.pop(0)
            return b""

    class _Proc:
        stdout = _GarbledStdout()
        pid = 1

        async def wait(self):
            return 0

        def terminate(self):
            pass

        def kill(self):
            pass

    ibc._proc = _Proc()  # type: ignore[assignment]

    # No raise on the garbled line — replacement characters substitute.
    await asyncio.wait_for(ibc.monitorAsync(), timeout=2)


# ---------------------------------------------------------------------------
# R11 — Watchdog.terminateAsync (actually IBC.terminateAsync) bounded
# by SIGTERM(20s) + SIGKILL(10s) (#217)
# ---------------------------------------------------------------------------


async def test_ibc_terminate_async_escalates_to_sigkill_on_timeout():
    """``IBC.terminateAsync`` caps SIGTERM at 20s; on timeout it
    escalates to SIGKILL with another 10s ceiling. Prior to R11 the
    wait was unbounded, so a hung TWS during the daily reset would
    block the Watchdog reconnect loop forever.
    """
    from ib_async.ibcontroller import IBC

    ibc = IBC(twsVersion=974, gateway=True)

    # Bookkeeping for what got called.
    calls: dict[str, int] = {"terminate": 0, "kill": 0, "wait_for_calls": 0}
    wait_for_timeouts: list[float] = []

    class _HungProc:
        pid = 1

        async def wait(self):
            # Real implementation would block; we never let it run
            # because asyncio.wait_for is stubbed to raise TimeoutError.
            await asyncio.sleep(60)
            return 0

        def terminate(self):
            calls["terminate"] += 1

        def kill(self):
            calls["kill"] += 1

    ibc._proc = _HungProc()  # type: ignore[assignment]
    # Skip the windows branch.
    ibc._isWindows = False

    # Replace asyncio.wait_for inside the ibcontroller module so the
    # bounded waits "fire" their timeout immediately.
    import ib_async.ibcontroller as ibc_mod

    real_wait_for = asyncio.wait_for

    async def fake_wait_for(awaitable, timeout):
        calls["wait_for_calls"] += 1
        wait_for_timeouts.append(timeout)
        # Cancel the awaitable so it doesn't leak.
        if asyncio.iscoroutine(awaitable):
            awaitable.close()
        raise TimeoutError

    ibc_mod.asyncio.wait_for = fake_wait_for  # type: ignore[assignment]
    try:
        await ibc.terminateAsync()
    finally:
        ibc_mod.asyncio.wait_for = real_wait_for  # type: ignore[assignment]

    # SIGTERM was sent first.
    assert calls["terminate"] == 1
    # Then the first wait_for fired with a 20s timeout, hit TimeoutError
    # and SIGKILL escalated.
    assert calls["kill"] == 1
    # Two wait_for invocations: 20s (SIGTERM) then 10s (SIGKILL).
    assert calls["wait_for_calls"] == 2
    assert wait_for_timeouts == [20, 10]
    # _proc cleared at end so subsequent calls become no-ops.
    assert ibc._proc is None


async def test_ibc_terminate_async_no_op_when_no_proc():
    """``IBC.terminateAsync`` is a no-op when ``_proc`` is None — it
    must not raise or accidentally invoke terminate/kill on the
    sentinel.
    """
    from ib_async.ibcontroller import IBC

    ibc = IBC(twsVersion=974, gateway=True)
    assert ibc._proc is None
    await ibc.terminateAsync()  # no raise


# ---------------------------------------------------------------------------
# v3.0 commission → commissionAndFees rename (#164) — deprecation alias
# ---------------------------------------------------------------------------


def test_commission_report_canonical_name_is_commission_and_fees():
    """``commissionAndFees`` is the canonical IBKR-aligned field name
    in v3.0. The legacy ``commission`` attribute still works but emits
    ``DeprecationWarning``; the canonical access does not.
    """
    import warnings

    report = ibi.CommissionReport(commissionAndFees=Decimal("1.25"))
    # Canonical access — no warning.
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        assert report.commissionAndFees == Decimal("1.25")


def test_commission_report_legacy_read_emits_deprecation_warning():
    """``report.commission`` (read) emits ``DeprecationWarning`` but
    returns the canonical value.
    """
    report = ibi.CommissionReport(commissionAndFees=Decimal("1.25"))
    with pytest.warns(DeprecationWarning, match="commissionAndFees"):
        value = report.commission
    assert value == Decimal("1.25")


def test_commission_report_legacy_write_emits_deprecation_warning():
    """``report.commission = X`` emits ``DeprecationWarning`` and routes
    the write to ``commissionAndFees``.
    """
    report = ibi.CommissionReport()
    with pytest.warns(DeprecationWarning, match="commissionAndFees"):
        report.commission = Decimal("2.50")
    assert report.commissionAndFees == Decimal("2.50")


def test_commission_report_legacy_construction_emits_deprecation_warning():
    """``CommissionReport(commission=...)`` keyword arg keeps working
    for v2.x callers but emits ``DeprecationWarning`` and aliases to
    ``commissionAndFees``.
    """
    with pytest.warns(DeprecationWarning, match="commissionAndFees"):
        report = ibi.CommissionReport(execId="x", commission=Decimal("3.75"))
    assert report.commissionAndFees == Decimal("3.75")
    assert report.execId == "x"


def test_order_state_commission_alias_round_trips():
    """``OrderState`` has the same deprecation alias; verify
    construction, read, and write all flow through to ``commissionAndFees``.
    """
    from ib_async.order import OrderState

    with pytest.warns(DeprecationWarning):
        state = OrderState(commission=Decimal("5.00"))
    assert state.commissionAndFees == Decimal("5.00")
    with pytest.warns(DeprecationWarning):
        assert state.commission == Decimal("5.00")
    with pytest.warns(DeprecationWarning):
        state.commission = Decimal("6.00")
    assert state.commissionAndFees == Decimal("6.00")
