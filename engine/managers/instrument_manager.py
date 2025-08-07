from enums import MarketType
from .futures_balance_manager import FuturesBalanceManager
from .spot_balance_manager import SpotBalanceManager
from ..market_maker import MarketMaker
from ..orderbook import OrderBook
from ..orders import Order, Order


class InstrumentManager:
    def __init__(self):
        self._orderbooks: dict = {}
        self._market_maker = MarketMaker()

    def get(
        self, instrument: str, market_type: MarketType | None = None
    ) -> tuple[OrderBook, SpotBalanceManager]:
        res = None

        if instrument not in self._orderbooks:
            if market_type == MarketType.FUTURES:
                BmTyp = FuturesBalanceManager
            else:
                BmTyp = SpotBalanceManager
            
            res = (OrderBook(), BmTyp())
            self._orderbooks[instrument] = res
        else:
            res = self._orderbooks[instrument]

        return res
