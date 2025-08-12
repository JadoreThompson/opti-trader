import copy
import uuid

import pytest

from src.engine import (
    SpotEngine,
    CommandType,
    Command,
    NewSingleOrder,
    NewOTOOrder,
    NewOCOOrder,
    NewOTOCOOrder,
    CancelOrderCommand,
)
from src.enums import OrderType, Side, StrategyType


ORDER_QUANTITIES = [10, 50, 100]
PRICE_STEP = 0.01
RESTING_ORDER_QTY = 10


@pytest.fixture(scope="session")
def populated_engine_factory():
    """
    (Session-Scoped) Factory fixture to create a SpotEngine.
    Returns a function that can create an engine with a specified book depth.
    """
    engine = SpotEngine(instrument_ids=["BTC-USD"])

    def _create_populated_engine(book_depth: int):
        orders_per_side = book_depth // 2
        mid_price = (orders_per_side * PRICE_STEP) + 1.0

        # Populate bids
        for i in range(orders_per_side):
            price = (mid_price - PRICE_STEP) - (i * PRICE_STEP)
            cmd = Command(
                command_type=CommandType.NEW_ORDER,
                data=NewSingleOrder(
                    strategy_type=StrategyType.SINGLE,
                    instrument_id="BTC-USD",
                    order={
                        "order_id": str(uuid.uuid4()),
                        "user_id": f"user_bid_{i}",
                        "order_type": OrderType.LIMIT,
                        "side": Side.BID,
                        "quantity": RESTING_ORDER_QTY,
                        "limit_price": price,
                    },
                ),
            )
            engine.process_command(cmd)

        # Populate asks
        for i in range(orders_per_side):
            price = (mid_price + PRICE_STEP) + (i * PRICE_STEP)
            cmd = Command(
                command_type=CommandType.NEW_ORDER,
                data=NewSingleOrder(
                    strategy_type=StrategyType.SINGLE,
                    instrument_id="BTC-USD",
                    order={
                        "order_id": str(uuid.uuid4()),
                        "user_id": f"user_ask_{i}",
                        "order_type": OrderType.LIMIT,
                        "side": Side.ASK,
                        "quantity": RESTING_ORDER_QTY,
                        "limit_price": price,
                    },
                ),
            )
            engine.process_command(cmd)
        return engine

    return _create_populated_engine


@pytest.fixture(scope="session")
def _master_deep_book_engine(populated_engine_factory):
    """
    (Session-Scoped) Creates the master, deeply populated engine ONCE per session.
    Tests should not use this directly to avoid state pollution.
    """
    print("\n[INFO] Creating session-scoped master engine with 1,000,000 orders...")
    engine = populated_engine_factory(10_000)
    print("[INFO] Master engine created.")
    return engine


@pytest.fixture
def deep_book_engine(_master_deep_book_engine):
    """
    (Function-Scoped) Provides each test function with a pristine, deep copy
    of the master engine, ensuring test isolation.
    """
    return copy.deepcopy(_master_deep_book_engine)


##### SINGLE STRATEGY ####


def test_perf_single_handle_new_non_matching(benchmark, deep_book_engine):
    """
    Benchmark processing a new, non-matching SINGLE limit order
    against a deeply populated order book.
    """

    def setup():
        cmd_data = NewSingleOrder(
            strategy_type=StrategyType.SINGLE,
            instrument_id="BTC-USD",
            order={
                "order_id": str(uuid.uuid4()),
                "user_id": "test_user",
                "order_type": OrderType.STOP,
                "side": Side.BID,
                "quantity": 10,
                "stop_price": deep_book_engine._ctxs["BTC-USD"].orderbook.best_bid
                + 500,  # Price is far from the market
            },
        )
        command = Command(command_type=CommandType.NEW_ORDER, data=cmd_data)
        return (command,), {}

    def target_func(command):
        deep_book_engine.process_command(command)

    benchmark.pedantic(target=target_func, setup=setup, rounds=10_000)


@pytest.mark.parametrize("order_quantity", ORDER_QUANTITIES)
def test_perf_single_match_and_fill(
    benchmark, deep_book_engine, order_quantity, populated_engine_factory
):
    """
    Benchmark matching a taker order that sweeps a varying number of price levels.
    """

    def setup():
        nonlocal deep_book_engine

        engine = copy.deepcopy(deep_book_engine)
        best_ask = engine._ctxs["BTC-USD"].orderbook.best_ask

        cmd_data = NewSingleOrder(
            strategy_type=StrategyType.SINGLE,
            instrument_id="BTC-USD",
            order={
                "order_id": str(uuid.uuid4()),
                "user_id": "taker",
                "order_type": OrderType.LIMIT,
                "side": Side.BID,
                "quantity": order_quantity,
                "limit_price": best_ask + (order_quantity * PRICE_STEP),
            },
        )
        command = Command(command_type=CommandType.NEW_ORDER, data=cmd_data)
        return (engine, command), {}

    def target_func(engine, cmd):
        engine.process_command(cmd)

    benchmark.pedantic(target=target_func, setup=setup, rounds=10_000, iterations=1)


@pytest.mark.parametrize("order_quantity", ORDER_QUANTITIES)
def test_perf_single_cancel(benchmark, deep_book_engine, order_quantity):
    """
    Benchmark cancelling a SINGLE order from a varying depth in the book.
    `order_quantity` here represents the N-th best price level to cancel from.
    """

    def setup():
        engine = copy.deepcopy(deep_book_engine)
        order_id_to_cancel = (
            engine._ctxs["BTC-USD"]
            .orderbook.bids.peekitem(-order_quantity)[1]
            .head.order.id
        )
        command = Command(
            command_type=CommandType.CANCEL_ORDER,
            data=CancelOrderCommand(order_id=order_id_to_cancel, symbol="BTC-USD"),
        )
        return (engine, command), {}

    def operation(engine, cmd):
        engine.process_command(cmd)

    benchmark.pedantic(operation, setup=setup, rounds=10_000, iterations=1)


##### OTO STRATEGY ####


def test_perf_oto_handle_new_parent_not_matching(benchmark, deep_book_engine):
    """
    Benchmark creating an OTO order where the parent does not match
    against the deep book.
    """

    def operation():
        entry_price = deep_book_engine._ctxs["BTC-USD"].orderbook.best_ask + 500
        parent_data = {
            "order_id": str(uuid.uuid4()),
            "user_id": "u1",
            "order_type": OrderType.STOP,
            "side": Side.BID,
            "quantity": 10,
            "stop_price": entry_price,
        }
        child_data = {
            "order_id": str(uuid.uuid4()),
            "user_id": "u1",
            "order_type": OrderType.LIMIT,
            "side": Side.ASK,
            "quantity": 10,
            "limit_price": entry_price + 100.0,
        }
        command = Command(
            command_type=CommandType.NEW_ORDER,
            data=NewOTOOrder(
                strategy_type=StrategyType.OTO,
                instrument_id="BTC-USD",
                parent=parent_data,
                child=child_data,
            ),
        )
        deep_book_engine.process_command(command)

    benchmark(operation)


@pytest.mark.parametrize("order_quantity", ORDER_QUANTITIES)
def test_perf_oto_parent_match_triggers_child(
    benchmark, deep_book_engine, order_quantity
):
    """
    Benchmark filling an OTO parent that sweeps `order_quantity` levels,
    which then triggers and places the child order.
    """

    def setup():
        engine = copy.deepcopy(deep_book_engine)
        best_bid = engine._ctxs["BTC-USD"].orderbook.best_bid

        # Parent order that will match against existing bids
        parent_data = {
            "order_id": str(uuid.uuid4()),
            "user_id": "u1",
            "order_type": OrderType.LIMIT,
            "side": Side.ASK,
            "quantity": order_quantity * RESTING_ORDER_QTY,
            "limit_price": best_bid,
        }
        child_data = {
            "order_id": str(uuid.uuid4()),
            "user_id": "u1",
            "order_type": OrderType.LIMIT,
            "side": Side.ASK,
            "quantity": 10,
            "limit_price": best_bid + 100.0,
        }
        oto_command = Command(
            command_type=CommandType.NEW_ORDER,
            data=NewOTOOrder(
                strategy_type=StrategyType.OTO,
                instrument_id="BTC-USD",
                parent=parent_data,
                child=child_data,
            ),
        )
        return (engine, oto_command), {}

    def operation_to_benchmark(engine, cmd):
        engine.process_command(cmd)

    benchmark.pedantic(
        target=operation_to_benchmark, setup=setup, rounds=10_000, iterations=1
    )


##### OCO STRATEGY ####


def test_perf_oco_handle_new(benchmark, deep_book_engine):
    """
    Benchmark creating a new OCO order, placing both non-matching legs
    on a deep book.
    """

    def operation():
        entry_price = deep_book_engine._ctxs["BTC-USD"].orderbook.best_ask + 500

        leg_a = {
            "order_id": str(uuid.uuid4()),
            "user_id": "u1",
            "order_type": OrderType.LIMIT,
            "side": Side.ASK,
            "quantity": 10,
            "limit_price": entry_price,
        }
        leg_b = {
            "order_id": str(uuid.uuid4()),
            "user_id": "u1",
            "order_type": OrderType.STOP,
            "side": Side.ASK,
            "quantity": 10,
            "stop_price": entry_price - 100.0,
        }
        command = Command(
            command_type=CommandType.NEW_ORDER,
            data=NewOCOOrder(
                strategy_type=StrategyType.OCO,
                instrument_id="BTC-USD",
                legs=[leg_a, leg_b],
            ),
        )
        deep_book_engine.process_command(command)

    benchmark(operation)


@pytest.mark.parametrize("order_quantity", ORDER_QUANTITIES)
def test_perf_oco_fill_one_leg_cancels_other(
    benchmark, deep_book_engine, order_quantity
):
    """
    Benchmark filling one OCO leg (by sweeping `order_quantity` levels),
    which triggers cancellation of the other leg.
    """

    def setup():
        engine = copy.deepcopy(deep_book_engine)
        best_ask = engine._ctxs["BTC-USD"].orderbook.best_ask

        # Place the OCO order first. Leg A will rest on the book.
        leg_a = {
            "order_id": "leg_a_id",
            "user_id": "u1",
            "order_type": OrderType.LIMIT,
            "side": Side.ASK,
            "quantity": order_quantity * RESTING_ORDER_QTY,
            "limit_price": best_ask + (order_quantity * PRICE_STEP) + 1,
        }
        leg_b = {
            "order_id": "leg_b_id",
            "user_id": "u1",
            "order_type": OrderType.LIMIT,
            "side": Side.ASK,
            "quantity": 10,
            "limit_price": leg_a["limit_price"] + 10,
        }
        oco_command = Command(
            command_type=CommandType.NEW_ORDER,
            data=NewOCOOrder(
                strategy_type=StrategyType.OCO,
                instrument_id="BTC-USD",
                legs=[leg_a, leg_b],
            ),
        )
        engine.process_command(oco_command)

        # This command will fill the existing orders and then fill leg_a
        filler_command = Command(
            command_type=CommandType.NEW_ORDER,
            data=NewSingleOrder(
                strategy_type=StrategyType.SINGLE,
                instrument_id="BTC-USD",
                order={
                    "order_id": str(uuid.uuid4()),
                    "user_id": "taker",
                    "order_type": OrderType.LIMIT,
                    "side": Side.BID,
                    "quantity": 500_000,
                    "limit_price": leg_a["limit_price"],
                },
            ),
        )
        return (engine, filler_command), {}

    def operation_to_benchmark(engine, cmd):
        engine.process_command(cmd)

    benchmark.pedantic(
        target=operation_to_benchmark, setup=setup, rounds=10, iterations=1
    )


##### OTOCO STRATEGY ####


def test_perf_otoco_handle_new_parent_not_matching(benchmark, deep_book_engine):
    """
    Benchmark creating an OTOCO order where the parent does not match
    against a deep book.
    """

    def operation():
        # entry_price = deep_book_engine._ctxs["BTC-USD"].orderbook.price + 5
        entry_price = deep_book_engine._ctxs["BTC-USD"].orderbook.best_bid - 500

        parent_data = {
            "order_id": str(uuid.uuid4()),
            "user_id": "u1",
            "order_type": OrderType.LIMIT,
            "side": Side.BID,
            "quantity": 10,
            "limit_price": entry_price,
        }
        leg_a = {
            "order_id": str(uuid.uuid4()),
            "user_id": "u1",
            "order_type": OrderType.LIMIT,
            "side": Side.ASK,
            "quantity": 10,
            "limit_price": entry_price + 100.0,
        }
        leg_b = {
            "order_id": str(uuid.uuid4()),
            "user_id": "u1",
            "order_type": OrderType.STOP,
            "side": Side.ASK,
            "quantity": 10,
            "stop_price": entry_price - 200.0,
        }
        command = Command(
            command_type=CommandType.NEW_ORDER,
            data=NewOTOCOOrder(
                strategy_type=StrategyType.OTOCO,
                instrument_id="BTC-USD",
                parent=parent_data,
                oco_legs=[leg_a, leg_b],
            ),
        )
        deep_book_engine.process_command(command)

    benchmark(operation)
