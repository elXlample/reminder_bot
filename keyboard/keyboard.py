from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from datetime import datetime

tomorrow_but = InlineKeyboardButton(text="tomorrow", callback_data="tomorrow")
today_but = InlineKeyboardButton(text="today", callback_data="today")
other_but = InlineKeyboardButton(text="other", callback_data="other")
back = InlineKeyboardButton(text="<", callback_data="<")
forward = InlineKeyboardButton(text=">", callback_data=">")
cancel = InlineKeyboardButton(text="cancel", callback_data="cancel")

keyboard_markup = InlineKeyboardMarkup(
    inline_keyboard=[[tomorrow_but, today_but, other_but]]
)


class DateFactory(CallbackData, prefix="months"):
    year_id: int
    month_id: int
    day_id: int


months_ids = [i for i in range(0, 12)]
months_names = [
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
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
##
regions_kb_buttons = [
    InlineKeyboardButton(text=regions[i], callback_data=regions[i].lower())
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
