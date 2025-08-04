from enums import MarketType
from .balance_manager import BalanceManager
from ..market_maker import MarketMaker
from ..orderbook import OrderBook
from ..orders import SpotOrder, Order


class InstrumentManager:
    def __init__(self):
        self._orderbooks: dict = {}
        self._market_maker = MarketMaker()

    def get(
        self, instrument: str, market_type: MarketType | None = None
    ) -> OrderBook[Order] | tuple[OrderBook[SpotOrder], BalanceManager]:
        res = None

        if instrument not in self._orderbooks:
            if market_type == MarketType.SPOT:
                self._orderbooks[instrument] = (
                    OrderBook[SpotOrder](), BalanceManager()
                )
                ob, bm = self._orderbooks[instrument]
                # self._market_maker.seed(instrument, ob, bm)
                res = ob, bm
            else:
                res = self._orderbooks[instrument] = OrderBook[Order]()
        else:
            res = self._orderbooks[instrument]

        return res
