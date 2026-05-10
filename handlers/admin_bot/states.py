"""FSM states for the admin/manager bot."""
from aiogram.fsm.state import State, StatesGroup


class AdminMenu(StatesGroup):
    main = State()


class BranchManagement(StatesGroup):
    list = State()
    detail = State()
    confirm_toggle = State()
    adding_name = State()
    adding_address = State()
    adding_lat = State()
    adding_lon = State()
    adding_group = State()
    adding_short_name = State()


class ManualRouting(StatesGroup):
    select_order = State()
    select_branch = State()
    confirm = State()


class Statistics(StatesGroup):
    menu = State()


class OrdersView(StatesGroup):
    recent = State()
    problematic = State()
    duplicates = State()
    detail = State()
