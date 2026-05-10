"""End-to-end dispatch + gating tests for Phase 5 REST messages.

Covers nextValidId / currentTime / currentTimeInMillis (NEW v3.0
capability) / userInfo / secDefOptParameter(End) / softDollarTiers /
symbolSamples / smartComponents / marketRule / familyCodes / receiveFA
/ replaceFAEnd on the receive side, plus the per-msgId gating for all
Phase 5 send methods.

The new public method ``IB.reqCurrentTimeInMillisAsync`` is exercised
end-to-end: open the singleton waiter, fire the proto receive handler,
verify the future settles with the millisecond timestamp.
"""

from __future__ import annotations

import struct

import ib_async as ibi
from ib_async._pb import (
    CalculateImpliedVolatilityRequest_pb2,
    CalculateOptionPriceRequest_pb2,
    CancelCalculateImpliedVolatility_pb2,
    CancelCalculateOptionPrice_pb2,
    CurrentTime_pb2,
    CurrentTimeInMillis_pb2,
    CurrentTimeInMillisRequest_pb2,
    CurrentTimeRequest_pb2,
    ExerciseOptionsRequest_pb2,
    FamilyCodes_pb2,
    FAReplace_pb2,
    FARequest_pb2,
    MarketRule_pb2,
    MarketRuleRequest_pb2,
    MatchingSymbolsRequest_pb2,
    NextValidId_pb2,
    ReceiveFA_pb2,
    ReplaceFAEnd_pb2,
    SecDefOptParameter_pb2,
    SecDefOptParameterEnd_pb2,
    SecDefOptParamsRequest_pb2,
    SetServerLogLevelRequest_pb2,
    SmartComponents_pb2,
    SmartComponentsRequest_pb2,
    SoftDollarTiers_pb2,
    SoftDollarTiersRequest_pb2,
    StartApiRequest_pb2,
    SymbolSamples_pb2,
    UserInfo_pb2,
    UserInfoRequest_pb2,
)
from ib_async._pb_msgids import (
    CANCEL_CALC_IMPLIED_VOLAT,
    CANCEL_CALC_OPTION_PRICE,
    EXERCISE_OPTIONS,
    PROTOBUF_MSG_ID,
    REPLACE_FA,
    REQ_CALC_IMPLIED_VOLAT,
    REQ_CALC_OPTION_PRICE,
    REQ_CURRENT_TIME,
    REQ_CURRENT_TIME_IN_MILLIS,
    REQ_FA,
    REQ_FAMILY_CODES,
    REQ_MARKET_RULE,
    REQ_MATCHING_SYMBOLS,
    REQ_SEC_DEF_OPT_PARAMS,
    REQ_SMART_COMPONENTS,
    REQ_SOFT_DOLLAR_TIERS,
    REQ_USER_INFO,
    SET_SERVER_LOGLEVEL,
    START_API,
)
from ib_async._requests import CompositeKey, ReqIdKey, SingletonKey


def _ibAtVersion(version: int):
    ib = ibi.IB()
    ib.client._serverVersion = version
    ib.client.connState = ib.client.CONNECTED
    return ib


def _captureSend(ib):
    sent: list[bytes] = []
    ib.client.conn.sendMsg = sent.append  # type: ignore[method-assign]
    return sent


def _decodeProtoFrame(framed: bytes) -> tuple[int, bytes]:
    body_len = struct.unpack(">I", framed[:4])[0]
    body = framed[4 : 4 + body_len]
    wireMsgId = struct.unpack(">I", body[:4])[0]
    return wireMsgId - PROTOBUF_MSG_ID, body[4:]


# ===========================================================================
# RECEIVE SIDE
# ===========================================================================


def test_next_valid_id_proto_does_not_raise():
    """``Wrapper.nextValidId`` is a stub on this client (the framework
    snoops on the binary equivalent during connect). Smoke-test only."""
    ib = ibi.IB()
    proto = NextValidId_pb2.NextValidId(orderId=42)
    ib.client.decoder.processProtoBuf(9, proto.SerializeToString())


def test_current_time_proto_settles_singleton():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(SingletonKey("currentTime"), container=[])
    proto = CurrentTime_pb2.CurrentTime(currentTime=1700000000)
    ib.client.decoder.processProtoBuf(49, proto.SerializeToString())
    assert req.future.done()


def test_current_time_in_millis_proto_settles_singleton_with_millis():
    """v3.0 NEW capability — settles the millis-precision singleton."""
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(SingletonKey("currentTimeInMillis"), container=[])
    proto = CurrentTimeInMillis_pb2.CurrentTimeInMillis(
        currentTimeInMillis=1700000000123
    )
    ib.client.decoder.processProtoBuf(109, proto.SerializeToString())
    assert req.future.done()
    assert req.future.result() == 1700000000123


def test_user_info_proto_settles_reqId():
    """``Wrapper.userInfo`` settles the reqId without surfacing the
    ``whiteBrandingId`` payload (mirrors binary path behaviour). The
    waiter sees the future done but no value bound."""
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = UserInfo_pb2.UserInfo(reqId=7, whiteBrandingId="ibapi")
    ib.client.decoder.processProtoBuf(107, proto.SerializeToString())
    assert req.future.done()


def test_sec_def_opt_parameter_proto_appends_to_reqId_list():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = SecDefOptParameter_pb2.SecDefOptParameter(
        reqId=7,
        exchange="SMART",
        underlyingConId=12345,
        tradingClass="AAPL",
        multiplier="100",
    )
    proto.expirations.extend(["20260119", "20260216"])
    proto.strikes.extend([150.0, 160.0, 170.0])
    ib.client.decoder.processProtoBuf(75, proto.SerializeToString())
    proto2 = SecDefOptParameterEnd_pb2.SecDefOptParameterEnd(reqId=7)
    ib.client.decoder.processProtoBuf(76, proto2.SerializeToString())
    assert req.future.done()
    items = req.future.result()
    assert len(items) == 1
    chain = items[0]
    assert chain.exchange == "SMART"
    assert chain.expirations == ["20260119", "20260216"]


def test_soft_dollar_tiers_proto_does_not_raise():
    """``Wrapper.softDollarTiers`` is currently a no-op stub on this
    client (no consumer wired); smoke-test only."""
    ib = ibi.IB()
    proto = SoftDollarTiers_pb2.SoftDollarTiers(reqId=7)
    t = proto.softDollarTiers.add()
    t.name, t.value, t.displayName = "TIER_A", "value-a", "Tier A"
    ib.client.decoder.processProtoBuf(77, proto.SerializeToString())


def test_symbol_samples_proto_settles_reqId():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = SymbolSamples_pb2.SymbolSamples(reqId=7)
    cd = proto.contractDescriptions.add()
    cd.contract.symbol = "AAPL"
    cd.contract.secType = "STK"
    cd.derivativeSecTypes.extend(["OPT", "WAR"])
    ib.client.decoder.processProtoBuf(79, proto.SerializeToString())
    assert req.future.done()
    descs = req.future.result()
    assert len(descs) == 1
    assert descs[0].contract.symbol == "AAPL"


def test_smart_components_proto_settles_reqId():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(ReqIdKey(7), container=[])
    proto = SmartComponents_pb2.SmartComponents(reqId=7)
    c = proto.smartComponents.add()
    c.bitNumber, c.exchange, c.exchangeLetter = 1, "ARCA", "P"
    ib.client.decoder.processProtoBuf(82, proto.SerializeToString())
    assert req.future.done()


def test_market_rule_proto_settles_composite_key():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(CompositeKey("marketRule", (5,)), container=[])
    proto = MarketRule_pb2.MarketRule(marketRuleId=5)
    pi = proto.priceIncrements.add()
    pi.lowEdge, pi.increment = 0.0, 0.01
    ib.client.decoder.processProtoBuf(93, proto.SerializeToString())
    assert req.future.done()
    assert req.future.result()[0].increment == 0.01


def test_family_codes_proto_does_not_raise():
    """``Wrapper.familyCodes`` is currently a no-op stub on this
    client; smoke-test only."""
    ib = ibi.IB()
    proto = FamilyCodes_pb2.FamilyCodes()
    f = proto.familyCodes.add()
    f.accountId, f.familyCode = "DU1", "ABC123"
    ib.client.decoder.processProtoBuf(78, proto.SerializeToString())


def test_receive_fa_proto_settles_singleton():
    ib = ibi.IB()
    req, _ = ib.wrapper.requests.open(SingletonKey("requestFA"), container=[])
    proto = ReceiveFA_pb2.ReceiveFA(faDataType=2, xml="<fa/>")
    ib.client.decoder.processProtoBuf(16, proto.SerializeToString())
    assert req.future.done()
    assert req.future.result() == "<fa/>"


def test_replace_fa_end_proto_does_not_raise():
    """No client-side waiter for replace-FA-end; smoke-test only."""
    ib = ibi.IB()
    proto = ReplaceFAEnd_pb2.ReplaceFAEnd(reqId=7, text="ok")
    ib.client.decoder.processProtoBuf(103, proto.SerializeToString())


# ===========================================================================
# SEND SIDE
# ===========================================================================


def test_req_current_time_uses_protobuf_at_gate():
    ib = _ibAtVersion(213)
    sent = _captureSend(ib)
    ib.client.reqCurrentTime()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_CURRENT_TIME
    proto = CurrentTimeRequest_pb2.CurrentTimeRequest()
    proto.ParseFromString(body)
    assert body == b""


def test_req_current_time_in_millis_always_protobuf():
    """v3.0 NEW capability — protobuf-only, no binary fallback."""
    ib = _ibAtVersion(213)
    sent = _captureSend(ib)
    ib.client.reqCurrentTimeInMillis()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_CURRENT_TIME_IN_MILLIS
    proto = CurrentTimeInMillisRequest_pb2.CurrentTimeInMillisRequest()
    proto.ParseFromString(body)


def test_req_current_time_in_millis_rejects_pre_213_server():
    """A pre-213 server has no idea what the protobuf +200 sentinel
    means. Better to raise on the caller's stack than ship a malformed
    frame and leave the awaiter wedged forever.
    """
    import pytest

    ib = _ibAtVersion(212)
    sent = _captureSend(ib)
    with pytest.raises(ValueError, match="version >= 213"):
        ib.client.reqCurrentTimeInMillis()
    assert sent == []


def test_req_user_info_uses_protobuf_at_gate():
    ib = _ibAtVersion(212)
    sent = _captureSend(ib)
    ib.client.reqUserInfo(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_USER_INFO
    proto = UserInfoRequest_pb2.UserInfoRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7


def test_set_server_log_level_uses_protobuf_at_gate():
    ib = _ibAtVersion(213)
    sent = _captureSend(ib)
    ib.client.setServerLogLevel(3)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == SET_SERVER_LOGLEVEL
    proto = SetServerLogLevelRequest_pb2.SetServerLogLevelRequest()
    proto.ParseFromString(body)
    assert proto.logLevel == 3


def test_start_api_uses_protobuf_at_gate():
    ib = _ibAtVersion(213)
    sent = _captureSend(ib)
    ib.client.clientId = 7
    ib.client.optCapab = ""
    ib.client.startApi()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == START_API
    proto = StartApiRequest_pb2.StartApiRequest()
    proto.ParseFromString(body)
    assert proto.clientId == 7


def test_request_fa_uses_protobuf_at_gate():
    ib = _ibAtVersion(211)
    sent = _captureSend(ib)
    ib.client.requestFA(2)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_FA
    proto = FARequest_pb2.FARequest()
    proto.ParseFromString(body)
    assert proto.faDataType == 2


def test_replace_fa_uses_protobuf_at_gate():
    ib = _ibAtVersion(211)
    sent = _captureSend(ib)
    ib.client.replaceFA(7, 2, "<xml/>")
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REPLACE_FA
    proto = FAReplace_pb2.FAReplace()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.faDataType == 2
    assert proto.xml == "<xml/>"


def test_exercise_options_uses_protobuf_at_gate():
    ib = _ibAtVersion(211)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    ib.client.exerciseOptions(7, contract, 1, 100, "DU1", 0)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == EXERCISE_OPTIONS
    proto = ExerciseOptionsRequest_pb2.ExerciseOptionsRequest()
    proto.ParseFromString(body)
    assert proto.orderId == 7
    assert proto.exerciseAction == 1
    assert proto.exerciseQuantity == 100
    assert proto.account == "DU1"


def test_calculate_implied_volatility_uses_protobuf_at_gate():
    ib = _ibAtVersion(211)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    ib.client.calculateImpliedVolatility(7, contract, 10.0, 150.0, [])
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_CALC_IMPLIED_VOLAT
    proto = CalculateImpliedVolatilityRequest_pb2.CalculateImpliedVolatilityRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.optionPrice == 10.0
    assert proto.underPrice == 150.0


def test_calculate_option_price_uses_protobuf_at_gate():
    ib = _ibAtVersion(211)
    sent = _captureSend(ib)
    contract = ibi.Stock("AAPL", "SMART", "USD")
    ib.client.calculateOptionPrice(7, contract, 0.25, 150.0, [])
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_CALC_OPTION_PRICE
    proto = CalculateOptionPriceRequest_pb2.CalculateOptionPriceRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.volatility == 0.25


def test_cancel_calculate_implied_vol_uses_protobuf_at_gate():
    ib = _ibAtVersion(211)
    sent = _captureSend(ib)
    ib.client.cancelCalculateImpliedVolatility(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_CALC_IMPLIED_VOLAT
    proto = CancelCalculateImpliedVolatility_pb2.CancelCalculateImpliedVolatility()
    proto.ParseFromString(body)
    assert proto.reqId == 7


def test_cancel_calculate_option_price_uses_protobuf_at_gate():
    ib = _ibAtVersion(211)
    sent = _captureSend(ib)
    ib.client.cancelCalculateOptionPrice(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == CANCEL_CALC_OPTION_PRICE
    proto = CancelCalculateOptionPrice_pb2.CancelCalculateOptionPrice()
    proto.ParseFromString(body)
    assert proto.reqId == 7


def test_req_sec_def_opt_params_uses_protobuf_at_gate():
    ib = _ibAtVersion(212)
    sent = _captureSend(ib)
    ib.client.reqSecDefOptParams(7, "AAPL", "", "STK", 12345)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_SEC_DEF_OPT_PARAMS
    proto = SecDefOptParamsRequest_pb2.SecDefOptParamsRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.underlyingSymbol == "AAPL"
    assert proto.underlyingSecType == "STK"
    assert proto.underlyingConId == 12345


def test_req_soft_dollar_tiers_uses_protobuf_at_gate():
    ib = _ibAtVersion(212)
    sent = _captureSend(ib)
    ib.client.reqSoftDollarTiers(7)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_SOFT_DOLLAR_TIERS
    proto = SoftDollarTiersRequest_pb2.SoftDollarTiersRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7


def test_req_family_codes_uses_protobuf_at_gate():
    ib = _ibAtVersion(212)
    sent = _captureSend(ib)
    ib.client.reqFamilyCodes()
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_FAMILY_CODES
    assert body == b""


def test_req_matching_symbols_uses_protobuf_at_gate():
    ib = _ibAtVersion(212)
    sent = _captureSend(ib)
    ib.client.reqMatchingSymbols(7, "AAPL")
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_MATCHING_SYMBOLS
    proto = MatchingSymbolsRequest_pb2.MatchingSymbolsRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.pattern == "AAPL"


def test_req_smart_components_uses_protobuf_at_gate():
    ib = _ibAtVersion(212)
    sent = _captureSend(ib)
    ib.client.reqSmartComponents(7, "ARCA")
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_SMART_COMPONENTS
    proto = SmartComponentsRequest_pb2.SmartComponentsRequest()
    proto.ParseFromString(body)
    assert proto.reqId == 7
    assert proto.bboExchange == "ARCA"


def test_req_market_rule_uses_protobuf_at_gate():
    ib = _ibAtVersion(212)
    sent = _captureSend(ib)
    ib.client.reqMarketRule(5)
    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == REQ_MARKET_RULE
    proto = MarketRuleRequest_pb2.MarketRuleRequest()
    proto.ParseFromString(body)
    assert proto.marketRuleId == 5


# ===========================================================================
# Below-gate sanity
# ===========================================================================


def test_req_current_time_below_gate_uses_binary():
    ib = _ibAtVersion(212)
    sent = _captureSend(ib)
    ib.client.reqCurrentTime()
    assert sent[0][4:].startswith(b"49\x00")


def test_set_server_log_level_below_gate_uses_binary():
    ib = _ibAtVersion(212)
    sent = _captureSend(ib)
    ib.client.setServerLogLevel(3)
    assert sent[0][4:].startswith(b"14\x00")
