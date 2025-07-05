from dataclasses import dataclass, field
from .node import Node


class OrderbookItem:
    def __init__(self) -> None:
        self.head: Node | None = None
        self.tail: Node | None = None
        self.tracker: dict[str, Node] = {}
