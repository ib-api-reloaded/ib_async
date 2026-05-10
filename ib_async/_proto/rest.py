"""Protobuf converters for REST-shape messages.

REST-shape covers the small one-shot request/response endpoints that
don't carry their own subscription lifecycle: server time, the new
millisecond-precision time, user info, soft-dollar tiers, smart
components, market rule, sec-def-opt-params, symbol samples, plus
the option-math sends (exercise / calc-implied-vol / calc-option-price)
and the bare-bones session envelopes (``StartApi`` / ``SetServerLogLevel``).

Pure functions: every converter takes only proto inputs (or domain
inputs on the send side). ``HasField`` guards every optional read so
malformed / partial wire frames produce safe-default args instead of
raising into the decoder's exception path.

Wire-shape notes:

* ``CurrentTime`` and ``CurrentTimeInMillis`` carry a single ``int64``
  timestamp each. The TWS-side spelling for the millisecond capability
  is new in v3.0 — the corresponding ``Wrapper.currentTimeInMillis``
  method ships in a follow-up commit alongside the public
  ``IB.reqCurrentTimeInMillisAsync`` entry point.
* ``NextValidId`` carries an ``orderId`` field on the wire; the wrapper
  consumes it as ``reqId`` (single-int positional dispatch — no args
  dataclass needed because there's nothing to name beyond the int).
* ``SoftDollarTier`` proto fields ``name`` / ``value`` / ``displayName``
  map to the domain dataclass's ``name`` / ``val`` / ``displayName``
  (``value`` → ``val`` is the legacy spelling).
* ``SecDefOptParameter`` carries repeated scalar containers
  ``expirations: string`` and ``strikes: double`` — converted to plain
  ``list[str]`` / ``list[float]`` so downstream call sites (``OptionChain``)
  see the same shapes the binary path produces.
* ``ExerciseOptionsRequest`` has three optional fields (``manualOrderTime``,
  ``customerAccount``, ``professionalCustomer``); the factory takes
  ``str | None`` / ``bool | None`` so callers can leave them unset and
  the wire frame stays compatible with older TWS builds.
* ``CalculateImpliedVolatilityRequest`` / ``CalculateOptionPriceRequest``
  each carry an options-string-map (``impliedVolatilityOptions`` /
  ``optionPriceOptions``); the binary path always sends them empty, so
  the factory leaves them empty too.
"""

from __future__ import annotations

from dataclasses import dataclass

from .._pb import (
    ApiConfig_pb2,
    CalculateImpliedVolatilityRequest_pb2,
    CalculateOptionPriceRequest_pb2,
    CancelCalculateImpliedVolatility_pb2,
    CancelCalculateOptionPrice_pb2,
    ConfigRequest_pb2,
    CurrentTime_pb2,
    CurrentTimeInMillis_pb2,
    CurrentTimeInMillisRequest_pb2,
    CurrentTimeRequest_pb2,
    ExerciseOptionsRequest_pb2,
    LockAndExitConfig_pb2,
    MarketRule_pb2,
    MarketRuleRequest_pb2,
    MatchingSymbolsRequest_pb2,
    MessageConfig_pb2,
    NextValidId_pb2,
    OrdersConfig_pb2,
    PriceIncrement_pb2,
    SecDefOptParameter_pb2,
    SecDefOptParameterEnd_pb2,
    SecDefOptParamsRequest_pb2,
    SetServerLogLevelRequest_pb2,
    SmartComponent_pb2,
    SmartComponents_pb2,
    SmartComponentsRequest_pb2,
    SoftDollarTier_pb2,
    SoftDollarTiers_pb2,
    SoftDollarTiersRequest_pb2,
    StartApiRequest_pb2,
    SymbolSamples_pb2,
    UpdateConfigRequest_pb2,
    UpdateConfigWarning_pb2,
    UserInfo_pb2,
    UserInfoRequest_pb2,
)
from ..contract import Contract, ContractDescription, TagValue
from ..objects import PriceIncrement, SmartComponent, SoftDollarTier
from .contracts import createContractDescription, createContractProto
from .safe import fill_tag_value_map

# ---------------------------------------------------------------------------
# Args dataclasses for converter return shapes — slotted, frozen, named.
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class SecDefOptParameterArgs:
    """Args for ``Wrapper.securityDefinitionOptionParameter(reqId, exchange, underlyingConId, tradingClass, multiplier, expirations, strikes)``."""

    reqId: int
    exchange: str
    underlyingConId: int
    tradingClass: str
    multiplier: str
    expirations: list[str]
    strikes: list[float]


@dataclass(slots=True, frozen=True)
class SoftDollarTiersArgs:
    """Args for ``Wrapper.softDollarTiers(reqId, tiers)``."""

    reqId: int
    tiers: list[SoftDollarTier]


@dataclass(slots=True, frozen=True)
class SymbolSamplesArgs:
    """Args for ``Wrapper.symbolSamples(reqId, contractDescriptions)``."""

    reqId: int
    contractDescriptions: list[ContractDescription]


@dataclass(slots=True, frozen=True)
class SmartComponentsArgs:
    """Args for ``Wrapper.smartComponents(reqId, components)``."""

    reqId: int
    components: list[SmartComponent]


@dataclass(slots=True, frozen=True)
class MarketRuleArgs:
    """Args for ``Wrapper.marketRule(marketRuleId, priceIncrements)``."""

    marketRuleId: int
    priceIncrements: list[PriceIncrement]


@dataclass(slots=True, frozen=True)
class UserInfoArgs:
    """Args for ``Wrapper.userInfo(reqId, whiteBrandingId)``."""

    reqId: int
    whiteBrandingId: str


# ---------------------------------------------------------------------------
# NextValidId (msgId 9) — single-int dispatch, no args dataclass needed.
# ---------------------------------------------------------------------------


def createNextValidIdOrderId(proto: NextValidId_pb2.NextValidId) -> int:
    """Decode a ``NextValidId`` proto to the single int the wrapper expects.

    Wire field is named ``orderId``; the wrapper parameter is named
    ``reqId``. Same int — IBKR uses the next-valid order id as the
    starting point for client-allocated reqIds.
    """
    return proto.orderId if proto.HasField("orderId") else 0


# ---------------------------------------------------------------------------
# CurrentTime (msgId 49) + CurrentTimeRequest envelope.
# ---------------------------------------------------------------------------


def createCurrentTimeSeconds(proto: CurrentTime_pb2.CurrentTime) -> int:
    """Decode a ``CurrentTime`` proto to the single int64 the wrapper expects.

    Returned value is epoch seconds (TWS's ``time(2)`` semantics).
    """
    return proto.currentTime if proto.HasField("currentTime") else 0


def createCurrentTimeRequestProto() -> CurrentTimeRequest_pb2.CurrentTimeRequest:
    """Empty-body request envelope for ``reqCurrentTime``."""
    return CurrentTimeRequest_pb2.CurrentTimeRequest()


# ---------------------------------------------------------------------------
# CurrentTimeInMillis (msgId 109) — NEW capability + request envelope.
# ---------------------------------------------------------------------------


def createCurrentTimeInMillisMillis(
    proto: CurrentTimeInMillis_pb2.CurrentTimeInMillis,
) -> int:
    """Decode a ``CurrentTimeInMillis`` proto to the single int64 timestamp.

    Returned value is epoch milliseconds. The dispatching wrapper method
    ``Wrapper.currentTimeInMillis(timeInMillis: int)`` ships in the
    follow-up commit that wires in ``IB.reqCurrentTimeInMillisAsync``.
    """
    return proto.currentTimeInMillis if proto.HasField("currentTimeInMillis") else 0


def createCurrentTimeInMillisRequestProto() -> (
    CurrentTimeInMillisRequest_pb2.CurrentTimeInMillisRequest
):
    """Empty-body request envelope for ``reqCurrentTimeInMillis``."""
    return CurrentTimeInMillisRequest_pb2.CurrentTimeInMillisRequest()


# ---------------------------------------------------------------------------
# UserInfo (msgId 107) + UserInfoRequest envelope.
# ---------------------------------------------------------------------------


def createUserInfoArgs(proto: UserInfo_pb2.UserInfo) -> UserInfoArgs:
    """``Wrapper.userInfo(reqId, whiteBrandingId)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    whiteBrandingId = proto.whiteBrandingId if proto.HasField("whiteBrandingId") else ""
    return UserInfoArgs(reqId=reqId, whiteBrandingId=whiteBrandingId)


def createUserInfoRequestProto(reqId: int) -> UserInfoRequest_pb2.UserInfoRequest:
    proto = UserInfoRequest_pb2.UserInfoRequest()
    proto.reqId = reqId
    return proto


# ---------------------------------------------------------------------------
# SoftDollarTier / SoftDollarTiers (msgId 77) + SoftDollarTiersRequest.
# ---------------------------------------------------------------------------


def createSoftDollarTier(
    proto: SoftDollarTier_pb2.SoftDollarTier,
) -> SoftDollarTier:
    """Decode a ``SoftDollarTier`` proto to the domain dataclass.

    Wire field ``value`` maps to domain field ``val`` (legacy spelling).
    """
    name = proto.name if proto.HasField("name") else ""
    val = proto.value if proto.HasField("value") else ""
    displayName = proto.displayName if proto.HasField("displayName") else ""
    return SoftDollarTier(name=name, val=val, displayName=displayName)


def createSoftDollarTiersArgs(
    proto: SoftDollarTiers_pb2.SoftDollarTiers,
) -> SoftDollarTiersArgs:
    """``Wrapper.softDollarTiers(reqId, tiers)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    tiers = [createSoftDollarTier(t) for t in proto.softDollarTiers]
    return SoftDollarTiersArgs(reqId=reqId, tiers=tiers)


def createSoftDollarTiersRequestProto(
    reqId: int,
) -> SoftDollarTiersRequest_pb2.SoftDollarTiersRequest:
    proto = SoftDollarTiersRequest_pb2.SoftDollarTiersRequest()
    proto.reqId = reqId
    return proto


# ---------------------------------------------------------------------------
# SmartComponent / SmartComponents (msgId 82) + SmartComponentsRequest.
# ---------------------------------------------------------------------------


def createSmartComponent(
    proto: SmartComponent_pb2.SmartComponent,
) -> SmartComponent:
    """Decode a ``SmartComponent`` proto to the domain dataclass."""
    bitNumber = proto.bitNumber if proto.HasField("bitNumber") else 0
    exchange = proto.exchange if proto.HasField("exchange") else ""
    exchangeLetter = proto.exchangeLetter if proto.HasField("exchangeLetter") else ""
    return SmartComponent(
        bitNumber=bitNumber, exchange=exchange, exchangeLetter=exchangeLetter
    )


def createSmartComponentsArgs(
    proto: SmartComponents_pb2.SmartComponents,
) -> SmartComponentsArgs:
    """``Wrapper.smartComponents(reqId, components)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    components = [createSmartComponent(c) for c in proto.smartComponents]
    return SmartComponentsArgs(reqId=reqId, components=components)


def createSmartComponentsRequestProto(
    reqId: int, bboExchange: str
) -> SmartComponentsRequest_pb2.SmartComponentsRequest:
    proto = SmartComponentsRequest_pb2.SmartComponentsRequest()
    proto.reqId = reqId
    proto.bboExchange = bboExchange
    return proto


# ---------------------------------------------------------------------------
# PriceIncrement / MarketRule (msgId 93) + MarketRuleRequest.
# ---------------------------------------------------------------------------


def createPriceIncrement(
    proto: PriceIncrement_pb2.PriceIncrement,
) -> PriceIncrement:
    """Decode a ``PriceIncrement`` proto to the domain dataclass."""
    lowEdge = proto.lowEdge if proto.HasField("lowEdge") else 0.0
    increment = proto.increment if proto.HasField("increment") else 0.0
    return PriceIncrement(lowEdge=lowEdge, increment=increment)


def createMarketRuleArgs(proto: MarketRule_pb2.MarketRule) -> MarketRuleArgs:
    """``Wrapper.marketRule(marketRuleId, priceIncrements)`` args."""
    marketRuleId = proto.marketRuleId if proto.HasField("marketRuleId") else 0
    priceIncrements = [createPriceIncrement(p) for p in proto.priceIncrements]
    return MarketRuleArgs(marketRuleId=marketRuleId, priceIncrements=priceIncrements)


def createMarketRuleRequestProto(
    marketRuleId: int,
) -> MarketRuleRequest_pb2.MarketRuleRequest:
    proto = MarketRuleRequest_pb2.MarketRuleRequest()
    proto.marketRuleId = marketRuleId
    return proto


# ---------------------------------------------------------------------------
# SecDefOptParameter (msgId 75) / SecDefOptParameterEnd (msgId 76)
# + SecDefOptParamsRequest.
# ---------------------------------------------------------------------------


def createSecDefOptParameterArgs(
    proto: SecDefOptParameter_pb2.SecDefOptParameter,
) -> SecDefOptParameterArgs:
    """``Wrapper.securityDefinitionOptionParameter(reqId, exchange, underlyingConId, tradingClass, multiplier, expirations, strikes)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    exchange = proto.exchange if proto.HasField("exchange") else ""
    underlyingConId = proto.underlyingConId if proto.HasField("underlyingConId") else 0
    tradingClass = proto.tradingClass if proto.HasField("tradingClass") else ""
    multiplier = proto.multiplier if proto.HasField("multiplier") else ""
    expirations = list(proto.expirations)
    strikes = list(proto.strikes)
    return SecDefOptParameterArgs(
        reqId=reqId,
        exchange=exchange,
        underlyingConId=underlyingConId,
        tradingClass=tradingClass,
        multiplier=multiplier,
        expirations=expirations,
        strikes=strikes,
    )


def createSecDefOptParameterEndReqId(
    proto: SecDefOptParameterEnd_pb2.SecDefOptParameterEnd,
) -> int:
    """Decode a ``SecDefOptParameterEnd`` proto to the single reqId int."""
    return proto.reqId if proto.HasField("reqId") else 0


def createSecDefOptParamsRequestProto(
    reqId: int,
    underlyingSymbol: str,
    futFopExchange: str,
    underlyingSecType: str,
    underlyingConId: int,
) -> SecDefOptParamsRequest_pb2.SecDefOptParamsRequest:
    proto = SecDefOptParamsRequest_pb2.SecDefOptParamsRequest()
    proto.reqId = reqId
    proto.underlyingSymbol = underlyingSymbol
    proto.futFopExchange = futFopExchange
    proto.underlyingSecType = underlyingSecType
    proto.underlyingConId = underlyingConId
    return proto


# ---------------------------------------------------------------------------
# SymbolSamples (msgId 79) + MatchingSymbolsRequest.
# ---------------------------------------------------------------------------


def createSymbolSamplesArgs(
    proto: SymbolSamples_pb2.SymbolSamples,
) -> SymbolSamplesArgs:
    """``Wrapper.symbolSamples(reqId, contractDescriptions)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    descriptions = [createContractDescription(d) for d in proto.contractDescriptions]
    return SymbolSamplesArgs(reqId=reqId, contractDescriptions=descriptions)


def createMatchingSymbolsRequestProto(
    reqId: int, pattern: str
) -> MatchingSymbolsRequest_pb2.MatchingSymbolsRequest:
    proto = MatchingSymbolsRequest_pb2.MatchingSymbolsRequest()
    proto.reqId = reqId
    proto.pattern = pattern
    return proto


# ---------------------------------------------------------------------------
# StartApi / SetServerLogLevel — bare-bones session envelopes.
# ---------------------------------------------------------------------------


def createStartApiRequestProto(
    clientId: int, optionalCapabilities: str
) -> StartApiRequest_pb2.StartApiRequest:
    proto = StartApiRequest_pb2.StartApiRequest()
    proto.clientId = clientId
    proto.optionalCapabilities = optionalCapabilities
    return proto


def createSetServerLogLevelRequestProto(
    logLevel: int,
) -> SetServerLogLevelRequest_pb2.SetServerLogLevelRequest:
    proto = SetServerLogLevelRequest_pb2.SetServerLogLevelRequest()
    proto.logLevel = logLevel
    return proto


# ---------------------------------------------------------------------------
# ExerciseOptionsRequest — option-math send path.
# ---------------------------------------------------------------------------


def createExerciseOptionsRequestProto(
    orderId: int,
    contract: Contract,
    exerciseAction: int,
    exerciseQuantity: int,
    account: str,
    override: bool,
    manualOrderTime: str | None = None,
    customerAccount: str | None = None,
    professionalCustomer: bool | None = None,
) -> ExerciseOptionsRequest_pb2.ExerciseOptionsRequest:
    """Build an ``ExerciseOptionsRequest`` from caller args.

    The three trailing fields (``manualOrderTime``, ``customerAccount``,
    ``professionalCustomer``) are optional — when the caller passes
    ``None`` we leave the proto field unset so older TWS builds without
    those fields still parse the request cleanly.

    The bool ``override`` is always written (even when ``False``) because
    proto3 default-skipping would otherwise indistinguishably encode
    "user explicitly said False" and "user didn't say". The wrapper /
    decoder honors the explicit-False semantic.
    """
    proto = ExerciseOptionsRequest_pb2.ExerciseOptionsRequest()
    proto.orderId = orderId
    proto.contract.CopyFrom(createContractProto(contract))
    proto.exerciseAction = exerciseAction
    proto.exerciseQuantity = exerciseQuantity
    proto.account = account
    proto.override = override
    if manualOrderTime is not None:
        proto.manualOrderTime = manualOrderTime
    if customerAccount is not None:
        proto.customerAccount = customerAccount
    if professionalCustomer is not None:
        proto.professionalCustomer = professionalCustomer
    return proto


# ---------------------------------------------------------------------------
# CalculateImpliedVolatility / CalculateOptionPrice + cancels.
# ---------------------------------------------------------------------------


def createCalculateImpliedVolatilityRequestProto(
    reqId: int,
    contract: Contract,
    optionPrice: float,
    underPrice: float,
    impliedVolatilityOptions: list[TagValue] | None = None,
) -> CalculateImpliedVolatilityRequest_pb2.CalculateImpliedVolatilityRequest:
    """Build a ``CalculateImpliedVolatilityRequest`` from caller args.

    Mirrors IBKR's ``client_utils.createCalculateImpliedVolatilityRequestProto``:
    forwards ``impliedVolatilityOptions`` as the proto's ``map<string, string>``
    so user-supplied trailers reach the wire.
    """
    proto = CalculateImpliedVolatilityRequest_pb2.CalculateImpliedVolatilityRequest()
    proto.reqId = reqId
    proto.contract.CopyFrom(createContractProto(contract))
    proto.optionPrice = optionPrice
    proto.underPrice = underPrice
    fill_tag_value_map(impliedVolatilityOptions, proto.impliedVolatilityOptions)
    return proto


def createCalculateOptionPriceRequestProto(
    reqId: int,
    contract: Contract,
    volatility: float,
    underPrice: float,
    optionPriceOptions: list[TagValue] | None = None,
) -> CalculateOptionPriceRequest_pb2.CalculateOptionPriceRequest:
    """Build a ``CalculateOptionPriceRequest`` from caller args.

    Mirrors IBKR's ``client_utils.createCalculateOptionPriceRequestProto``:
    forwards ``optionPriceOptions`` as the proto's ``map<string, string>``
    so user-supplied trailers reach the wire.
    """
    proto = CalculateOptionPriceRequest_pb2.CalculateOptionPriceRequest()
    proto.reqId = reqId
    proto.contract.CopyFrom(createContractProto(contract))
    proto.volatility = volatility
    proto.underPrice = underPrice
    fill_tag_value_map(optionPriceOptions, proto.optionPriceOptions)
    return proto


def createCancelCalculateImpliedVolatilityProto(
    reqId: int,
) -> CancelCalculateImpliedVolatility_pb2.CancelCalculateImpliedVolatility:
    proto = CancelCalculateImpliedVolatility_pb2.CancelCalculateImpliedVolatility()
    proto.reqId = reqId
    return proto


def createCancelCalculateOptionPriceProto(
    reqId: int,
) -> CancelCalculateOptionPrice_pb2.CancelCalculateOptionPrice:
    proto = CancelCalculateOptionPrice_pb2.CancelCalculateOptionPrice()
    proto.reqId = reqId
    return proto


# ---------------------------------------------------------------------------
# ConfigRequest / UpdateConfigRequest — proto-only API config messages.
#
# These two have no binary-protocol counterpart; the wire only carries
# them as protobuf payloads. The matching outbound msgIds (108
# ``REQ_CONFIG`` and 109 ``UPDATE_CONFIG``) are intentionally absent
# from ``PROTOBUF_MSG_IDS`` so the gating-table check is bypassed
# (``Client.useProtoBuf`` is not consulted on the proto-only path).
# ---------------------------------------------------------------------------


def createConfigRequestProto(reqId: int) -> ConfigRequest_pb2.ConfigRequest:
    """Build a ``ConfigRequest`` proto carrying only ``reqId``. Mirrors
    IBKR's ``client.py:reqConfigProtoBuf`` send shape — the request
    body is just an int identifier; the full config payload comes
    back on the response side.
    """
    proto = ConfigRequest_pb2.ConfigRequest()
    proto.reqId = reqId
    return proto


def createUpdateConfigRequestProto(
    reqId: int,
    lockAndExit: LockAndExitConfig_pb2.LockAndExitConfig | None = None,
    messages: list[MessageConfig_pb2.MessageConfig] | None = None,
    api: ApiConfig_pb2.ApiConfig | None = None,
    orders: OrdersConfig_pb2.OrdersConfig | None = None,
    acceptedWarnings: list[UpdateConfigWarning_pb2.UpdateConfigWarning] | None = None,
    resetAPIOrderSequence: bool | None = None,
) -> UpdateConfigRequest_pb2.UpdateConfigRequest:
    """Build an ``UpdateConfigRequest`` proto.

    Mirrors IBKR's ``client.py:updateConfigProtoBuf`` send shape — the
    request carries the full nested config family (lock-and-exit /
    messages / api / orders) plus a list of warnings the user has
    accepted and an opt-in flag to reset the API order sequence.

    All composite sub-messages are optional; when the caller passes
    ``None`` the field stays unset on the wire so older TWS builds
    that don't carry that part of the schema parse cleanly. The
    ``resetAPIOrderSequence`` bool is also optional — proto3 default
    skipping would otherwise make ``False`` indistinguishable from
    "user didn't say".
    """
    proto = UpdateConfigRequest_pb2.UpdateConfigRequest()
    proto.reqId = reqId
    if lockAndExit is not None:
        proto.lockAndExit.CopyFrom(lockAndExit)
    if messages:
        proto.messages.extend(messages)
    if api is not None:
        proto.api.CopyFrom(api)
    if orders is not None:
        proto.orders.CopyFrom(orders)
    if acceptedWarnings:
        proto.acceptedWarnings.extend(acceptedWarnings)
    if resetAPIOrderSequence is not None:
        proto.resetAPIOrderSequence = resetAPIOrderSequence
    return proto
