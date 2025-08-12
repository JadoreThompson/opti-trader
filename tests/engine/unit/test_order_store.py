import pytest
from src.engine.stores import OrderStore


def test_order_store_add_and_get(order_factory):
    """Test adding an order and retrieving it."""
    store = OrderStore()
    order = order_factory(order_id="order1")
    store.add(order)
    retrieved_order = store.get("order1")
    assert retrieved_order is not None
    assert retrieved_order.id == "order1"


def test_order_store_remove(order_factory):
    """Test removing an order from the store."""
    store = OrderStore()
    order = order_factory(order_id="order1")
    store.add(order)
    store.remove(order)
    assert store.get("order1") is None


def test_order_store_get_nonexistent(order_factory):
    """Test that getting a non-existent order returns None."""
    store = OrderStore()
    assert store.get("nonexistent") is None


def test_order_store_add_duplicate(order_factory):
    """Test that adding an order with a duplicate ID does not overwrite."""
    store = OrderStore()
    order1 = order_factory(order_id="order1", quantity=100)
    order2 = order_factory(order_id="order1", quantity=200)
    store.add(order1)
    store.add(order2)  # Should not replace
    retrieved = store.get("order1")
    assert retrieved.quantity == 100
