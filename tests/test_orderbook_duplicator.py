import pytest
from dataclasses import dataclass, field
from typing import Any

from src.enums import (
    Side,
    OrderType,
    TimeInForce,
    StrategyType,
    LiquidityRole,
    EventType,
    InstrumentEventType,
    TransactionType,
    OrderStatus,
    UserStatus,
    InstrumentStatus,
    TimeFrame,
)
from src.orderbook_duplicator import OrderBookReplicator, OrderEntry


@dataclass
class MockEvent:
    event_type: EventType
    related_id: str
    details: dict[str, Any] = field(default_factory=dict)


@pytest.fixture
def replicator() -> OrderBookReplicator:
    """Provides a clean OrderBookReplicator instance for each test."""
    return OrderBookReplicator(size=10)


def test_order_entry_initialization():
    """Tests that an OrderEntry object is initialized correctly."""
    entry = OrderEntry(executed_quantity=5.0, quantity=10.0, price=100.0, side=Side.BID)
    assert entry.executed_quantity == 5.0
    assert entry.quantity == 10.0
    assert entry.price == 100.0
    assert entry.side == Side.BID


def test_replicator_initialization(replicator: OrderBookReplicator):
    """Tests the initial state of the OrderBookReplicator."""
    assert replicator.size == 10
    assert len(replicator._bids) == 0
    assert len(replicator._asks) == 0
    assert len(replicator._orders) == 0
    assert replicator.snapshot() == {"bids": {}, "asks": {}}


def test_handle_order_placed_bid(replicator: OrderBookReplicator):
    """Tests processing a new bid order placement."""
    event = MockEvent(
        event_type=EventType.ORDER_PLACED,
        related_id="order1",
        details={
            "executed_quantity": 0.0,
            "quantity": 10.0,
            "price": 100.0,
            "side": Side.BID,
        },
    )
    replicator.process_event(event)

    snapshot = replicator.snapshot()
    assert snapshot["bids"] == {100.0: 10.0}
    assert snapshot["asks"] == {}
    assert "order1" in replicator._orders
    assert replicator._orders["order1"].quantity == 10.0


def test_handle_order_placed_ask(replicator: OrderBookReplicator):
    """Tests processing a new ask order placement."""
    event = MockEvent(
        event_type=EventType.ORDER_PLACED,
        related_id="order2",
        details={
            "executed_quantity": 0.0,
            "quantity": 5.0,
            "price": 101.0,
            "side": Side.ASK,
        },
    )
    replicator.process_event(event)

    snapshot = replicator.snapshot()
    assert snapshot["bids"] == {}
    assert snapshot["asks"] == {101.0: 5.0}
    assert "order2" in replicator._orders


def test_multiple_orders_at_same_price_level(replicator: OrderBookReplicator):
    """Tests that quantities are summed for multiple orders at the same price."""
    event1 = MockEvent(
        EventType.ORDER_PLACED,
        "order1",
        {"executed_quantity": 0, "quantity": 10, "price": 100, "side": Side.BID},
    )
    event2 = MockEvent(
        EventType.ORDER_PLACED,
        "order2",
        {"executed_quantity": 0, "quantity": 5, "price": 100, "side": Side.BID},
    )

    replicator.process_event(event1)
    replicator.process_event(event2)

    assert replicator.snapshot()["bids"] == {100: 15}
    assert "order1" in replicator._orders
    assert "order2" in replicator._orders


def test_handle_order_partially_filled(replicator: OrderBookReplicator):
    """Tests processing a partial fill event."""
    place_event = MockEvent(
        EventType.ORDER_PLACED,
        "order1",
        {"executed_quantity": 0, "quantity": 10, "price": 100, "side": Side.BID},
    )
    replicator.process_event(place_event)
    assert replicator.snapshot()["bids"] == {100: 10}

    fill_event = MockEvent(
        EventType.ORDER_PARTIALLY_FILLED,
        "order1",
        {"quantity": 10, "executed_quantity": 4},
    )
    replicator.process_event(fill_event)

    assert replicator.snapshot()["bids"] == {100: 6}
    assert replicator._orders["order1"].executed_quantity == 4


def test_handle_order_fully_filled(replicator: OrderBookReplicator):
    """Tests processing a full fill event which removes the order."""
    place_event = MockEvent(
        EventType.ORDER_PLACED,
        "order1",
        {"executed_quantity": 0, "quantity": 10, "price": 100, "side": Side.BID},
    )
    replicator.process_event(place_event)

    fill_event = MockEvent(
        EventType.ORDER_FILLED, "order1", {"quantity": 10, "executed_quantity": 10}
    )
    replicator.process_event(fill_event)

    assert replicator.snapshot()["bids"] == {}
    assert "order1" not in replicator._orders


def test_handle_order_cancelled(replicator: OrderBookReplicator):
    """Tests processing an order cancellation."""
    place_event = MockEvent(
        EventType.ORDER_PLACED,
        "order1",
        {"executed_quantity": 0, "quantity": 10, "price": 100, "side": Side.BID},
    )
    replicator.process_event(place_event)
    assert replicator.snapshot()["bids"] == {100: 10}

    cancel_event = MockEvent(EventType.ORDER_CANCELLED, "order1")
    replicator.process_event(cancel_event)

    assert replicator.snapshot()["bids"] == {}
    assert "order1" not in replicator._orders


def test_handle_cancellation_of_partially_filled_order(replicator: OrderBookReplicator):
    """Tests cancelling an order that has been partially filled."""
    place_event = MockEvent(
        EventType.ORDER_PLACED,
        "order1",
        {"executed_quantity": 0, "quantity": 10, "price": 100, "side": Side.BID},
    )
    fill_event = MockEvent(
        EventType.ORDER_PARTIALLY_FILLED,
        "order1",
        {"quantity": 10, "executed_quantity": 4},
    )
    replicator.process_event(place_event)
    replicator.process_event(fill_event)
    assert replicator.snapshot()["bids"] == {100: 6}

    cancel_event = MockEvent(EventType.ORDER_CANCELLED, "order1")
    replicator.process_event(cancel_event)

    assert replicator.snapshot()["bids"] == {}
    assert "order1" not in replicator._orders


def test_handle_order_modified_price(replicator: OrderBookReplicator):
    """Tests modifying an order's price."""
    place_event = MockEvent(
        EventType.ORDER_PLACED,
        "order1",
        {"executed_quantity": 0, "quantity": 10, "price": 100, "side": Side.BID},
    )
    replicator.process_event(place_event)
    assert replicator.snapshot()["bids"] == {100: 10}

    modify_event = MockEvent(EventType.ORDER_MODIFIED, "order1", {"price": 99})
    replicator.process_event(modify_event)

    assert replicator.snapshot()["bids"] == {99: 10}
    assert 100 not in replicator.snapshot()["bids"]
    assert replicator._orders["order1"].price == 99


def test_handle_order_modified_quantity(replicator: OrderBookReplicator):
    """Tests modifying an order's quantity."""
    place_event = MockEvent(
        EventType.ORDER_PLACED,
        "order1",
        {"executed_quantity": 0, "quantity": 10, "price": 100, "side": Side.BID},
    )
    replicator.process_event(place_event)
    assert replicator.snapshot()["bids"] == {100: 10}

    # Increase quantity
    modify_event_increase = MockEvent(
        EventType.ORDER_MODIFIED, "order1", {"price": 100, "quantity": 15}
    )
    replicator.process_event(modify_event_increase)
    assert replicator.snapshot()["bids"] == {100: 15}
    assert replicator._orders["order1"].quantity == 15

    # Decrease quantity
    modify_event_decrease = MockEvent(
        EventType.ORDER_MODIFIED, "order1", {"price": 100, "quantity": 8}
    )
    replicator.process_event(modify_event_decrease)
    assert replicator.snapshot()["bids"] == {100: 8}
    assert replicator._orders["order1"].quantity == 8


def test_handle_order_modified_price_and_quantity(replicator: OrderBookReplicator):
    """Tests modifying both price and quantity of an order."""
    place_event = MockEvent(
        EventType.ORDER_PLACED,
        "order1",
        {"executed_quantity": 0, "quantity": 10, "price": 100, "side": Side.BID},
    )
    replicator.process_event(place_event)

    modify_event = MockEvent(
        EventType.ORDER_MODIFIED, "order1", {"price": 98, "quantity": 5}
    )
    replicator.process_event(modify_event)

    assert replicator.snapshot()["bids"] == {98: 5}
    assert 100 not in replicator.snapshot()["bids"]
    assert replicator._orders["order1"].price == 98
    assert replicator._orders["order1"].quantity == 5


def test_snapshot_respects_size_limit():
    """Tests that the snapshot correctly truncates the book to the specified size."""
    replicator = OrderBookReplicator(size=2)

    # Add 3 bids and 3 asks
    bids = {100: 10, 99: 5, 98: 20}
    asks = {101: 8, 102: 12, 103: 3}

    for i, (price, qty) in enumerate(bids.items()):
        event = MockEvent(
            EventType.ORDER_PLACED,
            f"bid{i}",
            {"executed_quantity": 0, "quantity": qty, "price": price, "side": Side.BID},
        )
        replicator.process_event(event)

    for i, (price, qty) in enumerate(asks.items()):
        event = MockEvent(
            EventType.ORDER_PLACED,
            f"ask{i}",
            {"executed_quantity": 0, "quantity": qty, "price": price, "side": Side.ASK},
        )
        replicator.process_event(event)

    snapshot = replicator.snapshot()

    # Bids should be the highest 2 prices
    assert snapshot["bids"] == {100: 10, 99: 5}
    # Asks should be the lowest 2 prices
    assert snapshot["asks"] == {101: 8, 102: 12}
    assert len(snapshot["bids"]) == 2
    assert len(snapshot["asks"]) == 2


def test_processing_unhandled_event_type(replicator: OrderBookReplicator):
    """Tests that an unhandled event type does not alter state or raise an error."""
    event = MockEvent(EventType.NEW_TRADE, "trade1", {})
    replicator.process_event(event)
    snapshot = replicator.snapshot()
    assert snapshot == {"bids": {}, "asks": {}}


def test_processing_event_for_unknown_order(replicator: OrderBookReplicator):
    """Tests that events for non-existent orders are ignored gracefully."""
    fill_event = MockEvent(
        EventType.ORDER_FILLED,
        "unknown_order",
        {"quantity": 10, "executed_quantity": 10},
    )
    cancel_event = MockEvent(EventType.ORDER_CANCELLED, "unknown_order")

    # No exception should be raised
    replicator.process_event(fill_event)
    replicator.process_event(cancel_event)

    assert replicator.snapshot() == {"bids": {}, "asks": {}}
    assert "unknown_order" not in replicator._orders
