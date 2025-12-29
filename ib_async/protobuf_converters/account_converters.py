"""
Account data protobuf converters.
"""

from ib_async.util import isValidIntValue

from ..objects import AccountValue, PortfolioItem, Position
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
from ..protobuf.FAReplace_pb2 import FAReplace as FAReplaceProto
from ..protobuf.FARequest_pb2 import FARequest as FARequestProto
from ..protobuf.IdsRequest_pb2 import IdsRequest as IdsRequestProto
from ..protobuf.PortfolioValue_pb2 import PortfolioValue as PortfolioValueProto
from ..protobuf.Position_pb2 import Position as PositionProto
from ..protobuf.ReceiveFA_pb2 import ReceiveFA as ReceiveFAProto
from ..protobuf.ReplaceFAEnd_pb2 import ReplaceFAEnd as ReplaceFAEndProto
from .contract_converters import createContract


def createPosition(positionProto: PositionProto) -> Position:
    """
    Converts a Position protobuf message to an ib_async Position object.
    """
    contract = createContract(positionProto.contract)
    position = Position(
        account=positionProto.account,
        contract=contract,
        position=float(positionProto.position) if positionProto.position else 0.0,
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
    return PortfolioItem(
        contract=createContract(portfolioValueProto.contract),
        position=float(portfolioValueProto.position)
        if portfolioValueProto.position
        else 0.0,
        marketPrice=portfolioValueProto.marketPrice,
        marketValue=portfolioValueProto.marketValue,
        averageCost=portfolioValueProto.averageCost,
        unrealizedPNL=portfolioValueProto.unrealizedPNL,
        realizedPNL=portfolioValueProto.realizedPNL,
        account=portfolioValueProto.accountName,
    )


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
    faDataType = (
        msg.faDataType if msg.HasField("faDataType") else 0
    )
    xml = msg.xml if msg.HasField("xml") else ""

    return faDataType, xml

def createReplaceFAEnd(msg: ReplaceFAEndProto) -> str:
    text = msg.text if msg.HasField('text') else ""
    return text
   