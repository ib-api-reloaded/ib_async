"""Protobuf converters for scanner, fundamentals, and PnL.

Pure functions: every converter takes only proto inputs (or domain
inputs on the send side). No reads from module-level state, no
dependencies on ``Wrapper``. ``HasField`` guards every optional read so
malformed / partially-populated wire messages decode to safe defaults
instead of raising into the decoder's exception path.

Wire-shape notes:

* ``ScannerData`` carries a ``repeated ScannerDataElement``; each
  element produces an independent ``Wrapper.scannerData`` invocation.
  The wire ``Contract`` sub-message is wrapped as a domain
  ``ContractDetails(contract=..., marketName=...)`` since the wrapper
  takes ``ContractDetails``. The wire ``comboKey`` field maps to the
  wrapper's ``legsStr`` argument.
* ``PnLSingle.position`` is wire ``string`` (Decimal precision) but the
  wrapper expects ``pos: int``. Coercion is via
  ``int(safe_decimal(...) or 0)`` — fractional / nan / empty values
  collapse to ``0`` rather than raise.
* ``ScannerSubscription`` send-side mirrors the full ~21-field domain
  dataclass plus both wire map fields:
  ``scannerSubscriptionFilterOptions`` (the documented per-instrument
  generic filter options shipped on TWS >= MIN_SERVER_VER_SCANNER_GENERIC_OPTS)
  and ``scannerSubscriptionOptions`` (IBKR-internal, kept for parity).
* ``FundamentalsDataRequest`` and the news-side requests (article /
  historical news) carry trailing ``map<string, string>`` option fields
  — these are TagValue lists on the public surface; pass-through must
  preserve them or the proto path silently drops user-provided options
  the binary path would have shipped.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .._pb import (
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
    ScannerParametersRequest_pb2,
    ScannerSubscription_pb2,
    ScannerSubscriptionRequest_pb2,
)
from ..contract import Contract, ContractDetails, TagValue
from ..objects import ScannerSubscription
from ..util import UNSET_INTEGER
from .contracts import createContract, createContractProto
from .safe import (
    fill_tag_value_map,
    normalize_none_scalars,
    safe_decimal,
)
from .safe import (
    is_valid_float as _isValidFloat,
)
from .safe import (
    is_valid_int as _isValidInt,
)

# ---------------------------------------------------------------------------
# Args dataclasses (slotted, frozen — operator-mandated, not tuples)
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class ScannerDataElementArgs:
    """Args for ``Wrapper.scannerData(reqId, rank, contractDetails, distance, benchmark, projection, legsStr)``."""

    reqId: int
    rank: int
    contractDetails: ContractDetails
    distance: str
    benchmark: str
    projection: str
    legsStr: str


@dataclass(slots=True, frozen=True)
class ScannerDataArgs:
    """Batch decode of ``ScannerData`` proto: reqId + per-element args list.

    The decoder is expected to iterate ``elements`` and dispatch each
    via ``Wrapper.scannerData(...)``, then call ``Wrapper.scannerDataEnd(reqId)``.
    """

    reqId: int
    elements: list[ScannerDataElementArgs]


@dataclass(slots=True, frozen=True)
class FundamentalDataArgs:
    """Args for ``Wrapper.fundamentalData(reqId, data)``."""

    reqId: int
    data: str


@dataclass(slots=True, frozen=True)
class PnLArgs:
    """Args for ``Wrapper.pnl(reqId, dailyPnL, unrealizedPnL, realizedPnL)``."""

    reqId: int
    dailyPnL: float
    unrealizedPnL: float
    realizedPnL: float


@dataclass(slots=True, frozen=True)
class PnLSingleArgs:
    """Args for ``Wrapper.pnlSingle(reqId, pos, dailyPnL, unrealizedPnL, realizedPnL, value)``."""

    reqId: int
    pos: Decimal | None
    dailyPnL: float
    unrealizedPnL: float
    realizedPnL: float
    value: float


# ---------------------------------------------------------------------------
# ScannerData (msgId 20 receive)
# ---------------------------------------------------------------------------


def createScannerDataElementArgs(
    reqId: int, proto: ScannerDataElement_pb2.ScannerDataElement
) -> ScannerDataElementArgs:
    """Decode a single ``ScannerDataElement`` to wrapper args.

    ``reqId`` is carried separately because the wire's repeated
    element message itself doesn't carry one — it lives on the
    enclosing ``ScannerData``. The wire ``contract`` sub-message is
    wrapped into a ``ContractDetails(contract=..., marketName=...)``
    because the wrapper's ``scannerData`` signature takes
    ``ContractDetails`` not ``Contract``. Wire ``comboKey`` maps to
    ``legsStr``.
    """
    rank = proto.rank if proto.HasField("rank") else 0
    contract = (
        createContract(proto.contract) if proto.HasField("contract") else Contract()
    )
    marketName = proto.marketName if proto.HasField("marketName") else ""
    details = ContractDetails(contract=contract, marketName=marketName)
    distance = proto.distance if proto.HasField("distance") else ""
    benchmark = proto.benchmark if proto.HasField("benchmark") else ""
    projection = proto.projection if proto.HasField("projection") else ""
    legsStr = proto.comboKey if proto.HasField("comboKey") else ""
    return ScannerDataElementArgs(
        reqId=reqId,
        rank=rank,
        contractDetails=details,
        distance=distance,
        benchmark=benchmark,
        projection=projection,
        legsStr=legsStr,
    )


def createScannerDataArgs(proto: ScannerData_pb2.ScannerData) -> ScannerDataArgs:
    """Decode the whole ``ScannerData`` batch in one shot.

    Returns a ``ScannerDataArgs`` carrying ``reqId`` plus a list of
    per-element args. Decoder iterates ``elements`` and calls
    ``Wrapper.scannerData(...)`` per entry.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    elements = [
        createScannerDataElementArgs(reqId, e) for e in proto.scannerDataElement
    ]
    return ScannerDataArgs(reqId=reqId, elements=elements)


# ---------------------------------------------------------------------------
# ScannerParameters (msgId 19 receive)
# ---------------------------------------------------------------------------


def createScannerParametersXml(proto: ScannerParameters_pb2.ScannerParameters) -> str:
    """Decode ``ScannerParameters`` to its single ``xml`` payload."""
    return proto.xml if proto.HasField("xml") else ""


# ---------------------------------------------------------------------------
# FundamentalsData (msgId 51 receive) + request / cancel
# ---------------------------------------------------------------------------


def createFundamentalDataArgs(
    proto: FundamentalsData_pb2.FundamentalsData,
) -> FundamentalDataArgs:
    """``Wrapper.fundamentalData(reqId, data)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    data = proto.data if proto.HasField("data") else ""
    return FundamentalDataArgs(reqId=reqId, data=data)


def createFundamentalsDataRequestProto(
    reqId: int,
    contract: Contract,
    reportType: str,
    fundamentalsDataOptions: list[TagValue] | None = None,
) -> FundamentalsDataRequest_pb2.FundamentalsDataRequest:
    """Build a ``FundamentalsDataRequest`` envelope.

    ``fundamentalsDataOptions`` is the documented TagValue trailer the
    binary path sends after ``reportType``. The proto wire spells it
    ``fundamentalsDataOptions`` (a ``map<string, string>``); empty /
    ``None`` lists leave the field unset — matching IBKR's
    ``client_utils.createFundamentalsDataRequestProto``.
    """
    proto = FundamentalsDataRequest_pb2.FundamentalsDataRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    proto.contract.CopyFrom(createContractProto(contract))
    if reportType:
        proto.reportType = reportType
    fill_tag_value_map(fundamentalsDataOptions, proto.fundamentalsDataOptions)
    return proto


def createCancelFundamentalsDataProto(
    reqId: int,
) -> CancelFundamentalsData_pb2.CancelFundamentalsData:
    proto = CancelFundamentalsData_pb2.CancelFundamentalsData()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto


# ---------------------------------------------------------------------------
# PnL (msgId 94 receive) + request / cancel
# ---------------------------------------------------------------------------


def createPnLArgs(proto: PnL_pb2.PnL) -> PnLArgs:
    """``Wrapper.pnl(reqId, dailyPnL, unrealizedPnL, realizedPnL)`` args.

    All three numeric fields are wire ``double`` and stay ``float`` —
    the wrapper's signature takes ``float`` and downstream
    ``PnL`` domain dataclass stores floats today.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    dailyPnL = proto.dailyPnL if proto.HasField("dailyPnL") else 0.0
    unrealizedPnL = proto.unrealizedPnL if proto.HasField("unrealizedPnL") else 0.0
    realizedPnL = proto.realizedPnL if proto.HasField("realizedPnL") else 0.0
    return PnLArgs(
        reqId=reqId,
        dailyPnL=dailyPnL,
        unrealizedPnL=unrealizedPnL,
        realizedPnL=realizedPnL,
    )


def createPnLRequestProto(
    reqId: int, account: str, modelCode: str
) -> PnLRequest_pb2.PnLRequest:
    # Mirror IBKR's gating: empty ``modelCode`` MUST NOT reach the wire
    # (otherwise the server returns Error 321: Model name '' is incorrect).
    proto = PnLRequest_pb2.PnLRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    if account:
        proto.account = account
    if modelCode:
        proto.modelCode = modelCode
    return proto


def createCancelPnLProto(reqId: int) -> CancelPnL_pb2.CancelPnL:
    proto = CancelPnL_pb2.CancelPnL()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto


# ---------------------------------------------------------------------------
# PnLSingle (msgId 95 receive) + request / cancel
# ---------------------------------------------------------------------------


def createPnLSingleArgs(proto: PnLSingle_pb2.PnLSingle) -> PnLSingleArgs:
    """``Wrapper.pnlSingle(reqId, pos, dailyPnL, unrealizedPnL, realizedPnL, value)`` args.

    ``position`` is wire ``string`` (Decimal precision). v3.0 preserves
    that through to the domain ``PnLSingle.position: Decimal | None``
    so fractional positions on crypto / FRACTIONAL_SIZE_SUPPORT
    instruments don't silently truncate.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    pos = safe_decimal(proto.position) if proto.HasField("position") else None
    dailyPnL = proto.dailyPnL if proto.HasField("dailyPnL") else 0.0
    unrealizedPnL = proto.unrealizedPnL if proto.HasField("unrealizedPnL") else 0.0
    realizedPnL = proto.realizedPnL if proto.HasField("realizedPnL") else 0.0
    value = proto.value if proto.HasField("value") else 0.0
    return PnLSingleArgs(
        reqId=reqId,
        pos=pos,
        dailyPnL=dailyPnL,
        unrealizedPnL=unrealizedPnL,
        realizedPnL=realizedPnL,
        value=value,
    )


def createPnLSingleRequestProto(
    reqId: int, account: str, modelCode: str, conId: int
) -> PnLSingleRequest_pb2.PnLSingleRequest:
    # Mirror IBKR's gating; empty modelCode must NOT be written.
    proto = PnLSingleRequest_pb2.PnLSingleRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    if account:
        proto.account = account
    if modelCode:
        proto.modelCode = modelCode
    if conId != UNSET_INTEGER:
        proto.conId = conId
    return proto


def createCancelPnLSingleProto(reqId: int) -> CancelPnLSingle_pb2.CancelPnLSingle:
    proto = CancelPnLSingle_pb2.CancelPnLSingle()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto


# ---------------------------------------------------------------------------
# ScannerSubscriptionRequest send-side
# ---------------------------------------------------------------------------


def createScannerSubscriptionProto(
    sub: ScannerSubscription,
    scannerSubscriptionOptions: list[TagValue] | None = None,
    scannerSubscriptionFilterOptions: list[TagValue] | None = None,
) -> ScannerSubscription_pb2.ScannerSubscription:
    """Translate the ~21-field domain ``ScannerSubscription`` to its proto.

    The numeric filter fields (``abovePrice`` / ``belowPrice`` /
    ``marketCapAbove`` etc.) default to ``None`` on the domain
    dataclass — the universal unset marker. ``None`` skips the wire
    write entirely so the proto field stays unset when the user didn't
    provide a filter; mirrors IBKR's ``isValidFloatValue`` /
    ``isValidIntValue`` gating. ``Decimal``-typed filters are coerced
    through ``float()`` for the proto's wire ``double`` slot.

    ``numberOfRows`` keeps its legacy ``int = -1`` default (an explicit
    "all rows" marker the IBKR server understands); the ``_isValidInt``
    gate would also accept ``-1`` so the write goes through unchanged.

    Both option lists are TagValue trailers IBKR's reference encoder
    writes verbatim into the proto's ``map<string, string>`` fields. The
    *filter* options carry the documented per-instrument generic filter
    settings (server >= MIN_SERVER_VER_SCANNER_GENERIC_OPTS); the
    other is IBKR-internal but accepted for parity. Empty / ``None``
    lists leave the wire fields unset.
    """
    # Wire-boundary coalesce: if a caller stomps ``None`` onto a plain-
    # scalar field (e.g. ``sub.numberOfRows = None``), restore the
    # dataclass default before the gates run, mirroring the binary
    # path's ``NoneType → ""`` formatter.
    normalize_none_scalars(sub)

    proto = ScannerSubscription_pb2.ScannerSubscription()
    if _isValidInt(sub.numberOfRows):
        proto.numberOfRows = sub.numberOfRows
    if sub.instrument:
        proto.instrument = sub.instrument
    if sub.locationCode:
        proto.locationCode = sub.locationCode
    if sub.scanCode:
        proto.scanCode = sub.scanCode
    if _isValidFloat(sub.abovePrice):
        proto.abovePrice = float(sub.abovePrice)
    if _isValidFloat(sub.belowPrice):
        proto.belowPrice = float(sub.belowPrice)
    if _isValidInt(sub.aboveVolume):
        proto.aboveVolume = sub.aboveVolume
    if _isValidFloat(sub.marketCapAbove):
        proto.marketCapAbove = float(sub.marketCapAbove)
    if _isValidFloat(sub.marketCapBelow):
        proto.marketCapBelow = float(sub.marketCapBelow)
    if sub.moodyRatingAbove:
        proto.moodyRatingAbove = sub.moodyRatingAbove
    if sub.moodyRatingBelow:
        proto.moodyRatingBelow = sub.moodyRatingBelow
    if sub.spRatingAbove:
        proto.spRatingAbove = sub.spRatingAbove
    if sub.spRatingBelow:
        proto.spRatingBelow = sub.spRatingBelow
    if sub.maturityDateAbove:
        proto.maturityDateAbove = sub.maturityDateAbove
    if sub.maturityDateBelow:
        proto.maturityDateBelow = sub.maturityDateBelow
    if _isValidFloat(sub.couponRateAbove):
        proto.couponRateAbove = float(sub.couponRateAbove)
    if _isValidFloat(sub.couponRateBelow):
        proto.couponRateBelow = float(sub.couponRateBelow)
    if sub.excludeConvertible:
        proto.excludeConvertible = sub.excludeConvertible
    if _isValidInt(sub.averageOptionVolumeAbove):
        proto.averageOptionVolumeAbove = sub.averageOptionVolumeAbove
    if sub.scannerSettingPairs:
        proto.scannerSettingPairs = sub.scannerSettingPairs
    if sub.stockTypeFilter:
        proto.stockTypeFilter = sub.stockTypeFilter
    fill_tag_value_map(
        scannerSubscriptionFilterOptions, proto.scannerSubscriptionFilterOptions
    )
    fill_tag_value_map(scannerSubscriptionOptions, proto.scannerSubscriptionOptions)
    return proto


def createScannerSubscriptionRequestProto(
    reqId: int,
    sub: ScannerSubscription,
    scannerSubscriptionOptions: list[TagValue] | None = None,
    scannerSubscriptionFilterOptions: list[TagValue] | None = None,
) -> ScannerSubscriptionRequest_pb2.ScannerSubscriptionRequest:
    """Build the full ``ScannerSubscriptionRequest`` envelope.

    Mirrors IBKR's ``client_utils.createScannerSubscriptionRequestProto``:
    ``reqId`` plus the nested ``ScannerSubscription`` (which carries
    both TagValue trailer maps directly on the wire).
    """
    proto = ScannerSubscriptionRequest_pb2.ScannerSubscriptionRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    proto.scannerSubscription.CopyFrom(
        createScannerSubscriptionProto(
            sub,
            scannerSubscriptionOptions=scannerSubscriptionOptions,
            scannerSubscriptionFilterOptions=scannerSubscriptionFilterOptions,
        )
    )
    return proto


def createCancelScannerSubscriptionProto(
    reqId: int,
) -> CancelScannerSubscription_pb2.CancelScannerSubscription:
    proto = CancelScannerSubscription_pb2.CancelScannerSubscription()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    return proto


def createScannerParametersRequestProto() -> (
    ScannerParametersRequest_pb2.ScannerParametersRequest
):
    return ScannerParametersRequest_pb2.ScannerParametersRequest()
