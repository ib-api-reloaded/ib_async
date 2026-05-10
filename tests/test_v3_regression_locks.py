"""Regression locks for v3.0 IBKR-parity fixes.

Each test pins one specific behaviour that the v3.0 wire-protocol and
Decimal-coercion sweep caught and fixed against the IBKR reference
client. The tests are intentionally small, standalone, and worded so a
future refactor that unfixes the issue surfaces a clearly-named failure
rather than a silent regression cascade.

The companion ``test_proto_audit_regressions.py`` covers earlier
plumbing-level invariants; this file pins the lifecycle, coercion,
and send-side parity fixes.
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
# AccountValue.decimalValue rejects IBKR UNSET sentinels
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
# Order._toDecimal filters NaN / Infinity from float and Decimal inputs
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
# _pendingCommissionReports bounded FIFO eviction
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
# OrderState.transform covers all 9 OutsideRTH margin variants
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
    # 9 OutsideRTH variants — these were silently dropped by transform()
    # before the v3.0 sweep, leaving them as raw wire strings while their
    # siblings converted
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
    to floats just like the regular margins. Earlier versions of the
    library silently left the OutsideRTH fields as raw wire strings.
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
# tickOptionComputation vega/theta sentinel maps to None
# ---------------------------------------------------------------------------


def test_tick_option_computation_vega_theta_sentinel_maps_to_none():
    """IBKR uses ``-2`` to mark "not yet computed" for vega and theta.
    A prior tautology of the form ``vega if vega != -2 else -2``
    leaked the sentinel into ``OptionComputation`` where user code
    mistook -2 for a real greek.
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
    were correct before the v3.0 sweep too, but we lock them here so a
    regression that re-introduces the tautology pattern on any of them
    surfaces.
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
# Watchdog.probeContract is per-instance (not shared mutable default)
# ---------------------------------------------------------------------------


def test_watchdog_probe_contract_is_per_instance():
    """``Watchdog.probeContract`` uses ``field(default_factory=...)``
    in v3.0. A class-level mutable default would mean every Watchdog
    instance shared the same Forex object, so mutating probeContract
    on one watchdog (e.g. user changes the symbol) would silently
    affect every other live watchdog.
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
# Wrapper.headTimestamp catches ZoneInfoNotFoundError
# ---------------------------------------------------------------------------


def test_head_timestamp_zone_info_not_found_surfaces_as_request_error():
    """``parseIBDatetime`` raises ``ZoneInfoNotFoundError`` (a subclass
    of ``KeyError``, NOT of ``ValueError``) when IBKR ships a timezone
    the host doesn't know. Catching only ``ValueError`` would leave
    the awaiter on ``reqHeadTimeStampAsync`` hanging forever instead
    of seeing the error.
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
    """The ``ValueError`` branch still works — malformed datetimes
    that ``parseIBDatetime`` rejects with ``ValueError`` must continue
    to wake the awaiter with the error.
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
# Cross-check — math.nan handling on _toDecimal vs Decimal('NaN')
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
# Send-side test scaffolding lives in ``tests._helpers``.
# ---------------------------------------------------------------------------

from tests._helpers import _captureSend, _ibAtVersion

# ---------------------------------------------------------------------------
# Client.replaceFA reqId trailing field gated at server 157
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
# requestFA / replaceFA reject faData=2 (Profiles) at gate 177
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
# placeOrder volatility-clear runs above the protobuf-gated branch
# ---------------------------------------------------------------------------


def test_place_order_volatility_clear_applies_on_proto_path():
    """For a non-VOL order, ``placeOrder`` must reset ``order.volatility``
    to ``UNSET_DOUBLE`` BEFORE the protobuf-gated branch — so the proto
    converter's ``_isValidFloat`` guard skips the field. If the clear
    lived below the proto-branch return, a TWS-populated volatility
    would echo back out on every modify and the server would reject
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
# Binary openOrder duration gate at exact server 158
# ---------------------------------------------------------------------------


def test_min_server_ver_duration_constant_is_158():
    """The duration field on binary ``openOrder`` is gated at exactly
    server 158 (``MIN_SERVER_VER_DURATION``). A literal ``159`` would
    be off-by-one — duration would never read on a 158 server,
    silently shifting every subsequent field by one position and
    corrupting OpenOrder for that server. The named constant guards
    against this.
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
# Client.send raw-int msgId framing at server >= 201
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
# IB.disconnect fires wrapper.connectionClosed exactly once
# ---------------------------------------------------------------------------


def test_ib_disconnect_fires_connection_closed_exactly_once():
    """``IB.disconnect`` delegates to ``client.disconnect``, which is the
    single voluntary teardown path. If ``IB.disconnect`` ALSO called
    ``wrapper.connectionClosed`` directly, the callback would fire
    twice — once from the client, once again from IB. The duplicate
    fire would double-fail in-flight request futures (raising
    ``InvalidStateError`` on the second attempt) and emit
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
# IB._backgroundTasks holds reconnect-resync task strongly
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
# Cancel-async methods settle in-flight futures
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
    instead of hanging forever. A naive implementation sends the wire
    frame and returns, never waking the awaiter — TWS does not echo
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
# reqTickersAsync try/finally cleanup on gather raise
# ---------------------------------------------------------------------------


async def test_req_tickers_async_closes_subs_on_gather_raise():
    """``reqTickersAsync`` runs ``await gather(*futures)`` inside a
    ``try`` block; the ``finally`` closes every snapshot subscription
    that was registered for the call. If cleanup lived inline after
    gather instead of in ``finally``, a per-future failure would leak
    the other in-flight snapshot subs in the SubscriptionRegistry's
    reqId index.
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
# IBC.monitorAsync survives stdout read exceptions
# ---------------------------------------------------------------------------


async def test_ibc_monitor_async_breaks_on_stdout_read_exception():
    """``IBC.monitorAsync`` must catch arbitrary stdout-read failures
    and exit the loop cleanly. Without this guard a transient stdout
    transport failure (e.g. a decode raising on garbled bytes) would
    propagate out and silently kill the monitor task — the IBC process
    owner would never know.
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
# IBC.terminateAsync bounded by SIGTERM(20s) + SIGKILL(10s)
# ---------------------------------------------------------------------------


async def test_ibc_terminate_async_escalates_to_sigkill_on_timeout():
    """``IBC.terminateAsync`` caps SIGTERM at 20s; on timeout it
    escalates to SIGKILL with another 10s ceiling. An unbounded wait
    would let a hung TWS during the daily reset block the Watchdog
    reconnect loop forever.
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
# v3.0 commission → commissionAndFees rename — deprecation alias
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


# ---------------------------------------------------------------------------
# Binary orderStatus wire frame round-trips Decimal | None
# ---------------------------------------------------------------------------


def _seed_trade_for_order_status(
    ib: ibi.IB, *, orderId: int = 1234, clientId: int = 1, permId: int = 55
) -> ibi.order.Trade:
    """Register a Trade so ``Wrapper.orderStatus`` finds a matching row
    and lands the decoded fields on ``trade.orderStatus`` instead of
    logging "No order found".
    """
    from tests._helpers import inject_trade

    return inject_trade(
        ib,
        orderId=orderId,
        permId=permId,
        clientId=clientId,
        status="Submitted",
    )


@pytest.mark.parametrize(
    "filled, remaining, avgFillPrice, lastFillPrice, mktCapPrice, expected",
    [
        # Explicit numeric strings land as Decimal at full precision.
        (
            "10.5",
            "0",
            "120.25",
            "120.25",
            "5000000000",
            {
                "filled": Decimal("10.5"),
                "remaining": Decimal("0"),
                "avgFillPrice": Decimal("120.25"),
                "lastFillPrice": Decimal("120.25"),
                "mktCapPrice": Decimal("5000000000"),
            },
        ),
        # Empty strings land as None (the canonical unset sentinel).
        (
            "",
            "",
            "",
            "",
            "",
            {
                "filled": None,
                "remaining": None,
                "avgFillPrice": None,
                "lastFillPrice": None,
                "mktCapPrice": None,
            },
        ),
        # IBKR UNSET_DOUBLE sentinel lands as None — must NOT materialise
        # as a 1.8e308 Decimal that poisons "if filled:" guards.
        (
            "1.7976931348623157E308",
            "1.7976931348623157E308",
            "1.7976931348623157E308",
            "1.7976931348623157E308",
            "1.7976931348623157E308",
            {
                "filled": None,
                "remaining": None,
                "avgFillPrice": None,
                "lastFillPrice": None,
                "mktCapPrice": None,
            },
        ),
    ],
    ids=["explicit_decimal_strings", "empty_strings", "unset_double_sentinel"],
)
def test_binary_order_status_decimal_fields_round_trip(
    filled, remaining, avgFillPrice, lastFillPrice, mktCapPrice, expected
):
    """Binary path: ``Decoder.orderStatusMsg`` with serverVersion >=131
    sends Decimal-typed wire strings through ``safe_decimal`` and lands
    them on ``Trade.orderStatus``. Empty / UNSET sentinel inputs must
    coerce to ``None`` rather than NaN / 1.8e308 contamination.
    """
    ib = ibi.IB()
    ib.client._serverVersion = 200
    ib.client.decoder.serverVersion = 200
    trade = _seed_trade_for_order_status(ib)

    # Wire layout >=131: msgId, orderId, status, filled, remaining,
    # avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld,
    # mktCapPrice.
    fields = [
        "3",
        str(trade.order.orderId),
        "Filled",
        filled,
        remaining,
        avgFillPrice,
        str(trade.order.permId),
        "0",
        lastFillPrice,
        str(trade.order.clientId),
        "",
        mktCapPrice,
    ]
    ib.client.decoder.orderStatusMsg(fields)

    status = trade.orderStatus
    assert status.filled == expected["filled"]
    assert status.remaining == expected["remaining"]
    assert status.avgFillPrice == expected["avgFillPrice"]
    assert status.lastFillPrice == expected["lastFillPrice"]
    assert status.mktCapPrice == expected["mktCapPrice"]
    # Type-coherence: non-None values must be ``Decimal``, not float / str.
    for name in ("filled", "remaining", "avgFillPrice", "lastFillPrice", "mktCapPrice"):
        v = getattr(status, name)
        if v is not None:
            assert isinstance(v, Decimal), (
                f"{name} must be Decimal, got {type(v).__name__}"
            )


# ---------------------------------------------------------------------------
# Trade.serverOrder snapshot Decimal coherence on binary openOrder
# ---------------------------------------------------------------------------


def test_server_order_decimal_fields_round_trip_via_proto_open_order():
    """Receive-side ``openOrder`` (protobuf path) must populate
    ``Trade.serverOrder`` with proper ``Decimal`` instances on every
    Decimal-typed Order field — not coincidentally-equal floats.

    The binary openOrder handler shares ``self.wrapper.openOrder`` with
    the proto path, so the serverOrder snapshot is built identically;
    the proto path is the canonical receive path on modern servers
    (gate 203+) and is exercised here.
    """
    from ib_async._pb import OpenOrder_pb2

    ib = ibi.IB()
    ib.wrapper.clientId = 0

    proto = OpenOrder_pb2.OpenOrder()
    proto.orderId = 7
    proto.contract.symbol = "AAPL"
    proto.contract.secType = "STK"
    proto.contract.exchange = "SMART"
    proto.contract.currency = "USD"
    proto.order.orderId = 7
    proto.order.clientId = 0
    proto.order.permId = 4242
    proto.order.action = "BUY"
    proto.order.orderType = "LMT"
    # Decimal-typed wire fields under test.
    proto.order.totalQuantity = "150.75"
    proto.order.lmtPrice = 99.5
    proto.order.auxPrice = 95.25
    proto.orderState.status = "Submitted"

    ib.client.decoder.processProtoBuf(5, proto.SerializeToString())

    trade = ib.wrapper.trades[(0, 7)]
    snapshot = trade.serverOrder
    assert snapshot is not None
    # Value-level checks (modulo Decimal precision — float→Decimal via
    # ``safe_decimal(str(float))`` is the wire-canonical normalisation).
    assert snapshot.totalQuantity == Decimal("150.75")
    assert snapshot.lmtPrice == Decimal("99.5")
    assert snapshot.auxPrice == Decimal("95.25")
    # Type-coherence: every Decimal-typed field must be a real Decimal.
    for name in ("totalQuantity", "lmtPrice", "auxPrice"):
        v = getattr(snapshot, name)
        assert isinstance(v, Decimal), (
            f"serverOrder.{name} must be Decimal, got {type(v).__name__}"
        )


# ---------------------------------------------------------------------------
# createOrderProto exhaustive parity round-trip
# ---------------------------------------------------------------------------


def test_create_order_proto_exhaustive_parity_round_trip():
    """Build an ``Order`` with every commonly-set non-default field
    populated, encode via ``createOrderProto``, confirm the serialized
    proto is non-empty, then decode back through ``createOrder`` and
    assert each set field round-trips (modulo Decimal precision and
    the well-known wire-domain rename pairs).
    """
    from ib_async._proto.orders import createOrder, createOrderProto

    original = Order(
        orderId=42,
        clientId=7,
        permId=999,
        action="BUY",
        totalQuantity=Decimal("125.5"),
        orderType="LMT",
        lmtPrice=Decimal("150.25"),
        auxPrice=Decimal("145.50"),
        tif="DAY",
        ocaGroup="OCA-1",
        ocaType=1,
        orderRef="my-order",
        parentId=10,
        blockOrder=True,
        sweepToFill=True,
        displaySize=100,
        triggerMethod=2,
        outsideRth=True,
        hidden=True,
        goodAfterTime="20300101 09:30:00",
        goodTillDate="20301231 16:00:00",
        rule80A="I",
        allOrNone=True,
        account="DU111111",
        settlingFirm="SETTLE",
        clearingAccount="CLEAR",
        clearingIntent="IB",
        percentOffset=Decimal("0.5"),
        trailingPercent=Decimal("1.25"),
        trailStopPrice=Decimal("140.0"),
        transmit=False,
    )

    proto = createOrderProto(original)
    serialized = proto.SerializeToString()
    assert len(serialized) > 0, "Serialized proto must carry at least one set field"

    # Round-trip back to a domain Order.
    decoded = createOrder(proto)

    # Every set field must come back with the same value.
    assert decoded.orderId == original.orderId
    assert decoded.clientId == original.clientId
    assert decoded.permId == original.permId
    assert decoded.action == original.action
    assert decoded.totalQuantity == original.totalQuantity
    assert decoded.orderType == original.orderType
    assert decoded.lmtPrice == original.lmtPrice
    assert decoded.auxPrice == original.auxPrice
    assert decoded.tif == original.tif
    assert decoded.ocaGroup == original.ocaGroup
    assert decoded.ocaType == original.ocaType
    assert decoded.orderRef == original.orderRef
    assert decoded.parentId == original.parentId
    assert decoded.blockOrder == original.blockOrder
    assert decoded.sweepToFill == original.sweepToFill
    assert decoded.displaySize == original.displaySize
    assert decoded.triggerMethod == original.triggerMethod
    assert decoded.outsideRth == original.outsideRth
    assert decoded.hidden == original.hidden
    assert decoded.goodAfterTime == original.goodAfterTime
    assert decoded.goodTillDate == original.goodTillDate
    assert decoded.rule80A == original.rule80A
    assert decoded.allOrNone == original.allOrNone
    assert decoded.account == original.account
    assert decoded.settlingFirm == original.settlingFirm
    assert decoded.clearingAccount == original.clearingAccount
    assert decoded.clearingIntent == original.clearingIntent
    assert decoded.percentOffset == original.percentOffset
    assert decoded.trailingPercent == original.trailingPercent
    assert decoded.trailStopPrice == original.trailStopPrice
    # Type-coherence on every Decimal-typed round-trip.
    for name in (
        "totalQuantity",
        "lmtPrice",
        "auxPrice",
        "percentOffset",
        "trailingPercent",
        "trailStopPrice",
    ):
        v = getattr(decoded, name)
        assert isinstance(v, Decimal), (
            f"{name} must round-trip as Decimal, got {type(v).__name__}"
        )


# ---------------------------------------------------------------------------
# Cross-wire-path equivalence (binary vs protobuf produce identical wrapper state)
# ---------------------------------------------------------------------------


def test_binary_and_proto_order_status_produce_identical_trade_state():
    """msgId 3 (OrderStatus). Binary and protobuf paths must land
    byte-equivalent ``Decimal`` values on ``Trade.orderStatus`` —
    same precision, same sentinel→None mapping.
    """
    from ib_async._pb import OrderStatus_pb2
    from tests._helpers import inject_trade

    # Binary path
    ib_bin = ibi.IB()
    ib_bin.client._serverVersion = 200
    ib_bin.client.decoder.serverVersion = 200
    trade_bin = inject_trade(
        ib_bin, orderId=1, permId=999, clientId=0, status="Submitted"
    )
    ib_bin.client.decoder.orderStatusMsg(
        [
            "3",
            "1",
            "Filled",
            "100.5",
            "0",
            "150.25",
            "999",
            "0",
            "150.25",
            "0",
            "",
            "1000000",
        ]
    )

    # Proto path
    ib_proto = ibi.IB()
    trade_proto = inject_trade(
        ib_proto, orderId=1, permId=999, clientId=0, status="Submitted"
    )
    proto = OrderStatus_pb2.OrderStatus(
        orderId=1,
        status="Filled",
        filled="100.5",
        remaining="0",
        avgFillPrice=150.25,
        permId=999,
        parentId=0,
        lastFillPrice=150.25,
        clientId=0,
        whyHeld="",
        mktCapPrice=1000000.0,
    )
    ib_proto.client.decoder.processProtoBuf(3, proto.SerializeToString())

    b = trade_bin.orderStatus
    p = trade_proto.orderStatus
    assert b.status == p.status
    assert b.filled == p.filled == Decimal("100.5")
    assert b.remaining == p.remaining == Decimal("0")
    assert b.avgFillPrice == p.avgFillPrice == Decimal("150.25")
    assert b.lastFillPrice == p.lastFillPrice == Decimal("150.25")
    assert b.mktCapPrice == p.mktCapPrice == Decimal("1000000")


def test_binary_and_proto_exec_details_produce_identical_execution_state():
    """msgId 11 (ExecutionDetails). Binary and protobuf paths must land
    a byte-equivalent ``Execution`` with the same Decimal-typed
    ``shares`` / ``price`` / ``cumQty`` / ``avgPrice`` / ``evMultiplier``.
    """
    from ib_async._pb import Contract_pb2, Execution_pb2, ExecutionDetails_pb2

    # Binary path (mirroring _binary_exec_details_fields pattern)
    ib_bin = ibi.IB()
    ib_bin.client._serverVersion = 200
    ib_bin.client.decoder.serverVersion = 200
    seen_bin: list = []
    ib_bin.wrapper.execDetails = lambda reqId, c, ex: seen_bin.append((reqId, c, ex))
    ib_bin.client.decoder.execDetails(
        [
            "11",  # msgId
            "-1",  # reqId
            "200",  # orderId
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
            "EXEC-1",  # execId
            "20260510 14:30:00",  # time
            "DU111111",  # acctNumber
            "ISLAND",  # exchange (ex.exchange)
            "BOT",  # side
            "100.5",  # shares
            "150.25",  # price
            "999",  # permId
            "0",  # clientId
            "0",  # liquidation
            "100.5",  # cumQty
            "150.25",  # avgPrice
            "",  # orderRef
            "",  # evRule
            "0",  # evMultiplier
            "",  # modelCode
            "1",  # lastLiquidity
            "0",  # pendingPriceRevision (server >=178)
            "",  # submitter (server >=198)
        ]
    )

    # Proto path
    ib_proto = ibi.IB()
    proto = ExecutionDetails_pb2.ExecutionDetails()
    proto.reqId = -1
    proto.contract.CopyFrom(
        Contract_pb2.Contract(
            conId=12345,
            symbol="AAPL",
            secType="STK",
            exchange="SMART",
            currency="USD",
            localSymbol="AAPL",
            tradingClass="NMS",
        )
    )
    proto.execution.CopyFrom(
        Execution_pb2.Execution(
            orderId=200,
            execId="EXEC-1",
            time="20260510 14:30:00",
            acctNumber="DU111111",
            exchange="ISLAND",
            side="BOT",
            shares="100.5",
            price=150.25,
            permId=999,
            clientId=0,
            cumQty="100.5",
            avgPrice=150.25,
            lastLiquidity=1,
        )
    )
    seen_proto: list = []
    ib_proto.wrapper.execDetails = lambda reqId, c, ex: seen_proto.append(
        (reqId, c, ex)
    )
    ib_proto.client.decoder.processProtoBuf(11, proto.SerializeToString())

    assert len(seen_bin) == 1 and len(seen_proto) == 1
    _, _, ex_bin = seen_bin[0]
    _, _, ex_proto = seen_proto[0]
    assert ex_bin.shares == ex_proto.shares == Decimal("100.5")
    assert ex_bin.price == ex_proto.price == Decimal("150.25")
    assert ex_bin.cumQty == ex_proto.cumQty == Decimal("100.5")
    assert ex_bin.avgPrice == ex_proto.avgPrice == Decimal("150.25")


def test_binary_and_proto_commission_report_produce_identical_state():
    """msgId 59 (CommissionAndFeesReport). Binary and protobuf paths
    must land byte-equivalent Decimal-typed ``commissionAndFees`` /
    ``realizedPNL`` / ``yield_`` on the report.
    """
    from ib_async._pb import CommissionAndFeesReport_pb2

    # Binary path
    ib_bin = ibi.IB()
    ib_bin.client._serverVersion = 200
    ib_bin.client.decoder.serverVersion = 200
    seen_bin: list = []
    ib_bin.wrapper.commissionReport = lambda r: seen_bin.append(r)
    ib_bin.client.decoder.commissionReport(
        [
            "59",  # msgId
            "6",  # version
            "EXEC-7",  # execId
            "1.25",  # commissionAndFees
            "USD",  # currency
            "0.50",  # realizedPNL
            "0.0375",  # yield_
            "20300101",  # yieldRedemptionDate
        ]
    )

    # Proto path
    ib_proto = ibi.IB()
    seen_proto: list = []
    ib_proto.wrapper.commissionReport = lambda r: seen_proto.append(r)
    proto = CommissionAndFeesReport_pb2.CommissionAndFeesReport(
        execId="EXEC-7",
        commissionAndFees=1.25,
        currency="USD",
        realizedPNL=0.50,
        bondYield=0.0375,
        yieldRedemptionDate="20300101",
    )
    ib_proto.client.decoder.processProtoBuf(59, proto.SerializeToString())

    assert len(seen_bin) == 1 and len(seen_proto) == 1
    r_bin, r_proto = seen_bin[0], seen_proto[0]
    assert r_bin.execId == r_proto.execId == "EXEC-7"
    assert r_bin.commissionAndFees == r_proto.commissionAndFees == Decimal("1.25")
    assert r_bin.realizedPNL == r_proto.realizedPNL == Decimal("0.50")
    assert r_bin.yield_ == r_proto.yield_ == Decimal("0.0375")
    assert r_bin.yieldRedemptionDate == r_proto.yieldRedemptionDate == 20300101


def test_binary_and_proto_tick_price_produce_identical_ticker_state():
    """msgId 1 (TickPrice). Binary and protobuf paths must update the
    matching ``Ticker`` with the same price + size.
    """
    from ib_async._pb import TickPrice_pb2
    from ib_async._subscriptions import MktDataSub

    def _seedTicker(ib, reqId):
        contract = ibi.Stock("AAPL", "SMART", "USD")
        contract.conId = 7
        ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)
        ib.wrapper.subscriptions.add(
            MktDataSub(reqId=reqId, contract=contract, ticker=ticker)
        )
        return ticker

    # Binary path — tickType 1 (bid), price 150.25, size 100
    ib_bin = ibi.IB()
    ib_bin.client._serverVersion = 200
    ib_bin.client.decoder.serverVersion = 200
    ticker_bin = _seedTicker(ib_bin, 5)
    # Wire: [msgId, version, reqId, tickType, price, size, attrMask]
    ib_bin.client.decoder.priceSizeTick(["1", "1", "5", "1", "150.25", "100", "0"])

    # Proto path
    ib_proto = ibi.IB()
    ib_proto.client._serverVersion = 207
    ib_proto.client.decoder.serverVersion = 207
    ticker_proto = _seedTicker(ib_proto, 5)
    proto = TickPrice_pb2.TickPrice(
        reqId=5, tickType=1, price=150.25, size="100", attrMask=0
    )
    ib_proto.client.decoder.processProtoBuf(1, proto.SerializeToString())

    assert ticker_bin.bid == ticker_proto.bid == 150.25
    assert ticker_bin.bidSize == ticker_proto.bidSize == 100.0


def test_binary_and_proto_tick_size_produce_identical_ticker_state():
    """msgId 2 (TickSize). Binary and protobuf paths must update the
    matching ``Ticker`` with the same volume / size value.
    """
    from ib_async._pb import TickSize_pb2
    from ib_async._subscriptions import MktDataSub

    def _seedTicker(ib, reqId):
        contract = ibi.Stock("AAPL", "SMART", "USD")
        contract.conId = 7
        ticker = ib.wrapper.subscriptions.get_or_create_ticker(contract)
        ib.wrapper.subscriptions.add(
            MktDataSub(reqId=reqId, contract=contract, ticker=ticker)
        )
        return ticker

    # Binary path — tickType 8 (volume), size 1000
    # Wire: tickSize is wrap("tickSize", [int, int, float]) which skips 2 fields
    # so layout is [msgId, version, reqId, tickType, size]
    ib_bin = ibi.IB()
    ib_bin.client._serverVersion = 200
    ib_bin.client.decoder.serverVersion = 200
    ticker_bin = _seedTicker(ib_bin, 5)
    ib_bin.client.decoder.handlers[2](["2", "1", "5", "8", "1000"])

    # Proto path
    ib_proto = ibi.IB()
    ib_proto.client._serverVersion = 207
    ib_proto.client.decoder.serverVersion = 207
    ticker_proto = _seedTicker(ib_proto, 5)
    proto = TickSize_pb2.TickSize(reqId=5, tickType=8, size="1000")
    ib_proto.client.decoder.processProtoBuf(2, proto.SerializeToString())

    assert ticker_bin.volume == ticker_proto.volume == 1000.0
