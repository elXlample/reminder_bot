from aiogram import Router, F, Bot
import asyncio
from sql.todo_actions import add_todo
from aiogram.filters import Command, CommandStart, StateFilter
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import default_state, State, StatesGroup
from aiogram.filters import CommandObject
from keyboard.keyboard import (
    keyboard_markup,
    create_kb_month,
    DateFactory,
    region_kb_builder,
    regions,
)
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, available_timezones
from config.config import load_config, Config
from psycopg.connection_async import AsyncConnection
from sql.actions import get_user, add_user, change_user_alive_status
from sql.roles import UserRole

message_router = Router()
regions = [region.lower() for region in regions]
defaut_timezone = "Europe/Moscow"


class DatePicker(StatesGroup):
    reminder = State()
    pick_date = State()
    pick_time = State()
    pick_timezone = State()
    pick_country = State()


def available_timezone(region: str, city: str):
    tz_list = available_timezones()
    if f"{region}/{city}" in tz_list:
        return True
    else:
        return False


def register_handlers(message_router: Router, bot: Bot):
    async def schedule_reminder(bot, chat_id, todo, reminder_datetime):
        now = datetime.now(timezone.utc)
        delay = (reminder_datetime - now).total_seconds()
        if delay > 0:
            await asyncio.sleep(delay)
        await bot.send_message(chat_id, f"Don't forget to {todo}!")

    @message_router.message(CommandStart(), StateFilter(default_state))
    async def command_start(message: Message, conn: AsyncConnection, bot: Bot):
        user_row = await get_user(conn, user_id=message.from_user.id)
        if user_row is None:
            await add_user(
                conn,
                user_id=message.from_user.id,
                username=message.from_user.username,
                language=message.from_user.language_code,
                role=UserRole.USER,
            )
        else:
            await change_user_alive_status(
                conn, is_alive=True, user_id=message.from_user.id
            )

        await message.answer(
            "Hello! I am the ReminderBot! To get proper reminders, please, select your timezone using /timezone (In case of being in Moscow timezone do nothing)"
        )

    @message_router.message(Command(commands="timezone"), StateFilter(default_state))
    async def pick_timezone(message: Message, state: FSMContext):
        await message.answer(
            "To add your timezone, pick your region:",
            reply_markup=region_kb_builder.as_markup(),
        )
        await state.set_state(DatePicker.pick_timezone)

    @message_router.callback_query(
        StateFilter(DatePicker.pick_timezone), F.data.in_(regions)
    )
    async def right_timezone(callback: CallbackQuery, state: FSMContext):
        await state.set_state(DatePicker.pick_country)
        region = callback.data.capitalize()
        await state.update_data(region=region)
        await callback.message.edit_text(
            "Now please write down your country: (e.g. Moscow)"
        )

    @message_router.callback_query(
        StateFilter(DatePicker.pick_timezone), F.data == "cancel"
    )
    async def cancel_timezone(callback: CallbackQuery, state: FSMContext):
        await state.set_state(default_state)
        await callback.message.edit_text(
            "Region setting cancelled. To see all the commands use /help"
        )

    @message_router.message(StateFilter(DatePicker.pick_timezone))
    async def wrong_timezone(message: Message):
        await message.answer(
            "Please, select your region using inline keyboard or use /cancel",
            reply_markup=region_kb_builder.as_markup(),
        )

    @message_router.message(
        StateFilter(DatePicker.pick_country), lambda x: x and x.text.isalpha()
    )
    async def normal_country(message: Message, state: FSMContext):
        country = message.text.strip().capitalize()
        data = await state.get_data()
        region = data["region"]
        if available_timezone(region=region, city=country):
            await state.update_data(country=country)
            await message.answer(f"Timezone {region}/{country} set succesfully!")
            await state.set_state(default_state)
        else:
            await message.answer(
                f"Unfortunately there is no avaliable timezone({region}/{country}). \n Please select a different country or write /cancel"
            )

    @message_router.message(
        Command(commands="cancel"), StateFilter(DatePicker.pick_country)
    )
    async def cancel_country(message: Message, state: FSMContext):
        await state.set_state(default_state)
        await message.answer(
            "Coutry picking cancelled. To see all avialiable features use /help"
        )

    @message_router.message(StateFilter(DatePicker.pick_country))
    async def wrong_country(message: Message):
        await message.answer("Please, enter a valid country name!")

    @message_router.message(Command(commands="remind"), StateFilter(default_state))
    async def remind_message(
        message: Message, command: CommandObject, state: FSMContext
    ):
        text = command.args
        print(message.from_user.id)
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
        year = str(datetime.now())[:4]
        if callback.data == "tomorrow":
            await state.update_data(
                current_year=year, current_month=month, day=str(int(day) + 1)
            )
        elif callback.data == "today":
            await state.update_data(current_year=year, current_month=month, day=day)
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

        await state.update_data(current_year=year)
        await state.update_data(current_month=month)
        data = await state.get_data()
        current_year = data["current_year"]
        current_month = data["current_month"]
        month_id = (current_month - 1) % 12
        await callback.message.edit_text(
            "Pick a date:",
            reply_markup=create_kb_month(
                month_id=month_id, year=current_year
            ).as_markup(),
        )

    @message_router.message(StateFilter(DatePicker.pick_date))
    async def wrong_content_date(message: Message):
        await message.reply(
            "Please, use an inline keyboard to pick a date or use cancel button"
        )

    @message_router.callback_query(StateFilter(DatePicker.pick_date), F.data == ">")
    async def next_month(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        current_year = data["current_year"]
        current_month = data["current_month"]

        next_month = current_month + 1

        if next_month > 11:
            current_year += 1
            await state.update_data(current_year=current_year)

        next_month = (current_month + 1) % 12
        month_id = (next_month - 1) % 12
        await callback.message.edit_text(
            text="Pick a date:",
            reply_markup=create_kb_month(
                month_id=month_id, year=current_year
            ).as_markup(),
        )
        await state.update_data(current_month=next_month)

    @message_router.callback_query(StateFilter(DatePicker.pick_date), F.data == "<")
    async def prev_month(callback: CallbackQuery, state: FSMContext):
        data = await state.get_data()
        current_month = int(data["current_month"])
        current_year = int(data["current_year"])

        prev_month = current_month - 1

        if prev_month < 0:
            current_year -= 1
            await state.update_data(current_year=current_year)

        prev_month = (current_month - 1) % 12
        month_id = (prev_month - 1) % 12
        await callback.message.edit_text(
            text="Pick a date:",
            reply_markup=create_kb_month(
                month_id=month_id, year=current_year
            ).as_markup(),
        )
        await state.update_data(current_month=prev_month)

    @message_router.callback_query(
        StateFilter(DatePicker.pick_date), F.data == "cancel"
    )
    async def cancel_data_pick(callback: CallbackQuery, state: FSMContext):
        await state.set_state(default_state)
        await callback.message.edit_text(
            text="Data pick cancelled. To add new reminder use /remind"
        )
        await state.clear()

    @message_router.callback_query(
        StateFilter(DatePicker.pick_date), DateFactory.filter()
    )
    async def normal_other_data(
        callback: CallbackQuery, callback_data: DateFactory, state: FSMContext
    ):
        await state.set_state(DatePicker.pick_time)
        year = str(callback_data.year_id)
        month = str(callback_data.month_id + 1)
        day = str(callback_data.day_id)
        await state.update_data(year=year, month=month, day=day)

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
    async def normal_time(message: Message, state: FSMContext, conn: AsyncConnection):
        time = message.text
        hour = time[:2]
        minutes = time[3:]
        await state.update_data(hour=hour, minutes=minutes)
        data = await state.get_data()
        month = data.get("month")
        day = data.get("day")
        year = data.get("year")
        if int(day) < 10:
            day = "0" + str(day)

        hour = data.get("hour")
        minutes = data.get("minutes")
        todo = data.get("todo")
        reminder_datetime = datetime.strptime(
            f"{year}-{month}-{day} {hour}:{minutes}", "%Y-%m-%d %H:%M"
        )
        region = data.get("region")
        country = data.get("country")
        if not region:
            timezone = defaut_timezone
        else:
            timezone = f"{region}/{country}"

        reminder_datetime = reminder_datetime.replace(tzinfo=ZoneInfo(timezone))

        done = False
        if reminder_datetime.astimezone(timezone.utc) < datetime.now(
            timezone.utc
        ):  # time format utc and not
            done = True

        await add_todo(
            conn,
            user_id=message.from_user.id,
            username=message.from_user.username,
            todo=todo,
            done=done,
            reminder_time=reminder_datetime.astimezone(timezone.utc),
        )

        await message.answer(
            f"Will remind you to {todo} at {reminder_datetime.strftime('%Y-%m-%d %H:%M')}"
        )
        asyncio.create_task(
            schedule_reminder(
                bot=bot,
                chat_id=message.from_user.id,
                todo=todo,
                reminder_datetime=reminder_datetime.astimezone(timezone.utc),
            )
        )
        await state.clear()

    @message_router.message(
        StateFilter(DatePicker.pick_time), Command(commands="cancel")
    )
    async def cancel_time_pick(message: Message, state: FSMContext):
        await state.set_state(default_state)
        await message.answer(
            text="Time pick cancelled. To add new reminder use /remind"
        )
        await state.clear()

    @message_router.message(StateFilter(DatePicker.pick_time))
    async def wrong_date(message: Message):
        await message.answer("Please, write a valid time! Format 03:35")
