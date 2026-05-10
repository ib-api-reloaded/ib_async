"""Negative-path-first tests for the contracts protobuf converter.

The contributor's PR shipped converters with several CRITICAL bugs:
``createComboLegProto`` read the freshly-empty target proto for
field-presence instead of the source domain object (so every field
copy was unconditional and stomped on the proto with blanks); a
partial ``DeltaNeutralContract`` proto produced an
``UnboundLocalError``; ``Decimal`` coercion of empty strings was
unguarded. These tests guard against those regressions and document
the expected behaviour for partial / malformed input.

The 3.0 release uses ``Decimal`` natively for size, tick, multiplier,
and coupon fields on ``ContractDetails`` — these tests exercise the
Decimal-coerced values rather than the legacy float types.

Happy-path round-trip tests follow at the end.
"""

from __future__ import annotations

from decimal import Decimal

from ib_async._pb import (
    ComboLeg_pb2,
    Contract_pb2,
    ContractData_pb2,
    ContractDescription_pb2,
    ContractDetails_pb2,
    DeltaNeutralContract_pb2,
)
from ib_async._proto.contracts import (
    createComboLeg,
    createComboLegProto,
    createContract,
    createContractDescription,
    createContractDetails,
    createContractDetailsFromContractData,
    createContractProto,
    createDeltaNeutralContract,
)
from ib_async.contract import (
    ComboLeg,
    Contract,
    ContractDetails,
    DeltaNeutralContract,
    IneligibilityReason,
    Stock,
    TagValue,
)

# ---------------------------------------------------------------------------
# DeltaNeutralContract — defended against the contributor's UnboundLocalError
# ---------------------------------------------------------------------------


def test_create_delta_neutral_contract_handles_completely_empty_proto():
    proto = DeltaNeutralContract_pb2.DeltaNeutralContract()
    dnc = createDeltaNeutralContract(proto)
    # Domain-default values, never an exception.
    assert dnc.conId == 0
    assert dnc.delta == 0.0
    assert dnc.price == 0.0


def test_create_delta_neutral_contract_handles_partial_proto():
    # Only ``conId`` set — the contributor's code raised UnboundLocalError
    # on this exact shape.
    proto = DeltaNeutralContract_pb2.DeltaNeutralContract()
    proto.conId = 12345
    dnc = createDeltaNeutralContract(proto)
    assert dnc.conId == 12345
    assert dnc.delta == 0.0
    assert dnc.price == 0.0


# ---------------------------------------------------------------------------
# ComboLeg — guards the source-vs-target swap that silently zeroed fields
# ---------------------------------------------------------------------------


def test_combo_leg_proto_reads_from_source_not_target():
    # The contributor's PR had ``if comboLegProto.exchange is not None:``
    # which is always true for proto3 string defaults, then
    # ``comboLegProto.exchange = comboLeg.exchange`` — the conditional
    # was vacuous AND fields were copied even when the source had a
    # non-default placeholder. This test ensures that an empty source
    # field stays empty on the proto, and a populated source field
    # round-trips.
    leg = ComboLeg(
        conId=42,
        ratio=2,
        action="BUY",
        exchange="SMART",
    )
    proto = createComboLegProto(leg)
    assert proto.conId == 42
    assert proto.ratio == 2
    assert proto.action == "BUY"
    assert proto.exchange == "SMART"
    # Unset source fields stay unset on the proto.
    assert not proto.HasField("openClose")
    assert not proto.HasField("designatedLocation")


def test_combo_leg_proto_skips_default_exempt_code():
    # exemptCode default is -1 in the domain dataclass; round-tripping
    # the default would corrupt servers that interpret -1 differently
    # from "unset".
    leg = ComboLeg()  # exemptCode defaults to -1
    proto = createComboLegProto(leg)
    assert not proto.HasField("exemptCode")


def test_combo_leg_proto_emits_explicit_exempt_code_value():
    leg = ComboLeg(exemptCode=0)
    proto = createComboLegProto(leg)
    assert proto.HasField("exemptCode")
    assert proto.exemptCode == 0


def test_combo_leg_decode_handles_empty_proto():
    proto = ComboLeg_pb2.ComboLeg()
    leg = createComboLeg(proto)
    assert leg.conId == 0
    assert leg.action == ""
    assert leg.exemptCode == -1  # domain default preserved


def test_combo_leg_round_trip_preserves_fields():
    original = ComboLeg(
        conId=99,
        ratio=3,
        action="SELL",
        exchange="ARCA",
        openClose=1,
        shortSaleSlot=2,
        designatedLocation="loc",
        exemptCode=4,
    )
    proto = createComboLegProto(original)
    decoded = createComboLeg(proto)
    assert decoded == original


# ---------------------------------------------------------------------------
# Contract — full domain shape with partial-message defence
# ---------------------------------------------------------------------------


def test_create_contract_handles_completely_empty_proto():
    proto = Contract_pb2.Contract()
    contract = createContract(proto)
    assert contract.conId == 0
    assert contract.symbol == ""
    assert contract.multiplier == ""
    assert contract.comboLegs == []
    assert contract.deltaNeutralContract is None


def test_create_contract_proto_field_name_mapping_primary_exchange():
    # Wire field is "primaryExch"; domain field is "primaryExchange".
    # Both directions must respect the rename or routing breaks.
    contract = Stock("AAPL", "SMART", "USD")
    contract.primaryExchange = "NASDAQ"
    proto = createContractProto(contract)
    assert proto.primaryExch == "NASDAQ"
    decoded = createContract(proto)
    assert decoded.primaryExchange == "NASDAQ"


def test_create_contract_multiplier_round_trip_whole_number():
    # multiplier is wire-double, domain-string. "100" round-trips as
    # "100" not "100.0".
    contract = Contract(symbol="ES", secType="FUT", multiplier="100")
    proto = createContractProto(contract)
    assert proto.multiplier == 100.0
    decoded = createContract(proto)
    assert decoded.multiplier == "100"


def test_create_contract_multiplier_round_trip_fraction():
    contract = Contract(symbol="X", secType="OPT", multiplier="50.5")
    proto = createContractProto(contract)
    assert proto.multiplier == 50.5
    decoded = createContract(proto)
    assert decoded.multiplier == "50.5"


def test_create_contract_with_combo_legs_round_trip():
    contract = Contract(
        symbol="SPX",
        secType="BAG",
        currency="USD",
        comboLegs=[
            ComboLeg(conId=1, ratio=1, action="BUY", exchange="SMART"),
            ComboLeg(conId=2, ratio=1, action="SELL", exchange="SMART"),
        ],
    )
    proto = createContractProto(contract)
    assert len(proto.comboLegs) == 2
    decoded = createContract(proto)
    assert len(decoded.comboLegs) == 2
    assert decoded.comboLegs[0].conId == 1
    assert decoded.comboLegs[1].action == "SELL"


def test_create_contract_with_delta_neutral_round_trip():
    contract = Stock("AAPL", "SMART", "USD")
    contract.deltaNeutralContract = DeltaNeutralContract(
        conId=42, delta=0.5, price=100.0
    )
    proto = createContractProto(contract)
    assert proto.HasField("deltaNeutralContract")
    decoded = createContract(proto)
    assert decoded.deltaNeutralContract is not None
    assert decoded.deltaNeutralContract.conId == 42
    assert decoded.deltaNeutralContract.delta == 0.5
    assert decoded.deltaNeutralContract.price == 100.0


# ---------------------------------------------------------------------------
# ContractDetails — field-name mismatches, type mismatches, partial messages
# ---------------------------------------------------------------------------


def test_create_contract_details_handles_completely_empty_proto():
    proto = ContractDetails_pb2.ContractDetails()
    contract = Contract()
    details = createContractDetails(proto, contract)
    assert isinstance(details, ContractDetails)
    assert details.contract is contract
    assert details.marketName == ""
    # Decimal-typed numeric fields default to ``None`` for "unset" so
    # ``if price:`` correctly evaluates falsy in user code.
    assert details.minTick is None
    assert details.minSize is None
    assert details.sizeIncrement is None
    assert details.suggestedSizeIncrement is None
    assert details.evMultiplier is None
    assert details.coupon is None


def test_create_contract_details_min_tick_string_to_decimal():
    proto = ContractDetails_pb2.ContractDetails()
    proto.minTick = "0.01"
    details = createContractDetails(proto, Contract())
    assert details.minTick == Decimal("0.01")


def test_create_contract_details_min_tick_unparseable_stays_none():
    # If TWS ever sends garbage in a Decimal field, the converter must
    # not crash — the field stays ``None``.
    proto = ContractDetails_pb2.ContractDetails()
    proto.minTick = "not-a-number"
    details = createContractDetails(proto, Contract())
    assert details.minTick is None


def test_create_contract_details_ev_multiplier_preserves_fractional_value():
    # Wire is double, domain is now ``Decimal | None``: 1.5 round-trips
    # as Decimal('1.5') without truncation. The 2.x path coerced to int
    # and lost the fraction; 3.0 keeps it.
    proto = ContractDetails_pb2.ContractDetails()
    proto.evMultiplier = 1.5
    details = createContractDetails(proto, Contract())
    assert details.evMultiplier == Decimal("1.5")


def test_create_contract_details_putable_field_name_mismatch():
    # Wire spells it "puttable"; domain spells it "putable" (one t).
    proto = ContractDetails_pb2.ContractDetails()
    proto.puttable = True
    details = createContractDetails(proto, Contract())
    assert details.putable is True


def test_create_contract_details_size_fields_string_to_decimal():
    proto = ContractDetails_pb2.ContractDetails()
    proto.minSize = "1"
    proto.sizeIncrement = "0.5"
    proto.suggestedSizeIncrement = "1"
    details = createContractDetails(proto, Contract())
    assert details.minSize == Decimal("1")
    assert details.sizeIncrement == Decimal("0.5")
    assert details.suggestedSizeIncrement == Decimal("1")


def test_create_contract_details_size_field_unparseable_stays_none():
    proto = ContractDetails_pb2.ContractDetails()
    proto.minSize = ""
    proto.sizeIncrement = "garbage"
    details = createContractDetails(proto, Contract())
    assert details.minSize is None
    assert details.sizeIncrement is None


def test_create_contract_details_decimal_field_works_with_truthy_check():
    # Live-code regression guard: ``if details.minTick:`` must behave
    # the same as ``if details.minTick is not None and details.minTick``.
    # ``Decimal('NaN')`` would silently break this; ``None`` doesn't.
    empty = createContractDetails(ContractDetails_pb2.ContractDetails(), Contract())
    assert not empty.minTick
    populated = ContractDetails_pb2.ContractDetails()
    populated.minTick = "0.01"
    decoded = createContractDetails(populated, Contract())
    assert decoded.minTick


def test_create_contract_details_bond_fields_unified_with_regular():
    # The proto unifies bond-specific fields into ContractDetails; the
    # binary path handled them via a separate bondContractDetails msg.
    # Both paths must produce equivalent domain objects when bond data
    # arrives. ``coupon`` is now Decimal end-to-end.
    proto = ContractDetails_pb2.ContractDetails()
    proto.cusip = "037833100"
    proto.ratings = "Aaa"
    proto.bondType = "CORP"
    proto.couponType = "FIXED"
    proto.coupon = 4.5
    proto.callable = True
    proto.puttable = False
    proto.convertible = False
    proto.bondNotes = "Senior secured"
    details = createContractDetails(proto, Contract())
    assert details.cusip == "037833100"
    assert details.ratings == "Aaa"
    assert details.bondType == "CORP"
    assert details.coupon == Decimal("4.5")
    assert details.callable is True
    assert details.notes == "Senior secured"


def test_create_contract_details_from_contract_data_decodes_both_halves():
    proto = ContractData_pb2.ContractData()
    proto.contract.symbol = "AAPL"
    proto.contract.secType = "STK"
    proto.contractDetails.marketName = "NMS"
    details = createContractDetailsFromContractData(proto)
    assert details.contract is not None
    assert details.contract.symbol == "AAPL"
    assert details.marketName == "NMS"


def test_create_contract_details_populates_fund_family_fields():
    # Fund-family wire fields populate the matching domain fields. The
    # one rename is wire ``fundMinimumSubsequentPurchase`` ->
    # domain ``fundSubsequentMinimumPurchase``.
    proto = ContractDetails_pb2.ContractDetails()
    proto.fundName = "Vanguard Total Stock"
    proto.fundFamily = "Vanguard"
    proto.fundType = "Open-End"
    proto.fundFrontLoad = "0"
    proto.fundBackLoad = "0"
    proto.fundBackLoadTimeInterval = "0"
    proto.fundManagementFee = "0.04"
    proto.fundClosed = True
    proto.fundClosedForNewInvestors = False
    proto.fundClosedForNewMoney = True
    proto.fundNotifyAmount = "1000"
    proto.fundMinimumInitialPurchase = "3000"
    proto.fundMinimumSubsequentPurchase = "100"
    proto.fundBlueSkyStates = "CA,NY"
    proto.fundBlueSkyTerritories = "PR"
    proto.fundDistributionPolicyIndicator = "N"
    proto.fundAssetType = "004"
    proto.eventContract1 = "EC1"
    proto.eventContractDescription1 = "First desc"
    proto.eventContractDescription2 = "Second desc"
    proto.minAlgoSize = "5"
    proto.lastPricePrecision = "0.01"
    proto.lastSizePrecision = "0.001"
    details = createContractDetails(proto, Contract())
    assert details.fundName == "Vanguard Total Stock"
    assert details.fundFamily == "Vanguard"
    assert details.fundType == "Open-End"
    assert details.fundFrontLoad == "0"
    assert details.fundBackLoad == "0"
    assert details.fundBackLoadTimeInterval == "0"
    assert details.fundManagementFee == "0.04"
    assert details.fundClosed is True
    assert details.fundClosedForNewInvestors is False
    assert details.fundClosedForNewMoney is True
    assert details.fundNotifyAmount == "1000"
    assert details.fundMinimumInitialPurchase == "3000"
    assert details.fundSubsequentMinimumPurchase == "100"
    assert details.fundBlueSkyStates == "CA,NY"
    assert details.fundBlueSkyTerritories == "PR"
    assert details.fundDistributionPolicyIndicator == "N"
    assert details.fundAssetType == "004"
    assert details.eventContract1 == "EC1"
    assert details.eventContractDescription1 == "First desc"
    assert details.eventContractDescription2 == "Second desc"
    assert details.minAlgoSize == Decimal("5")
    assert details.lastPricePrecision == Decimal("0.01")
    assert details.lastSizePrecision == Decimal("0.001")


def test_create_contract_details_populates_sec_id_and_ineligibility_lists():
    # Wire ``secIdList`` is a string-keyed map; the domain field is a
    # list of ``TagValue``. Two entries -> two TagValues.
    # ``ineligibilityReasonList`` is a repeated message of (id, description).
    proto = ContractDetails_pb2.ContractDetails()
    proto.secIdList["ISIN"] = "US0378331005"
    proto.secIdList["CUSIP"] = "037833100"
    reason = proto.ineligibilityReasonList.add()
    reason.id = "REASON_1"
    reason.description = "Not eligible for trading"
    details = createContractDetails(proto, Contract())
    assert len(details.secIdList) == 2
    by_tag = {tv.tag: tv.value for tv in details.secIdList}
    assert by_tag == {"ISIN": "US0378331005", "CUSIP": "037833100"}
    assert all(isinstance(tv, TagValue) for tv in details.secIdList)
    assert len(details.ineligibilityReasonList) == 1
    assert isinstance(details.ineligibilityReasonList[0], IneligibilityReason)
    assert details.ineligibilityReasonList[0].id_ == "REASON_1"
    assert details.ineligibilityReasonList[0].description == "Not eligible for trading"


def test_create_contract_details_from_contract_data_handles_missing_inner():
    # If the wrapper has only the inner contract but no details payload,
    # we still produce a valid (empty-default) ContractDetails.
    proto = ContractData_pb2.ContractData()
    proto.contract.symbol = "AAPL"
    details = createContractDetailsFromContractData(proto)
    assert details.contract is not None
    assert details.contract.symbol == "AAPL"
    assert details.marketName == ""


# ---------------------------------------------------------------------------
# ContractDescription
# ---------------------------------------------------------------------------


def test_create_contract_description_round_trip():
    proto = ContractDescription_pb2.ContractDescription()
    proto.contract.symbol = "AAPL"
    proto.contract.secType = "STK"
    proto.derivativeSecTypes.extend(["OPT", "WAR"])
    desc = createContractDescription(proto)
    assert desc.contract is not None
    assert desc.contract.symbol == "AAPL"
    assert desc.derivativeSecTypes == ["OPT", "WAR"]


def test_create_contract_description_handles_missing_inner_contract():
    proto = ContractDescription_pb2.ContractDescription()
    proto.derivativeSecTypes.append("STK")
    desc = createContractDescription(proto)
    assert desc.contract is not None  # default-constructed
    assert desc.contract.symbol == ""
    assert desc.derivativeSecTypes == ["STK"]
