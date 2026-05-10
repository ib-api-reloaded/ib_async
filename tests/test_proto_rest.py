"""Negative-path-first tests for the REST-messages converter.

Coverage strategy:

* Empty / partial protos must produce safe-default args without
  crashing — exercises the ``HasField`` discipline on every optional
  field.
* Repeated containers (``softDollarTiers`` / ``smartComponents`` /
  ``priceIncrements`` / ``contractDescriptions``) round-trip both
  empty and multi-element cases.
* ``SecDefOptParameter.expirations`` (repeated string) and ``strikes``
  (repeated double) round-trip with multiple entries.
* int64 timestamps (``CurrentTime`` / ``CurrentTimeInMillis``) survive
  the full unsigned-32-bit threshold — the wire field is int64 so a
  value beyond ``2**31`` must come back unchanged.
* ``ExerciseOptionsRequest`` bool fields ``override`` and
  ``professionalCustomer`` round-trip True specifically — proto3 default
  is False and a missing assignment would silently swallow a True.
* ``ExerciseOptionsRequest`` optional trailing fields stay unset when the
  caller passes ``None`` (so older TWS builds parse cleanly).
* Wire field-name mismatches (``SoftDollarTier.value`` → domain
  ``val``) round-trip to the domain spelling.
"""

from __future__ import annotations

from ib_async._pb import (
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
    NextValidId_pb2,
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
    UserInfo_pb2,
    UserInfoRequest_pb2,
)
from ib_async._proto.rest import (
    createCalculateImpliedVolatilityRequestProto,
    createCalculateOptionPriceRequestProto,
    createCancelCalculateImpliedVolatilityProto,
    createCancelCalculateOptionPriceProto,
    createConfigRequestProto,
    createCurrentTimeInMillisMillis,
    createCurrentTimeInMillisRequestProto,
    createCurrentTimeRequestProto,
    createCurrentTimeSeconds,
    createExerciseOptionsRequestProto,
    createMarketRuleArgs,
    createMarketRuleRequestProto,
    createMatchingSymbolsRequestProto,
    createNextValidIdOrderId,
    createPriceIncrement,
    createSecDefOptParameterArgs,
    createSecDefOptParameterEndReqId,
    createSecDefOptParamsRequestProto,
    createSetServerLogLevelRequestProto,
    createSmartComponent,
    createSmartComponentsArgs,
    createSmartComponentsRequestProto,
    createSoftDollarTier,
    createSoftDollarTiersArgs,
    createSoftDollarTiersRequestProto,
    createStartApiRequestProto,
    createSymbolSamplesArgs,
    createUpdateConfigRequestProto,
    createUserInfoArgs,
    createUserInfoRequestProto,
)
from ib_async.contract import Contract

# ---------------------------------------------------------------------------
# NextValidId (single-int)
# ---------------------------------------------------------------------------


def test_next_valid_id_empty_proto_returns_zero():
    assert createNextValidIdOrderId(NextValidId_pb2.NextValidId()) == 0


def test_next_valid_id_round_trip():
    proto = NextValidId_pb2.NextValidId(orderId=42)
    assert createNextValidIdOrderId(proto) == 42


# ---------------------------------------------------------------------------
# CurrentTime (msgId 49) + request envelope
# ---------------------------------------------------------------------------


def test_current_time_empty_proto_returns_zero():
    assert createCurrentTimeSeconds(CurrentTime_pb2.CurrentTime()) == 0


def test_current_time_round_trips_int64_full_range():
    # Value beyond 2**31 — must come back unchanged through the int64 wire.
    big = 2**40 + 7
    proto = CurrentTime_pb2.CurrentTime()
    proto.currentTime = big
    raw = proto.SerializeToString()
    parsed = CurrentTime_pb2.CurrentTime()
    parsed.ParseFromString(raw)
    assert createCurrentTimeSeconds(parsed) == big


def test_current_time_request_proto_serializes_empty_body():
    raw = createCurrentTimeRequestProto().SerializeToString()
    # Empty body — single byte buffer at most (proto3 field tag + length zero
    # produce zero-length frames).
    parsed = CurrentTimeRequest_pb2.CurrentTimeRequest()
    parsed.ParseFromString(raw)
    assert raw == b""


# ---------------------------------------------------------------------------
# CurrentTimeInMillis (NEW capability) + request envelope
# ---------------------------------------------------------------------------


def test_current_time_in_millis_empty_proto_returns_zero():
    assert (
        createCurrentTimeInMillisMillis(CurrentTimeInMillis_pb2.CurrentTimeInMillis())
        == 0
    )


def test_current_time_in_millis_round_trips_int64_full_range():
    # Realistic millisecond-precision Unix timestamp — well beyond 2**31.
    big = 1_700_000_000_000
    proto = CurrentTimeInMillis_pb2.CurrentTimeInMillis()
    proto.currentTimeInMillis = big
    raw = proto.SerializeToString()
    parsed = CurrentTimeInMillis_pb2.CurrentTimeInMillis()
    parsed.ParseFromString(raw)
    assert createCurrentTimeInMillisMillis(parsed) == big


def test_current_time_in_millis_request_proto_serializes_empty_body():
    raw = createCurrentTimeInMillisRequestProto().SerializeToString()
    parsed = CurrentTimeInMillisRequest_pb2.CurrentTimeInMillisRequest()
    parsed.ParseFromString(raw)
    assert raw == b""


# ---------------------------------------------------------------------------
# UserInfo
# ---------------------------------------------------------------------------


def test_user_info_empty_proto_returns_safe_defaults():
    args = createUserInfoArgs(UserInfo_pb2.UserInfo())
    assert args.reqId == 0
    assert args.whiteBrandingId == ""


def test_user_info_round_trip():
    proto = UserInfo_pb2.UserInfo(reqId=7, whiteBrandingId="brand-X")
    args = createUserInfoArgs(proto)
    assert args.reqId == 7
    assert args.whiteBrandingId == "brand-X"


def test_user_info_request_proto_round_trip():
    raw = createUserInfoRequestProto(reqId=11).SerializeToString()
    parsed = UserInfoRequest_pb2.UserInfoRequest()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 11


# ---------------------------------------------------------------------------
# SoftDollarTier / SoftDollarTiers
# ---------------------------------------------------------------------------


def test_soft_dollar_tier_empty_proto_returns_safe_defaults():
    tier = createSoftDollarTier(SoftDollarTier_pb2.SoftDollarTier())
    assert tier.name == ""
    assert tier.val == ""
    assert tier.displayName == ""


def test_soft_dollar_tier_value_field_maps_to_val_domain_field():
    proto = SoftDollarTier_pb2.SoftDollarTier(
        name="tier-a", value="discount-1", displayName="Tier A"
    )
    tier = createSoftDollarTier(proto)
    assert tier.name == "tier-a"
    assert tier.val == "discount-1"
    assert tier.displayName == "Tier A"


def test_soft_dollar_tiers_empty_repeated_returns_empty_list():
    args = createSoftDollarTiersArgs(SoftDollarTiers_pb2.SoftDollarTiers())
    assert args.reqId == 0
    assert args.tiers == []


def test_soft_dollar_tiers_multiple_entries_round_trip():
    proto = SoftDollarTiers_pb2.SoftDollarTiers(reqId=3)
    proto.softDollarTiers.add(name="a", value="va", displayName="A")
    proto.softDollarTiers.add(name="b", value="vb", displayName="B")
    args = createSoftDollarTiersArgs(proto)
    assert args.reqId == 3
    assert len(args.tiers) == 2
    assert args.tiers[0].name == "a"
    assert args.tiers[0].val == "va"
    assert args.tiers[1].name == "b"
    assert args.tiers[1].val == "vb"


def test_soft_dollar_tiers_request_proto_round_trip():
    raw = createSoftDollarTiersRequestProto(reqId=5).SerializeToString()
    parsed = SoftDollarTiersRequest_pb2.SoftDollarTiersRequest()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 5


# ---------------------------------------------------------------------------
# SmartComponent / SmartComponents
# ---------------------------------------------------------------------------


def test_smart_component_empty_proto_returns_safe_defaults():
    comp = createSmartComponent(SmartComponent_pb2.SmartComponent())
    assert comp.bitNumber == 0
    assert comp.exchange == ""
    assert comp.exchangeLetter == ""


def test_smart_components_empty_repeated_returns_empty_list():
    args = createSmartComponentsArgs(SmartComponents_pb2.SmartComponents())
    assert args.reqId == 0
    assert args.components == []


def test_smart_components_multiple_entries_round_trip():
    proto = SmartComponents_pb2.SmartComponents(reqId=2)
    proto.smartComponents.add(bitNumber=1, exchange="NYSE", exchangeLetter="N")
    proto.smartComponents.add(bitNumber=2, exchange="NASDAQ", exchangeLetter="Q")
    args = createSmartComponentsArgs(proto)
    assert args.reqId == 2
    assert len(args.components) == 2
    assert args.components[0].bitNumber == 1
    assert args.components[0].exchange == "NYSE"
    assert args.components[1].exchangeLetter == "Q"


def test_smart_components_request_proto_round_trip():
    raw = createSmartComponentsRequestProto(
        reqId=9, bboExchange="ARCA"
    ).SerializeToString()
    parsed = SmartComponentsRequest_pb2.SmartComponentsRequest()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 9
    assert parsed.bboExchange == "ARCA"


# ---------------------------------------------------------------------------
# PriceIncrement / MarketRule
# ---------------------------------------------------------------------------


def test_price_increment_empty_proto_returns_safe_defaults():
    inc = createPriceIncrement(PriceIncrement_pb2.PriceIncrement())
    assert inc.lowEdge == 0.0
    assert inc.increment == 0.0


def test_market_rule_empty_repeated_returns_empty_list():
    args = createMarketRuleArgs(MarketRule_pb2.MarketRule())
    assert args.marketRuleId == 0
    assert args.priceIncrements == []


def test_market_rule_multiple_entries_round_trip():
    proto = MarketRule_pb2.MarketRule(marketRuleId=99)
    proto.priceIncrements.add(lowEdge=0.0, increment=0.01)
    proto.priceIncrements.add(lowEdge=1.0, increment=0.05)
    args = createMarketRuleArgs(proto)
    assert args.marketRuleId == 99
    assert len(args.priceIncrements) == 2
    assert args.priceIncrements[0].lowEdge == 0.0
    assert args.priceIncrements[0].increment == 0.01
    assert args.priceIncrements[1].lowEdge == 1.0
    assert args.priceIncrements[1].increment == 0.05


def test_market_rule_request_proto_round_trip():
    raw = createMarketRuleRequestProto(marketRuleId=42).SerializeToString()
    parsed = MarketRuleRequest_pb2.MarketRuleRequest()
    parsed.ParseFromString(raw)
    assert parsed.marketRuleId == 42


# ---------------------------------------------------------------------------
# SecDefOptParameter / SecDefOptParameterEnd / SecDefOptParamsRequest
# ---------------------------------------------------------------------------


def test_sec_def_opt_parameter_empty_proto_returns_safe_defaults():
    args = createSecDefOptParameterArgs(SecDefOptParameter_pb2.SecDefOptParameter())
    assert args.reqId == 0
    assert args.exchange == ""
    assert args.underlyingConId == 0
    assert args.tradingClass == ""
    assert args.multiplier == ""
    assert args.expirations == []
    assert args.strikes == []


def test_sec_def_opt_parameter_repeated_slots_round_trip():
    proto = SecDefOptParameter_pb2.SecDefOptParameter(
        reqId=4,
        exchange="SMART",
        underlyingConId=12345,
        tradingClass="AAPL",
        multiplier="100",
        expirations=["20260117", "20260221", "20260320"],
        strikes=[140.0, 150.0, 160.0, 170.0],
    )
    raw = proto.SerializeToString()
    parsed = SecDefOptParameter_pb2.SecDefOptParameter()
    parsed.ParseFromString(raw)
    args = createSecDefOptParameterArgs(parsed)
    assert args.reqId == 4
    assert args.exchange == "SMART"
    assert args.underlyingConId == 12345
    assert args.tradingClass == "AAPL"
    assert args.multiplier == "100"
    assert args.expirations == ["20260117", "20260221", "20260320"]
    assert args.strikes == [140.0, 150.0, 160.0, 170.0]


def test_sec_def_opt_parameter_end_empty_proto_returns_zero():
    assert (
        createSecDefOptParameterEndReqId(
            SecDefOptParameterEnd_pb2.SecDefOptParameterEnd()
        )
        == 0
    )


def test_sec_def_opt_parameter_end_round_trip():
    proto = SecDefOptParameterEnd_pb2.SecDefOptParameterEnd(reqId=8)
    assert createSecDefOptParameterEndReqId(proto) == 8


def test_sec_def_opt_params_request_proto_round_trip():
    raw = createSecDefOptParamsRequestProto(
        reqId=1,
        underlyingSymbol="AAPL",
        futFopExchange="",
        underlyingSecType="STK",
        underlyingConId=265598,
    ).SerializeToString()
    parsed = SecDefOptParamsRequest_pb2.SecDefOptParamsRequest()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 1
    assert parsed.underlyingSymbol == "AAPL"
    assert parsed.underlyingSecType == "STK"
    assert parsed.underlyingConId == 265598


# ---------------------------------------------------------------------------
# SymbolSamples / MatchingSymbolsRequest
# ---------------------------------------------------------------------------


def test_symbol_samples_empty_repeated_returns_empty_list():
    args = createSymbolSamplesArgs(SymbolSamples_pb2.SymbolSamples())
    assert args.reqId == 0
    assert args.contractDescriptions == []


def test_symbol_samples_multiple_entries_round_trip():
    proto = SymbolSamples_pb2.SymbolSamples(reqId=12)
    desc1 = proto.contractDescriptions.add()
    desc1.contract.symbol = "AAPL"
    desc1.derivativeSecTypes.append("OPT")
    desc1.derivativeSecTypes.append("WAR")
    desc2 = proto.contractDescriptions.add()
    desc2.contract.symbol = "MSFT"
    args = createSymbolSamplesArgs(proto)
    assert args.reqId == 12
    assert len(args.contractDescriptions) == 2
    assert args.contractDescriptions[0].contract is not None
    assert args.contractDescriptions[0].contract.symbol == "AAPL"
    assert args.contractDescriptions[0].derivativeSecTypes == ["OPT", "WAR"]
    assert args.contractDescriptions[1].contract is not None
    assert args.contractDescriptions[1].contract.symbol == "MSFT"


def test_matching_symbols_request_proto_round_trip():
    raw = createMatchingSymbolsRequestProto(reqId=20, pattern="APP").SerializeToString()
    parsed = MatchingSymbolsRequest_pb2.MatchingSymbolsRequest()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 20
    assert parsed.pattern == "APP"


# ---------------------------------------------------------------------------
# StartApi / SetServerLogLevel
# ---------------------------------------------------------------------------


def test_start_api_request_proto_round_trip():
    raw = createStartApiRequestProto(
        clientId=123, optionalCapabilities="cap-A"
    ).SerializeToString()
    parsed = StartApiRequest_pb2.StartApiRequest()
    parsed.ParseFromString(raw)
    assert parsed.clientId == 123
    assert parsed.optionalCapabilities == "cap-A"


def test_set_server_log_level_request_proto_round_trip():
    raw = createSetServerLogLevelRequestProto(logLevel=4).SerializeToString()
    parsed = SetServerLogLevelRequest_pb2.SetServerLogLevelRequest()
    parsed.ParseFromString(raw)
    assert parsed.logLevel == 4


# ---------------------------------------------------------------------------
# ExerciseOptionsRequest — bool-flag round-trip + optional-trailing-fields
# ---------------------------------------------------------------------------


def test_exercise_options_request_minimal_no_optional_trailing_fields():
    contract = Contract(symbol="AAPL", secType="OPT", exchange="SMART")
    proto = createExerciseOptionsRequestProto(
        orderId=1,
        contract=contract,
        exerciseAction=1,
        exerciseQuantity=10,
        account="DU123",
        override=False,
    )
    raw = proto.SerializeToString()
    parsed = ExerciseOptionsRequest_pb2.ExerciseOptionsRequest()
    parsed.ParseFromString(raw)
    assert parsed.orderId == 1
    assert parsed.contract.symbol == "AAPL"
    assert parsed.exerciseAction == 1
    assert parsed.exerciseQuantity == 10
    assert parsed.account == "DU123"
    # override=False is the proto3 default, so HasField should report unset
    # for the False-explicit case — we still write it but the wire form is
    # equivalent. The trailing optional fields stay unset because we passed
    # None.
    assert not parsed.HasField("manualOrderTime")
    assert not parsed.HasField("customerAccount")
    # professionalCustomer is a plain bool (not optional in proto3), but we
    # never assigned it, so it reads as False.
    assert parsed.professionalCustomer is False


def test_exercise_options_request_override_true_round_trip():
    # The bug we'd catch: a missing assignment + proto3 default would
    # silently swallow override=True from the caller.
    contract = Contract(symbol="SPY", secType="OPT", exchange="SMART")
    proto = createExerciseOptionsRequestProto(
        orderId=2,
        contract=contract,
        exerciseAction=2,
        exerciseQuantity=5,
        account="DU456",
        override=True,
    )
    raw = proto.SerializeToString()
    parsed = ExerciseOptionsRequest_pb2.ExerciseOptionsRequest()
    parsed.ParseFromString(raw)
    assert parsed.override is True


def test_exercise_options_request_professional_customer_true_round_trip():
    # Same risk for professionalCustomer — bool-True must survive
    # proto3 default-skipping.
    contract = Contract(symbol="QQQ", secType="OPT", exchange="SMART")
    proto = createExerciseOptionsRequestProto(
        orderId=3,
        contract=contract,
        exerciseAction=1,
        exerciseQuantity=1,
        account="DU789",
        override=True,
        manualOrderTime="20261015 14:30:00",
        customerAccount="CUST-1",
        professionalCustomer=True,
    )
    raw = proto.SerializeToString()
    parsed = ExerciseOptionsRequest_pb2.ExerciseOptionsRequest()
    parsed.ParseFromString(raw)
    assert parsed.override is True
    assert parsed.professionalCustomer is True
    assert parsed.manualOrderTime == "20261015 14:30:00"
    assert parsed.customerAccount == "CUST-1"


# ---------------------------------------------------------------------------
# CalculateImpliedVolatility / CalculateOptionPrice + cancels
# ---------------------------------------------------------------------------


def test_calculate_implied_volatility_request_round_trip():
    contract = Contract(symbol="AAPL", secType="OPT", exchange="SMART")
    raw = createCalculateImpliedVolatilityRequestProto(
        reqId=10, contract=contract, optionPrice=1.25, underPrice=200.0
    ).SerializeToString()
    parsed = CalculateImpliedVolatilityRequest_pb2.CalculateImpliedVolatilityRequest()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 10
    assert parsed.contract.symbol == "AAPL"
    assert parsed.optionPrice == 1.25
    assert parsed.underPrice == 200.0
    # Options map is sent empty (binary path doesn't carry it either).
    assert len(parsed.impliedVolatilityOptions) == 0


def test_calculate_option_price_request_round_trip():
    contract = Contract(symbol="SPY", secType="OPT", exchange="SMART")
    raw = createCalculateOptionPriceRequestProto(
        reqId=11, contract=contract, volatility=0.30, underPrice=420.0
    ).SerializeToString()
    parsed = CalculateOptionPriceRequest_pb2.CalculateOptionPriceRequest()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 11
    assert parsed.contract.symbol == "SPY"
    assert parsed.volatility == 0.30
    assert parsed.underPrice == 420.0
    assert len(parsed.optionPriceOptions) == 0


def test_cancel_calculate_implied_volatility_round_trip():
    raw = createCancelCalculateImpliedVolatilityProto(reqId=10).SerializeToString()
    parsed = CancelCalculateImpliedVolatility_pb2.CancelCalculateImpliedVolatility()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 10


def test_cancel_calculate_option_price_round_trip():
    raw = createCancelCalculateOptionPriceProto(reqId=11).SerializeToString()
    parsed = CancelCalculateOptionPrice_pb2.CancelCalculateOptionPrice()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 11


# ---------------------------------------------------------------------------
# ConfigRequest / UpdateConfigRequest — proto-only API config family.
# ---------------------------------------------------------------------------


def test_config_request_proto_round_trip():
    raw = createConfigRequestProto(reqId=42).SerializeToString()
    parsed = ConfigRequest_pb2.ConfigRequest()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 42


def test_update_config_request_proto_minimal_round_trip():
    """Caller passes only ``reqId``; all composite sub-messages remain
    unset — older TWS builds without the corresponding schema fields
    must still parse the body cleanly."""
    raw = createUpdateConfigRequestProto(reqId=7).SerializeToString()
    parsed = UpdateConfigRequest_pb2.UpdateConfigRequest()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 7
    assert not parsed.HasField("lockAndExit")
    assert not parsed.HasField("api")
    assert not parsed.HasField("orders")
    assert len(parsed.messages) == 0
    assert len(parsed.acceptedWarnings) == 0
    assert not parsed.HasField("resetAPIOrderSequence")


def test_update_config_request_proto_full_round_trip():
    """Caller fills every composite sub-message; round-trip must
    preserve nested fields and the ``resetAPIOrderSequence`` opt-in
    bool (proto3 default-skipping would otherwise drop ``False``)."""
    lock = LockAndExitConfig_pb2.LockAndExitConfig()
    api = ApiConfig_pb2.ApiConfig()
    proto = createUpdateConfigRequestProto(
        reqId=99,
        lockAndExit=lock,
        api=api,
        resetAPIOrderSequence=True,
    )
    raw = proto.SerializeToString()
    parsed = UpdateConfigRequest_pb2.UpdateConfigRequest()
    parsed.ParseFromString(raw)
    assert parsed.reqId == 99
    assert parsed.HasField("lockAndExit")
    assert parsed.HasField("api")
    assert parsed.HasField("resetAPIOrderSequence")
    assert parsed.resetAPIOrderSequence is True
