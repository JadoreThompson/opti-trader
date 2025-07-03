from dataclasses import dataclass, field
from .node import Node


@dataclass
class OrderbookItem:
    head: Node | None = None
    tail: Node | None = None
    tracker: dict[str, Node] = field(default_factory=dict)
