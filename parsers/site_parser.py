"""Parser for orders received from the website (pizza-ragazzi.ru)."""
from __future__ import annotations

import re
from typing import Optional

from parsers.base import BaseParser, ParsedItem, ParsedOrder
from database.models import OrderSource, OrderType


_RE_ORDER_NUM = re.compile(r"Order\s+#(\d+)", re.IGNORECASE)
_RE_ITEM = re.compile(
    r"^\s*\d+\.\s*(.+?):\s*([\d.]+)\s*\((\d+)\s*x\s*([\d.]+)\)",
    re.MULTILINE,
)
_RE_PAYMENT_AMOUNT = re.compile(r"Payment Amount:\s*([\d.]+)\s*RUB", re.IGNORECASE)
_RE_NAME = re.compile(r"Имя:\s*(.+)", re.IGNORECASE)
_RE_PHONE = re.compile(r"Телефон:\s*(.+)", re.IGNORECASE)
_RE_DELIVERY_TYPE = re.compile(r"Delivery:\s*(.+)", re.IGNORECASE)
_RE_PICKUP_LOCATION = re.compile(r"Самовывоз:\s*(.+)", re.IGNORECASE)
_RE_DELIVERY_ADDRESS = re.compile(r"Адрес доставки:\s*(.+)", re.IGNORECASE)
_RE_DELIVERY_TIME = re.compile(r"Время_доставки:\s*(.+)", re.IGNORECASE)
_RE_DATE = re.compile(r"Дата:\s*(.+)", re.IGNORECASE)
_RE_PAYMENT_ID = re.compile(r"Payment ID:\s*(.+)", re.IGNORECASE)
_RE_PAID = re.compile(r"The order is paid for", re.IGNORECASE)
_RE_COD = re.compile(r"оплата при получении|наличные|cash on delivery", re.IGNORECASE)


class SiteParser(BaseParser):
    name = "site"
    priority = 10

    def can_parse(self, text: str) -> bool:
        return bool(_RE_ORDER_NUM.search(text)) and "pizza-ragazzi.ru" in text.lower()

    def parse(self, text: str) -> ParsedOrder:
        order = ParsedOrder(source=OrderSource.SITE)

        m = _RE_ORDER_NUM.search(text)
        if m:
            order.order_number = m.group(1)

        # Items
        for m in _RE_ITEM.finditer(text):
            name = m.group(1).strip()
            qty = int(m.group(3))
            price = float(m.group(4))
            order.items.append(ParsedItem(name=name, quantity=qty, price=price))

        # Total from payment amount
        m = _RE_PAYMENT_AMOUNT.search(text)
        if m:
            order.total_amount = float(m.group(1))
        else:
            # Fallback: sum items
            if order.items:
                order.total_amount = sum(i.quantity * i.price for i in order.items)
                order.parse_warnings.append("Total calculated from items (no Payment Amount field)")

        # Customer
        m = _RE_NAME.search(text)
        if m:
            order.customer_name = m.group(1).strip()

        m = _RE_PHONE.search(text)
        if m:
            order.customer_phone = self._normalize_phone(m.group(1).strip())

        # Delivery type
        is_pickup = False
        m = _RE_DELIVERY_TYPE.search(text)
        if m:
            delivery_val = m.group(1).strip().lower()
            is_pickup = "самовывоз" in delivery_val

        if is_pickup:
            order.order_type = OrderType.PICKUP
            m = _RE_PICKUP_LOCATION.search(text)
            if m:
                order.pickup_branch_name = m.group(1).strip()
            else:
                order.parse_warnings.append("Pickup location not found")
        else:
            order.order_type = OrderType.DELIVERY
            m = _RE_DELIVERY_ADDRESS.search(text)
            if m:
                order.delivery_address = m.group(1).strip()
            else:
                # Try to extract address from Delivery field itself
                m2 = _RE_DELIVERY_TYPE.search(text)
                if m2 and "самовывоз" not in m2.group(1).lower():
                    order.delivery_address = m2.group(1).strip()
                    order.parse_warnings.append("Delivery address extracted from Delivery field")
                else:
                    order.parse_warnings.append("Delivery address not found")

        # Time and date
        m = _RE_DELIVERY_TIME.search(text)
        if m:
            order.delivery_time = m.group(1).strip()

        m = _RE_DATE.search(text)
        if m:
            order.order_date = m.group(1).strip()

        # Payment
        payment_id_match = _RE_PAYMENT_ID.search(text)
        if _RE_PAID.search(text):
            order.payment_status = "Оплачено"
            if payment_id_match:
                pid = payment_id_match.group(1).strip()
                order.payment_method = self._detect_payment_method(pid)
            else:
                order.payment_method = "Online"
        elif _RE_COD.search(text):
            order.payment_status = "При получении"
            order.payment_method = "Наличные"
        else:
            order.payment_status = "Не оплачено"

        if not order.order_number:
            raise ValueError("Order number not found in site message")

        return order

    @staticmethod
    def _normalize_phone(raw: str) -> str:
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 11 and digits.startswith("7"):
            d = digits[1:]
            return f"+7 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:]}"
        if len(digits) == 10:
            return f"+7 ({digits[:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:]}"
        return raw

    @staticmethod
    def _detect_payment_method(payment_id: str) -> str:
        lower = payment_id.lower()
        if "yookassa" in lower or "юкасса" in lower:
            return "YooKassa (Online)"
        if "sber" in lower:
            return "СберПэй (Online)"
        if "tinkoff" in lower or "tpay" in lower:
            return "Tinkoff Pay (Online)"
        return "Online эквайринг"
