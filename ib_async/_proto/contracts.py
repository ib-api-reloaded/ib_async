"""Protobuf converters for ``Contract`` and related messages.

Pure functions: every converter takes only the proto and (where
applicable) explicit defaults. No reads from module-level state, no
calls into ``Wrapper`` internals. The output is always a fully-typed
domain dataclass with each optional field guarded by ``HasField`` so a
sparsely-populated wire message produces an equivalent partially-set
domain object instead of an exception.

Send-side helpers (``create*Proto``) read fields from the source
domain object only. Empty-string / zero values on the source mean
"not set" and are skipped on the proto so the wire message stays
sparse.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .._pb import (
    ComboLeg_pb2,
    Contract_pb2,
    ContractData_pb2,
    ContractDataRequest_pb2,
    ContractDescription_pb2,
    ContractDetails_pb2,
    DeltaNeutralContract_pb2,
)
from ..contract import (
    ComboLeg,
    Contract,
    ContractDescription,
    ContractDetails,
    DeltaNeutralContract,
    IneligibilityReason,
    TagValue,
)
from ..util import UNSET_DOUBLE, UNSET_INTEGER
from .safe import format_proto_double, safe_decimal

if TYPE_CHECKING:
    from ..order import Order

# --- ComboLeg -------------------------------------------------------------


def createComboLeg(proto: ComboLeg_pb2.ComboLeg) -> ComboLeg:
    leg = ComboLeg()
    if proto.HasField("conId"):
        leg.conId = proto.conId
    if proto.HasField("ratio"):
        leg.ratio = proto.ratio
    if proto.HasField("action"):
        leg.action = proto.action
    if proto.HasField("exchange"):
        leg.exchange = proto.exchange
    if proto.HasField("openClose"):
        leg.openClose = proto.openClose
    # Note: domain field is shortSaleSlot (no 's'), proto is shortSalesSlot.
    if proto.HasField("shortSalesSlot"):
        leg.shortSaleSlot = proto.shortSalesSlot
    if proto.HasField("designatedLocation"):
        leg.designatedLocation = proto.designatedLocation
    if proto.HasField("exemptCode"):
        leg.exemptCode = proto.exemptCode
    return leg


def createComboLegProto(
    leg: ComboLeg, perLegPrice: float | None = None
) -> ComboLeg_pb2.ComboLeg:
    """Encode a domain ``ComboLeg`` plus the matching order's per-leg
    price into the wire proto.

    ``perLegPrice`` lives on the ``Order.orderComboLegs`` parallel list
    in our domain model — IBKR's reference encodes it on the
    ``ComboLeg`` proto's ``perLegPrice`` field. Pass ``None`` (or skip
    the arg) when there is no order pricing context.
    """
    proto = ComboLeg_pb2.ComboLeg()
    # Read every field from the SOURCE leg, never from the freshly-empty
    # target proto (the contributor's PR had this swapped, which made
    # every conditional vacuously true and stomped on the proto with
    # blanks). Zero / empty-string source values are treated as "unset".
    if leg.conId:
        proto.conId = leg.conId
    if leg.ratio:
        proto.ratio = leg.ratio
    if leg.action:
        proto.action = leg.action
    if leg.exchange:
        proto.exchange = leg.exchange
    if leg.openClose:
        proto.openClose = leg.openClose
    if leg.shortSaleSlot:
        proto.shortSalesSlot = leg.shortSaleSlot
    if leg.designatedLocation:
        proto.designatedLocation = leg.designatedLocation
    # ``exemptCode`` defaults to -1 in the domain dataclass, so explicit
    # presence-tracking guards against round-tripping the default as a
    # real value.
    if leg.exemptCode != -1:
        proto.exemptCode = leg.exemptCode
    # ``perLegPrice`` is BAG-secType-only and rides on the contract proto
    # alongside the leg, NOT the order proto. Mirror IBKR's
    # ``createComboLegProto(comboLeg, perLegPrice)`` reference.
    if perLegPrice is not None and perLegPrice != UNSET_DOUBLE:
        proto.perLegPrice = float(perLegPrice)
    return proto


# --- DeltaNeutralContract -------------------------------------------------


def createDeltaNeutralContract(
    proto: DeltaNeutralContract_pb2.DeltaNeutralContract,
) -> DeltaNeutralContract:
    dnc = DeltaNeutralContract()
    if proto.HasField("conId"):
        dnc.conId = proto.conId
    if proto.HasField("delta"):
        dnc.delta = proto.delta
    if proto.HasField("price"):
        dnc.price = proto.price
    return dnc


def createDeltaNeutralContractProto(
    dnc: DeltaNeutralContract,
) -> DeltaNeutralContract_pb2.DeltaNeutralContract:
    proto = DeltaNeutralContract_pb2.DeltaNeutralContract()
    if dnc.conId:
        proto.conId = dnc.conId
    if dnc.delta:
        proto.delta = dnc.delta
    if dnc.price:
        proto.price = dnc.price
    return proto


# --- Contract -------------------------------------------------------------


def createContract(proto: Contract_pb2.Contract) -> Contract:
    contract = Contract()
    if proto.HasField("conId"):
        contract.conId = proto.conId
    if proto.HasField("symbol"):
        contract.symbol = proto.symbol
    if proto.HasField("secType"):
        contract.secType = proto.secType
    if proto.HasField("lastTradeDateOrContractMonth"):
        contract.lastTradeDateOrContractMonth = proto.lastTradeDateOrContractMonth
    if proto.HasField("lastTradeDate"):
        contract.lastTradeDate = proto.lastTradeDate
    if proto.HasField("strike"):
        contract.strike = proto.strike
    if proto.HasField("right"):
        contract.right = proto.right
    if proto.HasField("multiplier"):
        # Wire type is double; domain stores a string in the canonical
        # IBKR form ("100", "0.5") to preserve backwards compat with
        # existing user code.
        contract.multiplier = format_proto_double(proto.multiplier)
    if proto.HasField("exchange"):
        contract.exchange = proto.exchange
    # Wire field is "primaryExch"; domain field is "primaryExchange".
    if proto.HasField("primaryExch"):
        contract.primaryExchange = proto.primaryExch
    if proto.HasField("currency"):
        contract.currency = proto.currency
    if proto.HasField("localSymbol"):
        contract.localSymbol = proto.localSymbol
    if proto.HasField("tradingClass"):
        contract.tradingClass = proto.tradingClass
    if proto.HasField("secIdType"):
        contract.secIdType = proto.secIdType
    if proto.HasField("secId"):
        contract.secId = proto.secId
    if proto.HasField("description"):
        contract.description = proto.description
    if proto.HasField("issuerId"):
        contract.issuerId = proto.issuerId
    if proto.HasField("includeExpired"):
        contract.includeExpired = proto.includeExpired
    if proto.HasField("comboLegsDescrip"):
        contract.comboLegsDescrip = proto.comboLegsDescrip
    if proto.comboLegs:
        contract.comboLegs = [createComboLeg(leg) for leg in proto.comboLegs]
    if proto.HasField("deltaNeutralContract"):
        contract.deltaNeutralContract = createDeltaNeutralContract(
            proto.deltaNeutralContract
        )
    return contract


def createContractProto(
    contract: Contract, order: Order | None = None
) -> Contract_pb2.Contract:
    """Encode a domain ``Contract`` (and optional ``Order`` for combo
    pricing context) into the wire proto.

    When ``order`` is provided AND the contract carries combo legs, the
    parallel ``order.orderComboLegs`` list supplies a ``perLegPrice``
    per leg. IBKR's reference helper signature is
    ``createContractProto(contract, order)``; only the place-order path
    has order context. All other call sites (market data, historical
    data, etc.) pass ``None`` and the wire proto omits ``perLegPrice``
    on every leg.
    """
    proto = Contract_pb2.Contract()
    # IBKR's reference gates ``conId`` and ``strike`` on the sentinel
    # check (``isValidIntValue`` / ``isValidFloatValue``), so a ``0``
    # value is emitted explicitly. Suppressing the field at zero leaves
    # the server reading the proto3-default-absent slot as the IBKR
    # ``UNSET_INTEGER`` / ``UNSET_DOUBLE`` sentinel and rejecting the
    # request — e.g. ``Error 135: Can't find order with id =
    # 2147483647`` on a placeOrder whose contract has not been
    # qualified yet (conId still at the dataclass default).
    if contract.conId != UNSET_INTEGER:
        proto.conId = contract.conId
    if contract.symbol:
        proto.symbol = contract.symbol
    if contract.secType:
        proto.secType = contract.secType
    if contract.lastTradeDateOrContractMonth:
        proto.lastTradeDateOrContractMonth = contract.lastTradeDateOrContractMonth
    if contract.lastTradeDate:
        proto.lastTradeDate = contract.lastTradeDate
    if contract.strike != UNSET_DOUBLE:
        proto.strike = contract.strike
    if contract.right:
        proto.right = contract.right
    if contract.multiplier:
        # String "100" round-trips to double 100.0; format_proto_double
        # on receive recovers "100".
        proto.multiplier = float(contract.multiplier)
    if contract.exchange:
        proto.exchange = contract.exchange
    if contract.primaryExchange:
        proto.primaryExch = contract.primaryExchange
    if contract.currency:
        proto.currency = contract.currency
    if contract.localSymbol:
        proto.localSymbol = contract.localSymbol
    if contract.tradingClass:
        proto.tradingClass = contract.tradingClass
    if contract.secIdType:
        proto.secIdType = contract.secIdType
    if contract.secId:
        proto.secId = contract.secId
    if contract.description:
        proto.description = contract.description
    if contract.issuerId:
        proto.issuerId = contract.issuerId
    if contract.includeExpired:
        proto.includeExpired = contract.includeExpired
    if contract.comboLegsDescrip:
        proto.comboLegsDescrip = contract.comboLegsDescrip
    # Per-leg pricing rides on ComboLeg.perLegPrice; the parallel list
    # ``order.orderComboLegs`` carries it on the order side. Match IBKR's
    # reference ``createComboLegProtoList`` — when there are more contract
    # legs than order legs, the extras get no per-leg price (i.e. unset
    # on the wire), which is the same behaviour the binary path produced.
    orderLegs = (
        order.orderComboLegs if order is not None and order.orderComboLegs else []
    )
    for i, leg in enumerate(contract.comboLegs):
        perLegPrice: float | None = None
        if i < len(orderLegs):
            raw = orderLegs[i].price
            # ``Decimal`` legs survive ``float()``; ``UNSET_DOUBLE`` (the
            # dataclass default) is filtered inside ``createComboLegProto``.
            perLegPrice = float(raw) if raw is not None else None
        proto.comboLegs.append(createComboLegProto(leg, perLegPrice))
    if contract.deltaNeutralContract is not None:
        proto.deltaNeutralContract.CopyFrom(
            createDeltaNeutralContractProto(contract.deltaNeutralContract)
        )
    return proto


# --- ContractDetails ------------------------------------------------------
#
# Receive-only: the server emits ContractDetails in response to
# ``reqContractDetails``. The wire shape unifies bond and non-bond
# contract details that the binary protocol kept separate, so this one
# converter populates both the regular and bond-specific fields on our
# domain ``ContractDetails`` dataclass when the proto carries them.
#
# Fund-family, ineligibility-reason, event-contract, min-algo-size,
# and last-price/size-precision fields are also populated here — they
# arrive on the same wire message and IBKR's reference decoder reads
# them all in one pass.


def createContractDetails(
    proto: ContractDetails_pb2.ContractDetails,
    contract: Contract,
) -> ContractDetails:
    details = ContractDetails()
    details.contract = contract
    if proto.HasField("marketName"):
        details.marketName = proto.marketName
    # ``minTick`` is wire-string carrying a Decimal value. ``safe_decimal``
    # handles empty / "nan" / malformed inputs by returning the default
    # rather than raising — a malformed value here used to crash the
    # converter and hang the awaiter.
    if proto.HasField("minTick"):
        details.minTick = safe_decimal(proto.minTick)
    if proto.HasField("orderTypes"):
        details.orderTypes = proto.orderTypes
    if proto.HasField("validExchanges"):
        details.validExchanges = proto.validExchanges
    if proto.HasField("priceMagnifier"):
        details.priceMagnifier = proto.priceMagnifier
    if proto.HasField("underConId"):
        details.underConId = proto.underConId
    if proto.HasField("longName"):
        details.longName = proto.longName
    if proto.HasField("contractMonth"):
        details.contractMonth = proto.contractMonth
    if proto.HasField("industry"):
        details.industry = proto.industry
    if proto.HasField("category"):
        details.category = proto.category
    if proto.HasField("subcategory"):
        details.subcategory = proto.subcategory
    if proto.HasField("timeZoneId"):
        details.timeZoneId = proto.timeZoneId
    if proto.HasField("tradingHours"):
        details.tradingHours = proto.tradingHours
    if proto.HasField("liquidHours"):
        details.liquidHours = proto.liquidHours
    if proto.HasField("evRule"):
        details.evRule = proto.evRule
    if proto.HasField("evMultiplier"):
        # Wire type is double; route through string to avoid binary-float
        # imprecision contaminating a fractional evMultiplier.
        details.evMultiplier = safe_decimal(proto.evMultiplier)
    if proto.HasField("aggGroup"):
        # Wire ``0`` (and IBKR's ``UNSET_INTEGER`` sentinel) collapse to
        # ``None`` so user code gating on ``if details.aggGroup:`` stays
        # falsy without surfacing the sentinel's magic int.
        if proto.aggGroup != 0 and proto.aggGroup != UNSET_INTEGER:
            details.aggGroup = proto.aggGroup
    if proto.HasField("underSymbol"):
        details.underSymbol = proto.underSymbol
    if proto.HasField("underSecType"):
        details.underSecType = proto.underSecType
    if proto.HasField("marketRuleIds"):
        details.marketRuleIds = proto.marketRuleIds
    if proto.HasField("realExpirationDate"):
        details.realExpirationDate = proto.realExpirationDate
    if proto.HasField("stockType"):
        details.stockType = proto.stockType
    # Size fields are wire-string Decimals.
    if proto.HasField("minSize"):
        details.minSize = safe_decimal(proto.minSize)
    if proto.HasField("sizeIncrement"):
        details.sizeIncrement = safe_decimal(proto.sizeIncrement)
    if proto.HasField("suggestedSizeIncrement"):
        details.suggestedSizeIncrement = safe_decimal(proto.suggestedSizeIncrement)
    if proto.HasField("minAlgoSize"):
        details.minAlgoSize = safe_decimal(proto.minAlgoSize)
    if proto.HasField("lastPricePrecision"):
        details.lastPricePrecision = safe_decimal(proto.lastPricePrecision)
    if proto.HasField("lastSizePrecision"):
        details.lastSizePrecision = safe_decimal(proto.lastSizePrecision)
    # Wire ``secIdList`` is a string-keyed map, not a repeated message;
    # iterate entries to populate the domain ``TagValue`` list.
    if proto.secIdList:
        details.secIdList = [
            TagValue(tag=tag, value=value) for tag, value in proto.secIdList.items()
        ]
    # Bond-side fields; the binary path handled them via a separate
    # ``bondContractDetails`` message. The proto unifies them here.
    if proto.HasField("cusip"):
        details.cusip = proto.cusip
    if proto.HasField("ratings"):
        details.ratings = proto.ratings
    if proto.HasField("descAppend"):
        details.descAppend = proto.descAppend
    if proto.HasField("bondType"):
        details.bondType = proto.bondType
    if proto.HasField("couponType"):
        details.couponType = proto.couponType
    if proto.HasField("callable"):
        details.callable = proto.callable
    if proto.HasField("puttable"):
        # Wire spelling is "puttable"; domain spelling is "putable".
        details.putable = proto.puttable
    if proto.HasField("coupon"):
        details.coupon = safe_decimal(proto.coupon)
    if proto.HasField("convertible"):
        details.convertible = proto.convertible
    if proto.HasField("issueDate"):
        details.issueDate = proto.issueDate
    if proto.HasField("nextOptionDate"):
        details.nextOptionDate = proto.nextOptionDate
    if proto.HasField("nextOptionType"):
        details.nextOptionType = proto.nextOptionType
    if proto.HasField("nextOptionPartial"):
        details.nextOptionPartial = proto.nextOptionPartial
    if proto.HasField("bondNotes"):
        details.notes = proto.bondNotes
    if proto.HasField("fundName"):
        details.fundName = proto.fundName
    if proto.HasField("fundFamily"):
        details.fundFamily = proto.fundFamily
    if proto.HasField("fundType"):
        details.fundType = proto.fundType
    if proto.HasField("fundFrontLoad"):
        details.fundFrontLoad = proto.fundFrontLoad
    if proto.HasField("fundBackLoad"):
        details.fundBackLoad = proto.fundBackLoad
    if proto.HasField("fundBackLoadTimeInterval"):
        details.fundBackLoadTimeInterval = proto.fundBackLoadTimeInterval
    if proto.HasField("fundManagementFee"):
        details.fundManagementFee = proto.fundManagementFee
    if proto.HasField("fundClosed"):
        details.fundClosed = proto.fundClosed
    if proto.HasField("fundClosedForNewInvestors"):
        details.fundClosedForNewInvestors = proto.fundClosedForNewInvestors
    if proto.HasField("fundClosedForNewMoney"):
        details.fundClosedForNewMoney = proto.fundClosedForNewMoney
    if proto.HasField("fundNotifyAmount"):
        details.fundNotifyAmount = proto.fundNotifyAmount
    if proto.HasField("fundMinimumInitialPurchase"):
        details.fundMinimumInitialPurchase = proto.fundMinimumInitialPurchase
    # Wire spelling is ``fundMinimumSubsequentPurchase``; domain spelling
    # is ``fundSubsequentMinimumPurchase`` (matches IBKR's dataclass).
    if proto.HasField("fundMinimumSubsequentPurchase"):
        details.fundSubsequentMinimumPurchase = proto.fundMinimumSubsequentPurchase
    if proto.HasField("fundBlueSkyStates"):
        details.fundBlueSkyStates = proto.fundBlueSkyStates
    if proto.HasField("fundBlueSkyTerritories"):
        details.fundBlueSkyTerritories = proto.fundBlueSkyTerritories
    if proto.HasField("fundDistributionPolicyIndicator"):
        details.fundDistributionPolicyIndicator = proto.fundDistributionPolicyIndicator
    if proto.HasField("fundAssetType"):
        details.fundAssetType = proto.fundAssetType
    if proto.ineligibilityReasonList:
        details.ineligibilityReasonList = [
            IneligibilityReason(
                id_=reason.id if reason.HasField("id") else "",
                description=reason.description
                if reason.HasField("description")
                else "",
            )
            for reason in proto.ineligibilityReasonList
        ]
    if proto.HasField("eventContract1"):
        details.eventContract1 = proto.eventContract1
    if proto.HasField("eventContractDescription1"):
        details.eventContractDescription1 = proto.eventContractDescription1
    if proto.HasField("eventContractDescription2"):
        details.eventContractDescription2 = proto.eventContractDescription2
    return details


def _setLastTradeDate(details: ContractDetails, isBond: bool) -> None:
    """Split ``contract.lastTradeDateOrContractMonth`` into the
    separate fields the binary path delivered.

    The wire packs date + time (and bond timezone) into a single
    space- or hyphen-separated string. The binary contractDetails
    decoder splits it; the proto path needs the same split or
    callers see ``ContractDetails.lastTradeTime`` (and bond
    ``maturity`` / ``timeZoneId``) empty.
    """
    contract = details.contract
    if contract is None:
        return
    raw = contract.lastTradeDateOrContractMonth
    if not raw:
        return
    parts = raw.split("-") if "-" in raw else raw.split()
    if parts:
        if isBond:
            details.maturity = parts[0]
        else:
            contract.lastTradeDateOrContractMonth = parts[0]
    if len(parts) > 1:
        details.lastTradeTime = parts[1]
    if isBond and len(parts) > 2:
        details.timeZoneId = parts[2]


def createContractDetailsFromContractData(
    proto: ContractData_pb2.ContractData,
) -> ContractDetails:
    """Decode a ``ContractData`` proto envelope into a ``ContractDetails``.

    ``ContractData`` is the wire wrapper around
    ``contract`` + ``ContractDetails`` that ``reqContractDetails`` returns.
    """
    contract = (
        createContract(proto.contract) if proto.HasField("contract") else Contract()
    )
    if proto.HasField("contractDetails"):
        details = createContractDetails(proto.contractDetails, contract)
        _setLastTradeDate(details, isBond=contract.secType == "BOND")
        return details
    details = ContractDetails()
    details.contract = contract
    return details


# --- ContractDescription --------------------------------------------------


def createContractDataRequestProto(
    reqId: int, contract: Contract
) -> ContractDataRequest_pb2.ContractDataRequest:
    """Encode a ``ContractDataRequest`` envelope for ``reqContractDetails``.

    Wraps a freshly-encoded ``ContractProto`` plus the request id. The
    reqId write is gated on ``isValidIntValue`` (mirrors IBKR's
    ``client_utils.createContractDataRequestProto``).
    """
    proto = ContractDataRequest_pb2.ContractDataRequest()
    if reqId != UNSET_INTEGER:
        proto.reqId = reqId
    proto.contract.CopyFrom(createContractProto(contract))
    return proto


def createContractDescription(
    proto: ContractDescription_pb2.ContractDescription,
) -> ContractDescription:
    contract = (
        createContract(proto.contract) if proto.HasField("contract") else Contract()
    )
    return ContractDescription(
        contract=contract,
        derivativeSecTypes=list(proto.derivativeSecTypes),
    )
