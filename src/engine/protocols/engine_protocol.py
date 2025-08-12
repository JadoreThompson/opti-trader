from typing import Protocol

from ..execution_context import ExecutionContext
from ..orders import Order
from ..typing import MatchResult


class EngineProtocol(Protocol):
    def match(self, order: Order, ctx: ExecutionContext) -> MatchResult: ...
