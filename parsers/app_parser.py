"""Parser for orders received from the mobile app «Pizza Ragazzi»."""
from __future__ import annotations

import re
from typing import Optional

from parsers.base import BaseParser, ParsedItem, ParsedOrder
from database.models import OrderSource, OrderType


_RE_DATETIME = re.compile(r"(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2}:\d{2})")
_RE_APP_HEADER = re.compile(
    r"Новый заказ через приложение\s+[«\"]Pizza Ragazzi[»\"]", re.IGNORECASE
)
_RE_ORDER_NUM = re.compile(r"№\s*(\d+)")
_RE_EMAIL = re.compile(r"[\w.+-]+@welcm\.app")
_RE_PHONE = re.compile(r"\+7\s*[\(\s]?\d{3}[\)\s]?\s*\d{3}[-\s]?\d{2}[-\s]?\d{2}")
_RE_DELIVERY_COST = re.compile(r"Стоимость доставки:\s*([\d.]+)")
_RE_RESTAURANT = re.compile(r"Ресторан:\s*(.+)")
_RE_DELIVERY_ADDRESS = re.compile(r"Адрес\s*(?:доставки)?:\s*(.+)", re.IGNORECASE)
_RE_DELIVERY_TIME = re.compile(r"Время доставки:\s*(.+)", re.IGNORECASE)
_RE_TOTAL = re.compile(r"Итого:\s*([\d.]+)\s*р\.", re.IGNORECASE)
_RE_DISCOUNT = re.compile(r"скидка:\s*([\d.]+)\s*р\.", re.IGNORECASE)
_RE_ITEM = re.compile(
    r"^-(.+?)\s+([\d.]+)?\s*(?:см\.?)?\s*\((\d+)\s*[xх]\s*([\d.]+)\s*р\.\)",
    re.MULTILINE | re.IGNORECASE,
)
_RE_ITEM_SIMPLE = re.compile(
    r"^-(.+?)\s*\((\d+)\s*[xх]\s*([\d.]+)\s*р\.\)",
    re.MULTILINE | re.IGNORECASE,
)


class AppParser(BaseParser):
    name = "app"
    priority = 10

    def can_parse(self, text: str) -> bool:
        return bool(_RE_APP_HEADER.search(text))

    def parse(self, text: str) -> ParsedOrder:
        order = ParsedOrder(source=OrderSource.APP)

        # Date and time
        m = _RE_DATETIME.search(text)
        if m:
            order.order_date = m.group(1)

        # Order number
        m = _RE_ORDER_NUM.search(text)
        if m:
            order.order_number = m.group(1)

        # Lines for extracting name (appears right after order number line)
        lines = [l.strip() for l in text.splitlines() if l.strip()]
        order.customer_name = self._extract_name(text, lines)

        # Phone
        m = _RE_PHONE.search(text)
        if m:
            order.customer_phone = self._normalize_phone(m.group(0).strip())

        # Order type
        is_pickup = "Самовывоз из ресторана" in text or "самовывоз" in text.lower()
        delivery_cost_match = _RE_DELIVERY_COST.search(text)
        delivery_cost = float(delivery_cost_match.group(1)) if delivery_cost_match else 0.0

        if is_pickup or delivery_cost == 0.0:
            order.order_type = OrderType.PICKUP
            m = _RE_RESTAURANT.search(text)
            if m:
                order.pickup_branch_name = m.group(1).strip()
        else:
            order.order_type = OrderType.DELIVERY
            m = _RE_DELIVERY_ADDRESS.search(text)
            if m:
                order.delivery_address = m.group(1).strip()
            else:
                order.parse_warnings.append("Delivery address not found in app message")

        # Delivery time
        m = _RE_DELIVERY_TIME.search(text)
        if m:
            order.delivery_time = m.group(1).strip()

        # Payment section
        order.payment_method, order.payment_status = self._parse_payment(text)

        # Comment
        order.comment = self._extract_comment(text)

        # Items
        order.items = self._parse_items(text)

        # Totals
        m = _RE_TOTAL.search(text)
        if m:
            order.total_amount = float(m.group(1))
        elif order.items:
            order.total_amount = sum(i.quantity * i.price for i in order.items)
            order.parse_warnings.append("Total calculated from items")

        m = _RE_DISCOUNT.search(text)
        if m:
            order.discount = float(m.group(1))

        if not order.order_number:
            raise ValueError("Order number not found in app message")

        return order

    @staticmethod
    def _extract_name(text: str, lines: list[str]) -> Optional[str]:
        """Name is the first non-special line after the order number line."""
        found_num = False
        skip_patterns = [
            _RE_EMAIL, _RE_PHONE, _RE_DATETIME, _RE_APP_HEADER,
            re.compile(r"^\d{2}\.\d{2}\.\d{4}"),
        ]
        for line in lines:
            if _RE_ORDER_NUM.match(line) or _RE_ORDER_NUM.search(line):
                found_num = True
                continue
            if found_num:
                skip = any(p.search(line) for p in skip_patterns)
                if not skip and len(line) > 1 and len(line) < 60:
                    return line
        return None

    @staticmethod
    def _parse_payment(text: str) -> tuple[str, str]:
        method = "Online эквайринг"
        status = "Не оплачено"

        if "Online эквайринг" in text or "online эквайринг" in text.lower():
            method = "Online эквайринг"
        elif "наличные" in text.lower() or "при получении" in text.lower():
            method = "Наличные"

        if "Оплачено" in text:
            status = "Оплачено"
        elif "Не оплачено" in text:
            status = "Не оплачено"

        return method, status

    @staticmethod
    def _extract_comment(text: str) -> Optional[str]:
        m = re.search(r"Комментарий к заказу:\s*(.*?)(?=Состав заказа|$)", text, re.DOTALL)
        if m:
            comment = m.group(1).strip()
            return comment if comment else None
        return None

    @staticmethod
    def _parse_items(text: str) -> list[ParsedItem]:
        # Grab everything after "Состав заказа"
        section_match = re.search(r"Состав заказа\s*(.*?)(?=Итого:|$)", text, re.DOTALL)
        section = section_match.group(1) if section_match else text

        items: list[ParsedItem] = []

        # Try full pattern with size: "- Name Size cm.(qty x price р.)"
        for m in _RE_ITEM.finditer(section):
            raw_name = m.group(1).strip()
            size = m.group(2)
            qty = int(m.group(3))
            price = float(m.group(4))
            name = f"{raw_name} {size} см." if size else raw_name
            name = name.strip()
            items.append(ParsedItem(name=name, quantity=qty, price=price))

        if items:
            return items

        # Fallback: simple pattern "(qty x price р.)"
        for m in _RE_ITEM_SIMPLE.finditer(section):
            name = m.group(1).strip()
            qty = int(m.group(2))
            price = float(m.group(3))
            items.append(ParsedItem(name=name, quantity=qty, price=price))

        return items

    @staticmethod
    def _normalize_phone(raw: str) -> str:
        digits = re.sub(r"\D", "", raw)
        if len(digits) == 11 and digits.startswith("7"):
            d = digits[1:]
            return f"+7 ({d[:3]}) {d[3:6]}-{d[6:8]}-{d[8:]}"
        if len(digits) == 10:
            return f"+7 ({digits[:3]}) {digits[3:6]}-{digits[6:8]}-{digits[8:]}"
        return raw
