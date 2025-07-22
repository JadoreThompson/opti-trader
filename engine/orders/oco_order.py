from .spot_order import SpotOrder


class OCOOrder:
    """
    Represents a group of linked spot orders where the execution of one leg
    should cancel the other(s).

    This object can optionally track up to three related legs:
      - leg_a: an optional main entry order (e.g. a limit buy)
      - leg_b: one protective or conditional leg (e.g. a stop-loss or stop order)
      - leg_c: another protective or conditional leg (e.g. a take-profit or stop order)
    """

    def __init__(
        self,
        id_: str,
        leg_a: SpotOrder | None = None,
        leg_b: SpotOrder | None = None,
        leg_c: SpotOrder | None = None,
    ) -> None:
        self._id = id_
        self.leg_a = leg_a
        self.leg_b = leg_b
        self.leg_c = leg_c
        
    @property
    def id(self) -> str:
        return self._id