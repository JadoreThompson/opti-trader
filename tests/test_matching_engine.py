import pytest
import copy

from uuid import uuid4
from datetime import datetime
from collections.abc import Iterable

from engine.futures_engine import FuturesEngine
from engine.orderbook import OrderBook
from engine.order import Order
from engine.enums import Tag
from engine.position_manager import PositionManager
from engine.typing import MatchOutcome, MatchResult
from engine.utils import calc_buy_pl, calc_sell_pl, calculate_upl
from enums import OrderStatus, OrderType, Side


# --- Mock Components ---
class MockLock:
    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class MockPusher:
    def __init__(self):
        self.payloads = []

    def append(self, payload: dict, speed: str = "slow", channel: str = None):
        self.payloads.append((payload, speed, channel))


class MockPosition:
    """A simple mock to represent an open position in the harness."""

    def __init__(self, order_state):
        self.order = Order(order_state, Tag.ENTRY, order_state["side"])
        self.take_profit = None
        self.stop_loss = None


class MockMatchingEngine:
    def __init__(self):
        self.shadow_book = OrderBook()
        self.predicted_order_states = {}
        self.position_manager = PositionManager()

    def predict_place_order(self, order_state: dict):
        """High-level entry point that mirrors engine.place_order."""
        order_state = copy.deepcopy(order_state)
        p_order = Order(order_state, Tag.ENTRY, order_state["side"])

        if order_state["order_id"] in self.predicted_order_states:
            raise ValueError("Cannot predict place order, order already in queue.")

        self.predicted_order_states[order_state["order_id"]] = order_state

        if order_state["order_type"] == OrderType.LIMIT:
            return self.shadow_book.append(p_order, order_state["limit_price"])

        result = self._predict_match(p_order)

        if result.outcome == MatchOutcome.SUCCESS:
            self.shadow_book.set_price(result.price)
            order_state["status"] = OrderStatus.FILLED
            order_state["standing_quantity"] = order_state["quantity"]
            order_state["filled_price"] = result.price

            self.position_manager.create(p_order)
            self._predict_place_tp_sl(p_order)
        else:
            self.shadow_book.append(p_order, result.price)
            if order_state["standing_quantity"] != order_state["quantity"]:
                order_state["status"] = OrderStatus.PARTIALLY_FILLED

    def _predict_match(self, aggressive_order: Order):
        """Mirrors the engine._match logic."""
        book_side_to_match = "asks" if aggressive_order.side == Side.BID else "bids"
        touched_orders, filled_orders = [], []

        target_price = (
            self.shadow_book.best_ask
            if aggressive_order.side == Side.BID
            else self.shadow_book.best_bid
        )
        if target_price is None:
            return MatchResult(MatchOutcome.FAILURE, None)

        aggressive_state = aggressive_order.payload

        for resting_order in self.shadow_book.get_orders(
            target_price, book_side_to_match
        ):
            if aggressive_state["standing_quantity"] == 0:
                break

            resting_state = self.predicted_order_states[
                resting_order.payload["order_id"]
            ]
            original_resting_qty = resting_state["standing_quantity"]

            qty_to_match = min(
                aggressive_state["standing_quantity"], original_resting_qty
            )

            aggressive_state["standing_quantity"] -= qty_to_match
            resting_state["standing_quantity"] -= qty_to_match

            if resting_state["standing_quantity"] == 0:
                filled_orders.append((resting_order, original_resting_qty))
            else:
                touched_orders.append((resting_order, original_resting_qty))

        self._predict_handle_touched_orders(touched_orders, filled_orders, target_price)
        self._predict_handle_filled_orders(filled_orders, target_price)

        if aggressive_order.payload["standing_quantity"] == 0:
            return MatchResult(MatchOutcome.SUCCESS, target_price)
        return MatchResult(MatchOutcome.PARTIAL, target_price)

    def _predict_handle_filled_orders(
        self, orders: Iterable[tuple[Order, int]], price: float
    ):
        """A perfect mock of the engine's _handle_filled_orders method."""
        for order, standing_quantity in orders:
            self.shadow_book.remove(order, price)
            state = order.payload

            if order.tag == Tag.ENTRY:
                state.update(
                    {
                        "status": OrderStatus.FILLED,
                        "standing_quantity": state["quantity"],
                        "filled_price": price,
                    }
                )
                self.position_manager.create(order)

                self._predict_place_tp_sl(order)
                calculate_upl(order, price, self.shadow_book)
            else:
                pos = self.position_manager.get(order.payload["order_id"])

                if pos.take_profit and pos.take_profit != order:
                    self.shadow_book.remove(
                        pos.take_profit, order.payload["take_profit"]
                    )
                if pos.stop_loss and pos.stop_loss != order:
                    self.shadow_book.remove(pos.stop_loss, order.payload["stop_loss"])

                self.position_manager.remove(order.payload["order_id"])
                state.update(
                    {
                        "status": OrderStatus.CLOSED,
                        "closed_at": datetime.now(),
                        "unrealised_pnl": 0.0,
                        "standing_quantity": 0,
                        "closed_price": price,
                    }
                )

                if order.payload["side"] == Side.BID:
                    order.payload["realised_pnl"] += calc_buy_pl(
                        order.payload["filled_price"] * standing_quantity,
                        order.payload["filled_price"],
                        price,
                    )
                else:
                    order.payload["realised_pnl"] += calc_sell_pl(
                        order.payload["filled_price"] * standing_quantity,
                        order.payload["filled_price"],
                        price,
                    )

    def _predict_handle_touched_orders(
        self,
        orders: Iterable[tuple[Order, int]],
        filled_orders: list,
        price: float,
    ):
        """A perfect mock of the engine's _handle_touched_orders method."""
        for order, standing_qty in orders:
            state = order.payload

            if order.tag == Tag.ENTRY:
                if state["standing_quantity"] > 0:
                    state["status"] = OrderStatus.PARTIALLY_FILLED
                else:
                    filled_orders.append((order, order.payload["standing_quantity"]))
                continue
            else:
                state["status"] = OrderStatus.PARTIALLY_CLOSED

            calculate_upl(order, price, self.shadow_book)

            if order.payload["status"] == OrderStatus.FILLED:
                filled_orders.append((order, standing_qty))
                continue

    def _predict_place_tp_sl(self, order: Order):
        """Mirrors the engine's _place_tp_sl method."""
        pos = self.position_manager.get(order.payload["order_id"])

        if order.payload["take_profit"] is not None:
            tp_order = Order(
                order.payload,
                Tag.TAKE_PROFIT,
                Side.ASK if order.side == Side.BID else Side.BID,
            )
            pos.take_profit = tp_order
            self.shadow_book.append(tp_order, order.payload["take_profit"])

        if order.payload["stop_loss"] is not None:
            sl_order = Order(
                order.payload,
                Tag.STOP_LOSS,
                Side.ASK if order.side == Side.BID else Side.BID,
            )
            pos.stop_loss = sl_order
            self.shadow_book.append(sl_order, order.payload["stop_loss"])

# --- Utilities ----
def create_order(i: int) -> dict:
    is_limit_order = i % 3 == 0
    order_type = OrderType.LIMIT if is_limit_order else OrderType.MARKET
    is_buy = i % 2 == 0
    side = Side.BID if is_buy else Side.ASK
    base_price, price_step, quantity = 100.0, 0.5, 10

    order = {
        "order_id": str(i),
        "user_id": str(uuid4()),
        "instrument": "HARNESS_INSTR",
        "side": side,
        "order_type": order_type,
        "quantity": quantity,
        "standing_quantity": quantity,
        "status": OrderStatus.PENDING,
        "realised_pnl": 0.0,
        "unrealised_pnl": 0.0,
        "filled_price": None,
        "limit_price": None,
        "price": None,
        "closed_at": None,
        "closed_price": None,
        "created_at": datetime.now(),
        "amount": 100,
        "take_profit": base_price + 20 if is_buy and is_limit_order else None,
        "stop_loss": base_price - 10 if is_buy and is_limit_order else None,
    }

    if order_type == OrderType.LIMIT:
        price_offset = (i // 2 * price_step) + 1
        order["limit_price"] = round(
            base_price - price_offset if is_buy else base_price + price_offset, 2
        )
    return order


def assert_books_are_identical(
    engine_book: OrderBook, harness: MockMatchingEngine, step_id: str
):
    """Performs a deep, step-by-step comparison of the two order books."""
    shadow_book = harness.shadow_book

    assert engine_book._cur_price == pytest.approx(
        shadow_book._cur_price
    ), f"Step {step_id}: Price mismatch"

    assert set(engine_book.bids.keys()) == set(
        shadow_book.bids.keys()
    ), f"Step {step_id}: Bid levels mismatch"
    assert set(engine_book.asks.keys()) == set(
        shadow_book.asks.keys()
    ), f"Step {step_id}: Ask levels mismatch"

    for price in engine_book.bids.keys():
        engine_ids = {
            o.payload["order_id"] for o in engine_book.get_orders(price, "bids")
        }
        shadow_ids = {
            o.payload["order_id"] for o in shadow_book.get_orders(price, "bids")
        }
        assert (
            engine_ids == shadow_ids
        ), f"Step {step_id}: Order IDs at bid price {price} mismatch"

    for price in engine_book.asks.keys():
        engine_ids = {
            o.payload["order_id"] for o in engine_book.get_orders(price, "asks")
        }
        shadow_ids = {
            o.payload["order_id"] for o in shadow_book.get_orders(price, "asks")
        }
        assert (
            engine_ids == shadow_ids
        ), f"Step {step_id}: Order IDs at ask price {price} mismatch"


# --- The Test Suite ---
TEST_SIZES = [int(2**i) for i in range(2, 9)] + [512, 1000, 10_000]


@pytest.mark.parametrize("num_orders", TEST_SIZES)
def test_place_order(num_orders):
    print(f"\n--- Running harness test with {num_orders} orders ---")

    instrument = "HARNESS_INSTR"
    engine = FuturesEngine(MockLock(), MockPusher())
    mock_engine = MockMatchingEngine()

    orders_for_engine = tuple(create_order(i) for i in range(num_orders))

    for i, order_to_process in enumerate(orders_for_engine):
        op = order_to_process.copy()
        op["fake"] = True
        mock_engine.predict_place_order(op)

        order_to_process["fake"] = False
        engine.place_order(order_to_process)
        engine_book = engine._order_books[instrument]
        assert_books_are_identical(engine_book, mock_engine, step_id=f"Order {i}")

    final_orders_from_engine = {o["order_id"]: o for o in orders_for_engine}
    for order_id in sorted(mock_engine.predicted_order_states.keys()):
        predicted_state = mock_engine.predicted_order_states[order_id]
        actual_state = final_orders_from_engine[order_id]

        for key in [
            "status",
            "standing_quantity",
            "filled_price",
            "realised_pnl",
            "unrealised_pnl",
        ]:
            pred_val, act_val = predicted_state.get(key), actual_state.get(key)
            # print(f"Key - {key} | ID: {order_id} | Pred: {pred_val} | Act: {act_val}")

            if isinstance(pred_val, float):
                assert act_val == pytest.approx(
                    pred_val
                ), f"Final state | ID {order_id} | {key}: Got {act_val}, Exp {pred_val} | Obj Got: {actual_state}, \nObj Exp: {predicted_state}"
            else:
                assert (
                    act_val == pred_val
                ), f"Final state | ID {order_id} | {key}: Got {act_val}, Exp {pred_val} | Obj Got: {actual_state}, \nObj Exp: {predicted_state}"

        # print("\n")

    print(f"--- Harness test with {num_orders} orders PASSED ---")
