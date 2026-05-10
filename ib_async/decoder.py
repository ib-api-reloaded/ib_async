"""Deserialize and dispatch messages."""

import dataclasses
import logging
import sys
import types
import typing
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any, Final

from ._proto.safe import safe_decimal
from ._server_versions import (
    MIN_SERVER_VER_ADVANCED_ORDER_REJECT,
    MIN_SERVER_VER_AGG_GROUP,
    MIN_SERVER_VER_AUTO_CANCEL_PARENT,
    MIN_SERVER_VER_BOND_ACCRUED_INTEREST,
    MIN_SERVER_VER_BOND_TRADING_HOURS,
    MIN_SERVER_VER_CME_TAGGING_FIELDS_IN_OPEN_ORDER,
    MIN_SERVER_VER_CUSTOMER_ACCOUNT,
    MIN_SERVER_VER_DURATION,
    MIN_SERVER_VER_ERROR_TIME,
    MIN_SERVER_VER_FULL_ORDER_PREVIEW_FIELDS,
    MIN_SERVER_VER_FUND_DATA_FIELDS,
    MIN_SERVER_VER_HISTORICAL_DATA_END,
    MIN_SERVER_VER_IMBALANCE_ONLY,
    MIN_SERVER_VER_INCLUDE_OVERNIGHT,
    MIN_SERVER_VER_INELIGIBILITY_REASONS,
    MIN_SERVER_VER_LAST_TRADE_DATE,
    MIN_SERVER_VER_MARKET_CAP_PRICE,
    MIN_SERVER_VER_MARKET_RULES,
    MIN_SERVER_VER_PEGBEST_PEGMID_OFFSETS,
    MIN_SERVER_VER_POST_TO_ATS,
    MIN_SERVER_VER_PROFESSIONAL_CUSTOMER,
    MIN_SERVER_VER_REAL_EXPIRATION_DATE,
    MIN_SERVER_VER_STOCK_TYPE,
    MIN_SERVER_VER_SUBMITTER,
    MIN_SERVER_VER_SYNT_REALTIME_BARS,
    MIN_SERVER_VER_UNDERLYING_INFO,
)
from .contract import (
    ComboLeg,
    Contract,
    ContractDescription,
    ContractDetails,
    DeltaNeutralContract,
    IneligibilityReason,
)
from .objects import (
    BarData,
    CommissionReport,
    DepthMktDataDescription,
    Execution,
    FamilyCode,
    HistogramData,
    HistoricalSession,
    HistoricalTick,
    HistoricalTickBidAsk,
    HistoricalTickLast,
    NewsProvider,
    PriceIncrement,
    SmartComponent,
    SoftDollarTier,
    TagValue,
    TickAttribBidAsk,
    TickAttribLast,
)
from .order import Order, OrderAllocation, OrderComboLeg, OrderCondition, OrderState
from .util import UNSET_DOUBLE, ZoneInfo, parseIBDatetime
from .wrapper import Wrapper

# Per-type wire-string-to-typed-value converters. The empty-string-to-default
# behaviour (``field or 0``) is preserved verbatim from the original inline
# ternary in Decoder.wrap(); hoisting lets that wrap() resolve the converter
# list once at construction time instead of branching per field per dispatch.
# ``Decimal`` is the 3.0-era type for size, quantity, and price fields:
# ``safe_decimal`` returns ``Decimal | None`` (``None`` for empty / "nan" /
# malformed input) so binary-path handlers and protobuf converters share
# the same Decimal-coherent shape on the way into the wrapper.
_CONV: Final[dict[type, Callable[[str], Any]]] = {
    str: lambda f: f,
    int: lambda f: int(f or 0),
    float: lambda f: float(f or 0),
    bool: lambda f: bool(int(f or 0)),
    Decimal: safe_decimal,
}

# Cache of dataclass-field coercion plans keyed by class. Each entry is a tuple
# of ``(field_name, target_type, default_value)`` for the int/float/bool fields
# that Decoder.parse() needs to coerce; str fields are skipped entirely. The
# cache populates lazily on first parse() of each class so we pay the
# dataclasses.fields() introspection once per class instead of per call.
_PARSE_FIELDS: dict[type, tuple[tuple[str, type, Any], ...]] = {}

# Sentinel module-like object used when a class's ``__module__`` is missing
# from ``sys.modules`` — keeps ``vars()`` from raising on dataclasses defined
# in synthetic modules (test fixtures, dynamically generated classes).
_NULL_MOD = types.ModuleType("_null_mod")

# tickByTick subtypes 1 and 2 share the same payload shape; both are
# "all-last" trades (1 = trades, 2 = all trades including odd lots).
_TICK_BY_TICK_LAST_TYPES: Final[frozenset[int]] = frozenset({1, 2})

# Order types where the wire payload includes a pegged-benchmark trailer.
_PEG_BENCH_ORDER_TYPES: Final[frozenset[str]] = frozenset({"PEG BENCH", "PEGBENCH"})


def _noopHandler(fields: list[str]) -> None:
    """Returned by Decoder.wrap() when the wrapper has no method for a msgId,
    so the dispatch table never contains None and hot-path lookup can call
    unconditionally."""


# Per-canonical-msgId protobuf dispatch table for ``Decoder.processProtoBuf``.
# Each entry is ``(ProtoClass, decoder_handler_method_name)``. Mirrors IBKR's
# ``decoder.py:msgId2handleInfoProtoBuf`` for the message families covered
# in the orders / contracts phase. Other phases extend this dict in place
# as they land. Build is deferred to the first instantiation so the heavy
# ``_pb`` imports don't fire at decoder-module import time.
_PROTO_MSG_HANDLERS: dict[int, tuple[type, str]] = {}


def _initProtoMsgHandlers() -> None:
    if _PROTO_MSG_HANDLERS:
        return
    from ._pb import (  # FA messages (gate 211)
        AccountDataEnd_pb2,
        AccountSummary_pb2,
        AccountSummaryEnd_pb2,
        AccountUpdateMulti_pb2,
        AccountUpdateMultiEnd_pb2,
        AccountUpdateTime_pb2,
        AccountValue_pb2,
        CommissionAndFeesReport_pb2,
        CompletedOrder_pb2,
        CompletedOrdersEnd_pb2,
        ConfigResponse_pb2,
        ContractData_pb2,
        ContractDataEnd_pb2,
        CurrentTime_pb2,
        CurrentTimeInMillis_pb2,
        DisplayGroupList_pb2,
        DisplayGroupUpdated_pb2,
        ErrorMessage_pb2,
        ExecutionDetails_pb2,
        ExecutionDetailsEnd_pb2,
        FamilyCodes_pb2,
        FundamentalsData_pb2,
        HeadTimestamp_pb2,
        HistogramData_pb2,
        HistoricalData_pb2,
        HistoricalDataEnd_pb2,
        HistoricalDataUpdate_pb2,
        HistoricalNews_pb2,
        HistoricalNewsEnd_pb2,
        HistoricalSchedule_pb2,
        HistoricalTicks_pb2,
        HistoricalTicksBidAsk_pb2,
        HistoricalTicksLast_pb2,
        ManagedAccounts_pb2,
        MarketDataType_pb2,
        MarketDepth_pb2,
        MarketDepthExchanges_pb2,
        MarketDepthL2_pb2,
        MarketRule_pb2,
        NewsArticle_pb2,
        NewsBulletin_pb2,
        NewsProviders_pb2,
        NextValidId_pb2,
        OpenOrder_pb2,
        OpenOrdersEnd_pb2,
        OrderBound_pb2,
        OrderStatus_pb2,
        PnL_pb2,
        PnLSingle_pb2,
        PortfolioValue_pb2,
        Position_pb2,
        PositionEnd_pb2,
        PositionMulti_pb2,
        PositionMultiEnd_pb2,
        RealTimeBarTick_pb2,
        ReceiveFA_pb2,
        ReplaceFAEnd_pb2,
        RerouteMarketDataRequest_pb2,
        RerouteMarketDepthRequest_pb2,
        ScannerData_pb2,
        ScannerParameters_pb2,
        SecDefOptParameter_pb2,
        SecDefOptParameterEnd_pb2,
        SmartComponents_pb2,
        SoftDollarTiers_pb2,
        SymbolSamples_pb2,
        TickByTickData_pb2,
        TickGeneric_pb2,
        TickNews_pb2,
        TickOptionComputation_pb2,
        TickPrice_pb2,
        TickReqParams_pb2,
        TickSize_pb2,
        TickSnapshotEnd_pb2,
        TickString_pb2,
        UpdateConfigResponse_pb2,
        UserInfo_pb2,
        VerifyCompleted_pb2,
        VerifyMessageApi_pb2,
        WshEventData_pb2,
        WshMetaData_pb2,
    )

    # Canonical IBKR ``IN`` msgIds (see ``ibapi/message.py``).
    _PROTO_MSG_HANDLERS.update(
        {
            3: (OrderStatus_pb2.OrderStatus, "_protoOrderStatus"),
            4: (ErrorMessage_pb2.ErrorMessage, "_protoError"),
            5: (OpenOrder_pb2.OpenOrder, "_protoOpenOrder"),
            6: (AccountValue_pb2.AccountValue, "_protoUpdateAccountValue"),
            7: (PortfolioValue_pb2.PortfolioValue, "_protoUpdatePortfolio"),
            8: (AccountUpdateTime_pb2.AccountUpdateTime, "_protoUpdateAccountTime"),
            10: (ContractData_pb2.ContractData, "_protoContractData"),
            11: (ExecutionDetails_pb2.ExecutionDetails, "_protoExecutionDetails"),
            15: (ManagedAccounts_pb2.ManagedAccounts, "_protoManagedAccounts"),
            18: (ContractData_pb2.ContractData, "_protoBondContractData"),
            52: (ContractDataEnd_pb2.ContractDataEnd, "_protoContractDataEnd"),
            53: (OpenOrdersEnd_pb2.OpenOrdersEnd, "_protoOpenOrderEnd"),
            54: (AccountDataEnd_pb2.AccountDataEnd, "_protoAccountDownloadEnd"),
            55: (
                ExecutionDetailsEnd_pb2.ExecutionDetailsEnd,
                "_protoExecutionDetailsEnd",
            ),
            59: (
                CommissionAndFeesReport_pb2.CommissionAndFeesReport,
                "_protoCommissionReport",
            ),
            61: (Position_pb2.Position, "_protoPosition"),
            62: (PositionEnd_pb2.PositionEnd, "_protoPositionEnd"),
            63: (AccountSummary_pb2.AccountSummary, "_protoAccountSummary"),
            64: (AccountSummaryEnd_pb2.AccountSummaryEnd, "_protoAccountSummaryEnd"),
            65: (VerifyMessageApi_pb2.VerifyMessageApi, "_protoVerifyMessageAPI"),
            66: (VerifyCompleted_pb2.VerifyCompleted, "_protoVerifyCompleted"),
            67: (DisplayGroupList_pb2.DisplayGroupList, "_protoDisplayGroupList"),
            68: (
                DisplayGroupUpdated_pb2.DisplayGroupUpdated,
                "_protoDisplayGroupUpdated",
            ),
            71: (PositionMulti_pb2.PositionMulti, "_protoPositionMulti"),
            72: (
                PositionMultiEnd_pb2.PositionMultiEnd,
                "_protoPositionMultiEnd",
            ),
            73: (
                AccountUpdateMulti_pb2.AccountUpdateMulti,
                "_protoAccountUpdateMulti",
            ),
            74: (
                AccountUpdateMultiEnd_pb2.AccountUpdateMultiEnd,
                "_protoAccountUpdateMultiEnd",
            ),
            100: (OrderBound_pb2.OrderBound, "_protoOrderBound"),
            101: (CompletedOrder_pb2.CompletedOrder, "_protoCompletedOrder"),
            102: (
                CompletedOrdersEnd_pb2.CompletedOrdersEnd,
                "_protoCompletedOrdersEnd",
            ),
            # --- market data + historical (gates 206 / 208) ---
            1: (TickPrice_pb2.TickPrice, "_protoPriceSizeTick"),
            2: (TickSize_pb2.TickSize, "_protoTickSize"),
            12: (MarketDepth_pb2.MarketDepth, "_protoUpdateMktDepth"),
            13: (MarketDepthL2_pb2.MarketDepthL2, "_protoUpdateMktDepthL2"),
            17: (HistoricalData_pb2.HistoricalData, "_protoHistoricalData"),
            21: (
                TickOptionComputation_pb2.TickOptionComputation,
                "_protoTickOptionComputation",
            ),
            45: (TickGeneric_pb2.TickGeneric, "_protoTickGeneric"),
            46: (TickString_pb2.TickString, "_protoTickString"),
            50: (RealTimeBarTick_pb2.RealTimeBarTick, "_protoRealtimeBar"),
            57: (TickSnapshotEnd_pb2.TickSnapshotEnd, "_protoTickSnapshotEnd"),
            58: (MarketDataType_pb2.MarketDataType, "_protoMarketDataType"),
            80: (
                MarketDepthExchanges_pb2.MarketDepthExchanges,
                "_protoMktDepthExchanges",
            ),
            81: (TickReqParams_pb2.TickReqParams, "_protoTickReqParams"),
            88: (HeadTimestamp_pb2.HeadTimestamp, "_protoHeadTimestamp"),
            89: (HistogramData_pb2.HistogramData, "_protoHistogramData"),
            90: (
                HistoricalDataUpdate_pb2.HistoricalDataUpdate,
                "_protoHistoricalDataUpdate",
            ),
            91: (
                RerouteMarketDataRequest_pb2.RerouteMarketDataRequest,
                "_protoRerouteMktDataReq",
            ),
            92: (
                RerouteMarketDepthRequest_pb2.RerouteMarketDepthRequest,
                "_protoRerouteMktDepthReq",
            ),
            96: (HistoricalTicks_pb2.HistoricalTicks, "_protoHistoricalTicks"),
            97: (
                HistoricalTicksBidAsk_pb2.HistoricalTicksBidAsk,
                "_protoHistoricalTicksBidAsk",
            ),
            98: (
                HistoricalTicksLast_pb2.HistoricalTicksLast,
                "_protoHistoricalTicksLast",
            ),
            99: (TickByTickData_pb2.TickByTickData, "_protoTickByTick"),
            106: (
                HistoricalSchedule_pb2.HistoricalSchedule,
                "_protoHistoricalSchedule",
            ),
            108: (
                HistoricalDataEnd_pb2.HistoricalDataEnd,
                "_protoHistoricalDataEnd",
            ),
            # --- news + scanner / fundamentals / PnL (gates 209 / 210) ---
            14: (NewsBulletin_pb2.NewsBulletin, "_protoUpdateNewsBulletin"),
            19: (ScannerParameters_pb2.ScannerParameters, "_protoScannerParameters"),
            20: (ScannerData_pb2.ScannerData, "_protoScannerData"),
            51: (FundamentalsData_pb2.FundamentalsData, "_protoFundamentalData"),
            83: (NewsArticle_pb2.NewsArticle, "_protoNewsArticle"),
            84: (TickNews_pb2.TickNews, "_protoTickNews"),
            85: (NewsProviders_pb2.NewsProviders, "_protoNewsProviders"),
            86: (HistoricalNews_pb2.HistoricalNews, "_protoHistoricalNews"),
            87: (HistoricalNewsEnd_pb2.HistoricalNewsEnd, "_protoHistoricalNewsEnd"),
            94: (PnL_pb2.PnL, "_protoPnL"),
            95: (PnLSingle_pb2.PnLSingle, "_protoPnLSingle"),
            104: (WshMetaData_pb2.WshMetaData, "_protoWshMetaData"),
            105: (WshEventData_pb2.WshEventData, "_protoWshEventData"),
            # --- REST messages (gates 211 / 212 / 213) ---
            9: (NextValidId_pb2.NextValidId, "_protoNextValidId"),
            16: (ReceiveFA_pb2.ReceiveFA, "_protoReceiveFA"),
            49: (CurrentTime_pb2.CurrentTime, "_protoCurrentTime"),
            75: (
                SecDefOptParameter_pb2.SecDefOptParameter,
                "_protoSecDefOptParameter",
            ),
            76: (
                SecDefOptParameterEnd_pb2.SecDefOptParameterEnd,
                "_protoSecDefOptParameterEnd",
            ),
            77: (SoftDollarTiers_pb2.SoftDollarTiers, "_protoSoftDollarTiers"),
            78: (FamilyCodes_pb2.FamilyCodes, "_protoFamilyCodes"),
            79: (SymbolSamples_pb2.SymbolSamples, "_protoSymbolSamples"),
            82: (SmartComponents_pb2.SmartComponents, "_protoSmartComponents"),
            93: (MarketRule_pb2.MarketRule, "_protoMarketRule"),
            103: (ReplaceFAEnd_pb2.ReplaceFAEnd, "_protoReplaceFAEnd"),
            107: (UserInfo_pb2.UserInfo, "_protoUserInfo"),
            109: (
                CurrentTimeInMillis_pb2.CurrentTimeInMillis,
                "_protoCurrentTimeInMillis",
            ),
            110: (ConfigResponse_pb2.ConfigResponse, "_protoConfigResponse"),
            111: (
                UpdateConfigResponse_pb2.UpdateConfigResponse,
                "_protoUpdateConfigResponse",
            ),
        }
    )


def _resolveCoerceType(annotation: Any) -> type | None:
    """Return the target coercion type for a dataclass field annotation.

    Walks ``T | None`` / ``Optional[T]`` / ``Union[T, None]`` down to
    the inner ``T``. Returns ``None`` when the annotation is not a
    type ``parse()`` knows how to coerce (e.g. plain ``str``, list,
    nested dataclass).
    """
    args = typing.get_args(annotation)
    if args:
        nonNone = [a for a in args if a is not type(None)]
        if len(nonNone) == 1:
            inner = nonNone[0]
            if inner in (int, float, bool, Decimal):
                return inner
        return None
    if annotation in (int, float, bool, Decimal):
        return annotation
    return None


class Decoder:
    """Decode IB messages and invoke corresponding wrapper methods."""

    def __init__(self, wrapper: Wrapper, serverVersion: int):
        self.wrapper = wrapper
        self.serverVersion = serverVersion
        self.logger = logging.getLogger("ib_async.Decoder")
        # Populate the protobuf dispatch table on first construction
        # so the heavy ``_pb`` imports don't fire at module-load time
        # for callers that only use the binary path.
        _initProtoMsgHandlers()
        # Pre-resolve the bound handler method for every protobuf
        # canonical msgId. ``processProtoBuf`` is on the receive
        # hot path (every wire frame post-201 server) so eliminating
        # the per-call ``getattr(self, handlerName)`` is worth the
        # one-time cost at construction. The cache also lets us skip
        # the second dict lookup on every dispatch.
        self._protoDispatch: dict[int, tuple[type, Any]] = {
            msgId: (protoCls, getattr(self, handlerName))
            for msgId, (protoCls, handlerName) in _PROTO_MSG_HANDLERS.items()
        }
        self.handlers = {
            1: self.priceSizeTick,
            2: self.wrap("tickSize", [int, int, float]),
            3: self.orderStatusMsg,
            4: self.errorMsg,
            5: self.openOrder,
            6: self.wrap("updateAccountValue", [str, str, str, str]),
            7: self.updatePortfolio,
            8: self.wrap("updateAccountTime", [str]),
            9: self.wrap("nextValidId", [int]),
            10: self.contractDetails,
            11: self.execDetails,
            12: self.wrap("updateMktDepth", [int, int, int, int, float, float]),
            13: self.wrap(
                "updateMktDepthL2", [int, int, str, int, int, float, float, bool]
            ),
            14: self.wrap("updateNewsBulletin", [int, int, str, str]),
            15: self.wrap("managedAccounts", [str]),
            16: self.wrap("receiveFA", [int, str]),
            17: self.historicalData,
            18: self.bondContractDetails,
            19: self.wrap("scannerParameters", [str]),
            20: self.scannerData,
            21: self.tickOptionComputation,
            45: self.wrap("tickGeneric", [int, int, float]),
            46: self.wrap("tickString", [int, int, str]),
            47: self.wrap(
                "tickEFP", [int, int, float, str, float, int, str, float, float]
            ),
            49: self.wrap("currentTime", [int]),
            50: self.wrap(
                "realtimeBar",
                [int, int, Decimal, Decimal, Decimal, Decimal, Decimal, Decimal, int],
            ),
            51: self.wrap("fundamentalData", [int, str]),
            52: self.wrap("contractDetailsEnd", [int]),
            53: self.wrap("openOrderEnd", []),
            54: self.wrap("accountDownloadEnd", [str]),
            55: self.wrap("execDetailsEnd", [int]),
            56: self.deltaNeutralValidation,
            57: self.wrap("tickSnapshotEnd", [int]),
            58: self.wrap("marketDataType", [int, int]),
            59: self.commissionReport,
            61: self.position,
            62: self.wrap("positionEnd", []),
            63: self.wrap("accountSummary", [int, str, str, str, str]),
            64: self.wrap("accountSummaryEnd", [int]),
            65: self.wrap("verifyMessageAPI", [str]),
            66: self.wrap("verifyCompleted", [bool, str]),
            67: self.wrap("displayGroupList", [int, str]),
            68: self.wrap("displayGroupUpdated", [int, str]),
            69: self.wrap("verifyAndAuthMessageAPI", [str, str]),
            70: self.wrap("verifyAndAuthCompleted", [bool, str]),
            71: self.positionMulti,
            72: self.wrap("positionMultiEnd", [int]),
            73: self.wrap("accountUpdateMulti", [int, str, str, str, str, str]),
            74: self.wrap("accountUpdateMultiEnd", [int]),
            75: self.securityDefinitionOptionParameter,
            76: self.wrap("securityDefinitionOptionParameterEnd", [int], skip=1),
            77: self.softDollarTiers,
            78: self.familyCodes,
            79: self.symbolSamples,
            80: self.mktDepthExchanges,
            81: self.wrap("tickReqParams", [int, float, str, int], skip=1),
            82: self.smartComponents,
            83: self.wrap("newsArticle", [int, int, str], skip=1),
            84: self.wrap("tickNews", [int, int, str, str, str, str], skip=1),
            85: self.newsProviders,
            86: self.wrap("historicalNews", [int, str, str, str, str], skip=1),
            87: self.wrap("historicalNewsEnd", [int, bool], skip=1),
            88: self.wrap("headTimestamp", [int, str], skip=1),
            89: self.histogramData,
            90: self.historicalDataUpdate,
            91: self.wrap("rerouteMktDataReq", [int, int, str], skip=1),
            92: self.wrap("rerouteMktDepthReq", [int, int, str], skip=1),
            93: self.marketRule,
            94: self.wrap("pnl", [int, float, float, float], skip=1),
            95: self.wrap(
                "pnlSingle", [Decimal, float, float, float, float, float], skip=1
            ),
            96: self.historicalTicks,
            97: self.historicalTicksBidAsk,
            98: self.historicalTicksLast,
            99: self.tickByTick,
            100: self.wrap("orderBound", [int, int, int], skip=1),
            101: self.completedOrder,
            102: self.wrap("completedOrdersEnd", [], skip=1),
            103: self.wrap("replaceFAEnd", [int, str], skip=1),
            104: self.wrap("wshMetaData", [int, str], skip=1),
            105: self.wrap("wshEventData", [int, str], skip=1),
            106: self.historicalSchedule,
            107: self.wrap("userInfo", [int, str], skip=1),
            108: self.historicalDataEnd,
        }

    def wrap(self, methodName, types, skip=2):
        """
        Create a message handler that invokes a wrapper method
        with the in-order message fields as parameters, skipping over
        the first ``skip`` fields, and parsed according to the ``types`` list.

        The wrapper method and the per-type converter list are resolved once
        at construction time so per-dispatch overhead is one zip + one call
        per field, not a four-way ``is``-comparison chain plus a getattr.
        """
        method = getattr(self.wrapper, methodName, None)
        if method is None:
            return _noopHandler

        converters = [_CONV[t] for t in types]
        logger = self.logger

        def handler(fields):
            try:
                args = [conv(f) for conv, f in zip(converters, fields[skip:])]
                method(*args)
            except Exception:
                logger.exception("Error for %s with fields=%r", methodName, fields)

        return handler

    def interpret(self, fields):
        """Decode fields and invoke corresponding wrapper method."""
        try:
            msgId = int(fields[0])
            handler = self.handlers[msgId]
            handler(fields)
        except Exception:
            self.logger.exception(f"Error handling fields: {fields}")

    def processProtoBuf(self, canonicalMsgId: int, payload: bytes) -> None:
        """Decode a protobuf-framed wire message and dispatch to the
        matching wrapper method.

        Per-msgId table maps canonical IBKR ``IN`` ids to ``(ProtoClass,
        handler_method_name)``. The handler parses the proto, calls the
        relevant ``_proto`` converter to produce domain dataclasses,
        and forwards to the same ``Wrapper`` method the binary path
        uses — so user-visible behaviour is identical regardless of
        which encoding the server chose for a given message family.

        An unknown msgId is logged at debug and dropped; an exception
        from a handler is logged and dropped so a single malformed
        message can't kill the connection. Any awaiter-fail behaviour
        (the registry-level ``set_error`` path) lives in the wrapper
        methods themselves, the same way it does on the binary path.

        Limitation: when ``ParseFromString`` itself fails (truncated /
        corrupted payload) the reqId lives inside the unparsed bytes,
        so we have no way to look up the awaiting future and surface
        an error there. The malformed frame is logged and dropped; the
        awaiter eventually clears via the connection-loss path
        (``Wrapper.disconnected`` drains every pending awaiter) or its
        own ``asyncio.wait_for`` timeout if the user wrapped it. A
        live connection with a single malformed frame in the middle
        survives, but the matching request never receives a result.
        """
        entry = self._protoDispatch.get(canonicalMsgId)
        if entry is None:
            self.logger.debug(
                "protobuf msg %d, %d bytes (no handler)",
                canonicalMsgId,
                len(payload),
            )
            return
        protoCls, handler = entry
        try:
            proto = protoCls()
            proto.ParseFromString(payload)
            handler(proto)
        except Exception:
            self.logger.exception(
                "Error decoding protobuf msg %d, %d bytes",
                canonicalMsgId,
                len(payload),
            )

    # --- protobuf message handlers ----------------------------------------
    #
    # Each ``_protoXxx`` helper translates a parsed proto into the same
    # arguments the binary-path equivalent passes to its wrapper method,
    # so wrapper code stays unaware of which encoding the wire used.

    def _protoError(self, proto: Any) -> None:
        # ``ErrorMessage`` is the protobuf-form of msgId 4. Without this
        # handler, server-pushed errors arriving as proto frames would
        # silently debug-drop and the user would never see them. Live
        # trading hazard: rejected orders, margin warnings, and
        # connection-degraded notices all flow through here.
        reqId = proto.id if proto.HasField("id") else 0
        errorCode = proto.errorCode if proto.HasField("errorCode") else 0
        errorMsg = proto.errorMsg if proto.HasField("errorMsg") else ""
        advancedOrderRejectJson = (
            proto.advancedOrderRejectJson
            if proto.HasField("advancedOrderRejectJson")
            else ""
        )
        errorTime = proto.errorTime if proto.HasField("errorTime") else 0
        self.wrapper.error(
            reqId, errorCode, errorMsg, advancedOrderRejectJson, errorTime
        )

    def _protoOrderStatus(self, proto: Any) -> None:
        from ._proto.orders import createOrderStatus

        s = createOrderStatus(proto)
        self.wrapper.orderStatus(
            s.orderId,
            s.status,
            s.filled,
            s.remaining,
            s.avgFillPrice,
            s.permId,
            s.parentId,
            s.lastFillPrice,
            s.clientId,
            s.whyHeld,
            s.mktCapPrice,
        )

    def _protoOpenOrder(self, proto: Any) -> None:
        # An OpenOrder frame missing any of contract / order / orderState
        # is malformed — the binary path delivers an empty-fielded openOrder
        # to user code in that case, which can poison the trade registry
        # with a half-formed Order. Match IBKR's reference behaviour and
        # drop the frame silently.
        if not (
            proto.HasField("contract")
            and proto.HasField("order")
            and proto.HasField("orderState")
        ):
            return
        from ._proto.orders import createOpenOrder

        orderId, contract, order, state = createOpenOrder(proto)
        self.wrapper.openOrder(orderId, contract, order, state)

    def _protoOpenOrderEnd(self, proto: Any) -> None:
        self.wrapper.openOrderEnd()

    def _protoCompletedOrder(self, proto: Any) -> None:
        if not (
            proto.HasField("contract")
            and proto.HasField("order")
            and proto.HasField("orderState")
        ):
            return
        from ._proto.contracts import createContract
        from ._proto.orders import createOrder, createOrderState

        contract = createContract(proto.contract)
        # Pass the contract proto so combo-leg-bearing orders decode
        # their orderComboLegs from the contract side of the wire.
        order = createOrder(proto.order, contractProto=proto.contract)
        state = createOrderState(proto.orderState)
        self.wrapper.completedOrder(contract, order, state)

    def _protoCompletedOrdersEnd(self, proto: Any) -> None:
        self.wrapper.completedOrdersEnd()

    def _protoExecutionDetails(self, proto: Any) -> None:
        from ._proto.contracts import createContract
        from ._proto.orders import createExecution

        reqId = proto.reqId if proto.HasField("reqId") else -1
        contract = (
            createContract(proto.contract) if proto.HasField("contract") else Contract()
        )
        execution = (
            createExecution(proto.execution)
            if proto.HasField("execution")
            else Execution()
        )
        # Wire ``Execution.time`` is a string in IBKR's
        # ``"YYYYmmdd HH:MM:SS [tz]"`` format. The converter leaves it
        # raw on the domain object; we normalize here so the proto path
        # produces the same datetime shape as the binary path.
        if proto.HasField("execution") and proto.execution.HasField("time"):
            execution.time = self._normalizeExecutionTime(proto.execution.time)
        self.wrapper.execDetails(reqId, contract, execution)

    def _protoExecutionDetailsEnd(self, proto: Any) -> None:
        # ExecutionDetailsEnd carries just a reqId.
        reqId = proto.reqId if proto.HasField("reqId") else -1
        self.wrapper.execDetailsEnd(reqId)

    def _protoCommissionReport(self, proto: Any) -> None:
        from ._proto.orders import createCommissionReport

        report = createCommissionReport(proto)
        self.wrapper.commissionReport(report)

    def _protoContractData(self, proto: Any) -> None:
        from ._proto.contracts import createContractDetailsFromContractData

        # ContractData wraps reqId + contract + contractDetails. Our
        # converter unwraps the inner contract+details into a single
        # ``ContractDetails`` (with ``.contract`` populated).
        reqId = proto.reqId if proto.HasField("reqId") else -1
        details = createContractDetailsFromContractData(proto)
        self.wrapper.contractDetails(reqId, details)

    def _protoBondContractData(self, proto: Any) -> None:
        # BondContractData uses the same proto shape as ContractData.
        # Bond-specific fields populate on the same ``ContractDetails``
        # dataclass; dispatch to ``Wrapper.bondContractDetails`` for
        # symmetry with the binary path so subclasses overriding the
        # bond callback (rather than the unified ``contractDetails``)
        # still receive proto-arriving bond rows. Default Wrapper
        # aliases ``bondContractDetails`` to ``contractDetails`` so
        # subclasses without a bond override see no behavioural change.
        from ._proto.contracts import createContractDetailsFromContractData

        reqId = proto.reqId if proto.HasField("reqId") else -1
        details = createContractDetailsFromContractData(proto)
        self.wrapper.bondContractDetails(reqId, details)

    def _protoContractDataEnd(self, proto: Any) -> None:
        reqId = proto.reqId if proto.HasField("reqId") else -1
        self.wrapper.contractDetailsEnd(reqId)

    def _normalizeExecutionTime(self, timeStr: str) -> datetime:
        """Parse an IBKR execution-time wire string into a tz-aware
        ``datetime`` in the wrapper's default timezone.

        Used by both the binary ``execDetails`` decoder and the protobuf
        ``_protoExecutionDetails`` handler so executions across both
        wire formats land with consistent timestamps. Without this, the
        protobuf path would leave ``ex.time`` at the dataclass default
        (epoch) and the wrapper's ``Fill`` would stamp ``self.lastTime``
        (the local clock at receive time) — wrong for any reconciliation
        or end-of-day analytics.
        """
        parsed = parseIBDatetime(timeStr)
        if isinstance(parsed, datetime):
            time = parsed
        else:
            # 8-char "YYYYmmdd" wire value lacks a time-of-day; combine with
            # midnight so downstream tz operations have a usable datetime.
            time = datetime.combine(parsed, datetime.min.time())
        if not time.tzinfo:
            tz = self.wrapper.ib.TimezoneTWS
            if tz:
                time = time.replace(tzinfo=ZoneInfo(str(tz)))
        return time.astimezone(self.wrapper.defaultTimezone)

    def _protoOrderBound(self, proto: Any) -> None:
        permId = proto.permId if proto.HasField("permId") else 0
        clientId = proto.clientId if proto.HasField("clientId") else 0
        orderId = proto.orderId if proto.HasField("orderId") else 0
        self.wrapper.orderBound(permId, clientId, orderId)

    # --- verify / displayGroup / config handlers --------------------------
    #
    # The matching wrapper methods don't exist on our base ``Wrapper`` —
    # the binary path's ``wrap()`` factory falls back to a noop when a
    # wrapper method is missing, so we mirror that here via ``getattr``.
    # Subclasses that wire up their own verify / display-group flow get
    # their handlers invoked; vanilla setups silently drop these wire
    # frames just like the binary path always has.

    def _protoVerifyMessageAPI(self, proto: Any) -> None:
        method = getattr(self.wrapper, "verifyMessageAPI", None)
        if method is None:
            return
        apiData = proto.apiData if proto.HasField("apiData") else ""
        method(apiData)

    def _protoVerifyCompleted(self, proto: Any) -> None:
        method = getattr(self.wrapper, "verifyCompleted", None)
        if method is None:
            return
        isSuccessful = proto.isSuccessful if proto.HasField("isSuccessful") else False
        errorText = proto.errorText if proto.HasField("errorText") else ""
        method(isSuccessful, errorText)

    def _protoDisplayGroupList(self, proto: Any) -> None:
        method = getattr(self.wrapper, "displayGroupList", None)
        if method is None:
            return
        reqId = proto.reqId if proto.HasField("reqId") else -1
        groups = proto.groups if proto.HasField("groups") else ""
        method(reqId, groups)

    def _protoDisplayGroupUpdated(self, proto: Any) -> None:
        method = getattr(self.wrapper, "displayGroupUpdated", None)
        if method is None:
            return
        reqId = proto.reqId if proto.HasField("reqId") else -1
        contractInfo = proto.contractInfo if proto.HasField("contractInfo") else ""
        method(reqId, contractInfo)

    def _protoConfigResponse(self, proto: Any) -> None:
        # ConfigResponse carries nested ``LockAndExitConfig`` / ``ApiConfig``
        # / ``MessageConfig`` / ``OrdersConfig`` sub-messages with no flat
        # equivalent — the wrapper hook receives the raw proto. IBKR's
        # reference does the same.
        method = getattr(self.wrapper, "configResponseProtoBuf", None)
        if method is not None:
            method(proto)

    def _protoUpdateConfigResponse(self, proto: Any) -> None:
        method = getattr(self.wrapper, "updateConfigResponseProtoBuf", None)
        if method is not None:
            method(proto)

    # --- accounts / positions handlers ------------------------------------

    def _protoUpdateAccountValue(self, proto: Any) -> None:
        from ._proto.accounts import createUpdateAccountValueArgs

        a = createUpdateAccountValueArgs(proto)
        self.wrapper.updateAccountValue(a.tag, a.val, a.currency, a.account)

    def _protoUpdatePortfolio(self, proto: Any) -> None:
        from ._proto.accounts import createUpdatePortfolioArgs

        a = createUpdatePortfolioArgs(proto)
        self.wrapper.updatePortfolio(
            a.contract,
            a.posSize,
            a.marketPrice,
            a.marketValue,
            a.averageCost,
            a.unrealizedPNL,
            a.realizedPNL,
            a.account,
        )

    def _protoUpdateAccountTime(self, proto: Any) -> None:
        ts = proto.timeStamp if proto.HasField("timeStamp") else ""
        self.wrapper.updateAccountTime(ts)

    def _protoAccountDownloadEnd(self, proto: Any) -> None:
        account = proto.accountName if proto.HasField("accountName") else ""
        self.wrapper.accountDownloadEnd(account)

    def _protoManagedAccounts(self, proto: Any) -> None:
        from ._proto.accounts import createManagedAccountsList

        self.wrapper.managedAccounts(createManagedAccountsList(proto))

    def _protoPosition(self, proto: Any) -> None:
        from ._proto.accounts import createPositionArgs

        a = createPositionArgs(proto)
        self.wrapper.position(a.account, a.contract, a.posSize, a.avgCost)

    def _protoPositionEnd(self, proto: Any) -> None:
        self.wrapper.positionEnd()

    def _protoAccountSummary(self, proto: Any) -> None:
        from ._proto.accounts import createAccountSummaryArgs

        a = createAccountSummaryArgs(proto)
        self.wrapper.accountSummary(a.reqId, a.account, a.tag, a.value, a.currency)

    def _protoAccountSummaryEnd(self, proto: Any) -> None:
        reqId = proto.reqId if proto.HasField("reqId") else -1
        self.wrapper.accountSummaryEnd(reqId)

    def _protoPositionMulti(self, proto: Any) -> None:
        from ._proto.accounts import createPositionMultiArgs

        a = createPositionMultiArgs(proto)
        self.wrapper.positionMulti(
            a.reqId, a.account, a.modelCode, a.contract, a.pos, a.avgCost
        )

    def _protoPositionMultiEnd(self, proto: Any) -> None:
        reqId = proto.reqId if proto.HasField("reqId") else -1
        self.wrapper.positionMultiEnd(reqId)

    def _protoAccountUpdateMulti(self, proto: Any) -> None:
        from ._proto.accounts import createAccountUpdateMultiArgs

        a = createAccountUpdateMultiArgs(proto)
        self.wrapper.accountUpdateMulti(
            a.reqId, a.account, a.modelCode, a.tag, a.val, a.currency
        )

    def _protoAccountUpdateMultiEnd(self, proto: Any) -> None:
        reqId = proto.reqId if proto.HasField("reqId") else -1
        self.wrapper.accountUpdateMultiEnd(reqId)

    # --- market data handlers ---------------------------------------------

    def _protoPriceSizeTick(self, proto: Any) -> None:
        from ._proto.market_data import createPriceSizeTickArgs

        a = createPriceSizeTickArgs(proto, self.serverVersion)
        self.wrapper.priceSizeTick(a.reqId, a.tickType, a.price, a.size, a.attrib)

    def _protoTickSize(self, proto: Any) -> None:
        from ._proto.market_data import createTickSizeArgs

        a = createTickSizeArgs(proto)
        self.wrapper.tickSize(a.reqId, a.tickType, a.size)

    def _protoTickGeneric(self, proto: Any) -> None:
        from ._proto.market_data import createTickGenericArgs

        a = createTickGenericArgs(proto)
        self.wrapper.tickGeneric(a.reqId, a.tickType, a.value)

    def _protoTickString(self, proto: Any) -> None:
        from ._proto.market_data import createTickStringArgs

        a = createTickStringArgs(proto)
        self.wrapper.tickString(a.reqId, a.tickType, a.value)

    def _protoTickReqParams(self, proto: Any) -> None:
        from ._proto.market_data import createTickReqParamsArgs

        a = createTickReqParamsArgs(proto)
        self.wrapper.tickReqParams(
            a.reqId, a.minTick, a.bboExchange, a.snapshotPermissions
        )

    def _protoTickSnapshotEnd(self, proto: Any) -> None:
        from ._proto.market_data import createTickSnapshotEndReqId

        self.wrapper.tickSnapshotEnd(createTickSnapshotEndReqId(proto))

    def _protoTickOptionComputation(self, proto: Any) -> None:
        from ._proto.market_data import createTickOptionComputationArgs

        a = createTickOptionComputationArgs(proto)
        self.wrapper.tickOptionComputation(
            a.reqId,
            a.tickType,
            a.tickAttrib,
            a.impliedVol,
            a.delta,
            a.optPrice,
            a.pvDividend,
            a.gamma,
            a.vega,
            a.theta,
            a.undPrice,
        )

    def _protoTickByTick(self, proto: Any) -> None:
        from ._proto.market_data import (
            TickByTickAllLastArgs,
            TickByTickBidAskArgs,
            TickByTickMidPointArgs,
            dispatchTickByTick,
        )

        a = dispatchTickByTick(proto)
        if isinstance(a, TickByTickAllLastArgs):
            self.wrapper.tickByTickAllLast(
                a.reqId,
                a.tickType,
                a.time,
                a.price,
                a.size,
                a.tickAttribLast,
                a.exchange,
                a.specialConditions,
            )
        elif isinstance(a, TickByTickBidAskArgs):
            self.wrapper.tickByTickBidAsk(
                a.reqId,
                a.time,
                a.bidPrice,
                a.askPrice,
                a.bidSize,
                a.askSize,
                a.tickAttribBidAsk,
            )
        elif isinstance(a, TickByTickMidPointArgs):
            self.wrapper.tickByTickMidPoint(a.reqId, a.time, a.midPoint)
        # else None — oneof not set, drop (matches binary path)

    def _protoMarketDataType(self, proto: Any) -> None:
        from ._proto.market_data import createMarketDataTypeArgs

        a = createMarketDataTypeArgs(proto)
        self.wrapper.marketDataType(a.reqId, a.marketDataType)

    def _protoUpdateMktDepth(self, proto: Any) -> None:
        from ._proto.market_data import createUpdateMktDepthArgs

        a = createUpdateMktDepthArgs(proto)
        self.wrapper.updateMktDepth(
            a.reqId, a.position, a.operation, a.side, a.price, a.size
        )

    def _protoUpdateMktDepthL2(self, proto: Any) -> None:
        from ._proto.market_data import createUpdateMktDepthL2Args

        a = createUpdateMktDepthL2Args(proto)
        self.wrapper.updateMktDepthL2(
            a.reqId,
            a.position,
            a.marketMaker,
            a.operation,
            a.side,
            a.price,
            a.size,
            a.isSmartDepth,
        )

    def _protoMktDepthExchanges(self, proto: Any) -> None:
        from ._proto.market_data import createMarketDepthExchangesList

        self.wrapper.mktDepthExchanges(createMarketDepthExchangesList(proto))

    def _protoRerouteMktDataReq(self, proto: Any) -> None:
        from ._proto.market_data import createRerouteMktDataReqArgs

        a = createRerouteMktDataReqArgs(proto)
        self.wrapper.rerouteMktDataReq(a.reqId, a.conId, a.exchange)

    def _protoRerouteMktDepthReq(self, proto: Any) -> None:
        from ._proto.market_data import createRerouteMktDepthReqArgs

        a = createRerouteMktDepthReqArgs(proto)
        self.wrapper.rerouteMktDepthReq(a.reqId, a.conId, a.exchange)

    # --- historical-data handlers -----------------------------------------

    def _protoHistoricalData(self, proto: Any) -> None:
        from ._proto.historical import createHistoricalDataBars

        a = createHistoricalDataBars(proto)
        for bar in a.bars:
            self.wrapper.historicalData(a.reqId, bar)

    def _protoHistoricalDataEnd(self, proto: Any) -> None:
        from ._proto.historical import createHistoricalDataEndArgs

        a = createHistoricalDataEndArgs(proto)
        self.wrapper.historicalDataEnd(a.reqId, a.start, a.end)

    def _protoHistoricalDataUpdate(self, proto: Any) -> None:
        from ._proto.historical import createHistoricalDataUpdateArgs

        a = createHistoricalDataUpdateArgs(proto)
        self.wrapper.historicalDataUpdate(a.reqId, a.bar)

    def _protoRealtimeBar(self, proto: Any) -> None:
        from ._proto.historical import createRealtimeBarArgs

        a = createRealtimeBarArgs(proto)
        self.wrapper.realtimeBar(
            a.reqId,
            a.time,
            a.open_,
            a.high,
            a.low,
            a.close,
            a.volume,
            a.wap,
            a.count,
        )

    def _protoHeadTimestamp(self, proto: Any) -> None:
        from ._proto.historical import createHeadTimestampArgs

        a = createHeadTimestampArgs(proto)
        self.wrapper.headTimestamp(a.reqId, a.headTimestamp)

    def _protoHistogramData(self, proto: Any) -> None:
        from ._proto.historical import createHistogramDataArgs

        a = createHistogramDataArgs(proto)
        self.wrapper.histogramData(a.reqId, a.items)

    def _protoHistoricalSchedule(self, proto: Any) -> None:
        from ._proto.historical import createHistoricalScheduleArgs

        a = createHistoricalScheduleArgs(proto)
        self.wrapper.historicalSchedule(
            a.reqId, a.startDateTime, a.endDateTime, a.timeZone, a.sessions
        )

    def _protoHistoricalTicks(self, proto: Any) -> None:
        from ._proto.historical import createHistoricalTicksArgs

        a = createHistoricalTicksArgs(proto)
        self.wrapper.historicalTicks(a.reqId, a.ticks, a.done)

    def _protoHistoricalTicksBidAsk(self, proto: Any) -> None:
        from ._proto.historical import createHistoricalTicksBidAskArgs

        a = createHistoricalTicksBidAskArgs(proto)
        self.wrapper.historicalTicksBidAsk(a.reqId, a.ticks, a.done)

    def _protoHistoricalTicksLast(self, proto: Any) -> None:
        from ._proto.historical import createHistoricalTicksLastArgs

        a = createHistoricalTicksLastArgs(proto)
        self.wrapper.historicalTicksLast(a.reqId, a.ticks, a.done)

    # --- news + WSH handlers ---------------------------------------------

    def _protoUpdateNewsBulletin(self, proto: Any) -> None:
        from ._proto.news import createUpdateNewsBulletinArgs

        a = createUpdateNewsBulletinArgs(proto)
        self.wrapper.updateNewsBulletin(a.msgId, a.msgType, a.message, a.origExchange)

    def _protoNewsProviders(self, proto: Any) -> None:
        from ._proto.news import createNewsProviders

        self.wrapper.newsProviders(createNewsProviders(proto))

    def _protoNewsArticle(self, proto: Any) -> None:
        from ._proto.news import createNewsArticleArgs

        a = createNewsArticleArgs(proto)
        self.wrapper.newsArticle(a.reqId, a.articleType, a.articleText)

    def _protoHistoricalNews(self, proto: Any) -> None:
        from ._proto.news import createHistoricalNewsArgs

        a = createHistoricalNewsArgs(proto)
        self.wrapper.historicalNews(
            a.reqId, a.time, a.providerCode, a.articleId, a.headline
        )

    def _protoHistoricalNewsEnd(self, proto: Any) -> None:
        from ._proto.news import createHistoricalNewsEndArgs

        a = createHistoricalNewsEndArgs(proto)
        self.wrapper.historicalNewsEnd(a.reqId, a.hasMore)

    def _protoTickNews(self, proto: Any) -> None:
        from ._proto.news import createTickNewsArgs

        a = createTickNewsArgs(proto)
        self.wrapper.tickNews(
            a.reqId,
            a.timeStamp,
            a.providerCode,
            a.articleId,
            a.headline,
            a.extraData,
        )

    def _protoWshMetaData(self, proto: Any) -> None:
        from ._proto.news import createWshMetaDataArgs

        a = createWshMetaDataArgs(proto)
        self.wrapper.wshMetaData(a.reqId, a.dataJson)

    def _protoWshEventData(self, proto: Any) -> None:
        from ._proto.news import createWshEventDataArgs

        a = createWshEventDataArgs(proto)
        self.wrapper.wshEventData(a.reqId, a.dataJson)

    # --- scanner + fundamentals + PnL handlers ----------------------------

    def _protoScannerParameters(self, proto: Any) -> None:
        from ._proto.scanner import createScannerParametersXml

        self.wrapper.scannerParameters(createScannerParametersXml(proto))

    def _protoScannerData(self, proto: Any) -> None:
        from ._proto.scanner import createScannerDataArgs

        a = createScannerDataArgs(proto)
        for el in a.elements:
            self.wrapper.scannerData(
                el.reqId,
                el.rank,
                el.contractDetails,
                el.distance,
                el.benchmark,
                el.projection,
                el.legsStr,
            )
        self.wrapper.scannerDataEnd(a.reqId)

    def _protoFundamentalData(self, proto: Any) -> None:
        from ._proto.scanner import createFundamentalDataArgs

        a = createFundamentalDataArgs(proto)
        self.wrapper.fundamentalData(a.reqId, a.data)

    def _protoPnL(self, proto: Any) -> None:
        from ._proto.scanner import createPnLArgs

        a = createPnLArgs(proto)
        self.wrapper.pnl(a.reqId, a.dailyPnL, a.unrealizedPnL, a.realizedPnL)

    def _protoPnLSingle(self, proto: Any) -> None:
        from ._proto.scanner import createPnLSingleArgs

        a = createPnLSingleArgs(proto)
        self.wrapper.pnlSingle(
            a.reqId, a.pos, a.dailyPnL, a.unrealizedPnL, a.realizedPnL, a.value
        )

    # --- REST handlers ----------------------------------------------------

    def _protoNextValidId(self, proto: Any) -> None:
        from ._proto.rest import createNextValidIdOrderId

        self.wrapper.nextValidId(createNextValidIdOrderId(proto))

    def _protoCurrentTime(self, proto: Any) -> None:
        from ._proto.rest import createCurrentTimeSeconds

        self.wrapper.currentTime(createCurrentTimeSeconds(proto))

    def _protoCurrentTimeInMillis(self, proto: Any) -> None:
        from ._proto.rest import createCurrentTimeInMillisMillis

        self.wrapper.currentTimeInMillis(createCurrentTimeInMillisMillis(proto))

    def _protoUserInfo(self, proto: Any) -> None:
        from ._proto.rest import createUserInfoArgs

        a = createUserInfoArgs(proto)
        self.wrapper.userInfo(a.reqId, a.whiteBrandingId)

    def _protoSecDefOptParameter(self, proto: Any) -> None:
        from ._proto.rest import createSecDefOptParameterArgs

        a = createSecDefOptParameterArgs(proto)
        self.wrapper.securityDefinitionOptionParameter(
            a.reqId,
            a.exchange,
            a.underlyingConId,
            a.tradingClass,
            a.multiplier,
            a.expirations,
            a.strikes,
        )

    def _protoSecDefOptParameterEnd(self, proto: Any) -> None:
        from ._proto.rest import createSecDefOptParameterEndReqId

        self.wrapper.securityDefinitionOptionParameterEnd(
            createSecDefOptParameterEndReqId(proto)
        )

    def _protoSoftDollarTiers(self, proto: Any) -> None:
        from ._proto.rest import createSoftDollarTiersArgs

        a = createSoftDollarTiersArgs(proto)
        self.wrapper.softDollarTiers(a.reqId, a.tiers)

    def _protoSymbolSamples(self, proto: Any) -> None:
        from ._proto.rest import createSymbolSamplesArgs

        a = createSymbolSamplesArgs(proto)
        self.wrapper.symbolSamples(a.reqId, a.contractDescriptions)

    def _protoSmartComponents(self, proto: Any) -> None:
        from ._proto.rest import createSmartComponentsArgs

        a = createSmartComponentsArgs(proto)
        self.wrapper.smartComponents(a.reqId, a.components)

    def _protoMarketRule(self, proto: Any) -> None:
        from ._proto.rest import createMarketRuleArgs

        a = createMarketRuleArgs(proto)
        self.wrapper.marketRule(a.marketRuleId, a.priceIncrements)

    def _protoFamilyCodes(self, proto: Any) -> None:
        from ._proto.accounts import createFamilyCodes

        self.wrapper.familyCodes(createFamilyCodes(proto))

    def _protoReceiveFA(self, proto: Any) -> None:
        from ._proto.accounts import createReceiveFAArgs

        a = createReceiveFAArgs(proto)
        self.wrapper.receiveFA(a.faDataType, a.xml)

    def _protoReplaceFAEnd(self, proto: Any) -> None:
        from ._proto.accounts import createReplaceFAEndArgs

        a = createReplaceFAEndArgs(proto)
        self.wrapper.replaceFAEnd(a.reqId, a.text)

    def parse(self, obj):
        """Parse the object's properties according to its default types."""
        cls = type(obj)
        entries = _PARSE_FIELDS.get(cls)
        if entries is None:
            # Cache miss: resolve every coercible field's type via the
            # class annotations so ``Decimal | None`` fields (whose
            # ``field.default`` is ``None``) are recognised. Subsequent
            # ``parse()`` calls of this class hit the cached plan.
            #
            # ``typing.get_type_hints(cls)`` evaluates the entire class
            # annotation block, including ``ClassVar`` entries. Compat
            # shims attached at import time (see ``ib_async/__init__.py``
            # binding ``cls.tuple = dataclassAsTuple``) overwrite class
            # attributes whose names collide with builtins used inside
            # those ClassVar annotations (``ClassVar[tuple[str, ...]]``).
            # When that happens the bulk evaluation raises with a confusing
            # ``'function' object is not subscriptable`` and ``parse()``
            # would crash for every Order/OrderState wire frame. We
            # resolve hints per-dataclass-field instead — ClassVars are
            # not in ``dataclasses.fields()`` so the broken annotations
            # are never touched.
            module_globals = vars(sys.modules.get(cls.__module__, None) or _NULL_MOD)
            plan: list[tuple[str, type, Any]] = []
            for field in dataclasses.fields(obj):
                raw = field.type
                if isinstance(raw, str):
                    try:
                        raw = eval(raw, module_globals)
                    except Exception:
                        continue
                typ = _resolveCoerceType(raw)
                if typ is not None:
                    plan.append((field.name, typ, field.default))
            entries = tuple(plan)
            _PARSE_FIELDS[cls] = entries

        for name, typ, default in entries:
            v = getattr(obj, name)
            if not v:
                setattr(obj, name, default)
            elif typ is int:
                setattr(obj, name, int(v))
            elif typ is float:
                setattr(obj, name, float(v))
            elif typ is Decimal:
                # Wire string → ``Decimal | None``. ``safe_decimal``
                # returns ``None`` for empty / "nan" / malformed input;
                # callers that need a non-``None`` floor (rare) can
                # post-process the field after ``parse()``.
                setattr(obj, name, safe_decimal(v))
            else:  # bool
                setattr(obj, name, bool(int(v)))

    def priceSizeTick(self, fields):
        # Wire layout: [msgId, version, reqId, tickType, price, size, attrMask]
        # The trailing attrMask was previously discarded — silently dropping
        # canAutoExecute / pastLimit / preOpen flags user code needs to gate
        # liquidity-quality decisions on. v3.0 surfaces them via TickAttrib.
        from ._proto.market_data import decodeTickAttribFromMask

        _, _, reqId, tickType, price, size, attrMask = fields

        if price:
            attrib = decodeTickAttribFromMask(int(attrMask or 0), self.serverVersion)
            self.wrapper.priceSizeTick(
                int(reqId),
                int(tickType),
                float(price),
                float(size or 0),
                attrib,
            )

    def errorMsg(self, fields):
        # Wire layout:
        #   pre-194:  msgId, version, reqId, errorCode, errorString [, advancedOrderRejectJson]
        #   >=194:    msgId, reqId, errorCode, errorString, advancedOrderRejectJson, errorTime
        # IBKR drops the legacy version prefix at MIN_SERVER_VER_ERROR_TIME (194)
        # and appends a wall-clock millis ``errorTime`` int. Without the gate,
        # a v>=194 server's reqId lands on errorCode, errorCode on errorString,
        # and every error message is corrupted.
        _, *fields = fields
        if self.serverVersion < MIN_SERVER_VER_ERROR_TIME:
            _, *fields = fields  # legacy version prefix
        reqId, errorCode, errorString, *fields = fields
        advancedOrderRejectJson = ""
        if self.serverVersion >= MIN_SERVER_VER_ADVANCED_ORDER_REJECT:
            advancedOrderRejectJson, *fields = fields
        errorTime = 0
        if self.serverVersion >= MIN_SERVER_VER_ERROR_TIME:
            errorTime, *fields = fields

        self.wrapper.error(
            int(reqId),
            int(errorCode),
            errorString,
            advancedOrderRejectJson,
            int(errorTime or 0),
        )

    def orderStatusMsg(self, fields):
        # Wire layout:
        #   pre-131:  msgId, version, orderId, status, filled, remaining,
        #             avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld
        #   >=131:    msgId, orderId, status, filled, remaining,
        #             avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld,
        #             mktCapPrice
        # IBKR drops the legacy version prefix at MIN_SERVER_VER_MARKET_CAP_PRICE
        # (131) and appends mktCapPrice. A static wrap() with skip=1 + 11 typed
        # slots either parses status as a Decimal (pre-131) or works (>=131);
        # the pre-131 case fails silently inside the wrap try/except, dropping
        # every orderStatus update from very-old servers.
        _, *fields = fields
        if self.serverVersion < MIN_SERVER_VER_MARKET_CAP_PRICE:
            _, *fields = fields  # legacy version prefix
        (
            orderId,
            status,
            filled,
            remaining,
            avgFillPrice,
            permId,
            parentId,
            lastFillPrice,
            clientId,
            whyHeld,
            *fields,
        ) = fields
        mktCapPrice: Decimal | None = None
        if self.serverVersion >= MIN_SERVER_VER_MARKET_CAP_PRICE:
            mktCapPriceStr, *fields = fields
            mktCapPrice = safe_decimal(mktCapPriceStr)
        self.wrapper.orderStatus(
            int(orderId),
            status,
            safe_decimal(filled),
            safe_decimal(remaining),
            safe_decimal(avgFillPrice),
            int(permId),
            int(parentId),
            safe_decimal(lastFillPrice),
            int(clientId),
            whyHeld,
            mktCapPrice,
        )

    def updatePortfolio(self, fields):
        c = Contract()
        (
            _,
            _,
            c.conId,
            c.symbol,
            c.secType,
            c.lastTradeDateOrContractMonth,
            c.strike,
            c.right,
            c.multiplier,
            c.primaryExchange,
            c.currency,
            c.localSymbol,
            c.tradingClass,
            position,
            marketPrice,
            marketValue,
            averageCost,
            unrealizedPNL,
            realizedPNL,
            accountName,
        ) = fields

        self.parse(c)
        self.wrapper.updatePortfolio(
            c,
            safe_decimal(position),
            safe_decimal(marketPrice),
            safe_decimal(marketValue),
            safe_decimal(averageCost),
            safe_decimal(unrealizedPNL),
            safe_decimal(realizedPNL),
            accountName,
        )

    def contractDetails(self, fields):
        cd = ContractDetails()
        cd.contract = c = Contract()
        if self.serverVersion < 164:
            fields.pop(0)
        (
            _,
            reqId,
            c.symbol,
            c.secType,
            lastTimes,
            *fields,
        ) = fields
        # Gate 182 (MIN_SERVER_VER_LAST_TRADE_DATE): IBKR appends a separate
        # ``lastTradeDate`` slot after the legacy ``lastTradeDateOrContractMonth``
        # block. Without this read every subsequent ContractDetails field shifts
        # one slot left on a 182+ server (strike lands as right, right as
        # exchange, etc.), corrupting the entire decode.
        if self.serverVersion >= MIN_SERVER_VER_LAST_TRADE_DATE:
            c.lastTradeDate, *fields = fields
        (
            c.strike,
            c.right,
            c.exchange,
            c.currency,
            c.localSymbol,
            cd.marketName,
            c.tradingClass,
            c.conId,
            cd.minTick,
            *fields,
        ) = fields
        if self.serverVersion < 164:
            fields.pop(0)  # obsolete mdSizeMultiplier

        (
            c.multiplier,
            cd.orderTypes,
            cd.validExchanges,
            cd.priceMagnifier,
            cd.underConId,
            cd.longName,
            c.primaryExchange,
            cd.contractMonth,
            cd.industry,
            cd.category,
            cd.subcategory,
            cd.timeZoneId,
            cd.tradingHours,
            cd.liquidHours,
            cd.evRule,
            cd.evMultiplier,
            numSecIds,
            *fields,
        ) = fields

        numSecIds = int(numSecIds)
        if numSecIds > 0:
            cd.secIdList = []
            for _ in range(numSecIds):
                tag, value, *fields = fields
                cd.secIdList += [TagValue(tag, value)]

        # IBKR adds these fields one gate at a time across server versions
        # 121-152. The min client version we declare is 100, so a server in
        # the 100-151 range can deliver a strictly shorter frame; reading
        # unconditionally would shift every subsequent gated field left.
        if self.serverVersion >= MIN_SERVER_VER_AGG_GROUP:
            cd.aggGroup, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_UNDERLYING_INFO:
            cd.underSymbol, cd.underSecType, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_MARKET_RULES:
            cd.marketRuleIds, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_REAL_EXPIRATION_DATE:
            cd.realExpirationDate, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_STOCK_TYPE:
            cd.stockType, *fields = fields

        if self.serverVersion == 163:
            cd.suggestedSizeIncrement, *fields = fields

        if self.serverVersion >= 164:
            (
                cd.minSize,
                cd.sizeIncrement,
                cd.suggestedSizeIncrement,
                # cd.minCashQtySize,
                *fields,
            ) = fields

        # Gate 179 (MIN_SERVER_VER_FUND_DATA_FIELDS): for FUND secType only,
        # the wire frame carries a 16-field fund-family block. The protobuf
        # path already reads these (see ``_proto/contracts.py`` at f11c4ba);
        # without the binary read every following gated field (ineligibility
        # reasons) shifts left and the FUND fields themselves are lost.
        if (
            self.serverVersion >= MIN_SERVER_VER_FUND_DATA_FIELDS
            and c.secType == "FUND"
        ):
            (
                cd.fundName,
                cd.fundFamily,
                cd.fundType,
                cd.fundFrontLoad,
                cd.fundBackLoad,
                cd.fundBackLoadTimeInterval,
                cd.fundManagementFee,
                cd.fundClosed,
                cd.fundClosedForNewInvestors,
                cd.fundClosedForNewMoney,
                cd.fundNotifyAmount,
                cd.fundMinimumInitialPurchase,
                cd.fundSubsequentMinimumPurchase,
                cd.fundBlueSkyStates,
                cd.fundBlueSkyTerritories,
                cd.fundDistributionPolicyIndicator,
                cd.fundAssetType,
                *fields,
            ) = fields

        # Gate 186 (MIN_SERVER_VER_INELIGIBILITY_REASONS): variable-length list
        # prefixed by its count. Each entry is two strings: ``id_`` and
        # ``description``. When count==0 only the count slot is present.
        if self.serverVersion >= MIN_SERVER_VER_INELIGIBILITY_REASONS:
            ineligibilityCount, *fields = fields
            n = int(ineligibilityCount or 0)
            if n > 0:
                cd.ineligibilityReasonList = []
                for _ in range(n):
                    rid, rdesc, *fields = fields
                    cd.ineligibilityReasonList.append(
                        IneligibilityReason(id_=rid, description=rdesc)
                    )

        times = lastTimes.split("-" if "-" in lastTimes else None)

        if len(times) > 0:
            c.lastTradeDateOrContractMonth = times[0]

        if len(times) > 1:
            cd.lastTradeTime = times[1]

        if len(times) > 2:
            cd.timeZoneId = times[2]

        cd.longName = cd.longName.encode().decode("unicode-escape")
        self.parse(cd)
        self.parse(c)
        self.wrapper.contractDetails(int(reqId), cd)

    def bondContractDetails(self, fields):
        cd = ContractDetails()
        cd.contract = c = Contract()
        if self.serverVersion < 164:
            fields.pop(0)

        (
            _,
            reqId,
            c.symbol,
            c.secType,
            cd.cusip,
            cd.coupon,
            lastTimes,
            cd.issueDate,
            cd.ratings,
            cd.bondType,
            cd.couponType,
            cd.convertible,
            cd.callable,
            cd.putable,
            cd.descAppend,
            c.exchange,
            c.currency,
            cd.marketName,
            c.tradingClass,
            c.conId,
            cd.minTick,
            *fields,
        ) = fields

        if self.serverVersion < 164:
            fields.pop(0)  # obsolete mdSizeMultiplier

        (
            cd.orderTypes,
            cd.validExchanges,
            cd.nextOptionDate,
            cd.nextOptionType,
            cd.nextOptionPartial,
            cd.notes,
            cd.longName,
            *fields,
        ) = fields

        # Gate 188 (MIN_SERVER_VER_BOND_TRADING_HOURS): IBKR inserts a
        # timezone + hours block between ``longName`` and ``evRule``.
        # Without these reads on a 188+ server, ``evRule`` lands as
        # ``timeZoneId`` and every following field shifts left.
        if self.serverVersion >= MIN_SERVER_VER_BOND_TRADING_HOURS:
            (
                cd.timeZoneId,
                cd.tradingHours,
                cd.liquidHours,
                *fields,
            ) = fields

        (
            cd.evRule,
            cd.evMultiplier,
            numSecIds,
            *fields,
        ) = fields

        numSecIds = int(numSecIds)
        if numSecIds > 0:
            cd.secIdList = []
            for _ in range(numSecIds):
                tag, value, *fields = fields
                cd.secIdList += [TagValue(tag, value)]

        cd.aggGroup, cd.marketRuleIds, *fields = fields
        if self.serverVersion >= 164:
            (
                cd.minSize,
                cd.sizeIncrement,
                cd.suggestedSizeIncrement,
                # cd.minCashQtySize,
                *fields,
            ) = fields

        times = lastTimes.split("-" if "-" in lastTimes else None)

        if len(times) > 0:
            cd.maturity = times[0]

        if len(times) > 1:
            cd.lastTradeTime = times[1]

        # Pre-188 servers pack the timezone into the third split component
        # of ``lastTradeDateOrContractMonth``; 188+ delivers it as an
        # explicit ``timeZoneId`` field above. Mirror IBKR's reference:
        # the explicit field WINS when both are present, so only adopt the
        # split-derived value below the gate.
        if len(times) > 2 and self.serverVersion < MIN_SERVER_VER_BOND_TRADING_HOURS:
            cd.timeZoneId = times[2]

        self.parse(cd)
        self.parse(c)
        self.wrapper.bondContractDetails(int(reqId), cd)

    def execDetails(self, fields):
        c = Contract()
        ex = Execution()
        (
            _,
            reqId,
            ex.orderId,
            c.conId,
            c.symbol,
            c.secType,
            c.lastTradeDateOrContractMonth,
            c.strike,
            c.right,
            c.multiplier,
            c.exchange,
            c.currency,
            c.localSymbol,
            c.tradingClass,
            ex.execId,
            timeStr,
            ex.acctNumber,
            ex.exchange,
            ex.side,
            ex.shares,
            ex.price,
            ex.permId,
            ex.clientId,
            ex.liquidation,
            ex.cumQty,
            ex.avgPrice,
            ex.orderRef,
            ex.evRule,
            ex.evMultiplier,
            ex.modelCode,
            ex.lastLiquidity,
            *fields,
        ) = fields
        if self.serverVersion >= 178:
            ex.pendingPriceRevision, *fields = fields

        # Gate 198 (MIN_SERVER_VER_SUBMITTER): IBKR appends the submitting
        # user identity past the pending-price-revision flag. Domain field
        # ``Execution.submitter`` already exists; without this read the
        # value is silently dropped on every modern fill.
        if self.serverVersion >= MIN_SERVER_VER_SUBMITTER:
            ex.submitter, *fields = fields

        self.parse(c)
        self.parse(ex)
        ex.time = self._normalizeExecutionTime(timeStr)
        self.wrapper.execDetails(int(reqId), c, ex)

    def historicalData(self, fields):
        # Wire layout shifts at MIN_SERVER_VER_HISTORICAL_DATA_END (196):
        #   pre-196: msgId, reqId, startDateStr, endDateStr, numBars, [bars...]
        #            historicalDataEnd is emitted inline at the tail.
        #   >=196:   msgId, reqId, numBars, [bars...]
        #            startDateStr/endDateStr ship as a separate
        #            HISTORICAL_DATA_END frame (msgId 108) which fires
        #            wrapper.historicalDataEnd. Without the gate, on a
        #            196+ server reqId/startDateStr/endDateStr/numBars
        #            shift one slot left and every bar is corrupted.
        _, *fields = fields
        if self.serverVersion < MIN_SERVER_VER_SYNT_REALTIME_BARS:
            _, *fields = fields  # legacy version prefix (pre-124)
        reqId, *fields = fields
        startDateStr = ""
        endDateStr = ""
        if self.serverVersion < MIN_SERVER_VER_HISTORICAL_DATA_END:
            startDateStr, endDateStr, *fields = fields
        numBars, *fields = fields
        get = iter(fields).__next__

        for _ in range(int(numBars)):
            bar = BarData(
                date=get(),
                open=safe_decimal(get()),
                high=safe_decimal(get()),
                low=safe_decimal(get()),
                close=safe_decimal(get()),
                volume=safe_decimal(get()),
                average=safe_decimal(get()),
                barCount=int(get()),
            )
            self.wrapper.historicalData(int(reqId), bar)

        if self.serverVersion < MIN_SERVER_VER_HISTORICAL_DATA_END:
            self.wrapper.historicalDataEnd(int(reqId), startDateStr, endDateStr)

    def historicalDataEnd(self, fields):
        # Binary handler for msgId 108 — the dedicated end-of-dataset
        # frame IBKR added at MIN_SERVER_VER_HISTORICAL_DATA_END (196).
        # On older servers historicalData itself fires the end signal.
        _, reqId, startDateStr, endDateStr = fields
        self.wrapper.historicalDataEnd(int(reqId), startDateStr, endDateStr)

    def historicalDataUpdate(self, fields):
        _, reqId, *fields = fields
        get = iter(fields).__next__

        bar = BarData(
            barCount=int(get() or 0),
            date=get(),
            open=safe_decimal(get()),
            close=safe_decimal(get()),
            high=safe_decimal(get()),
            low=safe_decimal(get()),
            average=safe_decimal(get()),
            volume=safe_decimal(get()),
        )

        self.wrapper.historicalDataUpdate(int(reqId), bar)

    def scannerData(self, fields):
        _, _, reqId, n, *fields = fields

        for _ in range(int(n)):
            cd = ContractDetails()
            cd.contract = c = Contract()
            (
                rank,
                c.conId,
                c.symbol,
                c.secType,
                c.lastTradeDateOrContractMonth,
                c.strike,
                c.right,
                c.exchange,
                c.currency,
                c.localSymbol,
                cd.marketName,
                c.tradingClass,
                distance,
                benchmark,
                projection,
                legsStr,
                *fields,
            ) = fields

            self.parse(cd)
            self.parse(c)
            self.wrapper.scannerData(
                int(reqId), int(rank), cd, distance, benchmark, projection, legsStr
            )

        self.wrapper.scannerDataEnd(int(reqId))

    def tickOptionComputation(self, fields):
        _, reqId, tickTypeInt, tickAttrib, *fields = fields
        impliedVol, delta, optPrice, pvDividend, gamma, vega, theta, undPrice = fields

        self.wrapper.tickOptionComputation(
            int(reqId),
            int(tickTypeInt),
            int(tickAttrib),
            float(impliedVol),
            float(delta),
            float(optPrice),
            float(pvDividend),
            float(gamma),
            float(vega),
            float(theta),
            float(undPrice),
        )

    def deltaNeutralValidation(self, fields):
        _, _, reqId, conId, delta, price = fields

        self.wrapper.deltaNeutralValidation(
            int(reqId),
            DeltaNeutralContract(int(conId), float(delta or 0), float(price or 0)),
        )

    def commissionReport(self, fields):
        (
            _,
            _,
            execId,
            commission,
            currency,
            realizedPNL,
            yield_,
            yieldRedemptionDate,
        ) = fields

        self.wrapper.commissionReport(
            CommissionReport(
                execId,
                safe_decimal(commission),
                currency,
                safe_decimal(realizedPNL),
                safe_decimal(yield_),
                int(yieldRedemptionDate or 0),
            )
        )

    def position(self, fields):
        c = Contract()
        (
            _,
            _,
            account,
            c.conId,
            c.symbol,
            c.secType,
            c.lastTradeDateOrContractMonth,
            c.strike,
            c.right,
            c.multiplier,
            c.exchange,
            c.currency,
            c.localSymbol,
            c.tradingClass,
            position,
            avgCost,
        ) = fields

        self.parse(c)
        self.wrapper.position(account, c, safe_decimal(position), safe_decimal(avgCost))

    def positionMulti(self, fields):
        c = Contract()
        (
            _,
            _,
            reqId,
            account,
            c.conId,
            c.symbol,
            c.secType,
            c.lastTradeDateOrContractMonth,
            c.strike,
            c.right,
            c.multiplier,
            c.exchange,
            c.currency,
            c.localSymbol,
            c.tradingClass,
            position,
            avgCost,
            modelCode,
        ) = fields

        self.parse(c)
        self.wrapper.positionMulti(
            int(reqId),
            account,
            modelCode,
            c,
            safe_decimal(position),
            safe_decimal(avgCost),
        )

    def securityDefinitionOptionParameter(self, fields):
        (
            _,
            reqId,
            exchange,
            underlyingConId,
            tradingClass,
            multiplier,
            n,
            *fields,
        ) = fields
        n = int(n)

        expirations = fields[:n]
        strikes = [float(field) for field in fields[n + 1 :]]

        self.wrapper.securityDefinitionOptionParameter(
            int(reqId),
            exchange,
            int(underlyingConId),
            tradingClass,
            multiplier,
            expirations,
            strikes,
        )

    def softDollarTiers(self, fields):
        _, reqId, n, *fields = fields
        get = iter(fields).__next__

        tiers = [
            SoftDollarTier(name=get(), val=get(), displayName=get())
            for _ in range(int(n))
        ]

        self.wrapper.softDollarTiers(int(reqId), tiers)

    def familyCodes(self, fields):
        _, n, *fields = fields
        get = iter(fields).__next__

        familyCodes = [
            FamilyCode(accountID=get(), familyCodeStr=get()) for _ in range(int(n))
        ]

        self.wrapper.familyCodes(familyCodes)

    def symbolSamples(self, fields):
        _, reqId, n, *fields = fields

        cds = []
        for _ in range(int(n)):
            cd = ContractDescription()
            cd.contract = c = Contract()
            (
                c.conId,
                c.symbol,
                c.secType,
                c.primaryExchange,
                c.currency,
                m,
                *fields,
            ) = fields
            c.conId = int(c.conId)
            m = int(m)
            cd.derivativeSecTypes = fields[:m]
            fields = fields[m:]
            if self.serverVersion >= 176:
                (cd.contract.description, cd.contract.issuerId, *fields) = fields
            cds.append(cd)

        self.wrapper.symbolSamples(int(reqId), cds)

    def smartComponents(self, fields):
        _, reqId, n, *fields = fields
        get = iter(fields).__next__

        components = [
            SmartComponent(bitNumber=int(get()), exchange=get(), exchangeLetter=get())
            for _ in range(int(n))
        ]

        self.wrapper.smartComponents(int(reqId), components)

    def mktDepthExchanges(self, fields):
        _, n, *fields = fields
        get = iter(fields).__next__

        descriptions = [
            DepthMktDataDescription(
                exchange=get(),
                secType=get(),
                listingExch=get(),
                serviceDataType=get(),
                aggGroup=int(get()),
            )
            for _ in range(int(n))
        ]

        self.wrapper.mktDepthExchanges(descriptions)

    def newsProviders(self, fields):
        _, n, *fields = fields
        get = iter(fields).__next__

        providers = [NewsProvider(code=get(), name=get()) for _ in range(int(n))]

        self.wrapper.newsProviders(providers)

    def histogramData(self, fields):
        _, reqId, n, *fields = fields
        get = iter(fields).__next__

        histogram = [
            HistogramData(price=float(get()), size=safe_decimal(get()))
            for _ in range(int(n))
        ]

        self.wrapper.histogramData(int(reqId), histogram)

    def marketRule(self, fields):
        _, marketRuleId, n, *fields = fields
        get = iter(fields).__next__

        increments = [
            PriceIncrement(lowEdge=float(get()), increment=float(get()))
            for _ in range(int(n))
        ]

        self.wrapper.marketRule(int(marketRuleId), increments)

    def historicalTicks(self, fields):
        _, reqId, n, *fields = fields
        get = iter(fields).__next__
        tz = self.wrapper.defaultTimezone

        ticks = []
        for _ in range(int(n)):
            time = int(get())
            get()
            price = float(get())
            size = float(get())
            dt = datetime.fromtimestamp(time, tz)
            ticks.append(HistoricalTick(dt, price, size))

        done = bool(int(get()))
        self.wrapper.historicalTicks(int(reqId), ticks, done)

    def historicalTicksBidAsk(self, fields):
        _, reqId, n, *fields = fields
        get = iter(fields).__next__
        tz = self.wrapper.defaultTimezone

        ticks = []
        for _ in range(int(n)):
            time = int(get())
            mask = int(get())
            attrib = TickAttribBidAsk(
                bidPastLow=bool(mask & 1), askPastHigh=bool(mask & 2)
            )
            priceBid = float(get())
            priceAsk = float(get())
            sizeBid = float(get())
            sizeAsk = float(get())
            dt = datetime.fromtimestamp(time, tz)
            ticks.append(
                HistoricalTickBidAsk(dt, attrib, priceBid, priceAsk, sizeBid, sizeAsk)
            )

        done = bool(int(get()))
        self.wrapper.historicalTicksBidAsk(int(reqId), ticks, done)

    def historicalTicksLast(self, fields):
        _, reqId, n, *fields = fields
        get = iter(fields).__next__
        tz = self.wrapper.defaultTimezone

        ticks = []
        for _ in range(int(n)):
            time = int(get())
            mask = int(get())
            attrib = TickAttribLast(pastLimit=bool(mask & 1), unreported=bool(mask & 2))
            price = float(get())
            size = float(get())
            exchange = get()
            specialConditions = get()
            dt = datetime.fromtimestamp(time, tz)
            ticks.append(
                HistoricalTickLast(dt, attrib, price, size, exchange, specialConditions)
            )

        done = bool(int(get()))
        self.wrapper.historicalTicksLast(int(reqId), ticks, done)

    def tickByTick(self, fields):
        _, reqId, tickType, time, *fields = fields
        reqId = int(reqId)
        tickType = int(tickType)
        time = int(time)

        if tickType in _TICK_BY_TICK_LAST_TYPES:
            price, size, mask, exchange, specialConditions = fields
            mask = int(mask)
            attrib: Any = TickAttribLast(
                pastLimit=bool(mask & 1), unreported=bool(mask & 2)
            )

            self.wrapper.tickByTickAllLast(
                reqId,
                tickType,
                time,
                float(price),
                float(size),
                attrib,
                exchange,
                specialConditions,
            )
        elif tickType == 3:
            bidPrice, askPrice, bidSize, askSize, mask = fields
            mask = int(mask)
            attrib = TickAttribBidAsk(
                bidPastLow=bool(mask & 1), askPastHigh=bool(mask & 2)
            )

            self.wrapper.tickByTickBidAsk(
                reqId,
                time,
                float(bidPrice),
                float(askPrice),
                float(bidSize),
                float(askSize),
                attrib,
            )
        elif tickType == 4:
            (midPoint,) = fields

            self.wrapper.tickByTickMidPoint(reqId, time, float(midPoint))

    def openOrder(self, fields):
        o = Order()
        c = Contract()
        st = OrderState()
        (
            _,
            o.orderId,
            c.conId,
            c.symbol,
            c.secType,
            c.lastTradeDateOrContractMonth,
            c.strike,
            c.right,
            c.multiplier,
            c.exchange,
            c.currency,
            c.localSymbol,
            c.tradingClass,
            o.action,
            o.totalQuantity,
            o.orderType,
            o.lmtPrice,
            o.auxPrice,
            o.tif,
            o.ocaGroup,
            o.account,
            o.openClose,
            o.origin,
            o.orderRef,
            o.clientId,
            o.permId,
            o.outsideRth,
            o.hidden,
            o.discretionaryAmt,
            o.goodAfterTime,
            _,
            o.faGroup,
            o.faMethod,
            o.faPercentage,
            *fields,
        ) = fields

        if self.serverVersion < 177:
            o.faProfile, *fields = fields

        (
            o.modelCode,
            o.goodTillDate,
            o.rule80A,
            o.percentOffset,
            o.settlingFirm,
            o.shortSaleSlot,
            o.designatedLocation,
            o.exemptCode,
            o.auctionStrategy,
            o.startingPrice,
            o.stockRefPrice,
            o.delta,
            o.stockRangeLower,
            o.stockRangeUpper,
            o.displaySize,
            o.blockOrder,
            o.sweepToFill,
            o.allOrNone,
            o.minQty,
            o.ocaType,
            o.eTradeOnly,
            o.firmQuoteOnly,
            o.nbboPriceCap,
            o.parentId,
            o.triggerMethod,
            o.volatility,
            o.volatilityType,
            o.deltaNeutralOrderType,
            o.deltaNeutralAuxPrice,
            *fields,
        ) = fields

        if o.deltaNeutralOrderType:
            (
                o.deltaNeutralConId,
                o.deltaNeutralSettlingFirm,
                o.deltaNeutralClearingAccount,
                o.deltaNeutralClearingIntent,
                o.deltaNeutralOpenClose,
                o.deltaNeutralShortSale,
                o.deltaNeutralShortSaleSlot,
                o.deltaNeutralDesignatedLocation,
                *fields,
            ) = fields

        (
            o.continuousUpdate,
            o.referencePriceType,
            o.trailStopPrice,
            o.trailingPercent,
            o.basisPoints,
            o.basisPointsType,
            c.comboLegsDescrip,
            *fields,
        ) = fields

        numLegs = int(fields.pop(0))
        c.comboLegs = []
        for _ in range(numLegs):
            leg: Any = ComboLeg()
            (
                leg.conId,
                leg.ratio,
                leg.action,
                leg.exchange,
                leg.openClose,
                leg.shortSaleSlot,
                leg.designatedLocation,
                leg.exemptCode,
                *fields,
            ) = fields
            self.parse(leg)
            c.comboLegs.append(leg)

        numOrderLegs = int(fields.pop(0))
        o.orderComboLegs = []
        for _ in range(numOrderLegs):
            leg = OrderComboLeg()
            leg.price = fields.pop(0)
            self.parse(leg)
            o.orderComboLegs.append(leg)

        numParams = int(fields.pop(0))
        if numParams > 0:
            o.smartComboRoutingParams = []
            for _ in range(numParams):
                tag, value, *fields = fields
                o.smartComboRoutingParams.append(TagValue(tag, value))

        (o.scaleInitLevelSize, o.scaleSubsLevelSize, increment, *fields) = fields

        o.scalePriceIncrement = float(increment or UNSET_DOUBLE)
        if 0 < o.scalePriceIncrement < UNSET_DOUBLE:
            (
                o.scalePriceAdjustValue,
                o.scalePriceAdjustInterval,
                o.scaleProfitOffset,
                o.scaleAutoReset,
                o.scaleInitPosition,
                o.scaleInitFillQty,
                o.scaleRandomPercent,
                *fields,
            ) = fields

        o.hedgeType = fields.pop(0)
        if o.hedgeType:
            o.hedgeParam = fields.pop(0)

        (
            o.optOutSmartRouting,
            o.clearingAccount,
            o.clearingIntent,
            o.notHeld,
            dncPresent,
            *fields,
        ) = fields

        if int(dncPresent):
            conId, delta, price, *fields = fields
            c.deltaNeutralContract = DeltaNeutralContract(
                int(conId or 0), float(delta or 0), float(price or 0)
            )

        o.algoStrategy = fields.pop(0)
        if o.algoStrategy:
            numParams = int(fields.pop(0))
            if numParams > 0:
                o.algoParams = []
                for _ in range(numParams):
                    tag, value, *fields = fields
                    o.algoParams.append(TagValue(tag, value))

        (
            o.solicited,
            o.whatIf,
            st.status,
            st.initMarginBefore,
            st.maintMarginBefore,
            st.equityWithLoanBefore,
            st.initMarginChange,
            st.maintMarginChange,
            st.equityWithLoanChange,
            st.initMarginAfter,
            st.maintMarginAfter,
            st.equityWithLoanAfter,
            st.commission,
            st.minCommission,
            st.maxCommission,
            st.commissionCurrency,
            *fields,
        ) = fields

        # FULL_ORDER_PREVIEW_FIELDS block — IBKR's reference appends the
        # OutsideRTH margin family, suggestedSize / rejectReason, and the
        # repeated orderAllocations between commissionCurrency and
        # warningText starting at server 195. Without this gating block
        # the wire stream shifts left and every gated read past warningText
        # reads from the wrong slot, silently corrupting the rest of the
        # decode. ``decodeWhatIfInfoAndCommissionAndFees`` mirror.
        if self.serverVersion >= MIN_SERVER_VER_FULL_ORDER_PREVIEW_FIELDS:
            (
                st.marginCurrency,
                st.initMarginBeforeOutsideRTH,
                st.maintMarginBeforeOutsideRTH,
                st.equityWithLoanBeforeOutsideRTH,
                st.initMarginChangeOutsideRTH,
                st.maintMarginChangeOutsideRTH,
                st.equityWithLoanChangeOutsideRTH,
                st.initMarginAfterOutsideRTH,
                st.maintMarginAfterOutsideRTH,
                st.equityWithLoanAfterOutsideRTH,
                suggestedSize,
                st.rejectReason,
                *fields,
            ) = fields
            st.suggestedSize = safe_decimal(suggestedSize)
            accountsCount = int(fields.pop(0))
            if accountsCount > 0:
                allocations: list[OrderAllocation] = []
                for _ in range(accountsCount):
                    (
                        allocAccount,
                        allocPosition,
                        allocPositionDesired,
                        allocPositionAfter,
                        allocDesiredAllocQty,
                        allocAllowedAllocQty,
                        allocIsMonetary,
                        *fields,
                    ) = fields
                    allocations.append(
                        OrderAllocation(
                            account=allocAccount,
                            position=safe_decimal(allocPosition),
                            positionDesired=safe_decimal(allocPositionDesired),
                            positionAfter=safe_decimal(allocPositionAfter),
                            desiredAllocQty=safe_decimal(allocDesiredAllocQty),
                            allowedAllocQty=safe_decimal(allocAllowedAllocQty),
                            isMonetary=bool(int(allocIsMonetary or 0)),
                        )
                    )
                st.orderAllocations = allocations

        (
            st.warningText,
            o.randomizeSize,
            o.randomizePrice,
            *fields,
        ) = fields

        if o.orderType in _PEG_BENCH_ORDER_TYPES:
            (
                o.referenceContractId,
                o.isPeggedChangeAmountDecrease,
                o.peggedChangeAmount,
                o.referenceChangeAmount,
                o.referenceExchangeId,
                *fields,
            ) = fields

        numConditions = int(fields.pop(0))
        if numConditions > 0:
            for _ in range(numConditions):
                condType = int(fields.pop(0))
                condCls = OrderCondition.createClass(condType)
                n = len(dataclasses.fields(condCls)) - 1
                cond = condCls(condType, *fields[:n])
                self.parse(cond)
                o.conditions.append(cond)
                fields = fields[n:]
            (o.conditionsIgnoreRth, o.conditionsCancelOrder, *fields) = fields

        (
            o.adjustedOrderType,
            o.triggerPrice,
            o.trailStopPrice,
            o.lmtPriceOffset,
            o.adjustedStopPrice,
            o.adjustedStopLimitPrice,
            o.adjustedTrailingAmount,
            o.adjustableTrailingUnit,
            o.softDollarTier.name,
            o.softDollarTier.val,
            o.softDollarTier.displayName,
            o.cashQty,
            o.dontUseAutoPriceForHedge,
            o.isOmsContainer,
            o.discretionaryUpToLimitPrice,
            o.usePriceMgmtAlgo,
            *fields,
        ) = fields

        if self.serverVersion >= MIN_SERVER_VER_DURATION:
            o.duration = fields.pop(0)

        if self.serverVersion >= MIN_SERVER_VER_POST_TO_ATS:
            o.postToAts = fields.pop(0)

        if self.serverVersion >= MIN_SERVER_VER_AUTO_CANCEL_PARENT:
            o.autoCancelParent = fields.pop(0)

        if self.serverVersion >= MIN_SERVER_VER_PEGBEST_PEGMID_OFFSETS:
            (
                o.minTradeQty,
                o.minCompeteSize,
                o.competeAgainstBestOffset,
                o.midOffsetAtWhole,
                o.midOffsetAtHalf,
                *fields,
            ) = fields

        # Trailing wire fields IBKR appends past gate 170. Most landing
        # slots have no Order dataclass field yet — they are consumed and
        # discarded so subsequent gated reads don't shift left. Order
        # dataclass field expansion is task #163; only ``extOperator`` and
        # ``imbalanceOnly`` (already on Order) are surfaced here.
        if self.serverVersion >= MIN_SERVER_VER_CUSTOMER_ACCOUNT:
            # Consumed but not surfaced; Order dataclass field expansion is task #163
            _customerAccount, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_PROFESSIONAL_CUSTOMER:
            # Consumed but not surfaced; Order dataclass field expansion is task #163
            _professionalCustomer, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_BOND_ACCRUED_INTEREST:
            # Consumed but not surfaced; Order dataclass field expansion is task #163
            _bondAccruedInterest, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_INCLUDE_OVERNIGHT:
            # Consumed but not surfaced; Order dataclass field expansion is task #163
            _includeOvernight, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_CME_TAGGING_FIELDS_IN_OPEN_ORDER:
            # ``extOperator`` lives on Order; ``manualOrderIndicator`` does not
            # yet — consumed and discarded. Order dataclass field expansion is
            # task #163.
            o.extOperator, _manualOrderIndicator, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_SUBMITTER:
            # Consumed but not surfaced; Order dataclass field expansion is task #163
            _submitter, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_IMBALANCE_ONLY:
            o.imbalanceOnly, *fields = fields

        self.parse(c)
        self.parse(o)
        self.parse(st)
        self.wrapper.openOrder(o.orderId, c, o, st)

    def completedOrder(self, fields):
        o = Order()
        c = Contract()
        st = OrderState()

        (
            _,
            c.conId,
            c.symbol,
            c.secType,
            c.lastTradeDateOrContractMonth,
            c.strike,
            c.right,
            c.multiplier,
            c.exchange,
            c.currency,
            c.localSymbol,
            c.tradingClass,
            o.action,
            o.totalQuantity,
            o.orderType,
            o.lmtPrice,
            o.auxPrice,
            o.tif,
            o.ocaGroup,
            o.account,
            o.openClose,
            o.origin,
            o.orderRef,
            o.permId,
            o.outsideRth,
            o.hidden,
            o.discretionaryAmt,
            o.goodAfterTime,
            o.faGroup,
            o.faMethod,
            o.faPercentage,
            *fields,
        ) = fields
        if self.serverVersion < 177:
            o.faProfile, *fields = fields

        (
            o.modelCode,
            o.goodTillDate,
            o.rule80A,
            o.percentOffset,
            o.settlingFirm,
            o.shortSaleSlot,
            o.designatedLocation,
            o.exemptCode,
            o.startingPrice,
            o.stockRefPrice,
            o.delta,
            o.stockRangeLower,
            o.stockRangeUpper,
            o.displaySize,
            o.sweepToFill,
            o.allOrNone,
            o.minQty,
            o.ocaType,
            o.triggerMethod,
            o.volatility,
            o.volatilityType,
            o.deltaNeutralOrderType,
            o.deltaNeutralAuxPrice,
            *fields,
        ) = fields

        if o.deltaNeutralOrderType:
            (
                o.deltaNeutralConId,
                o.deltaNeutralShortSale,
                o.deltaNeutralShortSaleSlot,
                o.deltaNeutralDesignatedLocation,
                *fields,
            ) = fields

        (
            o.continuousUpdate,
            o.referencePriceType,
            o.trailStopPrice,
            o.trailingPercent,
            c.comboLegsDescrip,
            *fields,
        ) = fields

        numLegs = int(fields.pop(0))
        c.comboLegs = []
        for _ in range(numLegs):
            leg: Any = ComboLeg()
            (
                leg.conId,
                leg.ratio,
                leg.action,
                leg.exchange,
                leg.openClose,
                leg.shortSaleSlot,
                leg.designatedLocation,
                leg.exemptCode,
                *fields,
            ) = fields
            self.parse(leg)
            c.comboLegs.append(leg)

        numOrderLegs = int(fields.pop(0))
        o.orderComboLegs = []
        for _ in range(numOrderLegs):
            leg = OrderComboLeg()
            leg.price = fields.pop(0)
            self.parse(leg)
            o.orderComboLegs.append(leg)

        numParams = int(fields.pop(0))
        if numParams > 0:
            o.smartComboRoutingParams = []
            for _ in range(numParams):
                tag, value, *fields = fields
                o.smartComboRoutingParams.append(TagValue(tag, value))
        (o.scaleInitLevelSize, o.scaleSubsLevelSize, increment, *fields) = fields

        o.scalePriceIncrement = float(increment or UNSET_DOUBLE)
        if 0 < o.scalePriceIncrement < UNSET_DOUBLE:
            (
                o.scalePriceAdjustValue,
                o.scalePriceAdjustInterval,
                o.scaleProfitOffset,
                o.scaleAutoReset,
                o.scaleInitPosition,
                o.scaleInitFillQty,
                o.scaleRandomPercent,
                *fields,
            ) = fields

        o.hedgeType = fields.pop(0)
        if o.hedgeType:
            o.hedgeParam = fields.pop(0)

        (o.clearingAccount, o.clearingIntent, o.notHeld, dncPresent, *fields) = fields

        if int(dncPresent):
            conId, delta, price, *fields = fields
            c.deltaNeutralContract = DeltaNeutralContract(
                int(conId or 0), float(delta or 0), float(price or 0)
            )

        o.algoStrategy = fields.pop(0)
        if o.algoStrategy:
            numParams = int(fields.pop(0))
            if numParams > 0:
                o.algoParams = []
                for _ in range(numParams):
                    tag, value, *fields = fields
                    o.algoParams.append(TagValue(tag, value))
        (o.solicited, st.status, o.randomizeSize, o.randomizePrice, *fields) = fields

        if o.orderType in _PEG_BENCH_ORDER_TYPES:
            (
                o.referenceContractId,
                o.isPeggedChangeAmountDecrease,
                o.peggedChangeAmount,
                o.referenceChangeAmount,
                o.referenceExchangeId,
                *fields,
            ) = fields

        numConditions = int(fields.pop(0))
        if numConditions > 0:
            for _ in range(numConditions):
                condType = int(fields.pop(0))
                condCls = OrderCondition.createClass(condType)
                n = len(dataclasses.fields(condCls)) - 1
                cond = condCls(condType, *fields[:n])
                self.parse(cond)
                o.conditions.append(cond)
                fields = fields[n:]
            (o.conditionsIgnoreRth, o.conditionsCancelOrder, *fields) = fields

        (
            o.trailStopPrice,
            o.lmtPriceOffset,
            o.cashQty,
            o.dontUseAutoPriceForHedge,
            o.isOmsContainer,
            o.autoCancelDate,
            o.filledQuantity,
            o.refFuturesConId,
            o.autoCancelParent,
            o.shareholder,
            o.imbalanceOnly,
            o.routeMarketableToBbo,
            o.parentPermId,
            st.completedTime,
            st.completedStatus,
            *fields,
        ) = fields

        if self.serverVersion >= MIN_SERVER_VER_PEGBEST_PEGMID_OFFSETS:
            (
                o.minTradeQty,
                o.minCompeteSize,
                o.competeAgainstBestOffset,
                o.midOffsetAtWhole,
                o.midOffsetAtHalf,
                *fields,
            ) = fields

        # Trailing wire fields IBKR's ``processCompletedOrderMsg`` appends past
        # gate 170. Order dataclass field expansion is task #163 — these slots
        # are consumed and discarded so subsequent gated reads stay aligned.
        if self.serverVersion >= MIN_SERVER_VER_CUSTOMER_ACCOUNT:
            # Consumed but not surfaced; Order dataclass field expansion is task #163
            _customerAccount, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_PROFESSIONAL_CUSTOMER:
            # Consumed but not surfaced; Order dataclass field expansion is task #163
            _professionalCustomer, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_SUBMITTER:
            # Consumed but not surfaced; Order dataclass field expansion is task #163
            _submitter, *fields = fields

        self.parse(c)
        self.parse(o)
        self.parse(st)
        self.wrapper.completedOrder(c, o, st)

    def historicalSchedule(self, fields):
        (_, reqId, startDateTime, endDateTime, timeZone, count, *fields) = fields
        get = iter(fields).__next__
        sessions = [
            HistoricalSession(startDateTime=get(), endDateTime=get(), refDate=get())
            for _ in range(int(count))
        ]
        self.wrapper.historicalSchedule(
            int(reqId), startDateTime, endDateTime, timeZone, sessions
        )
