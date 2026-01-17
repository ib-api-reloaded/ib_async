"""
Account data protobuf converters.
"""

from decimal import Decimal

from ..objects import (
    AccountValue,
    FamilyCode,
    PortfolioItem,
    Position,
    PositionMulti,
    SoftDollarTier,
)
from ..protobuf.AccountDataRequest_pb2 import (
    AccountDataRequest as AccountDataRequestProto,
)
from ..protobuf.AccountSummary_pb2 import AccountSummary as AccountSummaryProto
from ..protobuf.AccountUpdateMulti_pb2 import (
    AccountUpdateMulti as AccountUpdateMultiProto,
)
from ..protobuf.AccountUpdatesMultiRequest_pb2 import (
    AccountUpdatesMultiRequest as AccountUpdatesMultiRequestProto,
)
from ..protobuf.AccountValue_pb2 import AccountValue as AccountValueProto
from ..protobuf.CancelAccountUpdatesMulti_pb2 import (
    CancelAccountUpdatesMulti as CancelAccountUpdatesMultiProto,
)
from ..protobuf.CancelPositionsMulti_pb2 import (
    CancelPositionsMulti as CancelPositionsMultiProto,
)
from ..protobuf.FamilyCode_pb2 import FamilyCode as FamilyCodeProto
from ..protobuf.FamilyCodes_pb2 import FamilyCodes as FamilyCodesProto
from ..protobuf.FamilyCodesRequest_pb2 import (
    FamilyCodesRequest as FamilyCodesRequestProto,
)
from ..protobuf.FAReplace_pb2 import FAReplace as FAReplaceProto
from ..protobuf.FARequest_pb2 import FARequest as FARequestProto
from ..protobuf.IdsRequest_pb2 import IdsRequest as IdsRequestProto
from ..protobuf.PortfolioValue_pb2 import PortfolioValue as PortfolioValueProto
from ..protobuf.Position_pb2 import Position as PositionProto
from ..protobuf.PositionMulti_pb2 import PositionMulti as PositionMultiProto
from ..protobuf.PositionsMultiRequest_pb2 import (
    PositionsMultiRequest as PositionsMultiRequestProto,
)
from ..protobuf.ReceiveFA_pb2 import ReceiveFA as ReceiveFAProto
from ..protobuf.ReplaceFAEnd_pb2 import ReplaceFAEnd as ReplaceFAEndProto
from ..protobuf.SoftDollarTier_pb2 import SoftDollarTier as SoftDollarTierProto
from ..protobuf.SoftDollarTiersRequest_pb2 import (
    SoftDollarTiersRequest as SoftDollarTiersRequestProto,
)
from ..util import UNSET_DOUBLE, isValidIntValue
from .base_converters import ClientException, ib_defaults
from .contract_converters import createContract


def createPosition(positionProto: PositionProto) -> Position:
    """
    Converts a Position protobuf message to an ib_async Position object.
    """
    contract = createContract(positionProto.contract)
    position = Position(
        account=positionProto.account,
        contract=contract,
        position=Decimal(positionProto.position)
        if positionProto.position
        else ib_defaults.unset_decimal,
        avgCost=positionProto.avgCost,
    )
    return position


def createAccountDataRequestProto(
    subscribe: bool, acctCode: str
) -> AccountDataRequestProto:
    """
    Creates an AccountDataRequest protobuf message.
    """
    accountDataRequestProto = AccountDataRequestProto()
    accountDataRequestProto.subscribe = subscribe
    accountDataRequestProto.acctCode = acctCode
    return accountDataRequestProto


def createAccountMultiRequestProto(
    reqId: int, account: str, modelCode: str, ledgerAndNLV: bool
) -> AccountUpdatesMultiRequestProto:
    """
    Creates an AccountUpdatesMultiRequest protobuf message.
    """
    accountUpdatesMultiRequestProto = AccountUpdatesMultiRequestProto()
    accountUpdatesMultiRequestProto.reqId = reqId
    if account:
        accountUpdatesMultiRequestProto.account = account
    if modelCode:
        accountUpdatesMultiRequestProto.modelCode = modelCode
    if ledgerAndNLV:
        accountUpdatesMultiRequestProto.ledgerAndNLV = ledgerAndNLV
    return accountUpdatesMultiRequestProto


def createCancelAccMultiRequestProto(reqId: int) -> CancelAccountUpdatesMultiProto:
    cancelAccountUpdatesMultiProto = CancelAccountUpdatesMultiProto()
    cancelAccountUpdatesMultiProto.reqId = reqId
    return cancelAccountUpdatesMultiProto


def createAccountValueFromUpdateMulti(
    accountValueProto: AccountUpdateMultiProto,
) -> AccountValue:
    """
    Converts an AccountUpdateMulti protobuf message to an ib_async AccountValue object.
    """
    if accountValueProto.HasField("account"):
        _account = accountValueProto.account
    else:
        _account = ""
    if accountValueProto.HasField("key"):
        _tag = accountValueProto.key
    else:
        _tag = ""
    if accountValueProto.HasField("value"):
        _value = accountValueProto.value
    else:
        _value = ""
    if accountValueProto.HasField("currency"):
        _currency = accountValueProto.currency
    else:
        _currency = ""
    return AccountValue(
        account=_account,
        tag=_tag,
        value=_value,
        currency=_currency,
        modelCode="",
    )


def createAccountValue(accountValueProto: AccountValueProto) -> AccountValue:
    if accountValueProto.HasField("accountName"):
        _account = accountValueProto.accountName
    else:
        _account = ""
    if accountValueProto.HasField("key"):
        _tag = accountValueProto.key
    else:
        _tag = ""
    if accountValueProto.HasField("value"):
        _value = accountValueProto.value
    else:
        _value = ""
    if accountValueProto.HasField("currency"):
        _currency = accountValueProto.currency
    else:
        _currency = ""

    return AccountValue(
        account=_account,
        tag=_tag,
        value=_value,
        currency=_currency,
        modelCode="",
    )


def createAccountSummary(accountSummaryProto: AccountSummaryProto) -> AccountValue:
    if accountSummaryProto.HasField("account"):
        _account = accountSummaryProto.account
    else:
        _account = ""
    if accountSummaryProto.HasField("tag"):
        _tag = accountSummaryProto.tag
    else:
        _tag = ""
    if accountSummaryProto.HasField("value"):
        _value = accountSummaryProto.value
    else:
        _value = ""
    if accountSummaryProto.HasField("currency"):
        _currency = accountSummaryProto.currency
    else:
        _currency = ""

    return AccountValue(
        account=_account,
        tag=_tag,
        value=_value,
        currency=_currency,
        modelCode="",
    )


def createPortfolioItem(portfolioValueProto: PortfolioValueProto) -> PortfolioItem:
    contract = createContract(portfolioValueProto.contract)

    position = (
        Decimal(portfolioValueProto.position)
        if portfolioValueProto.HasField("position")
        else ib_defaults.unset_decimal
    )
    marketPrice = (
        portfolioValueProto.marketPrice
        if portfolioValueProto.HasField("marketPrice")
        else 0
    )
    marketValue = (
        portfolioValueProto.marketValue
        if portfolioValueProto.HasField("marketValue")
        else 0
    )
    averageCost = (
        portfolioValueProto.averageCost
        if portfolioValueProto.HasField("averageCost")
        else 0
    )
    unrealizedPNL = (
        portfolioValueProto.unrealizedPNL
        if portfolioValueProto.HasField("unrealizedPNL")
        else 0
    )
    realizedPNL = (
        portfolioValueProto.realizedPNL
        if portfolioValueProto.HasField("realizedPNL")
        else 0
    )
    accountName = (
        portfolioValueProto.accountName
        if portfolioValueProto.HasField("accountName")
        else ""
    )

    portfolioItem = PortfolioItem(
        contract=contract,
        position=position,
        marketPrice=marketPrice,
        marketValue=marketValue,
        averageCost=averageCost,
        unrealizedPNL=unrealizedPNL,
        realizedPNL=realizedPNL,
        account=accountName,
    )
    return portfolioItem


def createUserInfoRequestProto(reqId: int) -> IdsRequestProto:
    idsRequestProto = IdsRequestProto()
    if isValidIntValue(reqId):
        idsRequestProto.numIds = reqId
    return idsRequestProto


def createFARequestProto(faDataType: int) -> FARequestProto:
    faRequestProto = FARequestProto()
    if isValidIntValue(faDataType):
        faRequestProto.faDataType = faDataType
    return faRequestProto


def createFAReplaceProto(reqId: int, faDataType: int, xml: str) -> FAReplaceProto:
    faReplaceProto = FAReplaceProto()
    if isValidIntValue(reqId):
        faReplaceProto.reqId = reqId
    if isValidIntValue(faDataType):
        faReplaceProto.faDataType = faDataType
    if xml:
        faReplaceProto.xml = xml
    return faReplaceProto


def createFAmsg(msg: ReceiveFAProto) -> tuple[int, str]:
    faDataType = msg.faDataType if msg.HasField("faDataType") else 0
    xml = msg.xml if msg.HasField("xml") else ""

    return faDataType, xml


def createReplaceFAEnd(msg: ReplaceFAEndProto) -> str:
    text = msg.text if msg.HasField("text") else ""
    return text


def createPositionsMultiRequestProto(
    reqId: int, account: str, modelCode: str
) -> PositionsMultiRequestProto:
    positionsMultiRequestProto = PositionsMultiRequestProto()
    if isValidIntValue(reqId):
        positionsMultiRequestProto.reqId = reqId
    if account:
        positionsMultiRequestProto.account = account
    if modelCode:
        positionsMultiRequestProto.modelCode = modelCode
    return positionsMultiRequestProto


def createCancelPositionsMultiRequestProto(reqId: int) -> CancelPositionsMultiProto:
    cancelPositionsMultiProto = CancelPositionsMultiProto()
    if isValidIntValue(reqId):
        cancelPositionsMultiProto.reqId = reqId
    return cancelPositionsMultiProto


def createPositionMulti(positionMultiProto: PositionMultiProto) -> PositionMulti:
    account = (
        positionMultiProto.account if positionMultiProto.HasField("account") else ""
    )
    modelCode = (
        positionMultiProto.modelCode if positionMultiProto.HasField("modelCode") else ""
    )

    # decode contract fields
    if not positionMultiProto.HasField("contract"):
        raise ClientException(999, "Invalid postion contract.", "")
    contract = createContract(positionMultiProto.contract)

    position = (
        Decimal(positionMultiProto.position)
        if positionMultiProto.HasField("position")
        else ib_defaults.unset_decimal
    )
    avgCost = (
        positionMultiProto.avgCost if positionMultiProto.HasField("avgCost") else 0
    )

    return PositionMulti(account, contract, position, avgCost, modelCode)


def createFamilyCodesRequestProto() -> FamilyCodesRequestProto:
    familyCodesRequestProto = FamilyCodesRequestProto()
    return familyCodesRequestProto


def createFamilyCode(familyCodeProto: FamilyCodeProto) -> FamilyCode:
    accountID = ""
    familyCodeStr = ""
    if familyCodeProto:
        if familyCodeProto.HasField("accountId"):
            accountID = familyCodeProto.accountId
        if familyCodeProto.HasField("familyCode"):
            familyCodeStr = familyCodeProto.familyCode

    return FamilyCode(accountID, familyCodeStr)


def createFamilyCodes(familyCodesProto: FamilyCodesProto) -> list[FamilyCode]:
    familyCodes = []
    if familyCodesProto.familyCodes:
        for familCodeProto in familyCodesProto.familyCodes:
            familyCode = createFamilyCode(familCodeProto)
            familyCodes.append(familyCode)
    return familyCodes


def createSoftDollarTiersRequestProto(reqId: int) -> SoftDollarTiersRequestProto:
    softDollarTiersRequestProto = SoftDollarTiersRequestProto()
    if isValidIntValue(reqId):
        softDollarTiersRequestProto.reqId = reqId
    return softDollarTiersRequestProto


def createSoftDollarTier(softDollarTierProto: SoftDollarTierProto) -> SoftDollarTier:
    name = ""
    value = ""
    displayName = ""
    softDollarTier = None
    if softDollarTierProto is not None:
        if softDollarTierProto.HasField("name"):
            name = softDollarTierProto.name
        if softDollarTierProto.HasField("value"):
            value = softDollarTierProto.value
        if softDollarTierProto.HasField("displayName"):
            displayName = softDollarTierProto.displayName
        softDollarTier = SoftDollarTier(name, value, displayName)

    return softDollarTier


def createSoftDollarTiers(
    softDollarTiersProto: SoftDollarTiersRequestProto,
) -> list[SoftDollarTier]:
    tiers = []
    if softDollarTiersProto.softDollarTiers:
        for softDollarTierProto in softDollarTiersProto.softDollarTiers:
            tier = createSoftDollarTier(softDollarTierProto)
            if tier is not None:
                tiers.append(tier)
    return tiers
