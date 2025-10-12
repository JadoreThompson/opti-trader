class ExecutionContext:
    """
    An empty container object passed to strategy handlers
    """

    def __init__(
        self,
        *,
        engine: "EngineProtocol",
        orderbook: "OrderBook",
        order_store: "OrderStore",
        instrument_id: str,
    ) -> None:
        self.engine = engine
        self.orderbook = orderbook
        self.order_store = order_store
        self.instrument_id = instrument_id
