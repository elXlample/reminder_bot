from logging import basicConfig
from config.config import Config, load_config
from sql.todo_actions import get_total_pages
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from datetime import datetime
from zoneinfo import ZoneInfo
import logging
from psycopg import AsyncConnection

config: Config = load_config()
logging.basicConfig(
    level=config.log.level,
    format=config.log.format,
)

logger = logging.getLogger(__name__)


tomorrow_but = InlineKeyboardButton(text="Завтра", callback_data="tomorrow")
today_but = InlineKeyboardButton(text="Сегодня", callback_data="today")
other_but = InlineKeyboardButton(text="Другая дата", callback_data="other")


keyboard_markup = InlineKeyboardMarkup(
    inline_keyboard=[[tomorrow_but, today_but, other_but]]
)


class TodoFactory(CallbackData, prefix="todos"):
    todo_name: str
    todo_time: str | None
    todo_done: str


class TodoDeleteFactory(CallbackData, prefix="delete"):
    todo_name: str
    todo_done: str


class DateFactory(CallbackData, prefix="months"):
    year_id: int
    month_id: int
    day_id: int


class PageButton(CallbackData, prefix="pages"):
    page_up: int | None
    page_down: int | None
    from_page: int | None


cancel = InlineKeyboardButton(text="Отмена", callback_data="cancel")


months_ids = [i for i in range(0, 12)]
months_names = [
    "Январь",
    "Февраль",
    "Март",
    "Апрель",
    "Май",
    "Июнь",
    "Июль",
    "Август",
    "Сентябрь",
    "Октябрь",
    "Ноябрь",
    "Декабрь",
]
months_days = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]

regions = [
    "Africa",
    "America",
    "Antarctica",
    "Asia",
    "Atlantic",
    "Australia",
    "Europe",
    "Indian",
    "Pacific",
]
regions_ru = [
    "Африка",
    "Америка",
    "Антарктика",
    "Азия",
    "Атлантика",
    "Австралия",
    "Европа",
    "Индия",
    "Тихий Океан",
]
##
regions_kb_buttons = [
    InlineKeyboardButton(text=regions_ru[i], callback_data=regions[i].lower())
    for i in range(len(regions))
]
region_kb_builder = InlineKeyboardBuilder()
region_kb_builder.row(*regions_kb_buttons, width=3)
region_kb_builder.row(cancel)


def create_kb_month(month_id: int, year: int) -> InlineKeyboardBuilder:
    kb = []

    kb_builder = InlineKeyboardBuilder()
    days = months_days[month_id]
    month_button_text: str = months_names[month_id] + " " + str(year)
    month_button = InlineKeyboardButton(
        text=month_button_text, callback_data=str(month_id)
    )
    back = InlineKeyboardButton(text="<", callback_data="<")
    forward = InlineKeyboardButton(text=">", callback_data=">")

    kb_builder.row(back, month_button, forward, width=3)
    for day in range(1, days + 1):
        button = InlineKeyboardButton(
            text=str(day),
            callback_data=DateFactory(
                year_id=year, month_id=month_id, day_id=day
            ).pack(),
        )
        kb.append(button)
    kb_builder.row(*kb, width=7)
    kb_builder.row(cancel, width=1)
    return kb_builder


def build_todo_keyboard(
    todos: list,
    show_all: bool,
    user_id: int,
    conn: AsyncConnection,
    page: int | None,
    total_pages: int,
) -> InlineKeyboardBuilder:
    kb_builder = InlineKeyboardBuilder()
    back = InlineKeyboardButton(
        text="<",
        callback_data=PageButton(page_down=1, page_up=0, from_page=page).pack(),
    )
    forward = InlineKeyboardButton(
        text=">",
        callback_data=PageButton(page_up=1, page_down=0, from_page=page).pack(),
    )
    if not page:
        page = 1

    page_button = InlineKeyboardButton(
        text=f"Страница {page}/{total_pages}", callback_data=f"{page}"
    )

    kb_builder.row(back, page_button, forward, width=3)
    show_only_active = InlineKeyboardButton(
        text="Показать только активные", callback_data="show_only_active"
    )
    show_all_button = InlineKeyboardButton(
        text="Показать все", callback_data="show_all"
    )
    if show_all:
        kb_builder.row(show_only_active)
    else:
        kb_builder.row(show_all_button)
    for item in todos:
        user_timezone = item.get("timezone") or "Europe/Moscow"
        reminder_datetime = item.get("reminder_time")
        reminder_datetime = datetime.fromisoformat(reminder_datetime)
        reminder_datetime = reminder_datetime.replace(tzinfo=ZoneInfo(user_timezone))
        done = item.get("done")
        todo = item.get("todo")

        done_symbol = "☐"
        if str(done).lower() == "true":
            done_symbol = "☑"
        delete_symbol = "⌫ "

        reminder_datetime_text = reminder_datetime.strftime("%Y-%m-%d %H-%M")

        action = InlineKeyboardButton(
            text=f"{todo} {reminder_datetime_text[5:]}", callback_data=todo
        )
        done_button = InlineKeyboardButton(
            text=done_symbol,
            callback_data=TodoFactory(
                todo_name=todo.lower(),
                todo_done=str(done),
                todo_time=reminder_datetime_text,
            ).pack(),
        )
        delete_button = InlineKeyboardButton(
            text=delete_symbol,
            callback_data=TodoDeleteFactory(
                todo_name=todo.lower(),
                todo_done=str(done),
                todo_time=reminder_datetime_text,
            ).pack(),
        )

        if not show_all:
            if str(done).lower() == "true":
                continue
            else:
                kb_builder.row(action, done_button, delete_button)
        else:
            kb_builder.row(action, done_button, delete_button)
    kb_builder.row(cancel)
    return kb_builder


def build_activity_kb(stats: list) -> InlineKeyboardBuilder:
    kb_builder_activity = InlineKeyboardBuilder()
    buttons = []
    for stat in stats:
        user_id = stat[0]
        activity = stat[1]
        button = InlineKeyboardButton(
            text=f"{user_id}: {activity} действий",
            callback_data=f"{user_id}:{activity}",
        )
        buttons.append(button)
    kb_builder_activity.row(*buttons)
    return kb_builder_activity
