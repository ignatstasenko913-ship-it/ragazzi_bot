"""Formats a ParsedOrder into the unified Telegram message template."""
from __future__ import annotations

from parsers.base import ParsedOrder, ParsedItem
from database.models import OrderType, OrderSource


def format_order(order: ParsedOrder, branch_name: str = "") -> str:
    """
    Produces the canonical order message for sending to a branch group.

    Pickup format:
        Самовывоз: Сайт / Приложение
        №XXXX
        ...

    Delivery format:
        Доставка: Сайт / Приложение
        №XXXX
        ...
    """
    source_label = _source_label(order.source)
    order_type_label = _order_type_label(order.order_type)
    lines: list[str] = []

    # ── Header ─────────────────────────────────────────────────────────────────
    lines.append(f"{order_type_label}: {source_label}")
    lines.append(f"№{order.order_number or '—'}")
    lines.append(order.customer_name or "—")
    lines.append(order.customer_phone or "—")

    # ── Location ───────────────────────────────────────────────────────────────
    if order.order_type == OrderType.PICKUP:
        location = branch_name or order.pickup_branch_name or "—"
        lines.append(f"Самовывоз")
        lines.append(location)
    else:
        lines.append(f"Адрес доставки:")
        lines.append(order.delivery_address or "—")

    # ── Time ───────────────────────────────────────────────────────────────────
    time_val = order.delivery_time or "—"
    lines.append(f"Время: {time_val}")

    lines.append("")  # blank line

    # ── Payment ────────────────────────────────────────────────────────────────
    payment_line = _payment_line(order.payment_method, order.payment_status)
    lines.append(payment_line)

    # ── Comment ────────────────────────────────────────────────────────────────
    lines.append(f"Комментарий к заказу: {order.comment or ''}")

    lines.append("")  # blank line

    # ── Items ──────────────────────────────────────────────────────────────────
    for item in order.items:
        lines.append(_format_item(item))

    lines.append("")  # blank line

    # ── Totals ─────────────────────────────────────────────────────────────────
    total = f"{order.total_amount:.2f}" if order.total_amount is not None else "—"
    lines.append(f"Итого: {total} р.")

    if order.discount and order.discount > 0:
        lines.append(f"Скидка: {order.discount:.2f} р.")

    return "\n".join(lines)


def format_manager_notification(
    order: ParsedOrder,
    reason: str,
    branch_name: str = "",
    order_db_id: int = 0,
) -> str:
    """Notification sent to managers for problematic orders / duplicates."""
    source_label = _source_label(order.source)
    header = f"⚠️ Проблемный заказ — {reason}"
    body = format_order(order, branch_name=branch_name)
    footer = f"\n🆔 ID в БД: {order_db_id}" if order_db_id else ""
    return f"{header}\n\n{body}{footer}"


def format_duplicate_notification(
    order: ParsedOrder,
    original_order_db_id: int,
    order_db_id: int = 0,
) -> str:
    source_label = _source_label(order.source)
    body = format_order(order)
    return (
        f"🔁 Дубликат заказа\n"
        f"Оригинал ID: {original_order_db_id}\n\n"
        f"{body}"
        + (f"\n🆔 ID дубля: {order_db_id}" if order_db_id else "")
    )


def format_parse_error_notification(raw_text: str, error: str, order_db_id: int = 0) -> str:
    truncated = raw_text[:800] + ("…" if len(raw_text) > 800 else "")
    return (
        f"❌ Не удалось распознать заказ\n"
        f"Ошибка: {error}\n\n"
        f"Оригинальный текст:\n"
        f"```\n{truncated}\n```"
        + (f"\n🆔 ID: {order_db_id}" if order_db_id else "")
    )


# ── Helpers ───────────────────────────────────────────────────────────────────

def _source_label(source) -> str:
    from database.models import OrderSource
    return {
        OrderSource.SITE: "Сайт",
        OrderSource.APP: "Приложение",
        OrderSource.UNKNOWN: "Неизвестно",
    }.get(source, str(source))


def _order_type_label(order_type) -> str:
    from database.models import OrderType
    if order_type == OrderType.PICKUP:
        return "Самовывоз"
    if order_type == OrderType.DELIVERY:
        return "Доставка"
    return "Заказ"


def _payment_line(method: str | None, status: str | None) -> str:
    parts = []
    if method:
        parts.append(method)
    if status:
        parts.append(status)
    return " — ".join(parts) if parts else "Оплата: —"


def _format_item(item: ParsedItem) -> str:
    return f"-{item.name} ({item.quantity}x{item.price:.2f}р.)"
