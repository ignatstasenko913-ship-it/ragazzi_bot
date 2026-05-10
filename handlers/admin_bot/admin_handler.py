"""Admin bot handlers: main menu, branch management, statistics, manual routing."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from loguru import logger

from config import settings
from database import OrderType
from handlers.admin_bot.keyboards import (
    back_to_main_kb,
    branch_detail_kb,
    branch_select_kb,
    branches_list_kb,
    main_menu_kb,
    problematic_order_kb,
)
from handlers.admin_bot.states import AdminMenu, BranchManagement, ManualRouting
from services.branch_service import branch_service
from services.notification_service import notification_service
from services.order_service import order_service
from utils.formatters import format_order

router = Router(name="admin")


# ── Access control ─────────────────────────────────────────────────────────────

def is_admin(user_id: int) -> bool:
    return user_id in settings.ADMIN_IDS


def is_manager(user_id: int) -> bool:
    return user_id in settings.MANAGER_IDS or is_admin(user_id)


def admin_only(func):
    import functools
    @functools.wraps(func)
    async def wrapper(event, *args, **kwargs):
        uid = event.from_user.id if hasattr(event, "from_user") else 0
        if not is_admin(uid):
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Нет доступа", show_alert=True)
            else:
                await event.answer("⛔ Нет доступа")
            return
        return await func(event, *args, **kwargs)
    return wrapper


def manager_only(func):
    import functools
    @functools.wraps(func)
    async def wrapper(event, *args, **kwargs):
        uid = event.from_user.id if hasattr(event, "from_user") else 0
        if not is_manager(uid):
            if isinstance(event, CallbackQuery):
                await event.answer("⛔ Нет доступа", show_alert=True)
            else:
                await event.answer("⛔ Нет доступа")
            return
        return await func(event, *args, **kwargs)
    return wrapper


# ── /start ────────────────────────────────────────────────────────────────────

@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    uid = message.from_user.id
    if not is_manager(uid):
        await message.answer("⛔ У вас нет доступа к этой системе.")
        return
    role = "Администратор" if is_admin(uid) else "Менеджер"
    await state.set_state(AdminMenu.main)
    await message.answer(
        f"🍕 *Ragazzi — система маршрутизации заказов*\n\n"
        f"Роль: *{role}*\n\n"
        f"Выберите раздел:",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown",
    )


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext) -> None:
    await cmd_start(message, state)


# ── Main menu callbacks ────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:main")
@manager_only
async def cb_main_menu(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(AdminMenu.main)
    await call.message.edit_text(
        "🍕 *Ragazzi — система маршрутизации заказов*\n\nВыберите раздел:",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown",
    )
    await call.answer()


# ── Branches ──────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:branches")
@manager_only
async def cb_branches(call: CallbackQuery, state: FSMContext) -> None:
    branches = await branch_service.get_all()
    text = "🏪 *Управление филиалами*\n\nВыберите филиал для управления:"
    await call.message.edit_text(
        text,
        reply_markup=branches_list_kb(branches),
        parse_mode="Markdown",
    )
    await call.answer()


@router.callback_query(F.data.startswith("branch:detail:"))
@manager_only
async def cb_branch_detail(call: CallbackQuery, state: FSMContext) -> None:
    branch_id = int(call.data.split(":")[-1])
    branch = await branch_service.get_by_id(branch_id)
    if not branch:
        await call.answer("Филиал не найден", show_alert=True)
        return

    status = "🟢 Активен" if branch.is_active else "🔴 Отключён"
    last_order = (
        branch.last_order_sent_at.strftime("%d.%m.%Y %H:%M")
        if branch.last_order_sent_at
        else "нет данных"
    )

    text = (
        f"🏪 *{branch.name}*\n\n"
        f"📍 Адрес: {branch.address}\n"
        f"📌 Координаты: {branch.lat:.6f}, {branch.lon:.6f}\n"
        f"💬 Группа: `{branch.telegram_group_id}`\n"
        f"Статус: {status}\n"
        f"Последний заказ: {last_order}"
    )
    await call.message.edit_text(
        text,
        reply_markup=branch_detail_kb(branch),
        parse_mode="Markdown",
    )
    await call.answer()


@router.callback_query(F.data.startswith("branch:toggle:"))
@admin_only
async def cb_branch_toggle(call: CallbackQuery, state: FSMContext) -> None:
    branch_id = int(call.data.split(":")[-1])
    branch = await branch_service.get_by_id(branch_id)
    if not branch:
        await call.answer("Филиал не найден", show_alert=True)
        return

    action = "отключить" if branch.is_active else "включить"
    from handlers.admin_bot.keyboards import confirm_toggle_kb
    await call.message.edit_text(
        f"Вы уверены, что хотите *{action}* филиал *{branch.name}*?",
        reply_markup=confirm_toggle_kb(branch_id, action),
        parse_mode="Markdown",
    )
    await call.answer()


@router.callback_query(F.data.startswith("branch:toggle_confirm:"))
@admin_only
async def cb_branch_toggle_confirm(call: CallbackQuery, state: FSMContext) -> None:
    branch_id = int(call.data.split(":")[-1])
    branch = await branch_service.toggle_active(branch_id)
    if not branch:
        await call.answer("Ошибка", show_alert=True)
        return

    status = "включён 🟢" if branch.is_active else "отключён 🔴"
    await call.answer(f"Филиал {branch.name} {status}", show_alert=True)
    # Refresh detail page
    await cb_branch_detail.__wrapped__(call, state)  # type: ignore[attr-defined]


# ── Add branch ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "branch:add")
@admin_only
async def cb_branch_add_start(call: CallbackQuery, state: FSMContext) -> None:
    await state.set_state(BranchManagement.adding_name)
    await call.message.edit_text(
        "Введите *название* нового филиала:",
        reply_markup=back_to_main_kb(),
        parse_mode="Markdown",
    )
    await call.answer()


@router.message(BranchManagement.adding_name)
@admin_only
async def process_branch_name(message: Message, state: FSMContext) -> None:
    await state.update_data(name=message.text.strip())
    await state.set_state(BranchManagement.adding_short_name)
    await message.answer("Введите *краткое название* (например: жк Айвазовский):", parse_mode="Markdown")


@router.message(BranchManagement.adding_short_name)
@admin_only
async def process_branch_short_name(message: Message, state: FSMContext) -> None:
    await state.update_data(short_name=message.text.strip())
    await state.set_state(BranchManagement.adding_address)
    await message.answer("Введите *адрес* филиала:", parse_mode="Markdown")


@router.message(BranchManagement.adding_address)
@admin_only
async def process_branch_address(message: Message, state: FSMContext) -> None:
    await state.update_data(address=message.text.strip())
    await state.set_state(BranchManagement.adding_lat)
    await message.answer(
        "Введите *широту* (latitude), например: `43.200300`\n"
        "Можно получить на maps.google.com или 2gis.com",
        parse_mode="Markdown",
    )


@router.message(BranchManagement.adding_lat)
@admin_only
async def process_branch_lat(message: Message, state: FSMContext) -> None:
    try:
        lat = float(message.text.strip().replace(",", "."))
        await state.update_data(lat=lat)
        await state.set_state(BranchManagement.adding_lon)
        await message.answer(
            "Введите *долготу* (longitude), например: `131.937500`",
            parse_mode="Markdown",
        )
    except ValueError:
        await message.answer("❌ Некорректное значение. Введите число, например: `43.200300`", parse_mode="Markdown")


@router.message(BranchManagement.adding_lon)
@admin_only
async def process_branch_lon(message: Message, state: FSMContext) -> None:
    try:
        lon = float(message.text.strip().replace(",", "."))
        await state.update_data(lon=lon)
        await state.set_state(BranchManagement.adding_group)
        await message.answer(
            "Введите *ID группы* Telegram куда будут приходить заказы\n"
            "(например: `-1001234567890`)",
            parse_mode="Markdown",
        )
    except ValueError:
        await message.answer("❌ Некорректное значение. Введите число, например: `131.937500`", parse_mode="Markdown")


@router.message(BranchManagement.adding_group)
@admin_only
async def process_branch_group(message: Message, state: FSMContext) -> None:
    group_id = message.text.strip()
    data = await state.get_data()
    branch = await branch_service.create(
        name=data["name"],
        address=data["address"],
        lat=data["lat"],
        lon=data["lon"],
        telegram_group_id=group_id,
        short_name=data.get("short_name", ""),
    )
    await state.set_state(AdminMenu.main)
    await message.answer(
        f"✅ Филиал *{branch.name}* добавлен (ID: {branch.id})\n\n"
        f"Статус: 🟢 Активен",
        reply_markup=main_menu_kb(),
        parse_mode="Markdown",
    )


# ── Statistics ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:stats")
@manager_only
async def cb_stats(call: CallbackQuery) -> None:
    stats = await order_service.get_today_stats()
    today = datetime.now().strftime("%d.%m.%Y")
    text = (
        f"📊 *Статистика за {today}*\n\n"
        f"Всего заказов: *{stats['total']}*\n"
        f"✅ Распределено: *{stats['routed']}*\n"
        f"⚠️ Проблемных: *{stats['problematic']}*\n"
        f"🔁 Дубликатов: *{stats['duplicates']}*"
    )
    await call.message.edit_text(text, reply_markup=back_to_main_kb(), parse_mode="Markdown")
    await call.answer()


# ── Branch load ───────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:load")
@manager_only
async def cb_load(call: CallbackQuery) -> None:
    load_stats = await branch_service.get_load_stats()
    today = datetime.now().strftime("%d.%m.%Y")
    lines = [f"⚖️ *Нагрузка филиалов за {today}*\n"]
    for stat in load_stats:
        branch = stat["branch"]
        status = "🟢" if branch.is_active else "🔴"
        last = stat["last_order_sent"]
        last_str = last.strftime("%H:%M") if last else "—"
        lines.append(
            f"{status} *{branch.name}*\n"
            f"   Заказов сегодня: {stat['orders_today']}\n"
            f"   Последний заказ: {last_str}"
        )
    await call.message.edit_text(
        "\n\n".join(lines),
        reply_markup=back_to_main_kb(),
        parse_mode="Markdown",
    )
    await call.answer()


# ── Recent orders ─────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:recent")
@manager_only
async def cb_recent_orders(call: CallbackQuery) -> None:
    orders = await order_service.get_recent(limit=10)
    if not orders:
        await call.message.edit_text("📋 Заказов нет.", reply_markup=back_to_main_kb())
        await call.answer()
        return

    lines = ["📋 *Последние 10 заказов:*\n"]
    for o in orders:
        time_str = o.created_at.strftime("%d.%m %H:%M")
        status_emoji = {
            "routed": "✅", "pending": "⏳", "problematic": "⚠️",
            "duplicate": "🔁", "parse_error": "❌", "manually_routed": "🔧", "cancelled": "🚫",
        }.get(o.status.value if o.status else "", "❓")
        lines.append(
            f"{status_emoji} #{o.order_number or o.id} | {o.customer_name or '—'} | {time_str}"
        )

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=back_to_main_kb(),
        parse_mode="Markdown",
    )
    await call.answer()


# ── Problematic orders ────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:problematic")
@manager_only
async def cb_problematic(call: CallbackQuery) -> None:
    orders = await order_service.get_problematic(unresolved_only=True)
    if not orders:
        await call.message.edit_text(
            "✅ Проблемных заказов нет.", reply_markup=back_to_main_kb()
        )
        await call.answer()
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    lines = ["⚠️ *Проблемные заказы (нерешённые):*\n"]
    for o in orders[:20]:
        reason = o.problem_reason.value if o.problem_reason else "?"
        lines.append(f"• #{o.order_number or o.id} — {reason}")
        builder.row(
            InlineKeyboardButton(
                text=f"#{o.order_number or o.id}",
                callback_data=f"problematic:view:{o.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )
    await call.answer()


@router.callback_query(F.data.startswith("problematic:view:"))
@manager_only
async def cb_problematic_view(call: CallbackQuery) -> None:
    order_id = int(call.data.split(":")[-1])
    order = await order_service.get_by_id(order_id)
    if not order:
        await call.answer("Заказ не найден", show_alert=True)
        return

    reason = order.problem_reason.value if order.problem_reason else "неизвестно"
    detail = order.problem_detail or ""
    text_preview = (order.raw_text or "")[:500]

    text = (
        f"⚠️ *Проблемный заказ* ID:{order_id}\n\n"
        f"Номер: {order.order_number or '—'}\n"
        f"Клиент: {order.customer_name or '—'}\n"
        f"Телефон: {order.customer_phone or '—'}\n"
        f"Причина: `{reason}`\n"
        f"Детали: {detail}\n\n"
        f"Текст:\n```\n{text_preview}\n```"
    )
    await call.message.edit_text(
        text,
        reply_markup=problematic_order_kb(order_id),
        parse_mode="Markdown",
    )
    await call.answer()


# ── Duplicates ────────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:duplicates")
@manager_only
async def cb_duplicates(call: CallbackQuery) -> None:
    orders = await order_service.get_duplicates()
    if not orders:
        await call.message.edit_text("🔁 Дубликатов нет.", reply_markup=back_to_main_kb())
        await call.answer()
        return

    lines = ["🔁 *Дубликаты (последние 20):*\n"]
    for o in orders[:20]:
        time_str = o.created_at.strftime("%d.%m %H:%M")
        lines.append(f"• #{o.order_number or o.id} | {o.customer_name or '—'} | {time_str}")

    await call.message.edit_text(
        "\n".join(lines),
        reply_markup=back_to_main_kb(),
        parse_mode="Markdown",
    )
    await call.answer()


# ── Manual routing ────────────────────────────────────────────────────────────

@router.callback_query(F.data == "menu:manual_route")
@manager_only
async def cb_manual_route_menu(call: CallbackQuery, state: FSMContext) -> None:
    orders = await order_service.get_problematic(unresolved_only=True)
    if not orders:
        await call.answer("Нет проблемных заказов для ручного распределения", show_alert=True)
        return

    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    builder = InlineKeyboardBuilder()
    for o in orders[:20]:
        reason = o.problem_reason.value if o.problem_reason else "?"
        builder.row(
            InlineKeyboardButton(
                text=f"#{o.order_number or o.id} — {reason}",
                callback_data=f"manual_route:{o.id}",
            )
        )
    builder.row(InlineKeyboardButton(text="⬅️ Назад", callback_data="menu:main"))

    await call.message.edit_text(
        "📤 *Выберите заказ для ручного распределения:*",
        reply_markup=builder.as_markup(),
        parse_mode="Markdown",
    )
    await call.answer()


@router.callback_query(F.data.startswith("manual_route:"))
@manager_only
async def cb_manual_route_select_branch(call: CallbackQuery, state: FSMContext) -> None:
    order_id = int(call.data.split(":")[-1])
    branches = await branch_service.get_all()

    await state.set_state(ManualRouting.select_branch)
    await state.update_data(order_id=order_id)

    await call.message.edit_text(
        f"📤 Выберите филиал для заказа *ID:{order_id}*:",
        reply_markup=branch_select_kb(branches, order_id),
        parse_mode="Markdown",
    )
    await call.answer()


@router.callback_query(F.data.startswith("route_to:"))
@manager_only
async def cb_route_to_branch(call: CallbackQuery, state: FSMContext) -> None:
    _, order_id_str, branch_id_str = call.data.split(":")
    order_id = int(order_id_str)
    branch_id = int(branch_id_str)

    order = await order_service.get_by_id(order_id)
    branch = await branch_service.get_by_id(branch_id)

    if not order or not branch:
        await call.answer("Заказ или филиал не найден", show_alert=True)
        return

    # Build formatted text from raw
    from parsers import build_registry
    registry = build_registry()
    parsed, _, _ = registry.parse(order.raw_text or "")
    if parsed:
        formatted = format_order(parsed, branch_name=branch.name)
    else:
        formatted = f"Ручная отправка заказа #{order.order_number or order_id}\n\n{order.raw_text}"

    ok = await notification_service.send_to_branch(branch.telegram_group_id, formatted)
    if ok:
        await order_service.mark_manually_routed(
            order_id, branch_id, formatted, call.from_user.id
        )
        await branch_service.mark_order_sent(branch_id)
        await call.message.edit_text(
            f"✅ Заказ #{order.order_number or order_id} отправлен в *{branch.name}*",
            reply_markup=back_to_main_kb(),
            parse_mode="Markdown",
        )
    else:
        await call.message.edit_text(
            f"❌ Не удалось отправить заказ в группу {branch.name}.\n"
            f"Проверьте, что бот является участником группы.",
            reply_markup=back_to_main_kb(),
            parse_mode="Markdown",
        )
    await call.answer()


@router.callback_query(F.data.startswith("cancel_order:"))
@manager_only
async def cb_cancel_order(call: CallbackQuery) -> None:
    order_id = int(call.data.split(":")[-1])
    await order_service.mark_cancelled(order_id)
    await call.message.edit_text(
        f"🚫 Заказ ID:{order_id} отменён.",
        reply_markup=back_to_main_kb(),
        parse_mode="Markdown",
    )
    await call.answer("Заказ отменён")


@router.callback_query(F.data.startswith("cancel_route:"))
@manager_only
async def cb_cancel_route(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.message.edit_text(
        "Ручное распределение отменено.",
        reply_markup=back_to_main_kb(),
    )
    await call.answer()
