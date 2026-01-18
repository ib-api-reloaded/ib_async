from datetime import datetime
from decimal import Decimal

import pytest

from ib_async.contract import ComboLeg, Contract
from ib_async.objects import (
    CommissionReport,
    Execution,
    ExecutionFilter,
    Fill,
    OptionExerciseType,
    SoftDollarTier,
)
from ib_async.order import (
    ExecutionCondition,
    MarginCondition,
    Order,
    OrderCancel,
    OrderComboLeg,
    OrderState,
    OrderStatus,
    PercentChangeCondition,
    PriceCondition,
    TimeCondition,
    Trade,
    VolumeCondition,
)
from ib_async.protobuf.CancelOrderRequest_pb2 import (
    CancelOrderRequest as CancelOrderRequestProto,
)
from ib_async.protobuf.ComboLeg_pb2 import ComboLeg as ComboLegProto
from ib_async.protobuf.CommissionAndFeesReport_pb2 import (
    CommissionAndFeesReport as CommissionReportProto,
)
from ib_async.protobuf.Contract_pb2 import Contract as ContractProto
from ib_async.protobuf.Execution_pb2 import Execution as ExecutionProto
from ib_async.protobuf.ExecutionDetails_pb2 import (
    ExecutionDetails as ExecutionDetailsProto,
)
from ib_async.protobuf.ExecutionRequest_pb2 import (
    ExecutionRequest as ExecutionRequestProto,
)
from ib_async.protobuf.ExerciseOptionsRequest_pb2 import (
    ExerciseOptionsRequest as ExerciseOptionsRequestProto,
)
from ib_async.protobuf.GlobalCancelRequest_pb2 import (
    GlobalCancelRequest as GlobalCancelRequestProto,
)
from ib_async.protobuf.OpenOrder_pb2 import OpenOrder as OpenOrderProto
from ib_async.protobuf.Order_pb2 import Order as OrderProto
from ib_async.protobuf.OrderCancel_pb2 import OrderCancel as OrderCancelProto
from ib_async.protobuf.OrderCondition_pb2 import OrderCondition as OrderConditionProto
from ib_async.protobuf.OrderState_pb2 import OrderState as OrderStateProto
from ib_async.protobuf.OrderStatus_pb2 import OrderStatus as OrderStatusProto
from ib_async.protobuf.PlaceOrderRequest_pb2 import (
    PlaceOrderRequest as PlaceOrderRequestProto,
)
from ib_async.protobuf.SoftDollarTier_pb2 import SoftDollarTier as SoftDollarTierProto
from ib_async.protobuf_converters.trade_converters import (
    createCancelOrderRequestProto,
    createCommissionReport,
    createConditionsProto,
    createContractConditionProto,
    createContractFromExecutionDetails,
    createExecution,
    createExecutionCondition,
    createExecutionConditionProto,
    createExecutionRequestProto,
    createExerciseOptionsRequestProto,
    createFill,
    createGlobalCancelRequestProto,
    createMarginCondition,
    createMarginConditionProto,
    createOperatorConditionProto,
    createOrder,
    createOrderAllocations,
    createOrderCancelProto,
    createOrderComboLegs,
    createOrderConditionProto,
    createOrderConditions,
    createOrderProto,
    createOrderState,
    createOrderStatus,
    createPercentChangeCondition,
    createPercentChangeConditionProto,
    createPlaceOrderRequestProto,
    createPriceCondition,
    createPriceConditionProto,
    createSoftDollarTier,
    createSoftDollarTierFromOrder,
    createSoftDollarTierProto,
    createTagValueList,
    createTimeCondition,
    createTimeConditionProto,
    createTradeFromOpenOrder,
    createVolumeCondition,
    createVolumeConditionProto,
    setConditionFields,
    setContractConditionFields,
    setOperatorConditionFields,
)


class TestTradeConverters:
    def test_createPlaceOrderRequestProto(self):
        contract = Contract(conId=123, symbol="SPY", secType="STK", exchange="SMART")
        order = Order(
            orderId=1, action="BUY", totalQuantity=100, orderType="LMT", lmtPrice=400.0
        )

        proto = createPlaceOrderRequestProto(order.orderId, contract, order)

        assert isinstance(proto, PlaceOrderRequestProto)
        assert proto.orderId == 1
        assert proto.contract.conId == 123
        assert proto.order.action == "BUY"
        assert proto.order.totalQuantity == "100"
        assert proto.order.orderType == "LMT"
        assert proto.order.lmtPrice == 400.0

    def test_createOrderProto_simple_order(self):
        order = Order(
            action="SELL",
            totalQuantity=50,
            orderType="MKT",
            tif="DAY",
            account="DU12345",
            outsideRth=True,
            transmit=True,
        )
        proto = createOrderProto(order)
        assert isinstance(proto, OrderProto)
        assert proto.action == "SELL"
        assert proto.totalQuantity == "50"
        assert proto.orderType == "MKT"
        assert proto.tif == "DAY"
        assert proto.account == "DU12345"
        assert proto.outsideRth is True
        assert proto.transmit is True

    def test_createOrderProto_with_conditions(self):
        order = Order(action="BUY", totalQuantity=10, orderType="LMT", lmtPrice=100)

        price_cond = PriceCondition(
            conId=123,
            exch="SMART",
            isMore=True,
            price=101.0,
            triggerMethod=1,
            conjunction="a",
        )
        time_cond = TimeCondition(
            time="20251231 16:00:00", isMore=False, conjunction="a"
        )
        order.conditions = [price_cond, time_cond]

        proto = createOrderProto(order)

        assert isinstance(proto, OrderProto)
        assert len(proto.conditions) == 2

        # Check price condition
        price_cond_proto = proto.conditions[0]
        assert price_cond_proto.type == PriceCondition.condType
        assert price_cond_proto.isConjunctionConnection is True
        assert price_cond_proto.isMore is True
        assert price_cond_proto.conId == 123
        assert price_cond_proto.exchange == "SMART"
        assert price_cond_proto.price == 101.0
        assert price_cond_proto.triggerMethod == 1

        # Check time condition
        time_cond_proto = proto.conditions[1]
        assert time_cond_proto.type == TimeCondition.condType
        assert time_cond_proto.isConjunctionConnection is True
        assert time_cond_proto.isMore is False
        assert time_cond_proto.time == "20251231 16:00:00"

    def test_createOrderProto_with_combo_legs(self):
        leg1 = ComboLeg(conId=1, ratio=1, action="BUY", exchange="SMART")
        leg2 = ComboLeg(conId=2, ratio=2, action="SELL", exchange="SMART")
        contract = Contract(comboLegs=[leg1, leg2])
        order_combo_leg1 = OrderComboLeg(price=10.0)
        order_combo_leg2 = OrderComboLeg(price=20.0)
        order = Order(
            action="BUY",
            totalQuantity=1,
            orderType="LMT",
            lmtPrice=30.0,
            orderComboLegs=[order_combo_leg1, order_combo_leg2],
        )

        # Mock createContractProto to return a ContractProto with comboLegs
        # This is needed because createOrderProto internally calls createContractProto
        # which needs the contract object to build its comboLegs
        contract_proto_mock = ContractProto(
            comboLegs=[
                ComboLegProto(
                    conId=1, ratio=1, action="BUY", exchange="SMART", perLegPrice=10.0
                ),
                ComboLegProto(
                    conId=2, ratio=2, action="SELL", exchange="SMART", perLegPrice=20.0
                ),
            ]
        )
        with pytest.MonkeyPatch().context() as mp:
            mp.setattr(
                "ib_async.protobuf_converters.trade_converters.createContractProto",
                lambda c, o: contract_proto_mock,
            )
            place_order_proto = createPlaceOrderRequestProto(1, contract, order)
            order_proto = place_order_proto.order

            assert isinstance(order_proto, OrderProto)
            # The comboLegs are part of the ContractProto inside PlaceOrderRequestProto, not directly in OrderProto
            # So we check if the internal mocked contractProto's comboLegs are correctly set
            assert len(place_order_proto.contract.comboLegs) == 2
            assert place_order_proto.contract.comboLegs[0].perLegPrice == 10.0
            assert place_order_proto.contract.comboLegs[1].perLegPrice == 20.0

    def test_createConditionsProto_price_condition(self):
        order = Order()
        order.conditions = [
            PriceCondition(
                conId=1,
                exch="SMART",
                isMore=True,
                price=100.0,
                triggerMethod=1,
                conjunction="a",
            )
        ]
        conditions_proto_list = createConditionsProto(order)
        assert len(conditions_proto_list) == 1
        price_cond_proto = conditions_proto_list[0]
        assert price_cond_proto.type == PriceCondition.condType
        assert price_cond_proto.isConjunctionConnection is True
        assert price_cond_proto.isMore is True
        assert price_cond_proto.conId == 1
        assert price_cond_proto.exchange == "SMART"
        assert price_cond_proto.price == 100.0
        assert price_cond_proto.triggerMethod == 1

    def test_createConditionsProto_time_condition(self):
        order = Order()
        order.conditions = [
            TimeCondition(time="20250101 10:00:00", isMore=False, conjunction="o")
        ]
        conditions_proto_list = createConditionsProto(order)
        assert len(conditions_proto_list) == 1
        time_cond_proto = conditions_proto_list[0]
        assert time_cond_proto.type == TimeCondition.condType
        assert time_cond_proto.isConjunctionConnection is False
        assert time_cond_proto.isMore is False
        assert time_cond_proto.time == "20250101 10:00:00"

    def test_createConditionsProto_margin_condition(self):
        order = Order()
        order.conditions = [MarginCondition(percent=150, isMore=True, conjunction="a")]
        conditions_proto_list = createConditionsProto(order)
        assert len(conditions_proto_list) == 1
        margin_cond_proto = conditions_proto_list[0]
        assert margin_cond_proto.type == MarginCondition.condType
        assert margin_cond_proto.isConjunctionConnection is True
        assert margin_cond_proto.isMore is True
        assert margin_cond_proto.percent == 150

    def test_createConditionsProto_execution_condition(self):
        order = Order()
        order.conditions = [
            ExecutionCondition(
                secType="STK", exch="SMART", symbol="AAPL", conjunction="o"
            )
        ]
        conditions_proto_list = createConditionsProto(order)
        assert len(conditions_proto_list) == 1
        exec_cond_proto = conditions_proto_list[0]
        assert exec_cond_proto.type == ExecutionCondition.condType
        assert exec_cond_proto.isConjunctionConnection is False
        assert exec_cond_proto.secType == "STK"
        assert exec_cond_proto.exchange == "SMART"
        assert exec_cond_proto.symbol == "AAPL"

    def test_createConditionsProto_volume_condition(self):
        order = Order()
        order.conditions = [
            VolumeCondition(
                conId=2, exch="NASDAQ", volume=1000, isMore=True, conjunction="a"
            )
        ]
        conditions_proto_list = createConditionsProto(order)
        assert len(conditions_proto_list) == 1
        volume_cond_proto = conditions_proto_list[0]
        assert volume_cond_proto.type == VolumeCondition.condType
        assert volume_cond_proto.isConjunctionConnection is True
        assert volume_cond_proto.isMore is True
        assert volume_cond_proto.conId == 2
        assert volume_cond_proto.exchange == "NASDAQ"
        assert volume_cond_proto.volume == 1000

    def test_createConditionsProto_percent_change_condition(self):
        order = Order()
        order.conditions = [
            PercentChangeCondition(
                conId=3,
                exch="IDEALPRO",
                changePercent=5.0,
                isMore=False,
                conjunction="o",
            )
        ]
        conditions_proto_list = createConditionsProto(order)
        assert len(conditions_proto_list) == 1
        percent_change_cond_proto = conditions_proto_list[0]
        assert percent_change_cond_proto.type == PercentChangeCondition.condType
        assert percent_change_cond_proto.isConjunctionConnection is False
        assert percent_change_cond_proto.isMore is False
        assert percent_change_cond_proto.conId == 3
        assert percent_change_cond_proto.exchange == "IDEALPRO"
        assert percent_change_cond_proto.changePercent == 5.0

    def test_createConditionsProto_empty_conditions(self):
        order = Order()
        order.conditions = []
        conditions_proto_list = createConditionsProto(order)
        assert len(conditions_proto_list) == 0

    def test_createOrderConditionProto(self):
        cond = PriceCondition()
        cond.conjunction = "a"
        proto = createOrderConditionProto(cond)
        assert proto.isConjunctionConnection is True
        cond.conjunction = "o"
        proto = createOrderConditionProto(cond)
        assert proto.isConjunctionConnection is False

    def test_createOperatorConditionProto(self):
        cond = PriceCondition()
        cond.isMore = True
        proto = createOperatorConditionProto(cond)
        assert proto.isMore is True

    def test_createContractConditionProto(self):
        cond = PriceCondition()
        cond.conId = 123
        cond.exch = "SMART"
        proto = createContractConditionProto(cond)
        assert proto.conId == 123
        assert proto.exchange == "SMART"

    def test_createPriceConditionProto(self):
        cond = PriceCondition()
        cond.price = 100.0
        cond.triggerMethod = 1
        proto = createPriceConditionProto(cond)
        assert proto.price == 100.0
        assert proto.triggerMethod == 1

    def test_createTimeConditionProto(self):
        cond = TimeCondition()
        cond.time = "20250101 10:00:00"
        proto = createTimeConditionProto(cond)
        assert proto.time == "20250101 10:00:00"

    def test_createMarginConditionProto(self):
        cond = MarginCondition()
        cond.percent = 150
        proto = createMarginConditionProto(cond)
        assert proto.percent == 150

    def test_createExecutionConditionProto(self):
        cond = ExecutionCondition()
        cond.secType = "STK"
        cond.exch = "SMART"
        cond.symbol = "AAPL"
        proto = createExecutionConditionProto(cond)
        assert proto.secType == "STK"
        assert proto.exchange == "SMART"
        assert proto.symbol == "AAPL"

    def test_createVolumeConditionProto(self):
        cond = VolumeCondition()
        cond.volume = 1000
        proto = createVolumeConditionProto(cond)
        assert proto.volume == 1000

    def test_createPercentChangeConditionProto(self):
        cond = PercentChangeCondition()
        cond.changePercent = 5.0
        proto = createPercentChangeConditionProto(cond)
        assert proto.changePercent == 5.0

    def test_createOrder(self):
        order_proto = OrderProto(
            orderId=1,
            action="BUY",
            totalQuantity="100.0",
            orderType="LMT",
            lmtPrice=400.0,
            tif="DAY",
            account="U123456",
            permId=1001,
            clientId=10,
            parentId=0,
            outsideRth=True,
            hidden=False,
            discretionaryAmt=0.0,
            goodAfterTime="20250101 10:00:00",
            faGroup="Group1",
            faMethod="EqualQuantity",
            faPercentage="10",
            modelCode="ModelA",
            goodTillDate="20250101",
            rule80A="Individual",
            percentOffset=0.01,
            settlingFirm="FirmX",
            shortSaleSlot=1,
            designatedLocation="US",
            exemptCode=-1,
            startingPrice=0.0,
            stockRefPrice=0.0,
            delta=0.0,
            stockRangeLower=0.0,
            stockRangeUpper=0.0,
            displaySize=10,
            blockOrder=False,
            sweepToFill=True,
            allOrNone=False,
            minQty=1,
            ocaType=0,
            triggerMethod=0,
            volatility=0.0,
            volatilityType=0,
            deltaNeutralOrderType="",
            deltaNeutralAuxPrice=0.0,
            deltaNeutralConId=0,
            deltaNeutralSettlingFirm="",
            deltaNeutralClearingAccount="",
            deltaNeutralClearingIntent="",
            deltaNeutralOpenClose="",
            deltaNeutralShortSale=False,
            deltaNeutralShortSaleSlot=0,
            deltaNeutralDesignatedLocation="",
            continuousUpdate=False,
            referencePriceType=0,
            trailStopPrice=0.0,
            trailingPercent=0.0,
            optOutSmartRouting=False,
            clearingAccount="ClearAcc",
            clearingIntent="IB",
            notHeld=False,
            algoStrategy="Vwap",
            solicited=False,
            whatIf=False,
            randomizeSize=False,
            randomizePrice=False,
            referenceContractId=0,
            isPeggedChangeAmountDecrease=False,
            peggedChangeAmount=0.0,
            referenceChangeAmount=0.0,
            referenceExchangeId="",
            conditionsIgnoreRth=False,
            conditionsCancelOrder=False,
            adjustedOrderType="",
            triggerPrice=0.0,
            lmtPriceOffset=0.0,
            adjustedStopPrice=0.0,
            adjustedStopLimitPrice=0.0,
            adjustedTrailingAmount=0.0,
            adjustableTrailingUnit=0,
            cashQty=0.0,
            dontUseAutoPriceForHedge=False,
            isOmsContainer=False,
            discretionaryUpToLimitPrice=False,
            usePriceMgmtAlgo=0,
            duration=0,
            postToAts=0,
            autoCancelParent=False,
            minTradeQty=0,
            minCompeteSize=0,
            competeAgainstBestOffset=0.0,
            midOffsetAtWhole=0.0,
            midOffsetAtHalf=0.0,
            customerAccount="",
            professionalCustomer=False,
            bondAccruedInterest="",
            includeOvernight=False,
            extOperator="",
            manualOrderIndicator=0,
            submitter="",
            imbalanceOnly=False,
            autoCancelDate="",
            filledQuantity="0.0",
            refFuturesConId=0,
            shareholder="",
            routeMarketableToBbo=False,
            parentPermId=0,
        )
        contract_proto = ContractProto(conId=123, symbol="SPY")

        order = createOrder(order_proto.orderId, contract_proto, order_proto)

        assert isinstance(order, Order)
        assert order.orderId == 1
        assert order.action == "BUY"
        assert order.totalQuantity == Decimal("100.0")
        assert order.orderType == "LMT"
        assert order.lmtPrice == 400.0
        assert order.tif == "DAY"
        assert order.account == "U123456"
        assert order.permId == 1001
        assert order.clientId == 10
        assert order.goodAfterTime == "20250101 10:00:00"
        assert order.modelCode == "ModelA"
        assert order.rule80A == "Individual"
        assert order.displaySize == 10
        assert order.algoStrategy == "Vwap"
        assert order.clearingAccount == "ClearAcc"
        assert order.clearingIntent == "IB"
        assert order.minTradeQty == 0

    def test_createOrder_with_soft_dollar_tier(self):
        order_proto = OrderProto(
            orderId=1,
            action="BUY",
            totalQuantity="100.0",
            orderType="LMT",
            lmtPrice=400.0,
        )
        sd_tier_proto = SoftDollarTierProto(
            name="Tier1", value="Value1", displayName="Display1"
        )
        order_proto.softDollarTier.CopyFrom(sd_tier_proto)
        contract_proto = ContractProto(conId=123, symbol="SPY")

        order = createOrder(order_proto.orderId, contract_proto, order_proto)
        assert isinstance(order, Order)
        assert order.softDollarTier.name == "Tier1"
        assert order.softDollarTier.val == "Value1"
        assert order.softDollarTier.displayName == "Display1"

    def test_createOrderComboLegs(self):
        contract_proto = ContractProto()
        leg1_proto = contract_proto.comboLegs.add()
        leg1_proto.conId = 1
        leg1_proto.perLegPrice = 10.0
        leg2_proto = contract_proto.comboLegs.add()
        leg2_proto.conId = 2
        leg2_proto.perLegPrice = 20.0

        order_combo_legs = createOrderComboLegs(contract_proto)
        assert len(order_combo_legs) == 2
        assert order_combo_legs[0].price == 10.0
        assert order_combo_legs[1].price == 20.0

    def test_createOrderConditions(self):
        order_proto = OrderProto()
        price_cond_proto = order_proto.conditions.add()
        price_cond_proto.type = PriceCondition.condType
        price_cond_proto.isConjunctionConnection = True
        price_cond_proto.isMore = True
        price_cond_proto.conId = 123
        price_cond_proto.exchange = "SMART"
        price_cond_proto.price = 101.0
        price_cond_proto.triggerMethod = 1

        conditions = createOrderConditions(order_proto)
        assert len(conditions) == 1
        price_condition = conditions[0]
        assert isinstance(price_condition, PriceCondition)
        assert price_condition.conjunction == "a"
        assert price_condition.isMore is True
        assert price_condition.conId == 123
        assert price_condition.exch == "SMART"
        assert price_condition.price == 101.0
        assert price_condition.triggerMethod == 1

    def test_setConditionFields(self):
        cond_proto = OrderConditionProto()
        cond_proto.isConjunctionConnection = True
        order_cond = PriceCondition()
        setConditionFields(cond_proto, order_cond)
        assert order_cond.conjunction == "a"

    def test_setOperatorConditionFields(self):
        cond_proto = OrderConditionProto()
        cond_proto.isConjunctionConnection = False
        cond_proto.isMore = True
        op_cond = PriceCondition()
        setOperatorConditionFields(cond_proto, op_cond)
        assert op_cond.conjunction == "o"
        assert op_cond.isMore is True

    def test_setContractConditionFields(self):
        cond_proto = OrderConditionProto()
        cond_proto.conId = 456
        cond_proto.exchange = "GLOBEX"
        contract_cond = PriceCondition()
        setContractConditionFields(cond_proto, contract_cond)
        assert contract_cond.conId == 456
        assert contract_cond.exch == "GLOBEX"

    def test_createPriceCondition(self):
        cond_proto = OrderConditionProto(price=200.0, triggerMethod=2)
        price_cond = createPriceCondition(cond_proto)
        assert isinstance(price_cond, PriceCondition)
        assert price_cond.price == 200.0
        assert price_cond.triggerMethod == 2

    def test_createTimeCondition(self):
        cond_proto = OrderConditionProto(time="20250101 15:00:00")
        time_cond = createTimeCondition(cond_proto)
        assert isinstance(time_cond, TimeCondition)
        assert time_cond.time == "20250101 15:00:00"

    def test_createMarginCondition(self):
        cond_proto = OrderConditionProto(percent=180)
        margin_cond = createMarginCondition(cond_proto)
        assert isinstance(margin_cond, MarginCondition)
        assert margin_cond.percent == 180

    def test_createExecutionCondition(self):
        cond_proto = OrderConditionProto(secType="FUT", exchange="GLOBEX", symbol="ES")
        exec_cond = createExecutionCondition(cond_proto)
        assert isinstance(exec_cond, ExecutionCondition)
        assert exec_cond.secType == "FUT"
        assert exec_cond.exch == "GLOBEX"
        assert exec_cond.symbol == "ES"

    def test_createVolumeCondition(self):
        cond_proto = OrderConditionProto(volume=500)
        volume_cond = createVolumeCondition(cond_proto)
        assert isinstance(volume_cond, VolumeCondition)
        assert volume_cond.volume == 500

    def test_createPercentChangeCondition(self):
        cond_proto = OrderConditionProto(changePercent=10.0)
        percent_change_cond = createPercentChangeCondition(cond_proto)
        assert isinstance(percent_change_cond, PercentChangeCondition)
        assert percent_change_cond.changePercent == 10.0

    def test_createSoftDollarTier(self):
        sd_tier_proto = SoftDollarTierProto(
            name="Tier2", value="Value2", displayName="Display2"
        )
        sd_tier = createSoftDollarTier(sd_tier_proto)
        assert isinstance(sd_tier, SoftDollarTier)
        assert sd_tier.name == "Tier2"
        assert sd_tier.val == "Value2"
        assert sd_tier.displayName == "Display2"

    def test_createSoftDollarTier_empty(self):
        sd_tier_proto = SoftDollarTierProto()
        sd_tier = createSoftDollarTier(sd_tier_proto)
        assert isinstance(sd_tier, SoftDollarTier)
        assert sd_tier.name == ""
        assert sd_tier.val == ""
        assert sd_tier.displayName == ""

    def test_createSoftDollarTierFromOrder(self):
        order_proto = OrderProto()
        sd_tier_proto = SoftDollarTierProto(
            name="Tier3", value="Value3", displayName="Display3"
        )
        order_proto.softDollarTier.CopyFrom(sd_tier_proto)

        sd_tier = createSoftDollarTierFromOrder(order_proto)
        assert isinstance(sd_tier, SoftDollarTier)
        assert sd_tier.name == "Tier3"
        assert sd_tier.val == "Value3"
        assert sd_tier.displayName == "Display3"

    def test_createSoftDollarTierFromOrder_no_tier(self):
        order_proto = OrderProto()
        sd_tier = createSoftDollarTierFromOrder(order_proto)
        assert sd_tier is None

    def test_createTagValueList(self):
        proto_map = {"Tag1": "Value1", "Tag2": "Value2"}
        tag_value_list = createTagValueList(proto_map)
        assert len(tag_value_list) == 2
        assert tag_value_list[0].tag == "Tag1"
        assert tag_value_list[0].value == "Value1"
        assert tag_value_list[1].tag == "Tag2"
        assert tag_value_list[1].value == "Value2"

    def test_createTagValueList_empty(self):
        proto_map = {}  # type: ignore
        tag_value_list = createTagValueList(proto_map)
        assert len(tag_value_list) == 0

    def test_createOrderState(self):
        order_state_proto = OrderStateProto(
            status="Filled",
            initMarginBefore=1000.0,
            maintMarginBefore=500.0,
            equityWithLoanBefore=1500.0,
            initMarginChange=100.0,
            maintMarginChange=50.0,
            equityWithLoanChange=150.0,
            initMarginAfter=1100.0,
            maintMarginAfter=550.0,
            equityWithLoanAfter=1650.0,
            commissionAndFees=10.0,
            minCommissionAndFees=5.0,
            maxCommissionAndFees=15.0,
            commissionAndFeesCurrency="USD",
            warningText="",
            marginCurrency="USD",
            initMarginBeforeOutsideRTH=1000.0,
            maintMarginBeforeOutsideRTH=500.0,
            equityWithLoanBeforeOutsideRTH=1500.0,
            initMarginChangeOutsideRTH=100.0,
            maintMarginChangeOutsideRTH=50.0,
            equityWithLoanChangeOutsideRTH=150.0,
            initMarginAfterOutsideRTH=1100.0,
            maintMarginAfterOutsideRTH=550.0,
            equityWithLoanAfterOutsideRTH=1650.0,
            suggestedSize="100.0",
            rejectReason="",
            completedTime="20250101 10:00:00",
            completedStatus="Completed",
        )

        order_state = createOrderState(order_state_proto)
        assert isinstance(order_state, OrderState)
        assert order_state.status == "Filled"
        assert order_state.initMarginBefore == 1000.00
        assert order_state.commission == 10.00
        assert order_state.completedTime == "20250101 10:00:00"

    def test_createOrderAllocations(self):
        order_state_proto = OrderStateProto()
        alloc1_proto = order_state_proto.orderAllocations.add()
        alloc1_proto.account = "U1"
        alloc1_proto.position = "10.0"
        alloc1_proto.desiredAllocQty = "5"

        allocations = createOrderAllocations(order_state_proto)
        assert len(allocations) == 1
        assert allocations[0].account == "U1"
        assert allocations[0].position == Decimal("10.0")
        assert allocations[0].desiredAllocQty == Decimal("5")


    def test_createContractFromExecutionDetails(self):
        exec_details_proto = ExecutionDetailsProto()
        exec_details_proto.contract.symbol = "AAPL"
        exec_details_proto.contract.secType = "STK"

        contract = createContractFromExecutionDetails(exec_details_proto)
        assert isinstance(contract, Contract)
        assert contract.symbol == "AAPL"

    def test_createOrderStatus(self):
        order_status_proto = OrderStatusProto(
            orderId=1,
            status="Submitted",
            filled="50.0",
            remaining="50.0",
            avgFillPrice=150.0,
            permId=1001,
            parentId=0,
            lastFillPrice=150.5,
            clientId=10,
            whyHeld="",
            mktCapPrice=0.0,
        )
        order_status = createOrderStatus(order_status_proto)
        assert isinstance(order_status, OrderStatus)
        assert order_status.orderId == 1
        assert order_status.status == "Submitted"
        assert order_status.filled == Decimal("50.0")

    def test_createExecution(self):
        exec_proto = ExecutionProto(
            execId="0001",
            time="20250101 10:00:00",
            acctNumber="U123456",
            exchange="SMART",
            side="BOT",
            shares="100.0",
            price=150.0,
            permId=1001,
            clientId=10,
            orderId=1,
            isLiquidation=False,
            cumQty="100.0",
            avgPrice=150.0,
            orderRef="",
            evRule="",
            evMultiplier=0.0,
            modelCode="",
            lastLiquidity=1,
            isPriceRevisionPending=False,
            submitter="",
            optExerciseOrLapseType=OptionExerciseType.NoneItem.value[0],
        )
        execution = createExecution(exec_proto)
        assert isinstance(execution, Execution)
        assert execution.execId == "0001"
        assert execution.time == datetime(2025, 1, 1, 10, 0, 0)
        assert execution.shares == 100.0
        assert execution.optExerciseOrLapseType == OptionExerciseType.NoneItem

    def test_createFill(self):
        exec_details_proto = ExecutionDetailsProto()
        exec_details_proto.contract.symbol = "AAPL"
        exec_details_proto.execution.execId = "0002"
        exec_details_proto.execution.time = "20250101 11:00:00"

        fill = createFill(exec_details_proto)
        assert isinstance(fill, Fill)
        assert fill.contract.symbol == "AAPL"
        assert fill.execution.execId == "0002"
        assert isinstance(fill.commissionReport, CommissionReport)

    def test_createTradeFromOpenOrder(self):
        open_order_proto = OpenOrderProto()
        open_order_proto.contract.symbol = "GOOG"
        open_order_proto.order.orderId = 2
        open_order_proto.order.action = "SELL"
        open_order_proto.orderState.status = "Filled"

        trade, order_state = createTradeFromOpenOrder(open_order_proto)
        assert isinstance(trade, Trade)
        assert trade.contract.symbol == "GOOG"
        assert trade.order.orderId == 2
        assert isinstance(order_state, OrderState)
        assert order_state.status == "Filled"
        assert trade.orderStatus.status == "Filled"

    def test_createTradeFromOpenOrder_missing_contract(self):
        open_order_proto = OpenOrderProto()
        # open_order_proto.contract is missing
        result = createTradeFromOpenOrder(open_order_proto)
        assert result == (None, None)

    def test_createCommissionReport(self):
        commission_report_proto = CommissionReportProto(
            execId="0003",
            commissionAndFees=1.5,
            currency="USD",
            realizedPNL=10.0,
            bondYield=0.05,
            yieldRedemptionDate="20250101",
        )
        commission_report = createCommissionReport(commission_report_proto)
        assert isinstance(commission_report, CommissionReport)
        assert commission_report.execId == "0003"
        assert commission_report.commission == 1.5
        assert commission_report.currency == "USD"

    def test_createExecutionRequestProto(self):
        exec_filter = ExecutionFilter(clientId=1, acctCode="U123", symbol="MSFT")
        proto = createExecutionRequestProto(1, exec_filter)
        assert isinstance(proto, ExecutionRequestProto)
        assert proto.reqId == 1
        assert proto.executionFilter.clientId == 1
        assert proto.executionFilter.symbol == "MSFT"

    def test_createOrderCancelProto(self):
        order_cancel = OrderCancel(
            manualOrderCancelTime="20250101-12:00:00", extOperator="OP1"
        )
        proto = createOrderCancelProto(order_cancel)
        assert isinstance(proto, OrderCancelProto)
        assert proto.manualOrderCancelTime == "20250101-12:00:00"
        assert proto.extOperator == "OP1"

    def test_createOrderCancelProto_none(self):
        proto = createOrderCancelProto(None)  # type: ignore
        assert proto is None

    def test_createGlobalCancelRequestProto(self):
        order_cancel = OrderCancel(manualOrderCancelTime="20250101-12:00:00")
        proto = createGlobalCancelRequestProto(order_cancel)
        assert isinstance(proto, GlobalCancelRequestProto)
        assert proto.orderCancel.manualOrderCancelTime == "20250101-12:00:00"

    def test_createCancelOrderRequestProto(self):
        order_cancel = OrderCancel(manualOrderCancelTime="20250101-12:00:00")
        proto = createCancelOrderRequestProto(5, order_cancel)
        assert isinstance(proto, CancelOrderRequestProto)
        assert proto.orderId == 5
        assert proto.orderCancel.manualOrderCancelTime == "20250101-12:00:00"

    def test_createExerciseOptionsRequestProto(self):
        contract = Contract(conId=456, symbol="SPY", secType="OPT")
        proto = createExerciseOptionsRequestProto(
            6, contract, 1, 100, "U123", True, "20250101", "CUST1", False
        )
        assert isinstance(proto, ExerciseOptionsRequestProto)
        assert proto.orderId == 6
        assert proto.contract.conId == 456
        assert proto.exerciseAction == 1
        assert proto.exerciseQuantity == 100
        assert proto.account == "U123"
        assert proto.override is True

    def test_createSoftDollarTierProto(self):
        order = Order()
        order.softDollarTier = SoftDollarTier(
            name="TestTier", val="TestVal", displayName="Test Display"
        )
        proto = createSoftDollarTierProto(order)
        assert isinstance(proto, SoftDollarTierProto)
        assert proto.name == "TestTier"
        assert proto.value == "TestVal"
        assert proto.displayName == "Test Display"
