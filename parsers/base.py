from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional

from database.models import OrderSource, OrderType


@dataclass
class ParsedItem:
    name: str
    quantity: int
    price: float

    def to_dict(self) -> dict:
        return {"name": self.name, "quantity": self.quantity, "price": self.price}


@dataclass
class ParsedOrder:
    source: OrderSource
    order_type: Optional[OrderType] = None
    order_number: Optional[str] = None

    # Customer
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None

    # Delivery / pickup
    delivery_address: Optional[str] = None
    pickup_branch_name: Optional[str] = None

    # Items
    items: List[ParsedItem] = field(default_factory=list)
    total_amount: Optional[float] = None
    discount: Optional[float] = None
    comment: Optional[str] = None

    # Payment
    payment_method: Optional[str] = None
    payment_status: Optional[str] = None

    # Time
    delivery_time: Optional[str] = None
    order_date: Optional[str] = None

    # Confidence: 0.0 – 1.0
    confidence: float = 1.0
    parse_warnings: List[str] = field(default_factory=list)


class BaseParser(ABC):
    """Abstract order parser. Subclass and implement `can_parse` and `parse`."""

    name: str = "base"
    priority: int = 0  # higher = tried first

    @abstractmethod
    def can_parse(self, text: str) -> bool:
        """Return True if this parser can handle the given message text."""

    @abstractmethod
    def parse(self, text: str) -> ParsedOrder:
        """Parse text and return a ParsedOrder. May raise ValueError on hard failures."""

    def safe_parse(self, text: str) -> tuple[Optional[ParsedOrder], Optional[str]]:
        """Wraps parse() with exception handling. Returns (result, error_message)."""
        try:
            result = self.parse(text)
            return result, None
        except Exception as exc:
            return None, str(exc)
