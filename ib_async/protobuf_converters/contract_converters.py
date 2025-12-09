"""Contract converters"""

from ..contract import (
    ComboLeg,
    Contract,
    ContractDescription,
    ContractDetails,
    DeltaNeutralContract,
    FundAssetType,
    FundDistributionPolicyIndicator,
    IneligibilityReason,
)
from ..objects import OptionChain, SmartComponent
from ..order import Order
from ..protobuf.ComboLeg_pb2 import ComboLeg as ComboLegProto
from ..protobuf.Contract_pb2 import Contract as ContractProto
from ..protobuf.ContractData_pb2 import ContractData as ContractDataProto
from ..protobuf.ContractDescription_pb2 import (
    ContractDescription as ContractDescriptionProto,
)
from ..protobuf.ContractDetails_pb2 import ContractDetails as ContractDetailsProto
from ..protobuf.DeltaNeutralContract_pb2 import (
    DeltaNeutralContract as DeltaNeutralContractProto,
)
from ..protobuf.MarketRuleRequest_pb2 import MarketRuleRequest as MarketRuleRequestProto
from ..protobuf.MatchingSymbolsRequest_pb2 import (
    MatchingSymbolsRequest as MatchingSymbolsRequestProto,
)
from ..protobuf.SecDefOptParameter_pb2 import (
    SecDefOptParameter as SecDefOptParameterProto,
)
from ..protobuf.SecDefOptParamsRequest_pb2 import (
    SecDefOptParamsRequest as SecDefOptParamsRequestProto,
)
from ..protobuf.SmartComponentsRequest_pb2 import (
    SmartComponentsRequest as SmartComponentsRequestProto,
)
from ..protobuf.SmartComponents_pb2 import SmartComponents as SmartComponentsProto
from ..util import (
    UNSET_DOUBLE,
    floatMaxString,
    getEnumTypeFromString,
    isValidIntValue,
)


def createSecDefOptParamsRequestProto(
    reqId: int,
    underlyingSymbol: str,
    futFopExchange: str,
    underlyingSecType: str,
    underlyingConId: int,
) -> SecDefOptParamsRequestProto:
    """Create a SecDefOptParamsRequest protobuf message.

    Args:
        reqId (int): The request ID.
        underlyingSymbol (str): The underlying symbol.
        futFopExchange (str): The future/option exchange.
        underlyingSecType (str): The underlying security type.
        underlyingConId (int): The underlying contract ID.

    Returns:
        SecDefOptParamsRequestProto: The created SecDefOptParamsRequest protobuf
        message.
    """
    secDefOptParamsRequestProto = SecDefOptParamsRequestProto()
    if reqId is not None:
        secDefOptParamsRequestProto.reqId = reqId
    if underlyingSymbol is not None:
        secDefOptParamsRequestProto.underlyingSymbol = underlyingSymbol
    if futFopExchange is not None:
        secDefOptParamsRequestProto.futFopExchange = futFopExchange
    if underlyingSecType is not None:
        secDefOptParamsRequestProto.underlyingSecType = underlyingSecType
    if underlyingConId is not None:
        secDefOptParamsRequestProto.underlyingConId = underlyingConId
    return secDefOptParamsRequestProto


def createOptionChain(secDefOptParameterProto: SecDefOptParameterProto) -> OptionChain:
    """Create an OptionChain object from a protobuf message.

    Args:
        secDefOptParameterProto (SecDefOptParameterProto): The protobuf message.

    Returns:
        OptionChain: The created OptionChain object.
    """
    if secDefOptParameterProto.exchange is not None:
        exchange = secDefOptParameterProto.exchange
    if secDefOptParameterProto.underlyingConId is not None:
        underlyingConId = secDefOptParameterProto.underlyingConId
    if secDefOptParameterProto.tradingClass is not None:
        tradingClass = secDefOptParameterProto.tradingClass
    if secDefOptParameterProto.multiplier is not None:
        multiplier = secDefOptParameterProto.multiplier
    if secDefOptParameterProto.expirations is not None:
        expirations = list(secDefOptParameterProto.expirations)
    if secDefOptParameterProto.strikes is not None:
        strikes = list(secDefOptParameterProto.strikes)
    optionChain = OptionChain(
        exchange=exchange,
        underlyingConId=underlyingConId,
        tradingClass=tradingClass,
        multiplier=multiplier,
        expirations=expirations,
        strikes=strikes,
    )
    return optionChain


def createContract(contractProto: ContractProto) -> Contract:
    contract = Contract()
    if contractProto.HasField("conId"):
        contract.conId = contractProto.conId
    if contractProto.HasField("symbol"):
        contract.symbol = contractProto.symbol
    if contractProto.HasField("secType"):
        contract.secType = contractProto.secType
    if contractProto.HasField("lastTradeDateOrContractMonth"):
        contract.lastTradeDateOrContractMonth = (
            contractProto.lastTradeDateOrContractMonth
        )
    if contractProto.HasField("strike"):
        contract.strike = contractProto.strike
    if contractProto.HasField("right"):
        contract.right = contractProto.right
    if contractProto.HasField("multiplier"):
        contract.multiplier = floatMaxString(contractProto.multiplier)
    if contractProto.HasField("exchange"):
        contract.exchange = contractProto.exchange
    if contractProto.HasField("currency"):
        contract.currency = contractProto.currency
    if contractProto.HasField("localSymbol"):
        contract.localSymbol = contractProto.localSymbol
    if contractProto.HasField("tradingClass"):
        contract.tradingClass = contractProto.tradingClass
    if contractProto.HasField("comboLegsDescrip"):
        contract.comboLegsDescrip = contractProto.comboLegsDescrip

    comboLegs = createComboLegs(contractProto)
    if comboLegs is not None and comboLegs:
        contract.comboLegs = comboLegs

    deltaNeutralContract = createDeltaNeutralContract(contractProto)
    if deltaNeutralContract is not None:
        contract.deltaNeutralContract = deltaNeutralContract

    if contractProto.HasField("lastTradeDate"):
        contract.lastTradeDate = contractProto.lastTradeDate
    if contractProto.HasField("primaryExch"):
        contract.primaryExchange = contractProto.primaryExch
    if contractProto.HasField("issuerId"):
        contract.issuerId = contractProto.issuerId
    if contractProto.HasField("description"):
        contract.description = contractProto.description

    return contract


def createComboLegs(contractProto: ContractProto) -> list[ComboLeg]:
    comboLegs = []
    comboLegProtoList = contractProto.comboLegs
    if comboLegProtoList:
        for comboLegProto in comboLegProtoList:
            comboLeg = ComboLeg()
            if comboLegProto.HasField("conId"):
                comboLeg.conId = comboLegProto.conId
            if comboLegProto.HasField("ratio"):
                comboLeg.ratio = comboLegProto.ratio
            if comboLegProto.HasField("action"):
                comboLeg.action = comboLegProto.action
            if comboLegProto.HasField("exchange"):
                comboLeg.exchange = comboLegProto.exchange
            if comboLegProto.HasField("openClose"):
                comboLeg.openClose = comboLegProto.openClose
            if comboLegProto.HasField("shortSalesSlot"):
                comboLeg.shortSaleSlot = comboLegProto.shortSalesSlot
            if comboLegProto.HasField("designatedLocation"):
                comboLeg.designatedLocation = comboLegProto.designatedLocation
            if comboLegProto.HasField("exemptCode"):
                comboLeg.exemptCode = comboLegProto.exemptCode
            comboLegs.append(comboLeg)

    return comboLegs


def createDeltaNeutralContract(
    contractProto: ContractProto,
) -> DeltaNeutralContract | None:
    deltaNeutralContract = None
    if contractProto.HasField("deltaNeutralContract"):
        deltaNeutralContractProto = DeltaNeutralContractProto()
        deltaNeutralContractProto.CopyFrom(contractProto.deltaNeutralContract)
        if deltaNeutralContractProto is not None:
            deltaNeutralContract = DeltaNeutralContract()
            if deltaNeutralContractProto.HasField("conId"):
                deltaNeutralContract.conId = deltaNeutralContractProto.conId
            if deltaNeutralContractProto.HasField("delta"):
                deltaNeutralContract.delta = deltaNeutralContractProto.delta
            if deltaNeutralContractProto.HasField("price"):
                deltaNeutralContract.price = deltaNeutralContractProto.price

    return deltaNeutralContract


def createIneligibilityReasonList(
    contractDetailsProto: ContractDetailsProto,
) -> list[IneligibilityReason]:
    ineligibilityReasonList = []
    ineligibilityReasonProtoList = contractDetailsProto.ineligibilityReasonList
    if ineligibilityReasonProtoList:
        for ineligibilityReasonProto in ineligibilityReasonProtoList:
            ineligibilityReason = IneligibilityReason()
            if ineligibilityReasonProto.HasField("id"):
                ineligibilityReason.id_ = ineligibilityReasonProto.id
            if ineligibilityReasonProto.HasField("description"):
                ineligibilityReason.description = ineligibilityReasonProto.description
            ineligibilityReasonList.append(ineligibilityReason)
    return ineligibilityReasonList


def setLastTradeDate(
    lastTradeDateOrContractMonth: str, contract: ContractDetails, isBond: bool
):
    if lastTradeDateOrContractMonth is not None:
        if "-" in lastTradeDateOrContractMonth:
            split = lastTradeDateOrContractMonth.split("-")
        else:
            split = lastTradeDateOrContractMonth.split()

        if len(split) > 0:
            if isBond:
                contract.maturity = split[0]
            else:
                if contract.contract:
                    contract.contract.lastTradeDateOrContractMonth = split[0]

        if len(split) > 1:
            contract.lastTradeTime = split[1]

        if isBond and len(split) > 2:
            contract.timeZoneId = split[2]


def createContractDetails(
    msg: ContractDataProto, isBond: bool = False
) -> ContractDetails:
    """Create a ContractDetails object from a protobuf message.
    Args:
        msg (ContractDataProto): The protobuf message.
    Returns:
        ContractDetails: The created ContractDetails object.
    """
    contractDetails = ContractDetails()
    contractDetails.contract = createContract(msg.contract)
    details = msg.contractDetails

    contractDetails.marketName = details.marketName
    contractDetails.minTick = float(details.minTick) if details.minTick else 0.0
    contractDetails.orderTypes = details.orderTypes
    contractDetails.validExchanges = details.validExchanges
    contractDetails.priceMagnifier = details.priceMagnifier
    contractDetails.underConId = details.underConId
    contractDetails.longName = details.longName
    contractDetails.contractMonth = details.contractMonth
    contractDetails.industry = details.industry
    contractDetails.category = details.category
    contractDetails.subcategory = details.subcategory
    contractDetails.timeZoneId = details.timeZoneId
    contractDetails.tradingHours = details.tradingHours
    contractDetails.liquidHours = details.liquidHours
    contractDetails.evRule = details.evRule
    contractDetails.evMultiplier = details.evMultiplier
    # contractDetails.secIdList = details.secIdList
    # This is a map in proto, list of TagValue in ib_async
    contractDetails.aggGroup = details.aggGroup
    contractDetails.underSymbol = details.underSymbol
    contractDetails.underSecType = details.underSecType
    contractDetails.marketRuleIds = details.marketRuleIds
    contractDetails.realExpirationDate = details.realExpirationDate
    contractDetails.stockType = details.stockType
    contractDetails.minSize = float(details.minSize) if details.minSize else 0.0
    contractDetails.sizeIncrement = (
        float(details.sizeIncrement) if details.sizeIncrement else 0.0
    )
    contractDetails.suggestedSizeIncrement = (
        float(details.suggestedSizeIncrement) if details.suggestedSizeIncrement else 0.0
    )
    contractDetails.cusip = details.cusip
    contractDetails.ratings = details.ratings
    contractDetails.descAppend = details.descAppend
    contractDetails.bondType = details.bondType
    contractDetails.couponType = details.couponType
    contractDetails.callable = details.callable
    contractDetails.putable = details.puttable
    contractDetails.coupon = details.coupon
    contractDetails.convertible = details.convertible
    contractDetails.issueDate = details.issueDate
    contractDetails.nextOptionDate = details.nextOptionDate
    contractDetails.nextOptionType = details.nextOptionType
    contractDetails.nextOptionPartial = details.nextOptionPartial

    if details.HasField("fundName"):
        contractDetails.fundName = details.fundName
    if details.HasField("fundFamily"):
        contractDetails.fundFamily = details.fundFamily
    if details.HasField("fundType"):
        contractDetails.fundType = details.fundType
    if details.HasField("fundFrontLoad"):
        contractDetails.fundFrontLoad = details.fundFrontLoad
    if details.HasField("fundBackLoad"):
        contractDetails.fundBackLoad = details.fundBackLoad
    if details.HasField("fundBackLoadTimeInterval"):
        contractDetails.fundBackLoadTimeInterval = details.fundBackLoadTimeInterval
    if details.HasField("fundManagementFee"):
        contractDetails.fundManagementFee = details.fundManagementFee
    if details.HasField("fundClosed"):
        contractDetails.fundClosed = details.fundClosed
    if details.HasField("fundClosedForNewInvestors"):
        contractDetails.fundClosedForNewInvestors = details.fundClosedForNewInvestors
    if details.HasField("fundClosedForNewMoney"):
        contractDetails.fundClosedForNewMoney = details.fundClosedForNewMoney
    if details.HasField("fundNotifyAmount"):
        contractDetails.fundNotifyAmount = details.fundNotifyAmount
    if details.HasField("fundMinimumInitialPurchase"):
        contractDetails.fundMinimumInitialPurchase = details.fundMinimumInitialPurchase
    if details.HasField("fundMinimumSubsequentPurchase"):
        contractDetails.fundSubsequentMinimumPurchase = (
            details.fundMinimumSubsequentPurchase
        )
    if details.HasField("fundBlueSkyStates"):
        contractDetails.fundBlueSkyStates = details.fundBlueSkyStates
    if details.HasField("fundBlueSkyTerritories"):
        contractDetails.fundBlueSkyTerritories = details.fundBlueSkyTerritories

    if details.HasField("fundDistributionPolicyIndicator"):
        contractDetails.fundDistributionPolicyIndicator = getEnumTypeFromString(
            FundDistributionPolicyIndicator, details.fundDistributionPolicyIndicator
        )
    if details.HasField("fundAssetType"):
        contractDetails.fundAssetType = getEnumTypeFromString(
            FundAssetType, details.fundAssetType
        )

    ineligibilityReasonList = createIneligibilityReasonList(details)
    if ineligibilityReasonList is not None and ineligibilityReasonList:
        contractDetails.ineligibilityReasonList = ineligibilityReasonList

    if details.HasField("eventContract1"):
        contractDetails.eventContract1 = details.eventContract1
    if details.HasField("eventContractDescription1"):
        contractDetails.eventContractDescription1 = details.eventContractDescription1
    if details.HasField("eventContractDescription2"):
        contractDetails.eventContractDescription2 = details.eventContractDescription2

    setLastTradeDate(
        contractDetails.contract.lastTradeDateOrContractMonth, contractDetails, isBond
    )

    return contractDetails


def createContractDescription(
    contractDescriptionProto: ContractDescriptionProto,
) -> ContractDescription:
    """Create a ContractDescription object from a protobuf message.

    Args:
        contractDescriptionProto (ContractDescriptionProto): The protobuf message.

    Returns:
        ContractDescription: The created ContractDescription object.
    """
    contractDescription = ContractDescription()
    contractDescription.contract = createContract(contractDescriptionProto.contract)
    contractDescription.derivativeSecTypes.extend(
        contractDescriptionProto.derivativeSecTypes
    )
    return contractDescription


def createMatchingSymbolsRequestProto(
    reqId: int, pattern: str
) -> MatchingSymbolsRequestProto:
    """Create a MatchingSymbolsRequest protobuf message.

    Args:
        reqId (int): The request ID.
        pattern (str): The pattern to match.

    Returns:
        MatchingSymbolsRequestProto: The created MatchingSymbolsRequest protobuf
        message.
    """
    matchingSymbolsRequestProto = MatchingSymbolsRequestProto()
    matchingSymbolsRequestProto.reqId = reqId
    matchingSymbolsRequestProto.pattern = pattern
    return matchingSymbolsRequestProto


def createMarketRuleRequestProto(marketRuleId: int) -> MarketRuleRequestProto:
    """Create a MarketRuleRequest protobuf message.

    Args:
        marketRuleId (int): The ID of the market rule.

    Returns:
        MarketRuleRequestProto: The created MarketRuleRequest protobuf message.
    """
    marketRuleRequestProto = MarketRuleRequestProto()
    marketRuleRequestProto.marketRuleId = marketRuleId
    return marketRuleRequestProto


def createContractProto(contract: Contract, order: Order | None) -> ContractProto:
    """Create a Contract protobuf message.

    Args:
        contract (Contract): The contract.

    Returns:
        ContractProto: The created Contract protobuf message.
    """
    contractProto = ContractProto()
    if contract.conId:
        contractProto.conId = contract.conId
    if contract.symbol:
        contractProto.symbol = contract.symbol
    if contract.secType:
        contractProto.secType = contract.secType
    if contract.lastTradeDateOrContractMonth:
        contractProto.lastTradeDateOrContractMonth = (
            contract.lastTradeDateOrContractMonth
        )
    if contract.strike:
        contractProto.strike = contract.strike
    if contract.right:
        contractProto.right = contract.right
    if contract.multiplier:
        contractProto.multiplier = (
            float(contract.multiplier) if contract.multiplier else 0.0
        )
    if contract.exchange:
        contractProto.exchange = contract.exchange
    if contract.primaryExchange:
        contractProto.primaryExch = contract.primaryExchange
    if contract.currency:
        contractProto.currency = contract.currency
    if contract.localSymbol:
        contractProto.localSymbol = contract.localSymbol
    if contract.tradingClass:
        contractProto.tradingClass = contract.tradingClass
    if contract.includeExpired:
        contractProto.includeExpired = contract.includeExpired
    if contract.secIdType:
        contractProto.secIdType = contract.secIdType
    if contract.secId:
        contractProto.secId = contract.secId
    if contract.description:
        contractProto.description = contract.description
    if contract.issuerId:
        contractProto.issuerId = contract.issuerId

    comboLegProtoList = createComboLegProtoList(contract, order)
    if comboLegProtoList:
        contractProto.comboLegs.extend(comboLegProtoList)

    deltaNeutralContractProto = createDeltaNeutralContractProto(contract)
    if deltaNeutralContractProto is not None:
        contractProto.deltaNeutralContract.CopyFrom(deltaNeutralContractProto)

    return contractProto


def createDeltaNeutralContractProto(
    contract: Contract,
) -> DeltaNeutralContractProto | None:
    deltaNeutralContractProto = None
    if contract.deltaNeutralContract is not None:
        deltaNeutralContract = contract.deltaNeutralContract
        deltaNeutralContractProto = DeltaNeutralContractProto()
        if deltaNeutralContract.conId is not None:
            deltaNeutralContractProto.conId = deltaNeutralContract.conId
        if deltaNeutralContract.delta is not None:
            deltaNeutralContractProto.delta = deltaNeutralContract.delta
        if deltaNeutralContract.price is not None:
            deltaNeutralContractProto.price = deltaNeutralContract.price
    return deltaNeutralContractProto


def createComboLegProtoList(
    contract: Contract, order: Order | None
) -> list[ComboLegProto]:
    comboLegs = contract.comboLegs
    orderComboLegs = order.orderComboLegs if order else None
    comboLegProtoList = []
    if comboLegs:
        for i, comboLeg in enumerate(comboLegs):
            if orderComboLegs and i < len(orderComboLegs):
                perLegPrice = float(orderComboLegs[i].price)
                comboLegProto = createComboLegProto(comboLeg, perLegPrice)
            if comboLegProto is not None:
                comboLegProtoList.append(comboLegProto)
    return comboLegProtoList


def createComboLegProto(comboLeg: ComboLeg, perLegPrice: float) -> ComboLegProto:
    comboLegProto = ComboLegProto()
    if comboLeg.conId is not None:
        comboLegProto.conId = comboLeg.conId
    if comboLeg.ratio is not None:
        comboLegProto.ratio = comboLeg.ratio
    if comboLeg.action is not None:
        comboLegProto.action = comboLeg.action
    if comboLegProto.exchange is not None:
        comboLegProto.exchange = comboLeg.exchange
    if comboLegProto.openClose is not None:
        comboLegProto.openClose = comboLeg.openClose
    if comboLegProto.shortSalesSlot is not None:
        comboLegProto.shortSalesSlot = comboLeg.shortSaleSlot
    if comboLegProto.designatedLocation is not None:
        comboLegProto.designatedLocation = comboLeg.designatedLocation
    if comboLegProto.exemptCode is not None:
        comboLegProto.exemptCode = comboLeg.exemptCode
    if comboLegProto.perLegPrice is not None:
        comboLegProto.perLegPrice = perLegPrice
    return comboLegProto


def createSmartComponentsRequestProto(
    reqId: int, bboExchange: str
) -> SmartComponentsRequestProto:
    smartComponentsRequestProto = SmartComponentsRequestProto()
    if isValidIntValue(reqId):
        smartComponentsRequestProto.reqId = reqId
    if bboExchange:
        smartComponentsRequestProto.bboExchange = bboExchange
    return smartComponentsRequestProto


def createSmartComponents(
    smartComponentsProto: SmartComponentsProto,
) -> list[SmartComponent]:
    smartComponents = []
    if smartComponentsProto and smartComponentsProto.smartComponents:
        for smartComponentProto in smartComponentsProto.smartComponents:
            bitNumber = (
                smartComponentProto.bitNumber
                if smartComponentProto.HasField("bitNumber")
                else 0
            )
            exchange = (
                smartComponentProto.exchange
                if smartComponentProto.HasField("exchange")
                else ""
            )
            exchangeLetter = (
                smartComponentProto.exchangeLetter
                if smartComponentProto.HasField("exchangeLetter")
                else " "
            )
            smartComponents.append(SmartComponent(bitNumber, exchange, exchangeLetter))
    return smartComponents
