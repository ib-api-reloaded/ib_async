"""Protobuf converters for accounts, positions, portfolios, and FA.

Pure functions: every converter takes only proto inputs (or domain
inputs on the send side). No reads from module-level state, no
dependencies on ``Wrapper``. Decimal fields use ``safe_decimal`` so
malformed wire values land as ``None`` (the unset sentinel for
``Decimal | None`` domain fields) instead of raising into the
decoder's exception path.

Wire-shape notes:

* ``Position.position`` and ``PositionMulti.position`` and
  ``PortfolioValue.position`` are wire ``string`` (full Decimal
  precision); the rest of the portfolio numerics are wire ``double``
  routed through ``str()`` on the way to ``safe_decimal`` to dodge
  binary-float imprecision.
* ``AccountValue`` proto's ``key`` field maps to the domain
  dataclass's ``tag`` field; ``accountName`` maps to ``account``.
  ``AccountSummary`` and ``AccountUpdateMulti`` already use ``tag``
  on the wire.
* Most ``CancelXxx`` and ``XxxRequest`` envelopes are empty or
  carry a single int / string field; the corresponding factories are
  one-liners so the send-side gating in ``Client`` can call a single
  helper instead of constructing the proto inline.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .._pb import (
    AccountDataRequest_pb2,
    AccountSummary_pb2,
    AccountSummaryRequest_pb2,
    AccountUpdateMulti_pb2,
    AccountUpdatesMultiRequest_pb2,
    AccountValue_pb2,
    CancelAccountSummary_pb2,
    CancelAccountUpdatesMulti_pb2,
    CancelPositions_pb2,
    CancelPositionsMulti_pb2,
    FamilyCode_pb2,
    FamilyCodes_pb2,
    FamilyCodesRequest_pb2,
    FAReplace_pb2,
    FARequest_pb2,
    ManagedAccounts_pb2,
    ManagedAccountsRequest_pb2,
    PortfolioValue_pb2,
    Position_pb2,
    PositionMulti_pb2,
    PositionsMultiRequest_pb2,
    PositionsRequest_pb2,
    ReceiveFA_pb2,
    ReplaceFAEnd_pb2,
)
from ..contract import Contract
from ..objects import AccountValue, FamilyCode, PortfolioItem, Position
from .contracts import createContract
from .safe import safe_decimal

# Frozen slotted dataclasses for converter return shapes. Each one names the
# wrapper method whose positional arguments it carries — call sites can either
# read fields by name or splat into ``self.wrapper.X(*dataclasses.astuple(args))``
# when positional dispatch is preferred.


@dataclass(slots=True, frozen=True)
class UpdateAccountValueArgs:
    """Args for ``Wrapper.updateAccountValue(tag, val, currency, account)``."""

    tag: str
    val: str
    currency: str
    account: str


@dataclass(slots=True, frozen=True)
class AccountSummaryArgs:
    """Args for ``Wrapper.accountSummary(reqId, account, tag, value, currency)``."""

    reqId: int
    account: str
    tag: str
    value: str
    currency: str


@dataclass(slots=True, frozen=True)
class AccountUpdateMultiArgs:
    """Args for ``Wrapper.accountUpdateMulti(reqId, account, modelCode, tag, val, currency)``."""

    reqId: int
    account: str
    modelCode: str
    tag: str
    val: str
    currency: str


@dataclass(slots=True, frozen=True)
class PositionArgs:
    """Args for ``Wrapper.position(account, contract, posSize, avgCost)``."""

    account: str
    contract: Contract
    posSize: Decimal | None
    avgCost: Decimal | None


@dataclass(slots=True, frozen=True)
class PositionMultiArgs:
    """Args for ``Wrapper.positionMulti(reqId, account, modelCode, contract, pos, avgCost)``."""

    reqId: int
    account: str
    modelCode: str
    contract: Contract
    pos: Decimal | None
    avgCost: Decimal | None


@dataclass(slots=True, frozen=True)
class UpdatePortfolioArgs:
    """Args for ``Wrapper.updatePortfolio(contract, posSize, marketPrice, marketValue, averageCost, unrealizedPNL, realizedPNL, account)``."""

    contract: Contract
    posSize: Decimal | None
    marketPrice: Decimal | None
    marketValue: Decimal | None
    averageCost: Decimal | None
    unrealizedPNL: Decimal | None
    realizedPNL: Decimal | None
    account: str


@dataclass(slots=True, frozen=True)
class ReceiveFAArgs:
    """Args for ``Wrapper.receiveFA(faDataType, xml)``."""

    faDataType: int
    xml: str


@dataclass(slots=True, frozen=True)
class ReplaceFAEndArgs:
    """Args for ``Wrapper.replaceFAEnd(reqId, text)``."""

    reqId: int
    text: str


# ---------------------------------------------------------------------------
# AccountValue / updateAccountValue (msgId 6 receive)
# ---------------------------------------------------------------------------


def createUpdateAccountValueArgs(
    proto: AccountValue_pb2.AccountValue,
) -> UpdateAccountValueArgs:
    """Decode an ``AccountValue`` proto to the positional args
    ``Wrapper.updateAccountValue(tag, val, currency, account)`` expects.

    Wire ``key`` maps to domain ``tag``; wire ``accountName`` maps to
    domain ``account``. Missing fields fall through as empty strings —
    the binary path produces the same shape via ``self.wrap("updateAccountValue", [str, str, str, str])``.
    """
    tag = proto.key if proto.HasField("key") else ""
    val = proto.value if proto.HasField("value") else ""
    currency = proto.currency if proto.HasField("currency") else ""
    account = proto.accountName if proto.HasField("accountName") else ""
    return UpdateAccountValueArgs(tag=tag, val=val, currency=currency, account=account)


def createAccountValue(proto: AccountValue_pb2.AccountValue) -> AccountValue:
    """Decode an ``AccountValue`` proto directly into the domain dataclass.

    Convenience wrapper around ``createUpdateAccountValueArgs`` for tests
    and any caller that wants the full ``AccountValue`` (modelCode is
    always empty in this proto family — only ``AccountUpdateMulti``
    carries it).
    """
    args = createUpdateAccountValueArgs(proto)
    return AccountValue(args.account, args.tag, args.val, args.currency, "")


# ---------------------------------------------------------------------------
# AccountSummary (msgIds 63, 64) + AccountSummaryRequest, CancelAccountSummary
# ---------------------------------------------------------------------------


def createAccountSummaryArgs(
    proto: AccountSummary_pb2.AccountSummary,
) -> AccountSummaryArgs:
    """``Wrapper.accountSummary(reqId, account, tag, value, currency)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    account = proto.account if proto.HasField("account") else ""
    tag = proto.tag if proto.HasField("tag") else ""
    value = proto.value if proto.HasField("value") else ""
    currency = proto.currency if proto.HasField("currency") else ""
    return AccountSummaryArgs(
        reqId=reqId, account=account, tag=tag, value=value, currency=currency
    )


def createAccountSummaryRequestProto(
    reqId: int, group: str, tags: str
) -> AccountSummaryRequest_pb2.AccountSummaryRequest:
    proto = AccountSummaryRequest_pb2.AccountSummaryRequest()
    proto.reqId = reqId
    proto.group = group
    proto.tags = tags
    return proto


def createCancelAccountSummaryProto(
    reqId: int,
) -> CancelAccountSummary_pb2.CancelAccountSummary:
    proto = CancelAccountSummary_pb2.CancelAccountSummary()
    proto.reqId = reqId
    return proto


# ---------------------------------------------------------------------------
# AccountUpdateMulti (msgIds 73, 74) + request / cancel
# ---------------------------------------------------------------------------


def createAccountUpdateMultiArgs(
    proto: AccountUpdateMulti_pb2.AccountUpdateMulti,
) -> AccountUpdateMultiArgs:
    """``Wrapper.accountUpdateMulti(reqId, account, modelCode, tag, val, currency)`` args.

    Note the wire field is named ``key`` but the domain (and binary
    path) names it ``tag``. We translate.
    """
    reqId = proto.reqId if proto.HasField("reqId") else 0
    account = proto.account if proto.HasField("account") else ""
    modelCode = proto.modelCode if proto.HasField("modelCode") else ""
    tag = proto.key if proto.HasField("key") else ""
    val = proto.value if proto.HasField("value") else ""
    currency = proto.currency if proto.HasField("currency") else ""
    return AccountUpdateMultiArgs(
        reqId=reqId,
        account=account,
        modelCode=modelCode,
        tag=tag,
        val=val,
        currency=currency,
    )


def createAccountUpdatesMultiRequestProto(
    reqId: int, account: str, modelCode: str, ledgerAndNLV: bool
) -> AccountUpdatesMultiRequest_pb2.AccountUpdatesMultiRequest:
    proto = AccountUpdatesMultiRequest_pb2.AccountUpdatesMultiRequest()
    proto.reqId = reqId
    proto.account = account
    proto.modelCode = modelCode
    proto.ledgerAndNLV = ledgerAndNLV
    return proto


def createCancelAccountUpdatesMultiProto(
    reqId: int,
) -> CancelAccountUpdatesMulti_pb2.CancelAccountUpdatesMulti:
    proto = CancelAccountUpdatesMulti_pb2.CancelAccountUpdatesMulti()
    proto.reqId = reqId
    return proto


# ---------------------------------------------------------------------------
# AccountDataRequest — for ``reqAccountUpdates`` send path
# ---------------------------------------------------------------------------


def createAccountDataRequestProto(
    subscribe: bool, acctCode: str
) -> AccountDataRequest_pb2.AccountDataRequest:
    proto = AccountDataRequest_pb2.AccountDataRequest()
    proto.subscribe = subscribe
    proto.acctCode = acctCode
    return proto


# ---------------------------------------------------------------------------
# Position (msgId 61, 62) + PositionsRequest, CancelPositions
# ---------------------------------------------------------------------------


def createPosition(proto: Position_pb2.Position) -> Position:
    """Decode a ``Position`` proto with ``Decimal | None`` numerics.

    Wire field shapes:

    * ``account``  — string
    * ``contract`` — embedded ``Contract`` proto (delegated to ``createContract``)
    * ``position`` — string (Decimal-precision)
    * ``avgCost``  — double (routed through ``str(...)`` to avoid
      binary-float imprecision when coercing back to Decimal)
    """
    account = proto.account if proto.HasField("account") else ""
    contract = (
        createContract(proto.contract) if proto.HasField("contract") else Contract()
    )
    position = safe_decimal(proto.position) if proto.HasField("position") else None
    avgCost = safe_decimal(str(proto.avgCost)) if proto.HasField("avgCost") else None
    return Position(account, contract, position, avgCost)


def createPositionArgs(
    proto: Position_pb2.Position,
) -> PositionArgs:
    """``Wrapper.position(account, contract, posSize, avgCost)`` args."""
    pos = createPosition(proto)
    return PositionArgs(
        account=pos.account,
        contract=pos.contract,
        posSize=pos.position,
        avgCost=pos.avgCost,
    )


def createPositionsRequestProto() -> PositionsRequest_pb2.PositionsRequest:
    return PositionsRequest_pb2.PositionsRequest()


def createCancelPositionsProto() -> CancelPositions_pb2.CancelPositions:
    return CancelPositions_pb2.CancelPositions()


# ---------------------------------------------------------------------------
# PositionMulti (msgIds 71, 72) + request / cancel
# ---------------------------------------------------------------------------


def createPositionMultiArgs(
    proto: PositionMulti_pb2.PositionMulti,
) -> PositionMultiArgs:
    """``Wrapper.positionMulti(reqId, account, modelCode, contract, pos, avgCost)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    account = proto.account if proto.HasField("account") else ""
    modelCode = proto.modelCode if proto.HasField("modelCode") else ""
    contract = (
        createContract(proto.contract) if proto.HasField("contract") else Contract()
    )
    pos = safe_decimal(proto.position) if proto.HasField("position") else None
    avgCost = safe_decimal(str(proto.avgCost)) if proto.HasField("avgCost") else None
    return PositionMultiArgs(
        reqId=reqId,
        account=account,
        modelCode=modelCode,
        contract=contract,
        pos=pos,
        avgCost=avgCost,
    )


def createPositionsMultiRequestProto(
    reqId: int, account: str, modelCode: str
) -> PositionsMultiRequest_pb2.PositionsMultiRequest:
    proto = PositionsMultiRequest_pb2.PositionsMultiRequest()
    proto.reqId = reqId
    proto.account = account
    proto.modelCode = modelCode
    return proto


def createCancelPositionsMultiProto(
    reqId: int,
) -> CancelPositionsMulti_pb2.CancelPositionsMulti:
    proto = CancelPositionsMulti_pb2.CancelPositionsMulti()
    proto.reqId = reqId
    return proto


# ---------------------------------------------------------------------------
# PortfolioValue (msgId 7 receive — updatePortfolio)
# ---------------------------------------------------------------------------


def createPortfolioItem(proto: PortfolioValue_pb2.PortfolioValue) -> PortfolioItem:
    """Decode a ``PortfolioValue`` proto with ``Decimal | None`` numerics.

    Wire shapes: ``position`` is string, the five ``*PNL`` / ``market*``
    / ``averageCost`` fields are doubles (routed through ``str(...)``).
    """
    contract = (
        createContract(proto.contract) if proto.HasField("contract") else Contract()
    )
    position = safe_decimal(proto.position) if proto.HasField("position") else None
    marketPrice = (
        safe_decimal(str(proto.marketPrice)) if proto.HasField("marketPrice") else None
    )
    marketValue = (
        safe_decimal(str(proto.marketValue)) if proto.HasField("marketValue") else None
    )
    averageCost = (
        safe_decimal(str(proto.averageCost)) if proto.HasField("averageCost") else None
    )
    unrealizedPNL = (
        safe_decimal(str(proto.unrealizedPNL))
        if proto.HasField("unrealizedPNL")
        else None
    )
    realizedPNL = (
        safe_decimal(str(proto.realizedPNL)) if proto.HasField("realizedPNL") else None
    )
    account = proto.accountName if proto.HasField("accountName") else ""
    return PortfolioItem(
        contract,
        position,
        marketPrice,
        marketValue,
        averageCost,
        unrealizedPNL,
        realizedPNL,
        account,
    )


def createUpdatePortfolioArgs(
    proto: PortfolioValue_pb2.PortfolioValue,
) -> UpdatePortfolioArgs:
    """``Wrapper.updatePortfolio(contract, posSize, marketPrice, marketValue,
    averageCost, unrealizedPNL, realizedPNL, account)`` args."""
    item = createPortfolioItem(proto)
    return UpdatePortfolioArgs(
        contract=item.contract,
        posSize=item.position,
        marketPrice=item.marketPrice,
        marketValue=item.marketValue,
        averageCost=item.averageCost,
        unrealizedPNL=item.unrealizedPNL,
        realizedPNL=item.realizedPNL,
        account=item.account,
    )


# ---------------------------------------------------------------------------
# ManagedAccounts (msgId 15 receive) + request
# ---------------------------------------------------------------------------


def createManagedAccountsList(proto: ManagedAccounts_pb2.ManagedAccounts) -> str:
    """Wire payload is a single comma-separated string of account ids."""
    return proto.accountsList if proto.HasField("accountsList") else ""


def createManagedAccountsRequestProto() -> (
    ManagedAccountsRequest_pb2.ManagedAccountsRequest
):
    return ManagedAccountsRequest_pb2.ManagedAccountsRequest()


# ---------------------------------------------------------------------------
# FamilyCodes (msgId 78 receive) + request
# ---------------------------------------------------------------------------


def createFamilyCode(proto: FamilyCode_pb2.FamilyCode) -> FamilyCode:
    """Wire fields ``accountId`` / ``familyCode`` map to domain
    ``accountID`` / ``familyCodeStr`` (the binary path's spelling)."""
    accountID = proto.accountId if proto.HasField("accountId") else ""
    familyCodeStr = proto.familyCode if proto.HasField("familyCode") else ""
    return FamilyCode(accountID, familyCodeStr)


def createFamilyCodes(proto: FamilyCodes_pb2.FamilyCodes) -> list[FamilyCode]:
    return [createFamilyCode(c) for c in proto.familyCodes]


def createFamilyCodesRequestProto() -> FamilyCodesRequest_pb2.FamilyCodesRequest:
    return FamilyCodesRequest_pb2.FamilyCodesRequest()


# ---------------------------------------------------------------------------
# FA (Financial Advisor) — request / replace / receive (msgId 16, 103)
# ---------------------------------------------------------------------------


def createFARequestProto(faDataType: int) -> FARequest_pb2.FARequest:
    proto = FARequest_pb2.FARequest()
    proto.faDataType = faDataType
    return proto


def createFAReplaceProto(
    reqId: int, faDataType: int, xml: str
) -> FAReplace_pb2.FAReplace:
    proto = FAReplace_pb2.FAReplace()
    proto.reqId = reqId
    proto.faDataType = faDataType
    proto.xml = xml
    return proto


def createReceiveFAArgs(proto: ReceiveFA_pb2.ReceiveFA) -> ReceiveFAArgs:
    """``Wrapper.receiveFA(faDataType, xml)`` args."""
    faDataType = proto.faDataType if proto.HasField("faDataType") else 0
    xml = proto.xml if proto.HasField("xml") else ""
    return ReceiveFAArgs(faDataType=faDataType, xml=xml)


def createReplaceFAEndArgs(proto: ReplaceFAEnd_pb2.ReplaceFAEnd) -> ReplaceFAEndArgs:
    """``Wrapper.replaceFAEnd(reqId, text)`` args."""
    reqId = proto.reqId if proto.HasField("reqId") else 0
    text = proto.text if proto.HasField("text") else ""
    return ReplaceFAEndArgs(reqId=reqId, text=text)
