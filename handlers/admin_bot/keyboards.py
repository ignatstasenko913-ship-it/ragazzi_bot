"""All inline keyboards for the admin/manager bot."""
from __future__ import annotations

from typing import List

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from database import Branch


def main_menu_kb() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="🏪 Филиалы", callback_data="menu:branches"),
        InlineKeyboardButton(text="📊 Статистика", callback_data="menu:stats"),
    )
    builder.row(
        InlineKeyboardButton(text="📋 Последние заказы", callback_data="menu:recent"),
        InlineKeyboardButton(text="⚠️ Проблемные", callback_data="menu:problematic"),
    )
    builder.row(
        InlineKeyboardButton(text="🔁 Дубликаты", callback_data="menu:duplicates"),
        InlineKeyboardButton(text="⚖️ Нагрузка", callback_data="menu:load"),
    )
    builder.row(
        InlineKeyboardButton(text="📤 Ручное распределение", callback_data="menu:manual_route"),
    )
    return builder.as_markup()


def branches_list_kb(branches: List[Branch]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for branch in branches:
        status = "🟢" if branch.is_active else "🔴"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {branch.name}",
                callback_data=f"branch:detail:{branch.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="➕ Добавить филиал", callback_data="branch:add"),
        InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"),
    )
    return builder.as_markup()


def branch_detail_kb(branch: Branch) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_label = "🔴 Отключить" if branch.is_active else "🟢 Включить"
    builder.row(
        InlineKeyboardButton(
            text=toggle_label,
            callback_data=f"branch:toggle:{branch.id}",
        )
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ К списку филиалов", callback_data="menu:branches"),
        InlineKeyboardButton(text="🏠 Главное меню", callback_data="menu:main"),
    )
    return builder.as_markup()


def problematic_order_kb(order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📤 Отправить вручную", callback_data=f"manual_route:{order_id}"),
        InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"cancel_order:{order_id}"),
    )
    builder.row(
        InlineKeyboardButton(text="⬅️ К списку", callback_data="menu:problematic"),
    )
    return builder.as_markup()


def branch_select_kb(branches: List[Branch], order_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for branch in branches:
        status = "🟢" if branch.is_active else "🔴"
        builder.row(
            InlineKeyboardButton(
                text=f"{status} {branch.name}",
                callback_data=f"route_to:{order_id}:{branch.id}",
            )
        )
    builder.row(
        InlineKeyboardButton(text="❌ Отменить", callback_data=f"cancel_route:{order_id}"),
    )
    return builder.as_markup()


def back_to_main_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⬅️ Главное меню", callback_data="menu:main"),
    ]])


def confirm_toggle_kb(branch_id: int, action: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"branch:toggle_confirm:{branch_id}"),
        InlineKeyboardButton(text="❌ Отмена", callback_data=f"branch:detail:{branch_id}"),
    )
    return builder.as_markup()
