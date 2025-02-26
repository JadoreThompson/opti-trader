class Position:
    def __init__(self, order: dict) -> None:
        self.instrument = order['instrument']
        self.order = order
        self.stop_loss = None
        self.take_profit = None
        
    