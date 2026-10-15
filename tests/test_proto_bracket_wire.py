"""Wire-level regression pins for the attached-order (bracket) send path.

A live incident (NQZ6 future, clientId 169, 2026-09-16) placed a
``transmit=False`` parent followed by a ``transmit=True`` take-profit
child carrying ``parentId = <parent orderId>``. The broker answered with
``Error 135, reqId <child>: Can't find order with id = <parent>`` and the
parent never produced a single ``openOrder`` / ``orderStatus`` callback.

That failure mode has exactly two possible homes: the encoder dropped or
mis-stamped one of ``orderId`` / ``parentId`` / ``transmit``, or the
frames left in the wrong order. These tests pin both at the wire boundary
with no network: ``Client.conn.sendMsg`` is captured, the protobuf body is
parsed back, and every identity field is asserted against the domain
Order that produced it.

``transmit`` is written only when truthy, so an explicitly
non-transmitting parent legitimately leaves the field absent on the
wire; proto3 reads absent ``optional bool`` back as ``False``,
which is the value the server must act on. ``test_parent_transmit_false``
pins that the absent-field semantics survive a serialize / parse round
trip rather than asserting the field is present.
"""

from __future__ import annotations

from decimal import Decimal

import ib_async as ibi
from ib_async._pb import PlaceOrderRequest_pb2
from ib_async._pb_msgids import (
    MIN_SERVER_VER_PROTOBUF_PLACE_ORDER,
    PLACE_ORDER,
    REQ_CURRENT_TIME,
)
from ib_async.ordertypes import LimitOrder
from tests._helpers import _captureSend, _decodeProtoFrame, _ibAtVersion

#: The live incident ran against a current IB Gateway; every gate in
#: ``PROTOBUF_MSG_IDS`` is open there, so placeOrder takes the protobuf
#: path. Pin the tests at the placeOrder gate exactly.
_GATE = MIN_SERVER_VER_PROTOBUF_PLACE_ORDER

_PARENT_ID = 10282
_CHILD_ID = 10283


def _nqz6() -> ibi.Future:
    """The incident contract: NQZ6 on CME, already qualified by conId."""
    contract = ibi.Future(symbol="NQ", exchange="CME", currency="USD")
    contract.conId = 563947726
    contract.localSymbol = "NQZ6"
    return contract


def _bracket_orders() -> tuple[ibi.Order, ibi.Order]:
    """Build the incident's profit-only bracket: a held parent plus the
    single take-profit child that arms the graph.

    Mirrors ``icli.execution.bracket.build_bracket_orders`` — parent
    ``transmit=False``, child ``parentId`` = parent id and the lone
    ``transmit=True``.
    """
    parent = LimitOrder("BUY", Decimal(1), Decimal("29260.25"))
    parent.orderId = _PARENT_ID
    parent.tif = "GTC"
    parent.transmit = False

    child = LimitOrder("SELL", Decimal(1), Decimal("29262.25"))
    child.orderId = _CHILD_ID
    child.tif = "GTC"
    child.parentId = _PARENT_ID
    child.transmit = True

    return parent, child


def _place_bracket() -> list[PlaceOrderRequest_pb2.PlaceOrderRequest]:
    """Place parent then child through the real client and return the
    decoded ``PlaceOrderRequest`` protos in wire order."""
    ib = _ibAtVersion(_GATE)
    sent = _captureSend(ib)
    contract = _nqz6()
    parent, child = _bracket_orders()

    ib.client.placeOrder(parent.orderId, contract, parent)
    ib.client.placeOrder(child.orderId, contract, child)

    decoded: list[PlaceOrderRequest_pb2.PlaceOrderRequest] = []
    for framed in sent:
        canonical, body = _decodeProtoFrame(framed)
        assert canonical == PLACE_ORDER
        proto = PlaceOrderRequest_pb2.PlaceOrderRequest()
        proto.ParseFromString(body)
        decoded.append(proto)
    return decoded


def test_bracket_frames_leave_in_parent_then_child_order():
    """The parent's frame must hit the socket before the child's.

    ``Client.sendProto`` writes straight to the connection while
    ``Client.sendMsg`` (binary path) drains a throttle queue; a bracket
    whose legs took different paths could invert, and the server would
    reject the child for referencing an unknown parent.
    """
    parent_proto, child_proto = _place_bracket()
    assert parent_proto.orderId == _PARENT_ID
    assert child_proto.orderId == _CHILD_ID


def test_parent_envelope_and_order_carry_the_order_id():
    """``orderId`` is the identity the child's ``parentId`` resolves
    against; it must ride the envelope."""
    parent_proto, _ = _place_bracket()
    assert parent_proto.HasField("orderId")
    assert parent_proto.orderId == _PARENT_ID


def test_parent_transmit_false_reads_back_as_false():
    """A held parent must arrive as ``transmit == False``.

    The field is written only when truthy, so the wire carries no
    ``transmit`` at all; proto3 default-False makes the server read
    the intended value. Pin the round trip, not the presence bit.
    """
    parent_proto, _ = _place_bracket()
    assert parent_proto.order.transmit is False


def test_child_carries_parent_id_and_transmits():
    """The arming leg must name its parent and carry ``transmit=True``."""
    _, child_proto = _place_bracket()
    assert child_proto.order.HasField("parentId")
    assert child_proto.order.parentId == _PARENT_ID
    assert child_proto.order.HasField("transmit")
    assert child_proto.order.transmit is True


def test_bracket_legs_keep_price_quantity_and_tif():
    """Decimal-native quantities / prices must survive the proto hop."""
    parent_proto, child_proto = _place_bracket()
    assert parent_proto.order.action == "BUY"
    assert parent_proto.order.totalQuantity == "1"
    assert parent_proto.order.lmtPrice == 29260.25
    assert parent_proto.order.tif == "GTC"
    assert child_proto.order.action == "SELL"
    assert child_proto.order.totalQuantity == "1"
    assert child_proto.order.lmtPrice == 29262.25
    assert child_proto.order.tif == "GTC"


def test_parent_order_id_is_not_stamped_into_the_inner_order():
    """``Order.orderId`` is never written on a place request — the
    envelope's ``PlaceOrderRequest.orderId`` is the identity the server
    registers. Emitting both lets a stale ``order.orderId`` on a
    re-placed Order contradict the envelope; pin that the inner field
    stays absent so the two can never disagree.
    """
    parent_proto, child_proto = _place_bracket()
    assert not parent_proto.order.HasField("orderId")
    assert not child_proto.order.HasField("orderId")


def test_fresh_order_id_overrides_a_stale_id_on_a_reused_order():
    """``Client.placeOrder``'s documented contract: the caller may place
    under a freshly-allocated id "without having to mutate the source
    Order". The wire must then carry ONE id — the envelope's.

    Before the fix the inner ``Order.orderId`` also went out, so a reused
    Order object put a stale id on the same frame as the new one. A child
    attaching to the id the caller believed it used is then attaching to
    an order the server never registered — ``Error 135: Can't find order
    with id = …``.
    """
    ib = _ibAtVersion(_GATE)
    sent = _captureSend(ib)
    order = LimitOrder("BUY", Decimal(1), Decimal("29260.25"))
    order.orderId = 999  # stale id left on a reused Order object

    ib.client.placeOrder(_PARENT_ID, _nqz6(), order)

    canonical, body = _decodeProtoFrame(sent[0])
    assert canonical == PLACE_ORDER
    proto = PlaceOrderRequest_pb2.PlaceOrderRequest()
    proto.ParseFromString(body)
    assert proto.orderId == _PARENT_ID
    assert not proto.order.HasField("orderId")


def test_place_request_omits_server_owned_open_order_fields():
    """``autoCancelDate`` / ``parentPermId`` / ``shareholder`` /
    ``refFuturesConId`` / ``filledQuantity`` are reported BY the server
    on ``OpenOrder`` and are never sent on a place or modify request.
    Re-placing a fetched Order must not echo them back —
    ``filledQuantity`` on a modify is the sharpest case.
    """
    ib = _ibAtVersion(_GATE)
    sent = _captureSend(ib)
    order = LimitOrder("BUY", Decimal(1), Decimal("29260.25"))
    order.autoCancelDate = "20301231"
    order.parentPermId = 777
    order.shareholder = "SHAREHOLDER"
    order.refFuturesConId = 4242
    order.filledQuantity = Decimal(5)

    ib.client.placeOrder(_PARENT_ID, _nqz6(), order)

    _, body = _decodeProtoFrame(sent[0])
    proto = PlaceOrderRequest_pb2.PlaceOrderRequest()
    proto.ParseFromString(body)
    for serverOwned in (
        "autoCancelDate",
        "parentPermId",
        "shareholder",
        "refFuturesConId",
        "filledQuantity",
    ):
        assert not proto.order.HasField(serverOwned), serverOwned


def test_a_queued_binary_frame_is_not_overtaken_by_a_later_place_order():
    """FIFO across both wire paths.

    With the pacing budget exhausted, a binary frame waits in ``_msgQ``;
    a protobuf ``placeOrder`` issued afterwards must queue BEHIND it
    rather than jump straight to the socket. An order that overtakes the
    request that was supposed to precede it is the reordering hazard
    behind attached-order graphs.
    """
    ib = _ibAtVersion(_GATE)
    sent = _captureSend(ib)
    ib.client.MaxRequests = 1

    # REQ_CURRENT_TIME gates to protobuf only at 213, so at the placeOrder
    # gate (203) it is a plain binary frame.
    ib.client.send(REQ_CURRENT_TIME)
    assert len(sent) == 1

    ib.client.placeOrder(_PARENT_ID, _nqz6(), _bracket_orders()[0])
    # Budget spent: the order frame waits its turn instead of racing ahead.
    assert len(sent) == 1
    assert len(ib.client._msgQ) == 1
