"""Deserialize and dispatch messages."""

from __future__ import annotations

import dataclasses
import importlib
import logging
from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Final, Generic

from google.protobuf.message import Message

if TYPE_CHECKING:
    from ._pb.AccountDataEnd_pb2 import AccountDataEnd as AccountDataEndProto
    from ._pb.AccountSummary_pb2 import AccountSummary as AccountSummaryProto
    from ._pb.AccountSummaryEnd_pb2 import AccountSummaryEnd as AccountSummaryEndProto
    from ._pb.AccountUpdateMulti_pb2 import (
        AccountUpdateMulti as AccountUpdateMultiProto,
    )
    from ._pb.AccountUpdateMultiEnd_pb2 import (
        AccountUpdateMultiEnd as AccountUpdateMultiEndProto,
    )
    from ._pb.AccountUpdateTime_pb2 import AccountUpdateTime as AccountUpdateTimeProto
    from ._pb.AccountValue_pb2 import AccountValue as AccountValueProto
    from ._pb.CommissionAndFeesReport_pb2 import (
        CommissionAndFeesReport as CommissionAndFeesReportProto,
    )
    from ._pb.CompletedOrder_pb2 import CompletedOrder as CompletedOrderProto
    from ._pb.CompletedOrdersEnd_pb2 import (
        CompletedOrdersEnd as CompletedOrdersEndProto,
    )
    from ._pb.ConfigResponse_pb2 import ConfigResponse as ConfigResponseProto
    from ._pb.ContractData_pb2 import ContractData as ContractDataProto
    from ._pb.ContractDataEnd_pb2 import ContractDataEnd as ContractDataEndProto
    from ._pb.CurrentTime_pb2 import CurrentTime as CurrentTimeProto
    from ._pb.CurrentTimeInMillis_pb2 import (
        CurrentTimeInMillis as CurrentTimeInMillisProto,
    )
    from ._pb.DisplayGroupList_pb2 import DisplayGroupList as DisplayGroupListProto
    from ._pb.DisplayGroupUpdated_pb2 import (
        DisplayGroupUpdated as DisplayGroupUpdatedProto,
    )
    from ._pb.ErrorMessage_pb2 import ErrorMessage as ErrorMessageProto
    from ._pb.ExecutionDetails_pb2 import ExecutionDetails as ExecutionDetailsProto
    from ._pb.ExecutionDetailsEnd_pb2 import (
        ExecutionDetailsEnd as ExecutionDetailsEndProto,
    )
    from ._pb.FamilyCodes_pb2 import FamilyCodes as FamilyCodesProto
    from ._pb.HeadTimestamp_pb2 import HeadTimestamp as HeadTimestampProto
    from ._pb.HistogramData_pb2 import HistogramData as HistogramDataProto
    from ._pb.HistoricalData_pb2 import HistoricalData as HistoricalDataProto
    from ._pb.HistoricalDataEnd_pb2 import HistoricalDataEnd as HistoricalDataEndProto
    from ._pb.HistoricalDataUpdate_pb2 import (
        HistoricalDataUpdate as HistoricalDataUpdateProto,
    )
    from ._pb.HistoricalNews_pb2 import HistoricalNews as HistoricalNewsProto
    from ._pb.HistoricalNewsEnd_pb2 import HistoricalNewsEnd as HistoricalNewsEndProto
    from ._pb.HistoricalSchedule_pb2 import (
        HistoricalSchedule as HistoricalScheduleProto,
    )
    from ._pb.HistoricalTicks_pb2 import HistoricalTicks as HistoricalTicksProto
    from ._pb.HistoricalTicksBidAsk_pb2 import (
        HistoricalTicksBidAsk as HistoricalTicksBidAskProto,
    )
    from ._pb.HistoricalTicksLast_pb2 import (
        HistoricalTicksLast as HistoricalTicksLastProto,
    )
    from ._pb.ManagedAccounts_pb2 import ManagedAccounts as ManagedAccountsProto
    from ._pb.MarketDataType_pb2 import MarketDataType as MarketDataTypeProto
    from ._pb.MarketDepth_pb2 import MarketDepth as MarketDepthProto
    from ._pb.MarketDepthExchanges_pb2 import (
        MarketDepthExchanges as MarketDepthExchangesProto,
    )
    from ._pb.MarketDepthL2_pb2 import MarketDepthL2 as MarketDepthL2Proto
    from ._pb.MarketRule_pb2 import MarketRule as MarketRuleProto
    from ._pb.NewsArticle_pb2 import NewsArticle as NewsArticleProto
    from ._pb.NewsBulletin_pb2 import NewsBulletin as NewsBulletinProto
    from ._pb.NewsProviders_pb2 import NewsProviders as NewsProvidersProto
    from ._pb.NextValidId_pb2 import NextValidId as NextValidIdProto
    from ._pb.OpenOrder_pb2 import OpenOrder as OpenOrderProto
    from ._pb.OpenOrdersEnd_pb2 import OpenOrdersEnd as OpenOrdersEndProto
    from ._pb.OrderBound_pb2 import OrderBound as OrderBoundProto
    from ._pb.OrderStatus_pb2 import OrderStatus as OrderStatusProto
    from ._pb.PnL_pb2 import PnL as PnLProto
    from ._pb.PnLSingle_pb2 import PnLSingle as PnLSingleProto
    from ._pb.PortfolioValue_pb2 import PortfolioValue as PortfolioValueProto
    from ._pb.Position_pb2 import Position as PositionProto
    from ._pb.PositionEnd_pb2 import PositionEnd as PositionEndProto
    from ._pb.PositionMulti_pb2 import PositionMulti as PositionMultiProto
    from ._pb.PositionMultiEnd_pb2 import PositionMultiEnd as PositionMultiEndProto
    from ._pb.RealTimeBarTick_pb2 import RealTimeBarTick as RealTimeBarTickProto
    from ._pb.ReceiveFA_pb2 import ReceiveFA as ReceiveFAProto
    from ._pb.ReplaceFAEnd_pb2 import ReplaceFAEnd as ReplaceFAEndProto
    from ._pb.RerouteMarketDataRequest_pb2 import (
        RerouteMarketDataRequest as RerouteMarketDataRequestProto,
    )
    from ._pb.RerouteMarketDepthRequest_pb2 import (
        RerouteMarketDepthRequest as RerouteMarketDepthRequestProto,
    )
    from ._pb.ScannerData_pb2 import ScannerData as ScannerDataProto
    from ._pb.ScannerParameters_pb2 import ScannerParameters as ScannerParametersProto
    from ._pb.SecDefOptParameter_pb2 import (
        SecDefOptParameter as SecDefOptParameterProto,
    )
    from ._pb.SecDefOptParameterEnd_pb2 import (
        SecDefOptParameterEnd as SecDefOptParameterEndProto,
    )
    from ._pb.SmartComponents_pb2 import SmartComponents as SmartComponentsProto
    from ._pb.SoftDollarTiers_pb2 import SoftDollarTiers as SoftDollarTiersProto
    from ._pb.SymbolSamples_pb2 import SymbolSamples as SymbolSamplesProto
    from ._pb.TickByTickData_pb2 import TickByTickData as TickByTickDataProto
    from ._pb.TickGeneric_pb2 import TickGeneric as TickGenericProto
    from ._pb.TickNews_pb2 import TickNews as TickNewsProto
    from ._pb.TickOptionComputation_pb2 import (
        TickOptionComputation as TickOptionComputationProto,
    )
    from ._pb.TickPrice_pb2 import TickPrice as TickPriceProto
    from ._pb.TickReqParams_pb2 import TickReqParams as TickReqParamsProto
    from ._pb.TickSize_pb2 import TickSize as TickSizeProto
    from ._pb.TickSnapshotEnd_pb2 import TickSnapshotEnd as TickSnapshotEndProto
    from ._pb.TickString_pb2 import TickString as TickStringProto
    from ._pb.UpdateConfigResponse_pb2 import (
        UpdateConfigResponse as UpdateConfigResponseProto,
    )
    from ._pb.UserInfo_pb2 import UserInfo as UserInfoProto
    from ._pb.VerifyCompleted_pb2 import VerifyCompleted as VerifyCompletedProto
    from ._pb.VerifyMessageApi_pb2 import VerifyMessageApi as VerifyMessageApiProto
    from ._pb.WshEventData_pb2 import WshEventData as WshEventDataProto
    from ._pb.WshMetaData_pb2 import WshMetaData as WshMetaDataProto

from . import _proto as _converters
from ._proto.safe import clear_unset_fields
from ._requests import ReqIdKey
from .objects import EmptyT
from .runtime import Tally
from .util import parseIBDatetime
from .wrapper import Wrapper

# The one message TWS sends only as text: tickEFP (47) has no protobuf
# form.
_TICK_EFP: Final = 47


@dataclasses.dataclass(frozen=True, slots=True)
class _ProtoMessage:
    """A protobuf message the decoder reads: its message class's name
    (the class lives in the generated module ``ib_async._pb.<name>_pb2``)
    and the Decoder method that handles it."""

    name: str
    handler: str


@dataclasses.dataclass(frozen=True, slots=True)
class _ProtoHandler:
    """How a Decoder reads one protobuf message: its class, and the bound
    method that handles a parsed one."""

    protoClass: type[Message]
    handle: Callable[[Message], None]


# Per-canonical-msgId protobuf message classes, for every message in
# ``_PROTO_MESSAGES``. Resolved on the first instantiation so the
# heavy ``_pb`` imports don't fire at decoder-module import time.
_PROTO_MSG_CLASSES: dict[int, type] = {}


# Canonical IBKR ``IN`` msgId -> the protobuf message it carries.
_PROTO_MESSAGES: Final[dict[int, _ProtoMessage]] = {
    3: _ProtoMessage("OrderStatus", "_protoOrderStatus"),
    4: _ProtoMessage("ErrorMessage", "_protoError"),
    5: _ProtoMessage("OpenOrder", "_protoOpenOrder"),
    6: _ProtoMessage("AccountValue", "_protoUpdateAccountValue"),
    7: _ProtoMessage("PortfolioValue", "_protoUpdatePortfolio"),
    8: _ProtoMessage("AccountUpdateTime", "_protoUpdateAccountTime"),
    10: _ProtoMessage("ContractData", "_protoContractData"),
    11: _ProtoMessage("ExecutionDetails", "_protoExecutionDetails"),
    15: _ProtoMessage("ManagedAccounts", "_protoManagedAccounts"),
    18: _ProtoMessage("ContractData", "_protoBondContractData"),
    52: _ProtoMessage("ContractDataEnd", "_protoContractDataEnd"),
    53: _ProtoMessage("OpenOrdersEnd", "_protoOpenOrderEnd"),
    54: _ProtoMessage("AccountDataEnd", "_protoAccountDownloadEnd"),
    55: _ProtoMessage("ExecutionDetailsEnd", "_protoExecutionDetailsEnd"),
    59: _ProtoMessage("CommissionAndFeesReport", "_protoCommissionReport"),
    61: _ProtoMessage("Position", "_protoPosition"),
    62: _ProtoMessage("PositionEnd", "_protoPositionEnd"),
    63: _ProtoMessage("AccountSummary", "_protoAccountSummary"),
    64: _ProtoMessage("AccountSummaryEnd", "_protoAccountSummaryEnd"),
    65: _ProtoMessage("VerifyMessageApi", "_protoVerifyMessageAPI"),
    66: _ProtoMessage("VerifyCompleted", "_protoVerifyCompleted"),
    67: _ProtoMessage("DisplayGroupList", "_protoDisplayGroupList"),
    68: _ProtoMessage("DisplayGroupUpdated", "_protoDisplayGroupUpdated"),
    71: _ProtoMessage("PositionMulti", "_protoPositionMulti"),
    72: _ProtoMessage("PositionMultiEnd", "_protoPositionMultiEnd"),
    73: _ProtoMessage("AccountUpdateMulti", "_protoAccountUpdateMulti"),
    74: _ProtoMessage("AccountUpdateMultiEnd", "_protoAccountUpdateMultiEnd"),
    100: _ProtoMessage("OrderBound", "_protoOrderBound"),
    101: _ProtoMessage("CompletedOrder", "_protoCompletedOrder"),
    102: _ProtoMessage("CompletedOrdersEnd", "_protoCompletedOrdersEnd"),
    # --- market data + historical ---
    1: _ProtoMessage("TickPrice", "_protoPriceSizeTick"),
    2: _ProtoMessage("TickSize", "_protoTickSize"),
    12: _ProtoMessage("MarketDepth", "_protoUpdateMktDepth"),
    13: _ProtoMessage("MarketDepthL2", "_protoUpdateMktDepthL2"),
    17: _ProtoMessage("HistoricalData", "_protoHistoricalData"),
    21: _ProtoMessage("TickOptionComputation", "_protoTickOptionComputation"),
    45: _ProtoMessage("TickGeneric", "_protoTickGeneric"),
    46: _ProtoMessage("TickString", "_protoTickString"),
    50: _ProtoMessage("RealTimeBarTick", "_protoRealtimeBar"),
    57: _ProtoMessage("TickSnapshotEnd", "_protoTickSnapshotEnd"),
    58: _ProtoMessage("MarketDataType", "_protoMarketDataType"),
    80: _ProtoMessage("MarketDepthExchanges", "_protoMktDepthExchanges"),
    81: _ProtoMessage("TickReqParams", "_protoTickReqParams"),
    88: _ProtoMessage("HeadTimestamp", "_protoHeadTimestamp"),
    89: _ProtoMessage("HistogramData", "_protoHistogramData"),
    90: _ProtoMessage("HistoricalDataUpdate", "_protoHistoricalDataUpdate"),
    91: _ProtoMessage("RerouteMarketDataRequest", "_protoRerouteMktDataReq"),
    92: _ProtoMessage("RerouteMarketDepthRequest", "_protoRerouteMktDepthReq"),
    96: _ProtoMessage("HistoricalTicks", "_protoHistoricalTicks"),
    97: _ProtoMessage("HistoricalTicksBidAsk", "_protoHistoricalTicksBidAsk"),
    98: _ProtoMessage("HistoricalTicksLast", "_protoHistoricalTicksLast"),
    99: _ProtoMessage("TickByTickData", "_protoTickByTick"),
    106: _ProtoMessage("HistoricalSchedule", "_protoHistoricalSchedule"),
    108: _ProtoMessage("HistoricalDataEnd", "_protoHistoricalDataEnd"),
    # --- news + scanner / PnL ---
    14: _ProtoMessage("NewsBulletin", "_protoUpdateNewsBulletin"),
    19: _ProtoMessage("ScannerParameters", "_protoScannerParameters"),
    20: _ProtoMessage("ScannerData", "_protoScannerData"),
    83: _ProtoMessage("NewsArticle", "_protoNewsArticle"),
    84: _ProtoMessage("TickNews", "_protoTickNews"),
    85: _ProtoMessage("NewsProviders", "_protoNewsProviders"),
    86: _ProtoMessage("HistoricalNews", "_protoHistoricalNews"),
    87: _ProtoMessage("HistoricalNewsEnd", "_protoHistoricalNewsEnd"),
    94: _ProtoMessage("PnL", "_protoPnL"),
    95: _ProtoMessage("PnLSingle", "_protoPnLSingle"),
    104: _ProtoMessage("WshMetaData", "_protoWshMetaData"),
    105: _ProtoMessage("WshEventData", "_protoWshEventData"),
    # --- REST messages ---
    9: _ProtoMessage("NextValidId", "_protoNextValidId"),
    16: _ProtoMessage("ReceiveFA", "_protoReceiveFA"),
    49: _ProtoMessage("CurrentTime", "_protoCurrentTime"),
    75: _ProtoMessage("SecDefOptParameter", "_protoSecDefOptParameter"),
    76: _ProtoMessage("SecDefOptParameterEnd", "_protoSecDefOptParameterEnd"),
    77: _ProtoMessage("SoftDollarTiers", "_protoSoftDollarTiers"),
    78: _ProtoMessage("FamilyCodes", "_protoFamilyCodes"),
    79: _ProtoMessage("SymbolSamples", "_protoSymbolSamples"),
    82: _ProtoMessage("SmartComponents", "_protoSmartComponents"),
    93: _ProtoMessage("MarketRule", "_protoMarketRule"),
    103: _ProtoMessage("ReplaceFAEnd", "_protoReplaceFAEnd"),
    107: _ProtoMessage("UserInfo", "_protoUserInfo"),
    109: _ProtoMessage("CurrentTimeInMillis", "_protoCurrentTimeInMillis"),
    110: _ProtoMessage("ConfigResponse", "_protoConfigResponse"),
    111: _ProtoMessage("UpdateConfigResponse", "_protoUpdateConfigResponse"),
}


def _initProtoMsgClasses() -> None:
    """Resolve the protobuf message classes on first use, so the generated
    bindings are not imported with this module. All of them or none: an
    import that fails leaves the table empty, to fail again next time,
    rather than partly filled."""
    if _PROTO_MSG_CLASSES:
        return
    classes = {}
    for msgId, message in _PROTO_MESSAGES.items():
        module = importlib.import_module(f"{__package__}._pb.{message.name}_pb2")
        classes[msgId] = getattr(module, message.name)
    _PROTO_MSG_CLASSES.update(classes)


class Decoder(Generic[EmptyT]):
    """Decode IB messages and invoke corresponding wrapper methods."""

    def __init__(self, wrapper: Wrapper[EmptyT], tally: Tally | None = None):
        self.wrapper = wrapper
        # Counts messages it cannot handle (ib_async.runtime).
        self.tally = Tally() if tally is None else tally
        self.logger = logging.getLogger("ib_async.Decoder")
        # Resolve the protobuf message classes on first construction
        # so the heavy ``_pb`` imports don't fire at module-load time.
        _initProtoMsgClasses()
        # Pre-resolve the bound handler method for every protobuf
        # canonical msgId. ``processProtoBuf`` is on the receive
        # hot path (every wire frame) so eliminating
        # the per-call ``getattr`` of the handler is worth the
        # one-time cost at construction. The cache also lets us skip
        # the second dict lookup on every dispatch.
        self._protoDispatch: dict[int, _ProtoHandler] = {
            msgId: _ProtoHandler(
                protoClass, getattr(self, _PROTO_MESSAGES[msgId].handler)
            )
            for msgId, protoClass in _PROTO_MSG_CLASSES.items()
        }

    def processText(self, fields: list[str]) -> None:
        """Handle a text frame: ``fields`` is the message id, then the
        frame's NUL-separated fields.

        TWS sends every message as protobuf except the few that have no
        protobuf form. Of those, the client reads tickEFP. Any other
        text frame is counted as unknown and logged, naming its id.
        """
        msgId = int(fields[0])
        if msgId != _TICK_EFP:
            self.tally.unknownMessages += 1
            self.logger.warning(
                "Text message %d is not read: TWS sends the messages ib_async "
                "reads as protobuf (fields %r)",
                msgId,
                fields,
            )
            return
        try:
            self._tickEFP(fields)
        except Exception:
            self.tally.decodeFailures += 1
            self.logger.exception("Error for tickEFP with fields=%r", fields)

    def _tickEFP(self, fields: list[str]) -> None:
        """Read a tickEFP text message: message id, version, then the
        tick's fields. An empty number is 0."""
        (
            _,
            _,
            reqId,
            tickType,
            basisPoints,
            formattedBasisPoints,
            impliedFuture,
            holdDays,
            futureLastTradeDate,
            dividendImpact,
            dividendsToLastTradeDate,
            *_,
        ) = fields
        self.wrapper.tickEFP(
            int(reqId or 0),
            int(tickType or 0),
            float(basisPoints or 0),
            formattedBasisPoints,
            float(impliedFuture or 0),
            int(holdDays or 0),
            futureLastTradeDate,
            float(dividendImpact or 0),
            float(dividendsToLastTradeDate or 0),
        )

    def processProtoBuf(self, canonicalMsgId: int, payload: bytes) -> None:
        """Decode a protobuf-framed wire message and dispatch to the
        matching wrapper method.

        A per-msgId table maps canonical IBKR ``IN`` ids to how to read
        each (a ``_ProtoHandler``: its message class and the handler). The
        handler gets the parsed proto, calls the
        relevant ``_proto`` converter to produce domain dataclasses,
        and forwards to the matching ``Wrapper`` method.

        An unknown msgId is logged at debug and dropped; an exception
        from a handler is logged and dropped so a single malformed
        message can't kill the connection. Any awaiter-fail behaviour
        (the registry-level ``set_error`` path) lives in the wrapper
        methods themselves.

        Limitation: when ``ParseFromString`` itself fails (truncated /
        corrupted payload) the reqId lives inside the unparsed bytes,
        so we have no way to look up the awaiting future and surface
        an error there. The malformed frame is logged and dropped; the
        awaiter eventually clears via the connection-loss path
        (``Wrapper.connectionClosed`` fails every pending awaiter) or its
        own ``asyncio.wait_for`` timeout if the user wrapped it. A
        live connection with a single malformed frame in the middle
        survives, but the matching request never receives a result.
        """
        entry = self._protoDispatch.get(canonicalMsgId)
        if entry is None:
            self.tally.unknownMessages += 1
            self.logger.debug(
                "protobuf msg %d, %d bytes (no handler)",
                canonicalMsgId,
                len(payload),
            )
            return
        proto: Message | None = None
        try:
            proto = entry.protoClass()
            proto.ParseFromString(payload)
            # A field holding IBKR's unset value reads as absent.
            clear_unset_fields(proto)
            entry.handle(proto)
        except Exception as exc:
            self.tally.decodeFailures += 1
            # ``ParseFromString`` failures leave reqId inaccessible because
            # the bytes never landed in a typed field, so the awaiter only
            # clears via the connection-loss path or a user-side timeout.
            # Handler-raise failures (proto parsed, dispatch crashed) are
            # different — the parsed proto usually carries a reqId, so we
            # can settle the matching future with the exception. The
            # connection survives the crash either way; we never re-raise
            # here.
            self.logger.exception(
                "Error decoding protobuf msg %d (%s), %d bytes",
                canonicalMsgId,
                type(exc).__name__,
                len(payload),
            )
            reqId: int | None = None
            if proto is not None:
                # Most decoded protos expose ``reqId`` but it's conditional
                # by message type — Open/Cancel families lack it entirely.
                # ``HasField`` distinguishes "field present" from "default
                # 0" for proto2-style messages; on proto3 every scalar is
                # always reported as set, so we fall back to a raw read in
                # that case to surface anything non-zero.
                try:
                    if proto.HasField("reqId"):
                        reqId = int(proto.reqId)
                except (AttributeError, ValueError):
                    raw = getattr(proto, "reqId", None)
                    if isinstance(raw, int) and raw != 0:
                        reqId = raw
            if reqId is not None:
                try:
                    self.wrapper.requests.set_error(ReqIdKey(reqId), exc)
                except Exception:
                    self.logger.exception(
                        "Failed to settle awaiter for reqId %s after proto msg %d crash",
                        reqId,
                        canonicalMsgId,
                    )

    # --- protobuf message handlers ----------------------------------------
    #
    # Each ``_protoXxx`` helper translates a parsed proto into its wrapper
    # method's arguments.

    def _protoError(self, proto: ErrorMessageProto) -> None:
        # ``ErrorMessage`` is the protobuf-form of msgId 4. Without this
        # handler, server-pushed errors arriving as proto frames would
        # silently debug-drop and the user would never see them. Live
        # trading hazard: rejected orders, margin warnings, and
        # connection-degraded notices all flow through here.

        a = _converters.rest.createErrorArgs(proto)
        self.wrapper.error(
            a.reqId, a.errorCode, a.errorMsg, a.advancedOrderRejectJson, a.errorTime
        )

    def _protoOrderStatus(self, proto: OrderStatusProto) -> None:
        s = _converters.orders.createOrderStatus(proto)
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

    def _protoOpenOrder(self, proto: OpenOrderProto) -> None:
        # An OpenOrder frame missing any of contract / order / orderState
        # is malformed: handing it on would poison the trade registry with
        # a half-formed Order. Drop the frame silently.
        if not (
            proto.HasField("contract")
            and proto.HasField("order")
            and proto.HasField("orderState")
        ):
            return

        orderId, contract, order, state = _converters.orders.createOpenOrder(proto)
        self.wrapper.openOrder(orderId, contract, order, state)

    def _protoOpenOrderEnd(self, proto: OpenOrdersEndProto) -> None:
        self.wrapper.openOrderEnd()

    def _protoCompletedOrder(self, proto: CompletedOrderProto) -> None:
        decoded = _converters.orders.createCompletedOrder(proto)
        if decoded is None:
            return
        contract, order, state = decoded
        self.wrapper.completedOrder(contract, order, state)

    def _protoCompletedOrdersEnd(self, proto: CompletedOrdersEndProto) -> None:
        self.wrapper.completedOrdersEnd()

    def _protoExecutionDetails(self, proto: ExecutionDetailsProto) -> None:
        reqId, contract, execution = _converters.orders.createExecutionDetails(proto)
        # Wire ``Execution.time`` is a string in one of IBKR's date-time
        # formats. The converter leaves it raw on the domain object; we
        # normalize it here to a datetime. The rule needs the IB's settings
        # (``Wrapper._normalizeDatetime``), so it can't live inside the pure
        # converter.
        if proto.HasField("execution") and proto.execution.HasField("time"):
            execution.time = self._normalizeExecutionTime(proto.execution.time)
        self.wrapper.execDetails(reqId, contract, execution)

    def _protoExecutionDetailsEnd(self, proto: ExecutionDetailsEndProto) -> None:
        # ExecutionDetailsEnd carries just a reqId.
        reqId = proto.reqId if proto.HasField("reqId") else -1
        self.wrapper.execDetailsEnd(reqId)

    def _protoCommissionReport(self, proto: CommissionAndFeesReportProto) -> None:
        report = _converters.orders.createCommissionReport(proto)
        self.wrapper.commissionReport(report)

    def _protoContractData(self, proto: ContractDataProto) -> None:
        # ContractData wraps reqId + contract + contractDetails. Our
        # converter unwraps the inner contract+details into a single
        # ``ContractDetails`` (with ``.contract`` populated).
        reqId = proto.reqId if proto.HasField("reqId") else -1
        details = _converters.contracts.createContractDetailsFromContractData(proto)
        self.wrapper.contractDetails(reqId, details)

    def _protoBondContractData(self, proto: ContractDataProto) -> None:
        # BondContractData uses the same proto shape as ContractData.
        # Bond-specific fields populate on the same ``ContractDetails``
        # dataclass; it goes to ``Wrapper.bondContractDetails`` so
        # subclasses overriding the bond callback (rather than the
        # unified ``contractDetails``) receive bond rows. Default Wrapper
        # aliases ``bondContractDetails`` to ``contractDetails`` so
        # subclasses without a bond override see no behavioural change.

        reqId = proto.reqId if proto.HasField("reqId") else -1
        details = _converters.contracts.createContractDetailsFromContractData(proto)
        self.wrapper.bondContractDetails(reqId, details)

    def _protoContractDataEnd(self, proto: ContractDataEndProto) -> None:
        reqId = proto.reqId if proto.HasField("reqId") else -1
        self.wrapper.contractDetailsEnd(reqId)

    def _normalizeExecutionTime(self, timeStr: str) -> datetime:
        """Parse an IBKR execution-time wire string into a tz-aware
        ``datetime`` in the wrapper's default timezone, by the rule in
        ``Wrapper._normalizeDatetime``.

        Without this, ``ex.time`` would stay at the dataclass default
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
        return self.wrapper._normalizeDatetime(time)

    def _protoOrderBound(self, proto: OrderBoundProto) -> None:
        permId = proto.permId if proto.HasField("permId") else 0
        clientId = proto.clientId if proto.HasField("clientId") else 0
        orderId = proto.orderId if proto.HasField("orderId") else 0
        self.wrapper.orderBound(permId, clientId, orderId)

    # --- verify / displayGroup / config handlers --------------------------
    #
    # The base ``Wrapper`` defines these as hooks for subclasses. They are
    # looked up with ``getattr`` and skipped when absent, so a wrapper
    # object that does not implement every callback still works.

    def _protoVerifyMessageAPI(self, proto: VerifyMessageApiProto) -> None:
        method = getattr(self.wrapper, "verifyMessageAPI", None)
        if method is None:
            return
        apiData = proto.apiData if proto.HasField("apiData") else ""
        method(apiData)

    def _protoVerifyCompleted(self, proto: VerifyCompletedProto) -> None:
        method = getattr(self.wrapper, "verifyCompleted", None)
        if method is None:
            return
        isSuccessful = proto.isSuccessful if proto.HasField("isSuccessful") else False
        errorText = proto.errorText if proto.HasField("errorText") else ""
        method(isSuccessful, errorText)

    def _protoDisplayGroupList(self, proto: DisplayGroupListProto) -> None:
        method = getattr(self.wrapper, "displayGroupList", None)
        if method is None:
            return
        reqId = proto.reqId if proto.HasField("reqId") else -1
        groups = proto.groups if proto.HasField("groups") else ""
        method(reqId, groups)

    def _protoDisplayGroupUpdated(self, proto: DisplayGroupUpdatedProto) -> None:
        method = getattr(self.wrapper, "displayGroupUpdated", None)
        if method is None:
            return
        reqId = proto.reqId if proto.HasField("reqId") else -1
        contractInfo = proto.contractInfo if proto.HasField("contractInfo") else ""
        method(reqId, contractInfo)

    def _protoConfigResponse(self, proto: ConfigResponseProto) -> None:
        # ConfigResponse carries nested ``LockAndExitConfig`` / ``ApiConfig``
        # / ``MessageConfig`` / ``OrdersConfig`` sub-messages with no flat
        # equivalent — the wrapper hook receives the raw proto.
        method = getattr(self.wrapper, "configResponseProtoBuf", None)
        if method is not None:
            method(proto)

    def _protoUpdateConfigResponse(self, proto: UpdateConfigResponseProto) -> None:
        method = getattr(self.wrapper, "updateConfigResponseProtoBuf", None)
        if method is not None:
            method(proto)

    # --- accounts / positions handlers ------------------------------------

    def _protoUpdateAccountValue(self, proto: AccountValueProto) -> None:
        a = _converters.accounts.createUpdateAccountValueArgs(proto)
        self.wrapper.updateAccountValue(a.tag, a.val, a.currency, a.account)

    def _protoUpdatePortfolio(self, proto: PortfolioValueProto) -> None:
        a = _converters.accounts.createUpdatePortfolioArgs(proto)
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

    def _protoUpdateAccountTime(self, proto: AccountUpdateTimeProto) -> None:
        ts = proto.timeStamp if proto.HasField("timeStamp") else ""
        self.wrapper.updateAccountTime(ts)

    def _protoAccountDownloadEnd(self, proto: AccountDataEndProto) -> None:
        account = proto.accountName if proto.HasField("accountName") else ""
        self.wrapper.accountDownloadEnd(account)

    def _protoManagedAccounts(self, proto: ManagedAccountsProto) -> None:
        self.wrapper.managedAccounts(
            _converters.accounts.createManagedAccountsList(proto)
        )

    def _protoPosition(self, proto: PositionProto) -> None:
        a = _converters.accounts.createPositionArgs(proto)
        self.wrapper.position(a.account, a.contract, a.posSize, a.avgCost)

    def _protoPositionEnd(self, proto: PositionEndProto) -> None:
        self.wrapper.positionEnd()

    def _protoAccountSummary(self, proto: AccountSummaryProto) -> None:
        a = _converters.accounts.createAccountSummaryArgs(proto)
        self.wrapper.accountSummary(a.reqId, a.account, a.tag, a.value, a.currency)

    def _protoAccountSummaryEnd(self, proto: AccountSummaryEndProto) -> None:
        reqId = proto.reqId if proto.HasField("reqId") else -1
        self.wrapper.accountSummaryEnd(reqId)

    def _protoPositionMulti(self, proto: PositionMultiProto) -> None:
        a = _converters.accounts.createPositionMultiArgs(proto)
        self.wrapper.positionMulti(
            a.reqId, a.account, a.modelCode, a.contract, a.pos, a.avgCost
        )

    def _protoPositionMultiEnd(self, proto: PositionMultiEndProto) -> None:
        reqId = proto.reqId if proto.HasField("reqId") else -1
        self.wrapper.positionMultiEnd(reqId)

    def _protoAccountUpdateMulti(self, proto: AccountUpdateMultiProto) -> None:
        a = _converters.accounts.createAccountUpdateMultiArgs(proto)
        self.wrapper.accountUpdateMulti(
            a.reqId, a.account, a.modelCode, a.tag, a.val, a.currency
        )

    def _protoAccountUpdateMultiEnd(self, proto: AccountUpdateMultiEndProto) -> None:
        reqId = proto.reqId if proto.HasField("reqId") else -1
        self.wrapper.accountUpdateMultiEnd(reqId)

    # --- market data handlers ---------------------------------------------

    def _protoPriceSizeTick(self, proto: TickPriceProto) -> None:
        a = _converters.market_data.createPriceSizeTickArgs(proto)
        self.wrapper.priceSizeTick(a.reqId, a.tickType, a.price, a.size, a.attrib)

    def _protoTickSize(self, proto: TickSizeProto) -> None:
        a = _converters.market_data.createTickSizeArgs(proto)
        self.wrapper.tickSize(a.reqId, a.tickType, a.size)

    def _protoTickGeneric(self, proto: TickGenericProto) -> None:
        a = _converters.market_data.createTickGenericArgs(proto)
        self.wrapper.tickGeneric(a.reqId, a.tickType, a.value)

    def _protoTickString(self, proto: TickStringProto) -> None:
        a = _converters.market_data.createTickStringArgs(proto)
        self.wrapper.tickString(a.reqId, a.tickType, a.value)

    def _protoTickReqParams(self, proto: TickReqParamsProto) -> None:
        a = _converters.market_data.createTickReqParamsArgs(proto)
        self.wrapper.tickReqParams(
            a.reqId, a.minTick, a.bboExchange, a.snapshotPermissions
        )

    def _protoTickSnapshotEnd(self, proto: TickSnapshotEndProto) -> None:
        self.wrapper.tickSnapshotEnd(
            _converters.market_data.createTickSnapshotEndReqId(proto)
        )

    def _protoTickOptionComputation(self, proto: TickOptionComputationProto) -> None:
        a = _converters.market_data.createTickOptionComputationArgs(proto)
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

    def _protoTickByTick(self, proto: TickByTickDataProto) -> None:
        a = _converters.market_data.dispatchTickByTick(proto)
        if isinstance(a, _converters.market_data.TickByTickAllLastArgs):
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
        elif isinstance(a, _converters.market_data.TickByTickBidAskArgs):
            self.wrapper.tickByTickBidAsk(
                a.reqId,
                a.time,
                a.bidPrice,
                a.askPrice,
                a.bidSize,
                a.askSize,
                a.tickAttribBidAsk,
            )
        elif isinstance(a, _converters.market_data.TickByTickMidPointArgs):
            self.wrapper.tickByTickMidPoint(a.reqId, a.time, a.midPoint)
        # else None: no oneof set, nothing to report

    def _protoMarketDataType(self, proto: MarketDataTypeProto) -> None:
        a = _converters.market_data.createMarketDataTypeArgs(proto)
        self.wrapper.marketDataType(a.reqId, a.marketDataType)

    def _protoUpdateMktDepth(self, proto: MarketDepthProto) -> None:
        a = _converters.market_data.createUpdateMktDepthArgs(proto)
        self.wrapper.updateMktDepth(
            a.reqId, a.position, a.operation, a.side, a.price, a.size
        )

    def _protoUpdateMktDepthL2(self, proto: MarketDepthL2Proto) -> None:
        a = _converters.market_data.createUpdateMktDepthL2Args(proto)
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

    def _protoMktDepthExchanges(self, proto: MarketDepthExchangesProto) -> None:
        self.wrapper.mktDepthExchanges(
            _converters.market_data.createMarketDepthExchangesList(proto)
        )

    def _protoRerouteMktDataReq(self, proto: RerouteMarketDataRequestProto) -> None:
        a = _converters.market_data.createRerouteMktDataReqArgs(proto)
        self.wrapper.rerouteMktDataReq(a.reqId, a.conId, a.exchange)

    def _protoRerouteMktDepthReq(self, proto: RerouteMarketDepthRequestProto) -> None:
        a = _converters.market_data.createRerouteMktDepthReqArgs(proto)
        self.wrapper.rerouteMktDepthReq(a.reqId, a.conId, a.exchange)

    # --- historical-data handlers -----------------------------------------

    def _protoHistoricalData(self, proto: HistoricalDataProto) -> None:
        a = _converters.historical.createHistoricalDataBars(proto)
        for bar in a.bars:
            self.wrapper.historicalData(a.reqId, bar)

    def _protoHistoricalDataEnd(self, proto: HistoricalDataEndProto) -> None:
        a = _converters.historical.createHistoricalDataEndArgs(proto)
        self.wrapper.historicalDataEnd(a.reqId, a.start, a.end)

    def _protoHistoricalDataUpdate(self, proto: HistoricalDataUpdateProto) -> None:
        a = _converters.historical.createHistoricalDataUpdateArgs(proto)
        self.wrapper.historicalDataUpdate(a.reqId, a.bar)

    def _protoRealtimeBar(self, proto: RealTimeBarTickProto) -> None:
        a = _converters.historical.createRealtimeBarArgs(proto)
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

    def _protoHeadTimestamp(self, proto: HeadTimestampProto) -> None:
        a = _converters.historical.createHeadTimestampArgs(proto)
        self.wrapper.headTimestamp(a.reqId, a.headTimestamp)

    def _protoHistogramData(self, proto: HistogramDataProto) -> None:
        a = _converters.historical.createHistogramDataArgs(proto)
        self.wrapper.histogramData(a.reqId, a.items)

    def _protoHistoricalSchedule(self, proto: HistoricalScheduleProto) -> None:
        a = _converters.historical.createHistoricalScheduleArgs(proto)
        self.wrapper.historicalSchedule(
            a.reqId, a.startDateTime, a.endDateTime, a.timeZone, a.sessions
        )

    def _protoHistoricalTicks(self, proto: HistoricalTicksProto) -> None:
        a = _converters.historical.createHistoricalTicksArgs(proto)
        self.wrapper.historicalTicks(a.reqId, a.ticks, a.done)

    def _protoHistoricalTicksBidAsk(self, proto: HistoricalTicksBidAskProto) -> None:
        a = _converters.historical.createHistoricalTicksBidAskArgs(proto)
        self.wrapper.historicalTicksBidAsk(a.reqId, a.ticks, a.done)

    def _protoHistoricalTicksLast(self, proto: HistoricalTicksLastProto) -> None:
        a = _converters.historical.createHistoricalTicksLastArgs(proto)
        self.wrapper.historicalTicksLast(a.reqId, a.ticks, a.done)

    # --- news + WSH handlers ---------------------------------------------

    def _protoUpdateNewsBulletin(self, proto: NewsBulletinProto) -> None:
        a = _converters.news.createUpdateNewsBulletinArgs(proto)
        self.wrapper.updateNewsBulletin(a.msgId, a.msgType, a.message, a.origExchange)

    def _protoNewsProviders(self, proto: NewsProvidersProto) -> None:
        self.wrapper.newsProviders(_converters.news.createNewsProviders(proto))

    def _protoNewsArticle(self, proto: NewsArticleProto) -> None:
        a = _converters.news.createNewsArticleArgs(proto)
        self.wrapper.newsArticle(a.reqId, a.articleType, a.articleText)

    def _protoHistoricalNews(self, proto: HistoricalNewsProto) -> None:
        a = _converters.news.createHistoricalNewsArgs(proto)
        self.wrapper.historicalNews(
            a.reqId, a.time, a.providerCode, a.articleId, a.headline
        )

    def _protoHistoricalNewsEnd(self, proto: HistoricalNewsEndProto) -> None:
        a = _converters.news.createHistoricalNewsEndArgs(proto)
        self.wrapper.historicalNewsEnd(a.reqId, a.hasMore)

    def _protoTickNews(self, proto: TickNewsProto) -> None:
        a = _converters.news.createTickNewsArgs(proto)
        self.wrapper.tickNews(
            a.reqId,
            a.timeStamp,
            a.providerCode,
            a.articleId,
            a.headline,
            a.extraData,
        )

    def _protoWshMetaData(self, proto: WshMetaDataProto) -> None:
        a = _converters.news.createWshMetaDataArgs(proto)
        self.wrapper.wshMetaData(a.reqId, a.dataJson)

    def _protoWshEventData(self, proto: WshEventDataProto) -> None:
        a = _converters.news.createWshEventDataArgs(proto)
        self.wrapper.wshEventData(a.reqId, a.dataJson)

    # --- scanner + PnL handlers ---------------------------------------------

    def _protoScannerParameters(self, proto: ScannerParametersProto) -> None:
        self.wrapper.scannerParameters(
            _converters.scanner.createScannerParametersXml(proto)
        )

    def _protoScannerData(self, proto: ScannerDataProto) -> None:
        a = _converters.scanner.createScannerDataArgs(proto)
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

    def _protoPnL(self, proto: PnLProto) -> None:
        a = _converters.scanner.createPnLArgs(proto)
        self.wrapper.pnl(a.reqId, a.dailyPnL, a.unrealizedPnL, a.realizedPnL)

    def _protoPnLSingle(self, proto: PnLSingleProto) -> None:
        a = _converters.scanner.createPnLSingleArgs(proto)
        self.wrapper.pnlSingle(
            a.reqId, a.pos, a.dailyPnL, a.unrealizedPnL, a.realizedPnL, a.value
        )

    # --- REST handlers ----------------------------------------------------

    def _protoNextValidId(self, proto: NextValidIdProto) -> None:
        self.wrapper.nextValidId(_converters.rest.createNextValidIdOrderId(proto))

    def _protoCurrentTime(self, proto: CurrentTimeProto) -> None:
        self.wrapper.currentTime(_converters.rest.createCurrentTimeSeconds(proto))

    def _protoCurrentTimeInMillis(self, proto: CurrentTimeInMillisProto) -> None:
        self.wrapper.currentTimeInMillis(
            _converters.rest.createCurrentTimeInMillisMillis(proto)
        )

    def _protoUserInfo(self, proto: UserInfoProto) -> None:
        a = _converters.rest.createUserInfoArgs(proto)
        self.wrapper.userInfo(a.reqId, a.whiteBrandingId)

    def _protoSecDefOptParameter(self, proto: SecDefOptParameterProto) -> None:
        a = _converters.rest.createSecDefOptParameterArgs(proto)
        self.wrapper.securityDefinitionOptionParameter(
            a.reqId,
            a.exchange,
            a.underlyingConId,
            a.tradingClass,
            a.multiplier,
            a.expirations,
            a.strikes,
        )

    def _protoSecDefOptParameterEnd(self, proto: SecDefOptParameterEndProto) -> None:
        self.wrapper.securityDefinitionOptionParameterEnd(
            _converters.rest.createSecDefOptParameterEndReqId(proto)
        )

    def _protoSoftDollarTiers(self, proto: SoftDollarTiersProto) -> None:
        a = _converters.rest.createSoftDollarTiersArgs(proto)
        self.wrapper.softDollarTiers(a.reqId, a.tiers)

    def _protoSymbolSamples(self, proto: SymbolSamplesProto) -> None:
        a = _converters.rest.createSymbolSamplesArgs(proto)
        self.wrapper.symbolSamples(a.reqId, a.contractDescriptions)

    def _protoSmartComponents(self, proto: SmartComponentsProto) -> None:
        a = _converters.rest.createSmartComponentsArgs(proto)
        self.wrapper.smartComponents(a.reqId, a.components)

    def _protoMarketRule(self, proto: MarketRuleProto) -> None:
        a = _converters.rest.createMarketRuleArgs(proto)
        self.wrapper.marketRule(a.marketRuleId, a.priceIncrements)

    def _protoFamilyCodes(self, proto: FamilyCodesProto) -> None:
        self.wrapper.familyCodes(_converters.accounts.createFamilyCodes(proto))

    def _protoReceiveFA(self, proto: ReceiveFAProto) -> None:
        a = _converters.accounts.createReceiveFAArgs(proto)
        self.wrapper.receiveFA(a.faDataType, a.xml)

    def _protoReplaceFAEnd(self, proto: ReplaceFAEndProto) -> None:
        a = _converters.accounts.createReplaceFAEndArgs(proto)
        self.wrapper.replaceFAEnd(a.reqId, a.text)
