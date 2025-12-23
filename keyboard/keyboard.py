from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.filters.callback_data import CallbackData
from datetime import datetime

tomorrow_but = InlineKeyboardButton(text="tomorrow", callback_data="tomorrow")
today_but = InlineKeyboardButton(text="today", callback_data="today")
other_but = InlineKeyboardButton(text="other", callback_data="other")


buttons = [
    InlineKeyboardButton(text=f"{str(i)}:00", callback_data=str(i))
    for i in range(1, 13)
]
buttons.append(other_but)
builder = InlineKeyboardBuilder()
builder.row(*buttons, width=3)

keyboard_markup = InlineKeyboardMarkup(
    inline_keyboard=[[tomorrow_but, today_but, other_but]]
)

days = [InlineKeyboardButton(text=str(i), callback_data=str(i)) for i in range(1, 32)]
months = ["December", "January", "February"]
months_kb = [
    InlineKeyboardButton(text=months[i], callback_data=months[i].lower())
    for i in range(len(months))
]
back = InlineKeyboardButton(text="<", callback_data="<")
forward = InlineKeyboardButton(text=">", callback_data=">")


class DateFactory(CallbackData, prefix="months"):
    month_id: int
    day_id: int


months_ids = [i for i in range(1, 13)]
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


def create_kb_month(month_id: int, year: int) -> InlineKeyboardBuilder:
    kb = []
    

    kb_builder = InlineKeyboardBuilder()
    days = months_days[month_id - 1]
    month_button_text: str = months_names[month_id - 1] +' ' +str(year)
    month_button = InlineKeyboardButton(
        text=month_button_text, callback_data=str(month_id - 1)
    )
    back = InlineKeyboardButton(text="<", callback_data="<")
    forward = InlineKeyboardButton(text=">", callback_data=">")
    cancel = InlineKeyboardButton(text="cancel", callback_data="cancel")
    kb_builder.row(back, month_button, forward, width=3)
    for day in range(1, days + 1):
        button = InlineKeyboardButton(
            text=str(day),
            callback_data=DateFactory(month_id=month_id, day_id=day).pack(),
        )
        kb.append(button)
    kb_builder.row(*kb, width=7)
    kb_builder.row(cancel, width=1)
    return kb_builder
