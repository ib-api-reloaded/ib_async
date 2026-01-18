"""
Converters for trade-related Protobuf messages.
"""

import datetime as dt
from decimal import Decimal

from ib_async.contract import Contract
from ib_async.objects import (
    CommissionReport,
    Execution,
    ExecutionFilter,
    Fill,
    OptionExerciseType,
    SoftDollarTier,
    TagValue,
)
from ib_async.order import (
    ExecutionCondition,
    MarginCondition,
    Order,
    OrderAllocation,
    OrderCancel,
    OrderComboLeg,
    OrderCondition,
    OrderConditionType,
    OrderState,
    OrderStatus,
    PercentChangeCondition,
    PriceCondition,
    TimeCondition,
    Trade,
    VolumeCondition,
)
from ib_async.util import (
    UNSET_DOUBLE,
    UNSET_INTEGER,
    getEnumTypeFromString,
    isValidIntValue,
    parseIBDatetime,
)

from ..protobuf.CancelOrderRequest_pb2 import (
    CancelOrderRequest as CancelOrderRequestProto,
)
from ..protobuf.CommissionAndFeesReport_pb2 import (
    CommissionAndFeesReport as CommissionReportProto,
)
from ..protobuf.Contract_pb2 import Contract as ContractProto
from ..protobuf.Execution_pb2 import Execution as ExecutionProto
from ..protobuf.ExecutionDetails_pb2 import (
    ExecutionDetails as ExecutionDetailsProto,
)
from ..protobuf.ExecutionFilter_pb2 import ExecutionFilter as ExecutionFilterProto
from ..protobuf.ExecutionRequest_pb2 import ExecutionRequest as ExecutionRequestProto
from ..protobuf.ExerciseOptionsRequest_pb2 import (
    ExerciseOptionsRequest as ExerciseOptionsRequestProto,
)
from ..protobuf.GlobalCancelRequest_pb2 import (
    GlobalCancelRequest as GlobalCancelRequestProto,
)
from ..protobuf.OpenOrder_pb2 import OpenOrder as OpenOrderProto
from ..protobuf.Order_pb2 import Order as OrderProto
from ..protobuf.OrderCancel_pb2 import OrderCancel as OrderCancelProto
from ..protobuf.OrderCondition_pb2 import OrderCondition as OrderConditionProto
from ..protobuf.OrderState_pb2 import OrderState as OrderStateProto
from ..protobuf.OrderStatus_pb2 import OrderStatus as OrderStatusProto
from ..protobuf.PlaceOrderRequest_pb2 import PlaceOrderRequest as PlaceOrderRequestProto
from ..protobuf.SoftDollarTier_pb2 import SoftDollarTier as SoftDollarTierProto
from .base_converters import ClientException, fillTagValueList
from .contract_converters import (
    createContract,
    createContractProto,
)


def createPlaceOrderRequestProto(
    orderId: int, contract: Contract, order: Order
) -> PlaceOrderRequestProto:
    placeOrderRequestProto = PlaceOrderRequestProto()
    if isValidIntValue(orderId):
        placeOrderRequestProto.orderId = orderId
    contractProto = createContractProto(contract, order)
    if contractProto is not None:
        placeOrderRequestProto.contract.CopyFrom(contractProto)
    orderProto = createOrderProto(order)
    if orderProto is not None:
        placeOrderRequestProto.order.CopyFrom(orderProto)
    return placeOrderRequestProto


def createOrderProto(order: Order) -> OrderProto:
    orderProto = OrderProto()
    if isValidIntValue(order.clientId):
        order.clientId = order.clientId
    if isValidIntValue(order.permId):
        orderProto.permId = order.permId
    if isValidIntValue(order.parentId):
        orderProto.parentId = order.parentId
    if order.action:
        orderProto.action = order.action
    if order.totalQuantity != UNSET_DOUBLE:
        orderProto.totalQuantity = str(order.totalQuantity)
    if isValidIntValue(order.displaySize):
        orderProto.displaySize = order.displaySize
    if order.orderType:
        orderProto.orderType = order.orderType
    if order.lmtPrice != UNSET_DOUBLE and order.lmtPrice is not None:
        orderProto.lmtPrice = float(order.lmtPrice)
    if order.auxPrice != UNSET_DOUBLE and order.auxPrice is not None:
        orderProto.auxPrice = float(order.auxPrice)
    if order.tif:
        orderProto.tif = order.tif
    if order.account:
        orderProto.account = order.account
    if order.settlingFirm:
        orderProto.settlingFirm = order.settlingFirm
    if order.clearingAccount:
        orderProto.clearingAccount = order.clearingAccount
    if order.clearingIntent:
        orderProto.clearingIntent = order.clearingIntent
    if order.allOrNone:
        orderProto.allOrNone = order.allOrNone
    if order.blockOrder:
        orderProto.blockOrder = order.blockOrder
    if order.hidden:
        orderProto.hidden = order.hidden
    if order.outsideRth:
        orderProto.outsideRth = order.outsideRth
    if order.sweepToFill:
        orderProto.sweepToFill = order.sweepToFill
    if order.percentOffset != UNSET_DOUBLE:
        orderProto.percentOffset = float(order.percentOffset)
    if order.trailingPercent:
        orderProto.trailingPercent = float(order.trailingPercent)
    if order.trailStopPrice != UNSET_DOUBLE:
        orderProto.trailStopPrice = float(order.trailStopPrice)
    if isValidIntValue(order.minQty):
        orderProto.minQty = order.minQty
    if order.goodAfterTime:
        orderProto.goodAfterTime = order.goodAfterTime
    if order.goodTillDate:
        orderProto.goodTillDate = order.goodTillDate
    if order.ocaGroup:
        orderProto.ocaGroup = order.ocaGroup
    if order.orderRef:
        orderProto.orderRef = order.orderRef
    if order.rule80A:
        orderProto.rule80A = order.rule80A
    if isValidIntValue(order.ocaType):
        orderProto.ocaType = order.ocaType
    if isValidIntValue(order.triggerMethod):
        orderProto.triggerMethod = order.triggerMethod
    if order.activeStartTime:
        orderProto.activeStartTime = order.activeStartTime
    if order.activeStopTime:
        orderProto.activeStopTime = order.activeStopTime
    if order.faGroup:
        orderProto.faGroup = order.faGroup
    if order.faMethod:
        orderProto.faMethod = order.faMethod
    if order.faPercentage:
        orderProto.faPercentage = order.faPercentage
    if order.volatility != UNSET_DOUBLE:
        orderProto.volatility = float(order.volatility)
    if isValidIntValue(order.volatilityType):
        orderProto.volatilityType = order.volatilityType
    if order.continuousUpdate:
        orderProto.continuousUpdate = order.continuousUpdate
    if isValidIntValue(order.referencePriceType):
        orderProto.referencePriceType = order.referencePriceType
    if order.deltaNeutralOrderType:
        orderProto.deltaNeutralOrderType = order.deltaNeutralOrderType
    if order.deltaNeutralAuxPrice != UNSET_DOUBLE:
        orderProto.deltaNeutralAuxPrice = float(order.deltaNeutralAuxPrice)
    if isValidIntValue(order.deltaNeutralConId):
        orderProto.deltaNeutralConId = order.deltaNeutralConId
    if order.deltaNeutralOpenClose:
        orderProto.deltaNeutralOpenClose = order.deltaNeutralOpenClose
    if order.deltaNeutralShortSale:
        orderProto.deltaNeutralShortSale = order.deltaNeutralShortSale
    if isValidIntValue(order.deltaNeutralShortSaleSlot):
        orderProto.deltaNeutralShortSaleSlot = order.deltaNeutralShortSaleSlot
    if order.deltaNeutralDesignatedLocation:
        orderProto.deltaNeutralDesignatedLocation = order.deltaNeutralDesignatedLocation
    if isValidIntValue(order.scaleInitLevelSize):
        orderProto.scaleInitLevelSize = order.scaleInitLevelSize
    if isValidIntValue(order.scaleSubsLevelSize):
        orderProto.scaleSubsLevelSize = order.scaleSubsLevelSize
    if order.scalePriceIncrement != UNSET_DOUBLE:
        orderProto.scalePriceIncrement = float(order.scalePriceIncrement)
    if order.scalePriceAdjustValue != UNSET_DOUBLE:
        orderProto.scalePriceAdjustValue = float(order.scalePriceAdjustValue)
    if isValidIntValue(order.scalePriceAdjustInterval):
        orderProto.scalePriceAdjustInterval = order.scalePriceAdjustInterval
    if order.scaleProfitOffset != UNSET_DOUBLE:
        orderProto.scaleProfitOffset = float(order.scaleProfitOffset)
    if order.scaleAutoReset:
        orderProto.scaleAutoReset = order.scaleAutoReset
    if isValidIntValue(order.scaleInitPosition):
        orderProto.scaleInitPosition = order.scaleInitPosition
    if isValidIntValue(order.scaleInitFillQty):
        orderProto.scaleInitFillQty = order.scaleInitFillQty
    if order.scaleRandomPercent:
        orderProto.scaleRandomPercent = order.scaleRandomPercent
    if order.scaleTable:
        orderProto.scaleTable = order.scaleTable
    if order.hedgeType:
        orderProto.hedgeType = order.hedgeType
    if order.hedgeParam:
        orderProto.hedgeParam = order.hedgeParam

    if order.algoStrategy:
        orderProto.algoStrategy = order.algoStrategy
    fillTagValueList(order.algoParams, orderProto.algoParams)
    if order.algoId:
        orderProto.algoId = order.algoId

    fillTagValueList(order.smartComboRoutingParams, orderProto.smartComboRoutingParams)

    if order.whatIf:
        orderProto.whatIf = order.whatIf
    if order.transmit:
        orderProto.transmit = order.transmit
    if order.overridePercentageConstraints:
        orderProto.overridePercentageConstraints = order.overridePercentageConstraints
    if order.openClose:
        orderProto.openClose = order.openClose
    if isValidIntValue(order.origin):
        orderProto.origin = order.origin
    if isValidIntValue(order.shortSaleSlot):
        orderProto.shortSaleSlot = order.shortSaleSlot
    if order.designatedLocation:
        orderProto.designatedLocation = order.designatedLocation
    if isValidIntValue(order.exemptCode):
        orderProto.exemptCode = order.exemptCode
    if order.deltaNeutralSettlingFirm:
        orderProto.deltaNeutralSettlingFirm = order.deltaNeutralSettlingFirm
    if order.deltaNeutralClearingAccount:
        orderProto.deltaNeutralClearingAccount = order.deltaNeutralClearingAccount
    if order.deltaNeutralClearingIntent:
        orderProto.deltaNeutralClearingIntent = order.deltaNeutralClearingIntent
    if order.discretionaryAmt != UNSET_DOUBLE:
        orderProto.discretionaryAmt = order.discretionaryAmt
    if order.optOutSmartRouting:
        orderProto.optOutSmartRouting = order.optOutSmartRouting
    if isValidIntValue(order.exemptCode):
        orderProto.exemptCode = order.exemptCode
    if order.startingPrice != UNSET_DOUBLE:
        orderProto.startingPrice = float(order.startingPrice)
    if order.stockRefPrice != UNSET_DOUBLE:
        orderProto.stockRefPrice = float(order.stockRefPrice)
    if order.delta != UNSET_DOUBLE:
        orderProto.delta = float(order.delta)
    if order.stockRangeLower != UNSET_DOUBLE:
        orderProto.stockRangeLower = float(order.stockRangeLower)
    if order.stockRangeUpper != UNSET_DOUBLE:
        orderProto.stockRangeUpper = float(order.stockRangeUpper)
    if order.notHeld:
        orderProto.notHeld = order.notHeld

    fillTagValueList(order.orderMiscOptions, orderProto.orderMiscOptions)

    if order.solicited:
        orderProto.solicited = order.solicited
    if order.randomizeSize:
        orderProto.randomizeSize = order.randomizeSize
    if order.randomizePrice:
        orderProto.randomizePrice = order.randomizePrice
    if isValidIntValue(order.referenceContractId):
        orderProto.referenceContractId = order.referenceContractId
    if order.peggedChangeAmount != UNSET_DOUBLE:
        orderProto.peggedChangeAmount = order.peggedChangeAmount
    if order.isPeggedChangeAmountDecrease:
        orderProto.isPeggedChangeAmountDecrease = order.isPeggedChangeAmountDecrease
    if order.referenceChangeAmount != UNSET_DOUBLE:
        orderProto.referenceChangeAmount = order.referenceChangeAmount
    if order.referenceExchangeId:
        orderProto.referenceExchangeId = order.referenceExchangeId
    if order.adjustedOrderType:
        orderProto.adjustedOrderType = order.adjustedOrderType
    if order.triggerPrice != UNSET_DOUBLE and order.triggerPrice is not None:
        orderProto.triggerPrice = float(order.triggerPrice)
    if order.adjustedStopPrice != UNSET_DOUBLE and order.adjustedStopPrice is not None:
        orderProto.adjustedStopPrice = float(order.adjustedStopPrice)
    if (
        order.adjustedStopLimitPrice != UNSET_DOUBLE
        and order.adjustedStopLimitPrice is not None
    ):
        orderProto.adjustedStopLimitPrice = float(order.adjustedStopLimitPrice)  # type: ignore[assignment]
    if (
        order.adjustedTrailingAmount != UNSET_DOUBLE
        and order.adjustedTrailingAmount is not None
    ):
        orderProto.adjustedTrailingAmount = float(order.adjustedTrailingAmount)  # type: ignore[assignment]
    if isValidIntValue(order.adjustableTrailingUnit):
        orderProto.adjustableTrailingUnit = order.adjustableTrailingUnit
    if order.lmtPriceOffset != UNSET_DOUBLE and order.lmtPriceOffset is not None:
        orderProto.lmtPriceOffset = float(order.lmtPriceOffset)  # type: ignore[assignment]

    orderConditionList = createConditionsProto(order)
    if orderConditionList is not None and orderConditionList:
        orderProto.conditions.extend(orderConditionList)
    if order.conditionsCancelOrder:
        orderProto.conditionsCancelOrder = order.conditionsCancelOrder
    if order.conditionsIgnoreRth:
        orderProto.conditionsIgnoreRth = order.conditionsIgnoreRth

    if order.modelCode:
        orderProto.modelCode = order.modelCode
    if order.extOperator:
        orderProto.extOperator = order.extOperator

    softDollarTier = createSoftDollarTierProto(order)
    if softDollarTier is not None:
        orderProto.softDollarTier.CopyFrom(softDollarTier)

    if order.cashQty != UNSET_DOUBLE:
        orderProto.cashQty = float(order.cashQty)
    if order.mifid2DecisionMaker:
        orderProto.mifid2DecisionMaker = order.mifid2DecisionMaker
    if order.mifid2DecisionAlgo:
        orderProto.mifid2DecisionAlgo = order.mifid2DecisionAlgo
    if order.mifid2ExecutionTrader:
        orderProto.mifid2ExecutionTrader = order.mifid2ExecutionTrader
    if order.mifid2ExecutionAlgo:
        orderProto.mifid2ExecutionAlgo = order.mifid2ExecutionAlgo
    if order.dontUseAutoPriceForHedge:
        orderProto.dontUseAutoPriceForHedge = order.dontUseAutoPriceForHedge
    if order.isOmsContainer:
        orderProto.isOmsContainer = order.isOmsContainer
    if order.discretionaryUpToLimitPrice:
        orderProto.discretionaryUpToLimitPrice = order.discretionaryUpToLimitPrice
    if order.usePriceMgmtAlgo is not None:
        orderProto.usePriceMgmtAlgo = 1 if order.usePriceMgmtAlgo else 0
    if isValidIntValue(order.duration):
        orderProto.duration = order.duration
    if isValidIntValue(order.postToAts):
        orderProto.postToAts = order.postToAts
    if order.advancedErrorOverride:
        orderProto.advancedErrorOverride = order.advancedErrorOverride
    if order.manualOrderTime:
        orderProto.manualOrderTime = order.manualOrderTime
    if isValidIntValue(order.minTradeQty):
        orderProto.minTradeQty = order.minTradeQty
    if isValidIntValue(order.minCompeteSize):
        orderProto.minCompeteSize = order.minCompeteSize
    if order.competeAgainstBestOffset != UNSET_DOUBLE:
        orderProto.competeAgainstBestOffset = float(order.competeAgainstBestOffset)
    if order.midOffsetAtWhole != UNSET_DOUBLE:
        orderProto.midOffsetAtWhole = float(order.midOffsetAtWhole)
    if order.midOffsetAtHalf != UNSET_DOUBLE:
        orderProto.midOffsetAtHalf = float(order.midOffsetAtHalf)
    if order.customerAccount:
        orderProto.customerAccount = order.customerAccount
    if order.professionalCustomer:
        orderProto.professionalCustomer = order.professionalCustomer
    if order.bondAccruedInterest:
        orderProto.bondAccruedInterest = order.bondAccruedInterest
    if order.includeOvernight:
        orderProto.includeOvernight = order.includeOvernight
    if isValidIntValue(order.manualOrderIndicator):
        orderProto.manualOrderIndicator = order.manualOrderIndicator
    if order.submitter:
        orderProto.submitter = order.submitter
    if order.autoCancelParent:
        orderProto.autoCancelParent = order.autoCancelParent
    if order.imbalanceOnly:
        orderProto.imbalanceOnly = order.imbalanceOnly

    return orderProto


def createConditionsProto(order: Order) -> list[OrderConditionProto]:
    orderConditionProtoList = []
    try:
        if order.conditions is not None and order.conditions:
            for orderCondition in order.conditions:
                orderConditionProto = None
                if isinstance(orderCondition, PriceCondition):
                    orderConditionProto = createPriceConditionProto(orderCondition)
                elif isinstance(orderCondition, TimeCondition):
                    orderConditionProto = createTimeConditionProto(orderCondition)
                elif isinstance(orderCondition, MarginCondition):
                    orderConditionProto = createMarginConditionProto(orderCondition)
                elif isinstance(orderCondition, ExecutionCondition):
                    orderConditionProto = createExecutionConditionProto(orderCondition)
                elif isinstance(orderCondition, VolumeCondition):
                    orderConditionProto = createVolumeConditionProto(orderCondition)
                elif isinstance(orderCondition, PercentChangeCondition):
                    orderConditionProto = createPercentChangeConditionProto(
                        orderCondition
                    )

                if orderConditionProto is not None:
                    orderConditionProtoList.append(orderConditionProto)

    except Exception:
        raise ClientException(
            588,
            "Error encoding protobuf - ",
            "Error encoding conditions",
        )

    return orderConditionProtoList


def createOrderComboLegs(contractProto: ContractProto) -> list[OrderComboLeg]:
    orderComboLegs = []
    comboLegProtoList = contractProto.comboLegs
    if comboLegProtoList:
        for comboLegProto in comboLegProtoList:
            orderComboLeg = OrderComboLeg()
            if comboLegProto.HasField("perLegPrice"):
                orderComboLeg.price = comboLegProto.perLegPrice
            orderComboLegs.append(orderComboLeg)

    return orderComboLegs


def createOrderConditionProto(
    orderCondition: OrderConditionType,
) -> OrderConditionProto:
    conditionType = orderCondition.condType
    # Returns True if conjuction is AND, False if OR
    isConjunctionConnection = orderCondition.conjunction == "a"
    orderConditionProto = OrderConditionProto()
    if isValidIntValue(conditionType):
        orderConditionProto.type = conditionType
    orderConditionProto.isConjunctionConnection = isConjunctionConnection
    return orderConditionProto


def createOperatorConditionProto(
    operatorCondition: OrderConditionType,
) -> OrderConditionProto:
    orderConditionProto = createOrderConditionProto(operatorCondition)
    operatorConditionProto = OrderConditionProto()
    operatorConditionProto.MergeFrom(orderConditionProto)
    if hasattr(operatorCondition, "isMore"):
        operatorConditionProto.isMore = operatorCondition.isMore
    return operatorConditionProto


def createContractConditionProto(
    contractCondition: OrderConditionType,
) -> OrderConditionProto:
    operatorConditionProto = createOperatorConditionProto(contractCondition)
    contractConditionProto = OrderConditionProto()
    contractConditionProto.MergeFrom(operatorConditionProto)
    if hasattr(contractCondition, "conId") and isValidIntValue(contractCondition.conId):
        contractConditionProto.conId = contractCondition.conId
    if hasattr(contractCondition, "exch"):
        contractConditionProto.exchange = contractCondition.exch
    return contractConditionProto


def createPriceConditionProto(priceCondition: PriceCondition) -> OrderConditionProto:
    contractConditionProto = createContractConditionProto(priceCondition)
    priceConditionProto = OrderConditionProto()
    priceConditionProto.MergeFrom(contractConditionProto)
    if priceCondition.price != UNSET_DOUBLE:
        priceConditionProto.price = priceCondition.price
    if isValidIntValue(priceCondition.triggerMethod):
        priceConditionProto.triggerMethod = priceCondition.triggerMethod
    return priceConditionProto


def createTimeConditionProto(timeCondition: TimeCondition) -> OrderConditionProto:
    operatorConditionProto = createOperatorConditionProto(timeCondition)
    timeConditionProto = OrderConditionProto()
    timeConditionProto.MergeFrom(operatorConditionProto)
    if timeCondition.time:
        timeConditionProto.time = timeCondition.time
    return timeConditionProto


def createMarginConditionProto(marginCondition: MarginCondition) -> OrderConditionProto:
    operatorConditionProto = createOperatorConditionProto(marginCondition)
    marginConditionProto = OrderConditionProto()
    marginConditionProto.MergeFrom(operatorConditionProto)
    if marginCondition.percent != UNSET_DOUBLE:
        marginConditionProto.percent = marginCondition.percent
    return marginConditionProto


def createExecutionConditionProto(
    executionCondition: ExecutionCondition,
) -> OrderConditionProto:
    orderConditionProto = createOrderConditionProto(executionCondition)
    executionConditionProto = OrderConditionProto()
    executionConditionProto.MergeFrom(orderConditionProto)
    if executionCondition.secType:
        executionConditionProto.secType = executionCondition.secType
    if executionCondition.exch:
        executionConditionProto.exchange = executionCondition.exch
    if executionCondition.symbol:
        executionConditionProto.symbol = executionCondition.symbol
    return executionConditionProto


def createVolumeConditionProto(volumeCondition: VolumeCondition) -> OrderConditionProto:
    contractConditionProto = createContractConditionProto(volumeCondition)
    volumeConditionProto = OrderConditionProto()
    volumeConditionProto.MergeFrom(contractConditionProto)
    if isValidIntValue(volumeCondition.volume):
        volumeConditionProto.volume = volumeCondition.volume
    return volumeConditionProto


def createPercentChangeConditionProto(
    percentChangeCondition: PercentChangeCondition,
) -> OrderConditionProto:
    contractConditionProto = createContractConditionProto(percentChangeCondition)
    percentChangeConditionProto = OrderConditionProto()
    percentChangeConditionProto.MergeFrom(contractConditionProto)
    if percentChangeCondition.changePercent != UNSET_DOUBLE:
        percentChangeConditionProto.changePercent = percentChangeCondition.changePercent
    return percentChangeConditionProto


def createSoftDollarTierProto(order: Order) -> SoftDollarTierProto:
    softDollarTierProto = None
    tier = order.softDollarTier
    if tier is not None:
        softDollarTierProto = SoftDollarTierProto()
        if tier.name:
            softDollarTierProto.name = tier.name
        if tier.val:
            softDollarTierProto.value = tier.val
        if tier.displayName:
            softDollarTierProto.displayName = tier.displayName
    return softDollarTierProto


def createOrder(
    orderId: int, contractProto: ContractProto, orderProto: OrderProto
) -> Order:
    order = Order()
    if isValidIntValue(orderId):
        order.orderId = orderId
    if orderProto.HasField("orderId"):
        order.orderId = orderProto.orderId
    if orderProto.HasField("action"):
        order.action = orderProto.action
    if orderProto.HasField("totalQuantity"):
        order.totalQuantity = float(orderProto.totalQuantity)
    if orderProto.HasField("orderType"):
        order.orderType = orderProto.orderType
    if orderProto.HasField("lmtPrice"):
        order.lmtPrice = orderProto.lmtPrice
    if orderProto.HasField("auxPrice"):
        order.auxPrice = orderProto.auxPrice
    if orderProto.HasField("tif"):
        order.tif = orderProto.tif
    if orderProto.HasField("ocaGroup"):
        order.ocaGroup = orderProto.ocaGroup
    if orderProto.HasField("account"):
        order.account = orderProto.account
    if orderProto.HasField("openClose"):
        order.openClose = orderProto.openClose
    if orderProto.HasField("origin"):
        order.origin = orderProto.origin
    if orderProto.HasField("orderRef"):
        order.orderRef = orderProto.orderRef
    if orderProto.HasField("clientId"):
        order.clientId = orderProto.clientId
    if orderProto.HasField("permId"):
        order.permId = orderProto.permId
    if orderProto.HasField("outsideRth"):
        order.outsideRth = orderProto.outsideRth
    if orderProto.HasField("hidden"):
        order.hidden = orderProto.hidden
    if orderProto.HasField("discretionaryAmt"):
        order.discretionaryAmt = orderProto.discretionaryAmt
    if orderProto.HasField("goodAfterTime"):
        order.goodAfterTime = orderProto.goodAfterTime
    if orderProto.HasField("faGroup"):
        order.faGroup = orderProto.faGroup
    if orderProto.HasField("faMethod"):
        order.faMethod = orderProto.faMethod
    if orderProto.HasField("faPercentage"):
        order.faPercentage = orderProto.faPercentage
    if orderProto.HasField("modelCode"):
        order.modelCode = orderProto.modelCode
    if orderProto.HasField("goodTillDate"):
        order.goodTillDate = orderProto.goodTillDate
    if orderProto.HasField("rule80A"):
        order.rule80A = orderProto.rule80A
    if orderProto.HasField("percentOffset"):
        order.percentOffset = orderProto.percentOffset
    if orderProto.HasField("settlingFirm"):
        order.settlingFirm = orderProto.settlingFirm
    if orderProto.HasField("shortSaleSlot"):
        order.shortSaleSlot = orderProto.shortSaleSlot
    if orderProto.HasField("designatedLocation"):
        order.designatedLocation = orderProto.designatedLocation
    if orderProto.HasField("exemptCode"):
        order.exemptCode = orderProto.exemptCode
    if orderProto.HasField("startingPrice"):
        order.startingPrice = orderProto.startingPrice
    if orderProto.HasField("stockRefPrice"):
        order.stockRefPrice = orderProto.stockRefPrice
    if orderProto.HasField("delta"):
        order.delta = orderProto.delta
    if orderProto.HasField("stockRangeLower"):
        order.stockRangeLower = orderProto.stockRangeLower
    if orderProto.HasField("stockRangeUpper"):
        order.stockRangeUpper = orderProto.stockRangeUpper
    if orderProto.HasField("displaySize"):
        order.displaySize = orderProto.displaySize
    if orderProto.HasField("blockOrder"):
        order.blockOrder = orderProto.blockOrder
    if orderProto.HasField("sweepToFill"):
        order.sweepToFill = orderProto.sweepToFill
    if orderProto.HasField("allOrNone"):
        order.allOrNone = orderProto.allOrNone
    if orderProto.HasField("minQty"):
        order.minQty = orderProto.minQty
    if orderProto.HasField("ocaType"):
        order.ocaType = orderProto.ocaType
    if orderProto.HasField("parentId"):
        order.parentId = orderProto.parentId
    if orderProto.HasField("triggerMethod"):
        order.triggerMethod = orderProto.triggerMethod
    if orderProto.HasField("volatility"):
        order.volatility = orderProto.volatility
    if orderProto.HasField("volatilityType"):
        order.volatilityType = orderProto.volatilityType
    if orderProto.HasField("deltaNeutralOrderType"):
        order.deltaNeutralOrderType = orderProto.deltaNeutralOrderType
    if orderProto.HasField("deltaNeutralAuxPrice"):
        order.deltaNeutralAuxPrice = orderProto.deltaNeutralAuxPrice
    if orderProto.HasField("deltaNeutralConId"):
        order.deltaNeutralConId = orderProto.deltaNeutralConId
    if orderProto.HasField("deltaNeutralSettlingFirm"):
        order.deltaNeutralSettlingFirm = orderProto.deltaNeutralSettlingFirm
    if orderProto.HasField("deltaNeutralClearingAccount"):
        order.deltaNeutralClearingAccount = orderProto.deltaNeutralClearingAccount
    if orderProto.HasField("deltaNeutralClearingIntent"):
        order.deltaNeutralClearingIntent = orderProto.deltaNeutralClearingIntent
    if orderProto.HasField("deltaNeutralOpenClose"):
        order.deltaNeutralOpenClose = orderProto.deltaNeutralOpenClose
    if orderProto.HasField("deltaNeutralShortSale"):
        order.deltaNeutralShortSale = orderProto.deltaNeutralShortSale
    if orderProto.HasField("deltaNeutralShortSaleSlot"):
        order.deltaNeutralShortSaleSlot = orderProto.deltaNeutralShortSaleSlot
    if orderProto.HasField("deltaNeutralDesignatedLocation"):
        order.deltaNeutralDesignatedLocation = orderProto.deltaNeutralDesignatedLocation
    if orderProto.HasField("continuousUpdate"):
        order.continuousUpdate = orderProto.continuousUpdate
    if orderProto.HasField("referencePriceType"):
        order.referencePriceType = orderProto.referencePriceType
    if orderProto.HasField("trailStopPrice"):
        order.trailStopPrice = orderProto.trailStopPrice
    if orderProto.HasField("trailingPercent"):
        order.trailingPercent = orderProto.trailingPercent

    orderComboLegs = createOrderComboLegs(contractProto)
    if orderComboLegs is not None and orderComboLegs:
        order.orderComboLegs = orderComboLegs

    order.smartComboRoutingParams = createTagValueList(
        orderProto.smartComboRoutingParams
    )

    if orderProto.HasField("scaleInitLevelSize"):
        order.scaleInitLevelSize = orderProto.scaleInitLevelSize
    if orderProto.HasField("scaleSubsLevelSize"):
        order.scaleSubsLevelSize = orderProto.scaleSubsLevelSize
    if orderProto.HasField("scalePriceIncrement"):
        order.scalePriceIncrement = orderProto.scalePriceIncrement
    if orderProto.HasField("scalePriceAdjustValue"):
        order.scalePriceAdjustValue = orderProto.scalePriceAdjustValue
    if orderProto.HasField("scalePriceAdjustInterval"):
        order.scalePriceAdjustInterval = orderProto.scalePriceAdjustInterval
    if orderProto.HasField("scaleProfitOffset"):
        order.scaleProfitOffset = orderProto.scaleProfitOffset
    if orderProto.HasField("scaleAutoReset"):
        order.scaleAutoReset = orderProto.scaleAutoReset
    if orderProto.HasField("scaleInitPosition"):
        order.scaleInitPosition = orderProto.scaleInitPosition
    if orderProto.HasField("scaleInitFillQty"):
        order.scaleInitFillQty = orderProto.scaleInitFillQty
    if orderProto.HasField("scaleRandomPercent"):
        order.scaleRandomPercent = orderProto.scaleRandomPercent
    if orderProto.HasField("hedgeType"):
        order.hedgeType = orderProto.hedgeType
    if (
        orderProto.HasField("hedgeType")
        and orderProto.HasField("hedgeParam")
        and orderProto.hedgeType
    ):
        order.hedgeParam = orderProto.hedgeParam
    if orderProto.HasField("optOutSmartRouting"):
        order.optOutSmartRouting = orderProto.optOutSmartRouting
    if orderProto.HasField("clearingAccount"):
        order.clearingAccount = orderProto.clearingAccount
    if orderProto.HasField("clearingIntent"):
        order.clearingIntent = orderProto.clearingIntent
    if orderProto.HasField("notHeld"):
        order.notHeld = orderProto.notHeld

    if orderProto.HasField("algoStrategy"):
        order.algoStrategy = orderProto.algoStrategy
        order.algoParams = createTagValueList(orderProto.algoParams)

    if orderProto.HasField("solicited"):
        order.solicited = orderProto.solicited
    if orderProto.HasField("whatIf"):
        order.whatIf = orderProto.whatIf
    if orderProto.HasField("randomizeSize"):
        order.randomizeSize = orderProto.randomizeSize
    if orderProto.HasField("randomizePrice"):
        order.randomizePrice = orderProto.randomizePrice
    if orderProto.HasField("referenceContractId"):
        order.referenceContractId = orderProto.referenceContractId
    if orderProto.HasField("isPeggedChangeAmountDecrease"):
        order.isPeggedChangeAmountDecrease = orderProto.isPeggedChangeAmountDecrease
    if orderProto.HasField("peggedChangeAmount"):
        order.peggedChangeAmount = orderProto.peggedChangeAmount
    if orderProto.HasField("referenceChangeAmount"):
        order.referenceChangeAmount = orderProto.referenceChangeAmount
    if orderProto.HasField("referenceExchangeId"):
        order.referenceExchangeId = orderProto.referenceExchangeId

    conditions = createOrderConditions(orderProto)
    if conditions is not None and conditions:
        order.conditions = conditions
    if orderProto.HasField("conditionsIgnoreRth"):
        order.conditionsIgnoreRth = orderProto.conditionsIgnoreRth
    if orderProto.HasField("conditionsCancelOrder"):
        order.conditionsCancelOrder = orderProto.conditionsCancelOrder

    if orderProto.HasField("adjustedOrderType"):
        order.adjustedOrderType = orderProto.adjustedOrderType
    if orderProto.HasField("triggerPrice"):
        order.triggerPrice = orderProto.triggerPrice
    if orderProto.HasField("lmtPriceOffset"):
        order.lmtPriceOffset = orderProto.lmtPriceOffset
    if orderProto.HasField("adjustedStopPrice"):
        order.adjustedStopPrice = orderProto.adjustedStopPrice
    if orderProto.HasField("adjustedStopLimitPrice"):
        order.adjustedStopLimitPrice = orderProto.adjustedStopLimitPrice
    if orderProto.HasField("adjustedTrailingAmount"):
        order.adjustedTrailingAmount = orderProto.adjustedTrailingAmount
    if orderProto.HasField("adjustableTrailingUnit"):
        order.adjustableTrailingUnit = orderProto.adjustableTrailingUnit

    softDollarTier = createSoftDollarTierFromOrder(orderProto)
    if softDollarTier is not None:
        order.softDollarTier = softDollarTier

    if orderProto.HasField("cashQty"):
        order.cashQty = orderProto.cashQty
    if orderProto.HasField("dontUseAutoPriceForHedge"):
        order.dontUseAutoPriceForHedge = orderProto.dontUseAutoPriceForHedge
    if orderProto.HasField("isOmsContainer"):
        order.isOmsContainer = orderProto.isOmsContainer
    if orderProto.HasField("discretionaryUpToLimitPrice"):
        order.discretionaryUpToLimitPrice = orderProto.discretionaryUpToLimitPrice
    if orderProto.HasField("usePriceMgmtAlgo"):
        order.usePriceMgmtAlgo = bool(orderProto.usePriceMgmtAlgo)
    if orderProto.HasField("duration"):
        order.duration = orderProto.duration
    if orderProto.HasField("postToAts"):
        order.postToAts = orderProto.postToAts
    if orderProto.HasField("autoCancelParent"):
        order.autoCancelParent = orderProto.autoCancelParent
    if orderProto.HasField("minTradeQty"):
        order.minTradeQty = orderProto.minTradeQty
    if orderProto.HasField("minCompeteSize"):
        order.minCompeteSize = orderProto.minCompeteSize
    if orderProto.HasField("competeAgainstBestOffset"):
        order.competeAgainstBestOffset = orderProto.competeAgainstBestOffset
    if orderProto.HasField("midOffsetAtWhole"):
        order.midOffsetAtWhole = orderProto.midOffsetAtWhole
    if orderProto.HasField("midOffsetAtHalf"):
        order.midOffsetAtHalf = orderProto.midOffsetAtHalf
    if orderProto.HasField("customerAccount"):
        order.customerAccount = orderProto.customerAccount
    if orderProto.HasField("professionalCustomer"):
        order.professionalCustomer = orderProto.professionalCustomer
    if orderProto.HasField("bondAccruedInterest"):
        order.bondAccruedInterest = orderProto.bondAccruedInterest
    if orderProto.HasField("includeOvernight"):
        order.includeOvernight = orderProto.includeOvernight
    if orderProto.HasField("extOperator"):
        order.extOperator = orderProto.extOperator
    if orderProto.HasField("manualOrderIndicator"):
        order.manualOrderIndicator = orderProto.manualOrderIndicator
    if orderProto.HasField("submitter"):
        order.submitter = orderProto.submitter
    if orderProto.HasField("imbalanceOnly"):
        order.imbalanceOnly = orderProto.imbalanceOnly
    if orderProto.HasField("autoCancelDate"):
        order.autoCancelDate = orderProto.autoCancelDate
    if orderProto.HasField("filledQuantity"):
        order.filledQuantity = Decimal(orderProto.filledQuantity)
    if orderProto.HasField("refFuturesConId"):
        order.refFuturesConId = orderProto.refFuturesConId
    if orderProto.HasField("shareholder"):
        order.shareholder = orderProto.shareholder
    if orderProto.HasField("routeMarketableToBbo"):
        order.routeMarketableToBbo = orderProto.routeMarketableToBbo
    if orderProto.HasField("parentPermId"):
        order.parentPermId = orderProto.parentPermId

    return order


def createOrderConditions(orderProto: OrderProto) -> list[OrderConditionType]:
    orderConditions: list[OrderConditionType] = []
    orderConditionsProtoList = []
    if orderProto.conditions is not None:
        orderConditionsProtoList = orderProto.conditions

    if orderConditionsProtoList:
        for orderConditionProto in orderConditionsProtoList:
            conditionType = (
                orderConditionProto.type if orderConditionProto.HasField("type") else 0
            )

            condition: OrderConditionType | None = None
            if PriceCondition.condType == conditionType:
                condition = createPriceCondition(orderConditionProto)
            elif TimeCondition.condType == conditionType:
                condition = createTimeCondition(orderConditionProto)
            elif MarginCondition.condType == conditionType:
                condition = createMarginCondition(orderConditionProto)
            elif ExecutionCondition.condType == conditionType:
                condition = createExecutionCondition(orderConditionProto)
            elif VolumeCondition.condType == conditionType:
                condition = createVolumeCondition(orderConditionProto)
            elif PercentChangeCondition.condType == conditionType:
                condition = createPercentChangeCondition(orderConditionProto)

            if condition is not None:
                orderConditions.append(condition)

    return orderConditions


def setConditionFields(
    orderConditionProto: OrderConditionProto, orderCondition: OrderCondition
):
    if orderConditionProto.HasField("isConjunctionConnection"):
        orderCondition.conjunction = (
            "a" if orderConditionProto.isConjunctionConnection else "o"
        )


def setOperatorConditionFields(
    orderConditionProto: OrderConditionProto, operatorCondition: OrderConditionType
):
    setConditionFields(orderConditionProto, operatorCondition)
    if orderConditionProto.HasField("isMore"):
        if isinstance(
            operatorCondition,
            (
                PriceCondition,
                TimeCondition,
                MarginCondition,
                VolumeCondition,
                PercentChangeCondition,
            ),
        ):
            operatorCondition.isMore = orderConditionProto.isMore


def setContractConditionFields(
    orderConditionProto: OrderConditionProto, contractCondition: OrderConditionType
):
    setOperatorConditionFields(orderConditionProto, contractCondition)
    if orderConditionProto.HasField("conId"):
        if isinstance(
            contractCondition,
            (PriceCondition, VolumeCondition, PercentChangeCondition),
        ):
            contractCondition.conId = orderConditionProto.conId
    if orderConditionProto.HasField("exchange"):
        if isinstance(
            contractCondition,
            (
                PriceCondition,
                ExecutionCondition,
                VolumeCondition,
                PercentChangeCondition,
            ),
        ):
            contractCondition.exch = orderConditionProto.exchange


def createPriceCondition(orderConditionProto: OrderConditionProto) -> PriceCondition:
    priceCondition = PriceCondition()
    setContractConditionFields(orderConditionProto, priceCondition)
    if orderConditionProto.HasField("price"):
        priceCondition.price = orderConditionProto.price
    if orderConditionProto.HasField("triggerMethod"):
        priceCondition.triggerMethod = orderConditionProto.triggerMethod
    return priceCondition


def createTimeCondition(orderConditionProto: OrderConditionProto) -> TimeCondition:
    timeCondition = TimeCondition()
    setOperatorConditionFields(orderConditionProto, timeCondition)
    if orderConditionProto.HasField("time"):
        timeCondition.time = orderConditionProto.time
    return timeCondition


def createMarginCondition(orderConditionProto: OrderConditionProto) -> MarginCondition:
    marginCondition = MarginCondition()
    setOperatorConditionFields(orderConditionProto, marginCondition)
    if orderConditionProto.HasField("percent"):
        marginCondition.percent = orderConditionProto.percent
    return marginCondition


def createExecutionCondition(
    orderConditionProto: OrderConditionProto,
) -> ExecutionCondition:
    executionCondition = ExecutionCondition()
    setConditionFields(orderConditionProto, executionCondition)
    if orderConditionProto.HasField("secType"):
        executionCondition.secType = orderConditionProto.secType
    if orderConditionProto.HasField("exchange"):
        executionCondition.exch = orderConditionProto.exchange
    if orderConditionProto.HasField("symbol"):
        executionCondition.symbol = orderConditionProto.symbol
    return executionCondition


def createVolumeCondition(orderConditionProto: OrderConditionProto) -> VolumeCondition:
    volumeCondition = VolumeCondition()
    setContractConditionFields(orderConditionProto, volumeCondition)
    if orderConditionProto.HasField("volume"):
        volumeCondition.volume = orderConditionProto.volume
    return volumeCondition


def createPercentChangeCondition(
    orderConditionProto: OrderConditionProto,
) -> PercentChangeCondition:
    percentChangeCondition = PercentChangeCondition()
    setContractConditionFields(orderConditionProto, percentChangeCondition)
    if orderConditionProto.HasField("changePercent"):
        percentChangeCondition.changePercent = orderConditionProto.changePercent
    return percentChangeCondition


def createSoftDollarTierFromOrder(orderProto: OrderProto) -> SoftDollarTier | None:
    softDollarTierProto = None
    if orderProto.softDollarTier is not None:
        softDollarTierProto = orderProto.softDollarTier

    softDollarTier = None
    if softDollarTierProto is not None:
        created_tier = createSoftDollarTier(softDollarTierProto)
        if created_tier:  # Check if the created tier is not empty
            softDollarTier = created_tier

    return softDollarTier


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


def createTagValueList(protoMap: dict[str, str]) -> list[TagValue]:
    tagValueList = []
    if protoMap is not None and protoMap:
        for tag, value in protoMap.items():
            tagValue = TagValue(tag, value)
            tagValueList.append(tagValue)
    return tagValueList


def createOrderState(orderStateProto: OrderStateProto) -> OrderState:
    orderState = OrderState()
    if orderStateProto.HasField("status"):
        orderState.status = orderStateProto.status
    if orderStateProto.HasField("initMarginBefore"):
        orderState.initMarginBefore = orderStateProto.initMarginBefore
    if orderStateProto.HasField("maintMarginBefore"):
        orderState.maintMarginBefore = orderStateProto.maintMarginBefore
    if orderStateProto.HasField("equityWithLoanBefore"):
        orderState.equityWithLoanBefore = orderStateProto.equityWithLoanBefore
    if orderStateProto.HasField("initMarginChange"):
        orderState.initMarginChange = orderStateProto.initMarginChange
    if orderStateProto.HasField("maintMarginChange"):
        orderState.maintMarginChange = orderStateProto.maintMarginChange
    if orderStateProto.HasField("equityWithLoanChange"):
        orderState.equityWithLoanChange = orderStateProto.equityWithLoanChange
    if orderStateProto.HasField("initMarginAfter"):
        orderState.initMarginAfter = orderStateProto.initMarginAfter
    if orderStateProto.HasField("maintMarginAfter"):
        orderState.maintMarginAfter = orderStateProto.maintMarginAfter
    if orderStateProto.HasField("equityWithLoanAfter"):
        orderState.equityWithLoanAfter = orderStateProto.equityWithLoanAfter
    if orderStateProto.HasField("commissionAndFees"):
        orderState.commission = orderStateProto.commissionAndFees
    if orderStateProto.HasField("minCommissionAndFees"):
        orderState.minCommission = orderStateProto.minCommissionAndFees
    if orderStateProto.HasField("maxCommissionAndFees"):
        orderState.maxCommission = orderStateProto.maxCommissionAndFees
    if orderStateProto.HasField("commissionAndFeesCurrency"):
        orderState.commissionCurrency = orderStateProto.commissionAndFeesCurrency
    if orderStateProto.HasField("warningText"):
        orderState.warningText = orderStateProto.warningText
    if orderStateProto.HasField("marginCurrency"):
        orderState.marginCurrency = orderStateProto.marginCurrency
    if orderStateProto.HasField("initMarginBeforeOutsideRTH"):
        orderState.initMarginBeforeOutsideRTH = (
            orderStateProto.initMarginBeforeOutsideRTH
        )

    if orderStateProto.HasField("maintMarginBeforeOutsideRTH"):
        orderState.maintMarginBeforeOutsideRTH = (
            orderStateProto.maintMarginBeforeOutsideRTH
        )

    if orderStateProto.HasField("equityWithLoanBeforeOutsideRTH"):
        orderState.equityWithLoanBeforeOutsideRTH = (
            orderStateProto.equityWithLoanBeforeOutsideRTH
        )

    if orderStateProto.HasField("initMarginChangeOutsideRTH"):
        orderState.initMarginChangeOutsideRTH = (
            orderStateProto.initMarginChangeOutsideRTH
        )

    if orderStateProto.HasField("maintMarginChangeOutsideRTH"):
        orderState.maintMarginChangeOutsideRTH = (
            orderStateProto.maintMarginChangeOutsideRTH
        )

    if orderStateProto.HasField("equityWithLoanChangeOutsideRTH"):
        orderState.equityWithLoanChangeOutsideRTH = (
            orderStateProto.equityWithLoanChangeOutsideRTH
        )

    if orderStateProto.HasField("initMarginAfterOutsideRTH"):
        orderState.initMarginAfterOutsideRTH = orderStateProto.initMarginAfterOutsideRTH

    if orderStateProto.HasField("maintMarginAfterOutsideRTH"):
        orderState.maintMarginAfterOutsideRTH = (
            orderStateProto.maintMarginAfterOutsideRTH
        )

    if orderStateProto.HasField("equityWithLoanAfterOutsideRTH"):
        orderState.equityWithLoanAfterOutsideRTH = (
            orderStateProto.equityWithLoanAfterOutsideRTH
        )

    if orderStateProto.HasField("suggestedSize"):
        orderState.suggestedSize = Decimal(orderStateProto.suggestedSize)
    if orderStateProto.HasField("rejectReason"):
        orderState.rejectReason = orderStateProto.rejectReason

    orderAllocations = createOrderAllocations(orderStateProto)
    if orderAllocations is not None and orderAllocations:
        orderState.orderAllocations = orderAllocations

    if orderStateProto.HasField("completedTime"):
        orderState.completedTime = orderStateProto.completedTime
    if orderStateProto.HasField("completedStatus"):
        orderState.completedStatus = orderStateProto.completedStatus

    return orderState


def createOrderAllocations(orderStateProto: OrderStateProto) -> list[OrderAllocation]:
    orderAllocations = []
    orderAllocationProtoList = []
    if orderStateProto.orderAllocations is not None:
        orderAllocationProtoList = orderStateProto.orderAllocations
    if orderAllocationProtoList:
        for orderAllocationProto in orderAllocationProtoList:
            orderAllocation = OrderAllocation()
            if orderAllocationProto.HasField("account"):
                orderAllocation.account = orderAllocationProto.account
            if orderAllocationProto.HasField("position"):
                orderAllocation.position = Decimal(orderAllocationProto.position)
            if orderAllocationProto.HasField("positionDesired"):
                orderAllocation.positionDesired = Decimal(
                    orderAllocationProto.positionDesired
                )
            if orderAllocationProto.HasField("positionAfter"):
                orderAllocation.positionAfter = Decimal(
                    orderAllocationProto.positionAfter
                )
            if orderAllocationProto.HasField("desiredAllocQty"):
                orderAllocation.desiredAllocQty = Decimal(
                    orderAllocationProto.desiredAllocQty
                )
            if orderAllocationProto.HasField("allowedAllocQty"):
                orderAllocation.allowedAllocQty = Decimal(
                    orderAllocationProto.allowedAllocQty
                )
            if orderAllocationProto.HasField("isMonetary"):
                orderAllocation.isMonetary = orderAllocationProto.isMonetary
            orderAllocations.append(orderAllocation)
    return orderAllocations


def createContractFromExecutionDetails(
    exec_details_proto: ExecutionDetailsProto,
) -> Contract:
    """
    Create a Contract object from a Protobuf ExecutionDetails message.
    """
    return createContract(exec_details_proto.contract)


def createOrderStatus(orderStatusProto: OrderStatusProto) -> OrderStatus:
    orderStatus = OrderStatus()
    if orderStatusProto.HasField("orderId"):
        orderStatus.orderId = orderStatusProto.orderId
    if orderStatusProto.HasField("status"):
        orderStatus.status = orderStatusProto.status
    if orderStatusProto.HasField("filled"):
        orderStatus.filled = Decimal(orderStatusProto.filled)
    if orderStatusProto.HasField("remaining"):
        orderStatus.remaining = Decimal(orderStatusProto.remaining)
    if orderStatusProto.HasField("avgFillPrice"):
        orderStatus.avgFillPrice = Decimal(str(orderStatusProto.avgFillPrice))
    if orderStatusProto.HasField("permId"):
        orderStatus.permId = orderStatusProto.permId
    if orderStatusProto.HasField("parentId"):
        orderStatus.parentId = orderStatusProto.parentId
    if orderStatusProto.HasField("lastFillPrice"):
        orderStatus.lastFillPrice = Decimal(str(orderStatusProto.lastFillPrice))
    if orderStatusProto.HasField("clientId"):
        orderStatus.clientId = orderStatusProto.clientId
    if orderStatusProto.HasField("whyHeld"):
        orderStatus.whyHeld = orderStatusProto.whyHeld
    if orderStatusProto.HasField("mktCapPrice"):
        orderStatus.mktCapPrice = Decimal(str(orderStatusProto.mktCapPrice))
    return orderStatus


def createExecution(executionProto: ExecutionProto) -> Execution:
    execution = Execution()
    if executionProto.HasField("execId"):
        execution.execId = executionProto.execId
    if executionProto.HasField("time"):
        parsed_time = parseIBDatetime(executionProto.time)
        if not isinstance(parsed_time, dt.datetime):
            execution.time = dt.datetime(
                parsed_time.year, parsed_time.month, parsed_time.day
            )
        else:
            execution.time = parsed_time
    if executionProto.HasField("acctNumber"):
        execution.acctNumber = executionProto.acctNumber
    if executionProto.HasField("exchange"):
        execution.exchange = executionProto.exchange
    if executionProto.HasField("side"):
        execution.side = executionProto.side
    if executionProto.HasField("shares"):
        execution.shares = float(executionProto.shares)
    if executionProto.HasField("price"):
        execution.price = executionProto.price
    if executionProto.HasField("permId"):
        execution.permId = executionProto.permId
    if executionProto.HasField("clientId"):
        execution.clientId = executionProto.clientId
    if executionProto.HasField("orderId"):
        execution.orderId = executionProto.orderId
    if executionProto.HasField("isLiquidation"):
        execution.liquidation = 1 if executionProto.isLiquidation else 0
    if executionProto.HasField("cumQty"):
        execution.cumQty = float(executionProto.cumQty)
    if executionProto.HasField("avgPrice"):
        execution.avgPrice = executionProto.avgPrice
    if executionProto.HasField("orderRef"):
        execution.orderRef = executionProto.orderRef
    if executionProto.HasField("evRule"):
        execution.evRule = executionProto.evRule
    if executionProto.HasField("evMultiplier"):
        execution.evMultiplier = executionProto.evMultiplier
    if executionProto.HasField("modelCode"):
        execution.modelCode = executionProto.modelCode
    if executionProto.HasField("lastLiquidity"):
        execution.lastLiquidity = executionProto.lastLiquidity
    if executionProto.HasField("isPriceRevisionPending"):
        execution.pendingPriceRevision = executionProto.isPriceRevisionPending
    if executionProto.HasField("submitter"):
        execution.submitter = executionProto.submitter
    if executionProto.HasField("optExerciseOrLapseType"):
        execution.optExerciseOrLapseType = getEnumTypeFromString(
            OptionExerciseType, executionProto.optExerciseOrLapseType
        )
    return execution


def createFill(execDetailsProto: ExecutionDetailsProto) -> Fill:
    contract = createContract(execDetailsProto.contract)
    execution = createExecution(execDetailsProto.execution)
    return Fill(
        contract, execution, CommissionReport(execId=execution.execId), execution.time
    )


def createTradeFromOpenOrder(
    openOrderProto: OpenOrderProto,
) -> tuple[Trade | None, OrderState | None]:
    if not openOrderProto.HasField("contract"):
        return (None, None)
    contract = createContract(openOrderProto.contract)
    if not openOrderProto.HasField("order"):
        return (None, None)
    order = createOrder(
        openOrderProto.order.orderId, openOrderProto.contract, openOrderProto.order
    )
    if not openOrderProto.HasField("orderState"):
        return (None, None)
    orderState = createOrderState(openOrderProto.orderState)
    orderStatus = OrderStatus(orderId=order.orderId, status=orderState.status)
    return Trade(contract, order, orderStatus, [], []), orderState


def createCommissionReport(
    commissionReportProto: CommissionReportProto,
) -> CommissionReport:
    commissionReport = CommissionReport()
    commissionReport.execId = (
        commissionReportProto.execId if commissionReportProto.HasField("execId") else ""
    )
    commissionReport.commission = (
        commissionReportProto.commissionAndFees
        if commissionReportProto.HasField("commissionAndFees")
        else 0.0
    )
    commissionReport.currency = (
        commissionReportProto.currency
        if commissionReportProto.HasField("currency")
        else ""
    )
    commissionReport.realizedPNL = (
        commissionReportProto.realizedPNL
        if commissionReportProto.HasField("realizedPNL")
        else 0.0
    )
    commissionReport.yield_ = (
        commissionReportProto.bondYield
        if commissionReportProto.HasField("bondYield")
        else 0.0
    )
    commissionReport.yieldRedemptionDate = (
        int(commissionReportProto.yieldRedemptionDate)
        if commissionReportProto.HasField("yieldRedemptionDate")
        else 0
    )
    return commissionReport


def createExecutionRequestProto(
    reqId: int, execFilter: ExecutionFilter
) -> ExecutionRequestProto:
    """
    Create an ExecutionRequest protobuf message.
    """
    # execution filter
    executionFilterProto = ExecutionFilterProto()
    if execFilter.clientId is not None:
        executionFilterProto.clientId = execFilter.clientId
    if execFilter.acctCode is not None:
        executionFilterProto.acctCode = execFilter.acctCode
    if execFilter.time is not None:
        executionFilterProto.time = execFilter.time
    if execFilter.symbol is not None:
        executionFilterProto.symbol = execFilter.symbol
    if execFilter.secType is not None:
        executionFilterProto.secType = execFilter.secType
    if execFilter.exchange is not None:
        executionFilterProto.exchange = execFilter.exchange
    if execFilter.side is not None:
        executionFilterProto.side = execFilter.side
    if execFilter.lastNDays != UNSET_INTEGER:
        executionFilterProto.lastNDays = execFilter.lastNDays
    if execFilter.specificDates is not None and execFilter.specificDates:
        executionFilterProto.specificDates.extend(execFilter.specificDates)

    # execution request
    executionRequestProto = ExecutionRequestProto()
    executionRequestProto.reqId = reqId
    executionRequestProto.executionFilter.CopyFrom(executionFilterProto)
    return executionRequestProto


def createOrderCancelProto(orderCancel: OrderCancel) -> OrderCancelProto:
    if orderCancel is None:
        return None
    orderCancelProto = OrderCancelProto()
    if orderCancel.manualOrderCancelTime:
        orderCancelProto.manualOrderCancelTime = orderCancel.manualOrderCancelTime
    if orderCancel.extOperator:
        orderCancelProto.extOperator = orderCancel.extOperator
    if isValidIntValue(orderCancel.manualOrderIndicator):
        orderCancelProto.manualOrderIndicator = orderCancel.manualOrderIndicator
    return orderCancelProto


def createGlobalCancelRequestProto(
    orderCancel: OrderCancel,
) -> GlobalCancelRequestProto:
    globalCancelRequestProto = GlobalCancelRequestProto()
    orderCancelProto = createOrderCancelProto(orderCancel)
    if orderCancelProto is not None:
        globalCancelRequestProto.orderCancel.CopyFrom(orderCancelProto)
    return globalCancelRequestProto


def createCancelOrderRequestProto(
    orderId: int, orderCancel: OrderCancel
) -> CancelOrderRequestProto:
    cancelOrderRequestProto = CancelOrderRequestProto()
    if isValidIntValue(orderId):
        cancelOrderRequestProto.orderId = orderId
    orderCancelProto = createOrderCancelProto(orderCancel)
    if orderCancelProto is not None:
        cancelOrderRequestProto.orderCancel.CopyFrom(orderCancelProto)
    return cancelOrderRequestProto


def createExerciseOptionsRequestProto(
    orderId: int,
    contract: Contract,
    exerciseAction: int,
    exerciseQuantity: int,
    account: str,
    override: bool,
    manualOrderTime: str,
    customerAccount: str,
    professionalCustomer: bool,
) -> ExerciseOptionsRequestProto:
    exerciseOptionsRequestProto = ExerciseOptionsRequestProto()
    if isValidIntValue(orderId):
        exerciseOptionsRequestProto.orderId = orderId
    contractProto = createContractProto(contract, None)
    if contractProto is not None:
        exerciseOptionsRequestProto.contract.CopyFrom(contractProto)
    if isValidIntValue(exerciseAction):
        exerciseOptionsRequestProto.exerciseAction = exerciseAction
    if isValidIntValue(exerciseQuantity):
        exerciseOptionsRequestProto.exerciseQuantity = exerciseQuantity
    if account:
        exerciseOptionsRequestProto.account = account
    if override:
        exerciseOptionsRequestProto.override = override
    if manualOrderTime:
        exerciseOptionsRequestProto.manualOrderTime = manualOrderTime
    if customerAccount:
        exerciseOptionsRequestProto.customerAccount = customerAccount
    if professionalCustomer:
        exerciseOptionsRequestProto.professionalCustomer = professionalCustomer
    return exerciseOptionsRequestProto
