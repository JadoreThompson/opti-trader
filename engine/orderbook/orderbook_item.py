from dataclasses import dataclass
from .node import Node

@dataclass
class OrderbookItem:
    head: Node | None = None
    tail: Node | None = None
    tracker: dict[str, Node] | None = None