"""Property tests for the order type value checks and constructors.

For every Order field and any input value, the check either raises
OrderTypeError or returns a value of the field's type, which an Order
then stores unchanged. Every order type constructor, given arbitrary
arguments, either raises OrderTypeError or builds an order that its own
spec recognizes.
"""

from __future__ import annotations

import dataclasses
import math
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

import ib_async
from ib_async import Order, ordertypes
from ib_async.order import (
    COMPETE_AGAINST_BEST_OFFSET_UP_TO_MID,
    ORDER_FIELD_TYPES,
    finiteDecimal,
)
from ib_async.ordertypes import CATALOG, OrderTypeError, specsOf
from ib_async.ordertypes.spec import (
    ACTIONS,
    Kind,
    Param,
    checkedValue,
    takesInfinity,
)
from tests._property import examples

numbers = st.one_of(
    st.integers(-(10**12), 10**12),
    st.floats(allow_nan=True, allow_infinity=True),
    st.decimals(allow_nan=True, allow_infinity=True),
    st.booleans(),
)
texts = st.one_of(st.text(max_size=8), numbers.map(str))
anything = st.one_of(
    st.none(),
    numbers,
    texts,
    st.lists(st.integers(), max_size=3),
    st.binary(max_size=4),
)
FIELDS = sorted(ORDER_FIELD_TYPES)


def holds(kind: type, field: str, value: object) -> bool:
    """True if ``value`` is a valid value for a field of type ``kind``."""
    if kind is Decimal:
        if not isinstance(value, Decimal):
            return False
        return value.is_finite() or (
            takesInfinity(field) and value == COMPETE_AGAINST_BEST_OFFSET_UP_TO_MID
        )
    if kind is float:
        return type(value) is float and math.isfinite(value)
    if kind is int:
        return type(value) is int
    return type(value) is kind


@given(field=st.sampled_from(FIELDS), value=anything)
@examples()
def test_checked_value_is_refused_or_stored(field, value):
    try:
        checked = checkedValue("X", field, field, value, infinity=True)
    except OrderTypeError:
        return
    if value is None:
        assert checked is None
        return
    assert holds(ORDER_FIELD_TYPES[field], field, checked), (field, value, checked)
    order = Order(**{field: checked})
    assert getattr(order, field) == checked


@given(value=anything)
@examples()
def test_finite_decimal_never_raises_and_is_finite_or_none(value):
    result = finiteDecimal(value)
    assert result is None or (isinstance(result, Decimal) and result.is_finite())
    if type(value) is float and math.isfinite(value):
        assert result == Decimal(str(value))
    if type(value) is int:
        assert result == Decimal(value)


@given(kind=st.sampled_from(sorted(Kind)), value=anything)
@examples()
def test_tag_value_is_refused_or_encoded(kind, value):
    if kind in (Kind.FIELD, Kind.LEG_PRICES):
        return
    param = Param("x", "algoParams", "doc", tag="x", kind=kind)
    try:
        encoded = param.encode("X", value)
    except OrderTypeError:
        return
    assert isinstance(encoded, str)
    if kind is Kind.BOOL:
        assert encoded in ("0", "1")
    elif kind is Kind.INT:
        assert str(int(encoded)) == encoded
    elif kind is Kind.FLOAT:
        assert math.isfinite(float(encoded))
    else:
        assert encoded == value


def valueFor(param: Param, data: st.DataObject) -> object:
    """Draw a value for ``param``, usually of its type, sometimes anything."""
    kind = ORDER_FIELD_TYPES.get(param.field)
    if param.kind is Kind.LEG_PRICES:
        good = st.lists(st.decimals(0, 100, places=2), min_size=1, max_size=3)
    elif param.kind is Kind.BOOL or kind is bool:
        good = st.booleans()
    elif param.kind is Kind.INT or kind is int:
        good = st.integers(0, 10**6)
    elif param.kind is Kind.STR or kind is str:
        good = st.sampled_from(param.allowed) if param.allowed else st.text(max_size=4)
    else:
        good = st.decimals(min_value=Decimal("0.01"), max_value=10**6, places=2)
    return data.draw(st.one_of(st.none(), good, good, anything))


@given(
    spec=st.sampled_from(list(CATALOG)),
    action=st.sampled_from([*ACTIONS, "buy", "", "BYU"]),
    quantity=st.one_of(
        st.integers(1, 10**6),
        st.decimals(Decimal("0.0001"), 10**6, places=4),
        st.just("100"),
        anything,
    ),
    data=st.data(),
)
@examples()
def test_constructor_refuses_arguments_or_builds_its_type(spec, action, quantity, data):
    values = {p.name: valueFor(p, data) for p in spec.params}
    constructor = getattr(ib_async, spec.className)
    try:
        order = constructor(action, quantity, **values)
    except OrderTypeError:
        return
    assert type(order) is Order
    assert (order.orderType, order.action) == (spec.orderType, action)
    assert action in ACTIONS
    assert order.totalQuantity == finiteDecimal(quantity)
    for field, value in spec.definingFields.items():
        assert getattr(order, field) == value
    assert spec in specsOf(order), spec.className
    # The built order can be copied and printed.
    assert dataclasses.replace(order).orderType == spec.orderType
    assert spec.orderType in repr(order)


@given(
    changes=st.dictionaries(
        st.sampled_from(
            ["lmtPrice", "totalQuantity", "tif", "outsideRth", "volatility"]
        ),
        anything,
        max_size=3,
    ),
    preserveParentId=st.booleans(),
)
@examples()
def test_modified_order_is_refused_or_ready_to_send(changes, preserveParentId):
    live = Order(
        orderId=5,
        parentId=4,
        orderType="IBALGO",
        action="BUY",
        totalQuantity=Decimal(100),
        filledQuantity=Decimal(40),
        lmtPrice=Decimal(50),
        transmit=False,
        volatility=Decimal("0.3"),
        algoStrategy="Adaptive",
    )
    try:
        modified = ordertypes.modifiedOrder(
            live, preserveParentId=preserveParentId, **changes
        )
    except OrderTypeError:
        return
    assert modified.transmit is True
    assert modified.orderType == "LMT"
    assert modified.parentId == (4 if preserveParentId else 0)
    assert modified.volatility is None
    assert modified.totalQuantity is None or modified.totalQuantity >= Decimal(40)
    assert live.transmit is False and live.orderType == "IBALGO"  # untouched


@pytest.mark.parametrize("nan", [Decimal("sNaN"), Decimal("-sNaN")])
def test_signaling_nan_is_refused(nan):
    for field in ("lmtPrice", "discretionaryAmt", "minQty", "competeAgainstBestOffset"):
        with pytest.raises(OrderTypeError):
            checkedValue("X", field, field, nan, infinity=True)
