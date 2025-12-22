from aiogram import Router, F, Bot
import asyncio
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state, State, StatesGroup
from aiogram.filters import CommandObject
from keyboard.keyboard import (
    keyboard_markup,
    create_kb_month,
    DateFactory,
)
from datetime import datetime


message_router = Router()


class DatePicker(StatesGroup):
    reminder = State()
    pick_date = State()
    pick_time = State()


def register_handlers(message_router: Router, bot: Bot):
    async def schedule_reminder(bot, chat_id, todo, reminder_datetime):
        now = datetime.now()
        delay = (reminder_datetime - now).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        await bot.send_message(chat_id, f"Don't forget to {todo}!")

    @message_router.message(CommandStart(), StateFilter(default_state))
    async def command_start(message: Message):
        await message.answer("hello!")

    @message_router.message(Command(commands="remind"), StateFilter(default_state))
    async def remind_message(
        message: Message, command: CommandObject, state: FSMContext
    ):
        text = command.args
        if text:
            await state.update_data(todo=text)

            await message.answer(
                text="Now please pick a date:", reply_markup=keyboard_markup
            )
            await state.set_state(DatePicker.pick_date)
        else:
            await message.answer("task can not be empty!")

    @message_router.message(Command(commands="cancel"), ~StateFilter(default_state))
    async def cancel_reminder(message: Message, state: FSMContext):
        await state.clear()
        await message.answer("Reminder cancelled! To make another reminder use /remind")

    @message_router.callback_query(
        StateFilter(DatePicker.pick_date), F.data.in_(["tomorrow", "today"])
    )
    async def normal_date(callback: CallbackQuery, state: FSMContext):
        month = str(datetime.now())[5:7]
        day = str(datetime.now())[8:10]
        if callback.data == "tomorrow":
            await state.update_data(month=month, day=str(int(day) + 1))
        elif callback.data == "today":
            await state.update_data(month=month, day=str(day))
        data = await state.get_data()
        month = data["month"]
        day = data["day"]

        await callback.message.edit_text(
            text="now please write down time(format 14:00)"
        )
        await state.set_state(DatePicker.pick_time)

    @message_router.callback_query(
        StateFilter(DatePicker.pick_date), F.data.in_(["other"])
    )
    async def other_date(callback: CallbackQuery, state: FSMContext):
        month = datetime.now().month
        year = datetime.now().year
        await state.update_data(current_month=month)
        await callback.message.edit_text(
            "Pick a date:",
            reply_markup=create_kb_month(
                month_id=datetime.now().month, year=year
            ).as_markup(),
        )

    @message_router.callback_query(StateFilter(DatePicker.pick_date), F.data == ">")
    async def next_month(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        current_month = int(data["current_month"])
        year = datetime.now().year

        if current_month > 12:
            year += 1

        next_month = (current_month + 1) % 12
        await callback.message.edit_text(
            text="Pick a date:",
            reply_markup=create_kb_month(month_id=next_month, year=year).as_markup(),
        )
        await state.update_data(current_month=next_month)

    @message_router.callback_query(
        StateFilter(DatePicker.pick_date), DateFactory.filter()
    )
    async def normal_other_data(
        callback: CallbackQuery, callback_data: DateFactory, state: FSMContext
    ):
        await state.set_state(DatePicker.pick_time)
        month = str(callback_data.month_id)
        day = str(callback_data.day_id)
        await state.update_data(month=month, day=day)

        await callback.message.answer(text="now please write down time(format 14:00)")

    @message_router.message(
        StateFilter(DatePicker.pick_time),
        lambda message: (
            message.text
            and len(message.text) == 5
            and message.text[2] == ":"
            and message.text[:2].isdigit()
            and message.text[3:].isdigit()
        ),
    )
    async def normal_time(message: Message, state: FSMContext):
        time = message.text
        hour = time[:2]
        minutes = time[3:]
        await state.update_data(hour=hour, minutes=minutes)
        data = await state.get_data()
        month = data.get("month")
        day = data.get("day")
        if len(day) == 1:
            day = "0" + day

        hour = data.get("hour")
        minutes = data.get("minutes")
        todo = data.get("todo")
        year = str(datetime.now().year)

        reminder_datetime = datetime.strptime(
            f"{year}-{month}-{day} {hour}:{minutes}", "%Y-%m-%d %H:%M"
        )

        await message.answer(f"Will remind you to {todo} at {str(reminder_datetime)}")
        asyncio.create_task(
            schedule_reminder(
                bot=bot,
                chat_id=message.from_user.id,
                todo=todo,
                reminder_datetime=reminder_datetime,
            )
        )
        await state.clear()

    @message_router.message(StateFilter(DatePicker.pick_time))
    async def wrong_date(message: Message):
        await message.answer("Please, write a valid time! Format 03:35")
