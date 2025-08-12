class ExecutionContext:
    """
    An empty container object passed to strategy handlers
    """

    def __init__(
        self,
        *,
        engine: "EngineProtocol",
        orderbook: "OrderBook",
        balance_manager: "BalanceManager",
        order_store: "OrderStore",
    ) -> None:
        self.engine = engine
        self.orderbook = orderbook
        self.balance_manager = balance_manager
        self.order_store = order_store
