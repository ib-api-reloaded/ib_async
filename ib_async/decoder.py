"""Deserialize and dispatch messages."""

from __future__ import annotations

import dataclasses
import importlib
import logging
import sys
import types
import typing
from collections.abc import Callable
from datetime import date, datetime
from decimal import Decimal
from types import GenericAlias, UnionType
from typing import TYPE_CHECKING, Any, Final, Generic, TypeAlias

from eventkit import Event
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
from ._proto.safe import safe_decimal
from ._requests import ReqIdKey
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
    EmptyT,
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
from .order import (
    Order,
    OrderAllocation,
    OrderComboLeg,
    OrderCondition,
    OrderState,
    decimalOrInfinity,
)
from .util import (
    UNSET_DOUBLE,
    UNSET_INTEGER,
    Dataclass,
    ZoneInfo,
    parseIBDatetime,
    splitIBLastTradeDate,
)
from .wrapper import Wrapper

# Per-type wire-string-to-typed-value converters. The empty-string-to-default
# behaviour (``field or 0``) is preserved verbatim from the original inline
# ternary in Decoder.wrap(); hoisting lets that wrap() resolve the converter
# list once at construction time instead of branching per field per dispatch.
# ``Decimal`` is the 3.0-era type for size, quantity, and price fields:
# ``safe_decimal`` returns ``Decimal | None`` (``None`` for empty / "nan" /
# malformed input) so binary-path handlers and protobuf converters share
# the same Decimal-coherent shape on the way into the wrapper.
# ``Coerced`` is the set of classes that Decoder.parse() converts a wire
# string to. ``WireScalar`` is the wider set of classes that the binary
# handlers read fields as.
Coerced: TypeAlias = type[int] | type[float] | type[bool] | type[Decimal]
WireScalar: TypeAlias = type[str] | Coerced
# A field annotation in the form the wire dataclasses use. It is a class,
# ``X | None``, ``list[X]``, or the unevaluated string of one of these.
Annotation: TypeAlias = (
    WireScalar
    | type[datetime]
    | type[date]
    | type[Dataclass]
    | type[Event]
    | UnionType
    | GenericAlias
    | str
)

_CONV: Final[
    dict[WireScalar, Callable[[str], str | int | float | bool | Decimal | None]]
] = {
    str: lambda f: f,
    int: lambda f: int(f or 0),
    float: lambda f: float(f or 0),
    bool: lambda f: bool(int(f or 0)),
    Decimal: safe_decimal,
}


@dataclasses.dataclass(frozen=True, slots=True)
class _ParseField:
    """How Decoder.parse() coerces one int/float/Decimal/bool field."""

    name: str
    typ: Coerced
    default: str | int | float | bool | Decimal | None
    # A Decimal field where +Infinity is a value, not unset (the class's
    # ``_INFINITE_FIELDS``).
    infinite: bool = False


# Cache of dataclass-field coercion plans keyed by class: the fields
# Decoder.parse() needs to coerce; str fields are skipped entirely. The
# cache populates lazily on first parse() of each class so we pay the
# dataclasses.fields() introspection once per class instead of per call.
_PARSE_FIELDS: dict[type, tuple[_ParseField, ...]] = {}

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
    # --- market data + historical (gates 206 / 208) ---
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
    # --- news + scanner / PnL (gates 209 / 210) ---
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
    # --- REST messages (gates 211 / 212 / 213) ---
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


def _resolveCoerceType(annotation: Annotation) -> Coerced | None:
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
    for scalar in (int, float, bool, Decimal):
        if annotation is scalar:
            return scalar
    return None


class Decoder(Generic[EmptyT]):
    """Decode IB messages and invoke corresponding wrapper methods."""

    def __init__(self, wrapper: Wrapper[EmptyT], serverVersion: int):
        self.wrapper = wrapper
        self.serverVersion = serverVersion
        self.logger = logging.getLogger("ib_async.Decoder")
        # Resolve the protobuf message classes on first construction
        # so the heavy ``_pb`` imports don't fire at module-load time
        # for callers that only use the binary path.
        _initProtoMsgClasses()
        # Pre-resolve the bound handler method for every protobuf
        # canonical msgId. ``processProtoBuf`` is on the receive
        # hot path (every wire frame post-201 server) so eliminating
        # the per-call ``getattr`` of the handler is worth the
        # one-time cost at construction. The cache also lets us skip
        # the second dict lookup on every dispatch.
        self._protoDispatch: dict[int, _ProtoHandler] = {
            msgId: _ProtoHandler(
                protoClass, getattr(self, _PROTO_MESSAGES[msgId].handler)
            )
            for msgId, protoClass in _PROTO_MSG_CLASSES.items()
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
                # Newer servers may append fields this decoder does not read.
                args = [
                    conv(f) for conv, f in zip(converters, fields[skip:], strict=False)
                ]
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

        A per-msgId table maps canonical IBKR ``IN`` ids to how to read
        each (a ``_ProtoHandler``: its message class and the handler). The
        handler gets the parsed proto, calls the
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
        (``Wrapper.connectionClosed`` fails every pending awaiter) or its
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
        proto: Message | None = None
        try:
            proto = entry.protoClass()
            proto.ParseFromString(payload)
            entry.handle(proto)
        except Exception as exc:
            # ``ParseFromString`` failures leave reqId inaccessible because
            # the bytes never landed in a typed field, so the awaiter only
            # clears via the connection-loss path or a user-side timeout.
            # Handler-raise failures (proto parsed, dispatch crashed) are
            # different — the parsed proto usually carries a reqId, so we
            # can settle the matching future with the same exception type
            # the binary path would surface. The connection survives the
            # crash either way; we never re-raise here.
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
    # Each ``_protoXxx`` helper translates a parsed proto into the same
    # arguments the binary-path equivalent passes to its wrapper method,
    # so wrapper code stays unaware of which encoding the wire used.

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
        # is malformed — the binary path delivers an empty-fielded openOrder
        # to user code in that case, which can poison the trade registry
        # with a half-formed Order. Drop the frame silently.
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
        # Wire ``Execution.time`` is a string in IBKR's
        # ``"YYYYmmdd HH:MM:SS [tz]"`` format. The converter leaves it
        # raw on the domain object; we normalize here so the proto path
        # produces the same datetime shape as the binary path. The tz
        # source is decoder-instance state (``Wrapper.ib.TimezoneTWS``)
        # so it can't live inside the pure converter.
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
        # dataclass; dispatch to ``Wrapper.bondContractDetails`` for
        # symmetry with the binary path so subclasses overriding the
        # bond callback (rather than the unified ``contractDetails``)
        # still receive proto-arriving bond rows. Default Wrapper
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

    def _protoOrderBound(self, proto: OrderBoundProto) -> None:
        permId = proto.permId if proto.HasField("permId") else 0
        clientId = proto.clientId if proto.HasField("clientId") else 0
        orderId = proto.orderId if proto.HasField("orderId") else 0
        self.wrapper.orderBound(permId, clientId, orderId)

    # --- verify / displayGroup / config handlers --------------------------
    #
    # The base ``Wrapper`` defines these as hooks for subclasses. They are
    # looked up with ``getattr`` and skipped when absent, the same
    # tolerance the binary path's ``wrap()`` factory gives a wrapper
    # object that does not implement every callback.

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
        a = _converters.market_data.createPriceSizeTickArgs(proto, self.serverVersion)
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
        # else None — oneof not set, drop (matches binary path)

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
            plan: list[_ParseField] = []
            infinite: frozenset[str] = getattr(cls, "_INFINITE_FIELDS", frozenset())
            for field in dataclasses.fields(obj):
                raw = field.type
                if isinstance(raw, str):
                    try:
                        raw = eval(raw, module_globals)  # a type annotation
                    except (NameError, AttributeError, TypeError, SyntaxError):
                        continue
                typ = _resolveCoerceType(raw)
                if typ is not None:
                    # A field without a default gets None when unset.
                    default = (
                        None if field.default is dataclasses.MISSING else field.default
                    )
                    plan.append(
                        _ParseField(field.name, typ, default, field.name in infinite)
                    )
            entries = tuple(plan)
            _PARSE_FIELDS[cls] = entries

        for entry in entries:
            name, typ, default = entry.name, entry.typ, entry.default
            v = getattr(obj, name)
            if not v:
                setattr(obj, name, default)
            elif typ is int:
                iv = int(v)
                # IBKR's UNSET_INTEGER sentinel means "field not set": in the
                # v3 None-dialect an unset field IS its dataclass default, so
                # the sentinel never leaks into user-visible objects.
                setattr(obj, name, default if iv == UNSET_INTEGER else iv)
            elif typ is float:
                fv = float(v)
                setattr(obj, name, default if fv == UNSET_DOUBLE else fv)
            elif typ is Decimal:
                # Wire string → ``Decimal | None``. ``safe_decimal``
                # returns ``None`` for empty / "nan" / malformed input;
                # callers that need a non-``None`` floor (rare) can
                # post-process the field after ``parse()``. The UNSET_DOUBLE
                # sentinel compares as float (its Decimal expansion is not
                # textually stable on the wire).
                try:
                    unset = float(v) == UNSET_DOUBLE
                except (TypeError, ValueError):
                    unset = False
                parsed = decimalOrInfinity(v) if entry.infinite else safe_decimal(v)
                setattr(obj, name, default if unset else parsed)
            else:  # bool
                setattr(obj, name, bool(int(v)))

    def priceSizeTick(self, fields):
        # Wire layout: [msgId, version, reqId, tickType, price, size, attrMask]
        # The trailing attrMask was previously discarded — silently dropping
        # canAutoExecute / pastLimit / preOpen flags user code needs to gate
        # liquidity-quality decisions on. v3.0 surfaces them via TickAttrib.

        _, _, reqId, tickType, price, size, attrMask = fields

        if price:
            attrib = _converters.market_data.decodeTickAttribFromMask(
                int(attrMask or 0), self.serverVersion
            )
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

        times = splitIBLastTradeDate(lastTimes)

        if len(times) > 0:
            c.lastTradeDateOrContractMonth = times[0]

        if len(times) > 1:
            cd.lastTradeTime = times[1]

        if len(times) > 2:
            cd.timeZoneId = times[2]

        cd.longName = cd.longName.encode().decode("unicode-escape")
        self.parse(cd)
        self.parse(c)
        # ``aggGroup`` on the wire ships ``0`` (and IBKR's UNSET_INTEGER
        # sentinel) when the contract has no aggregate group. ``None`` is
        # the universal unset marker on the public dataclass so user code
        # gating on ``if details.aggGroup:`` stays falsy without the
        # sentinel's magic int leaking through.
        if cd.aggGroup in (0, UNSET_INTEGER):
            cd.aggGroup = None
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

        times = splitIBLastTradeDate(lastTimes)

        if len(times) > 0:
            cd.maturity = times[0]

        if len(times) > 1:
            cd.lastTradeTime = times[1]

        # Pre-188 servers pack the timezone into the third split component
        # of ``lastTradeDateOrContractMonth``; 188+ delivers it as an
        # explicit ``timeZoneId`` field above. The explicit field WINS
        # when both are present, so only adopt the split-derived value
        # below the gate.
        if len(times) > 2 and self.serverVersion < MIN_SERVER_VER_BOND_TRADING_HOURS:
            cd.timeZoneId = times[2]

        self.parse(cd)
        self.parse(c)
        # ``aggGroup`` on the wire ships ``0`` (and IBKR's UNSET_INTEGER
        # sentinel) when the contract has no aggregate group. ``None`` is
        # the universal unset marker on the public dataclass.
        if cd.aggGroup in (0, UNSET_INTEGER):
            cd.aggGroup = None
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
            commissionAndFees,
            currency,
            realizedPNL,
            yield_,
            yieldRedemptionDate,
        ) = fields

        self.wrapper.commissionReport(
            CommissionReport(
                execId,
                safe_decimal(commissionAndFees),
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

        def _aggGroupOrNone(raw: str) -> int | None:
            # Wire ships ``0`` (and IBKR's UNSET_INTEGER sentinel) when the
            # exchange isn't aggregated. ``None`` is the universal unset
            # marker on the dataclass — collapse both to ``None`` so
            # ``if desc.aggGroup:`` stays falsy without surfacing the
            # sentinel's magic int.
            try:
                value = int(raw)
            except (TypeError, ValueError):
                return None
            if value in (0, UNSET_INTEGER):
                return None
            return value

        descriptions = [
            DepthMktDataDescription(
                exchange=get(),
                secType=get(),
                listingExch=get(),
                serviceDataType=get(),
                aggGroup=_aggGroupOrNone(get()),
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
            attribLast = TickAttribLast(
                pastLimit=bool(mask & 1), unreported=bool(mask & 2)
            )

            self.wrapper.tickByTickAllLast(
                reqId,
                tickType,
                time,
                float(price),
                float(size),
                attribLast,
                exchange,
                specialConditions,
            )
        elif tickType == 3:
            bidPrice, askPrice, bidSize, askSize, mask = fields
            mask = int(mask)
            attribBidAsk = TickAttribBidAsk(
                bidPastLow=bool(mask & 1), askPastHigh=bool(mask & 2)
            )

            self.wrapper.tickByTickBidAsk(
                reqId,
                time,
                float(bidPrice),
                float(askPrice),
                float(bidSize),
                float(askSize),
                attribBidAsk,
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

        o.scalePriceIncrement = safe_decimal(increment)
        if (
            o.scalePriceIncrement is not None
            and 0 < o.scalePriceIncrement < UNSET_DOUBLE
        ):
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
            st.commissionAndFees,
            st.minCommission,
            st.maxCommission,
            st.commissionCurrency,
            *fields,
        ) = fields

        # FULL_ORDER_PREVIEW_FIELDS block — the server appends the
        # OutsideRTH margin family, suggestedSize / rejectReason, and the
        # repeated orderAllocations between commissionCurrency and
        # warningText starting at server 195. Without this gating block
        # the wire stream shifts left and every gated read past warningText
        # reads from the wrong slot, silently corrupting the rest of the
        # decode.
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

        # Trailing wire fields IBKR appends past gate 170. Each one lands
        # on the matching ``Order`` dataclass field — the order here MUST
        # match the order in which the server writes them.
        if self.serverVersion >= MIN_SERVER_VER_CUSTOMER_ACCOUNT:
            o.customerAccount, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_PROFESSIONAL_CUSTOMER:
            professionalCustomer, *fields = fields
            o.professionalCustomer = bool(int(professionalCustomer or 0))
        if self.serverVersion >= MIN_SERVER_VER_BOND_ACCRUED_INTEREST:
            o.bondAccruedInterest, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_INCLUDE_OVERNIGHT:
            includeOvernight, *fields = fields
            o.includeOvernight = bool(int(includeOvernight or 0))
        if self.serverVersion >= MIN_SERVER_VER_CME_TAGGING_FIELDS_IN_OPEN_ORDER:
            extOperator, manualOrderIndicator, *fields = fields
            o.extOperator = extOperator
            o.manualOrderIndicator = (
                int(manualOrderIndicator) if manualOrderIndicator else UNSET_INTEGER
            )
        if self.serverVersion >= MIN_SERVER_VER_SUBMITTER:
            o.submitter, *fields = fields
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

        o.scalePriceIncrement = safe_decimal(increment)
        if (
            o.scalePriceIncrement is not None
            and 0 < o.scalePriceIncrement < UNSET_DOUBLE
        ):
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
        # gate 170. The completedOrder feed lacks the bond / overnight /
        # CME-tagging block that openOrder carries, but customerAccount /
        # professionalCustomer / submitter all land on the corresponding
        # ``Order`` dataclass fields the same way openOrder does.
        if self.serverVersion >= MIN_SERVER_VER_CUSTOMER_ACCOUNT:
            o.customerAccount, *fields = fields
        if self.serverVersion >= MIN_SERVER_VER_PROFESSIONAL_CUSTOMER:
            professionalCustomer, *fields = fields
            o.professionalCustomer = bool(int(professionalCustomer or 0))
        if self.serverVersion >= MIN_SERVER_VER_SUBMITTER:
            o.submitter, *fields = fields

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
