from aiogram import Router, F, Bot
import asyncio
import logging
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
    build_todo_keyboard,
    TodoFactory,
    TodoDeleteFactory,
    PageButton,
)
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, available_timezones
from config.config import load_config, Config
from psycopg.connection_async import AsyncConnection
from sql.actions import get_user, add_user, change_user_alive_status
from sql.roles import UserRole
from sql.todo_actions import (
    get_todo_list,
    get_all_todos,
    change_todo_status,
    remove_todo,
    get_total_pages,
)
from aiogram.fsm.storage.redis import RedisStorage
from redis.asyncio import Redis
from logging import basicConfig
from config.config import Config, load_config


async def schedule_reminder(bot, chat_id, todo, reminder_datetime):
    try:
        await asyncio.sleep(
            (reminder_datetime - datetime.now(timezone.utc)).total_seconds()
        )
        await bot.send_message(chat_id, f"🔔 Reminder: {todo}")
    except asyncio.CancelledError:
        logger.info(f"Reminder cancelled for {chat_id}: {todo}")
        raise


scheduled_tasks: dict[tuple[int, str], asyncio.Task] = {}


async def restore_tasks(
    bot: Bot,
    conn: AsyncConnection,
):
    todos = await get_all_todos(conn)
    if todos:
        mapped_todos = [
            {
                "user_id": user_id,
                "todo": todo,
                "reminder_time": reminder_time.isoformat() if reminder_time else None,
                "done": done,
                "timezone": timezone if timezone else "Europe/Moscow",
            }
            for user_id, todo, reminder_time, done, timezone in todos
        ]
    else:
        logger.info("no reminders now")
    for todo in mapped_todos:
        user_id = todo["user_id"]
        reminder_time = todo["reminder_time"]
        todo = todo["todo"]
        task = asyncio.create_task(
            schedule_reminder(
                bot=bot,
                chat_id=user_id,
                todo=todo,
                reminder_datetime=datetime.fromisoformat(reminder_time),
            )
        )
        logger.info(f"task :{todo} created")
        scheduled_tasks[(user_id, todo)] = task


config: Config = load_config()
logging.basicConfig(
    level=config.log.level,
    format=config.log.format,
)


logger = logging.getLogger(__name__)

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
        try:
            await asyncio.sleep(
                (reminder_datetime - datetime.now(timezone.utc)).total_seconds()
            )
            await bot.send_message(chat_id, f"🔔 Reminder: {todo}")
        except asyncio.CancelledError:
            logger.info(f"Reminder cancelled for {chat_id}: {todo}")
            raise

    @message_router.message(CommandStart(), StateFilter(default_state))
    async def command_start(
        message: Message, conn: AsyncConnection, bot: Bot, state: FSMContext
    ):
        page = 1
        await state.update_data(page=page)
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

    @message_router.message(Command(commands="todos"), StateFilter(default_state))
    async def check_todos(message: Message, state: FSMContext, conn: AsyncConnection):
        todos = await get_todo_list(conn=conn, user_id=message.from_user.id)

        all = True

        await state.update_data(all=all)
        if todos:
            mapped_todos = [
                {
                    "todo": todo,
                    "reminder_time": reminder_time.isoformat()
                    if reminder_time
                    else None,
                    "done": done,
                    "timezone": timezone,
                }
                for todo, reminder_time, done, timezone in todos
            ]

            await state.update_data(todos=mapped_todos)
            data = await state.get_data()
            page = data.get("page")
            await message.answer(
                "all your active reminders:",
                reply_markup=build_todo_keyboard(
                    todos=mapped_todos,
                    show_all=True,
                    user_id=message.from_user.id,
                    conn=conn,
                    page=page,
                ).as_markup(),
            )

        else:
            await message.answer(text="User has no todos. To add use /remind")

    @message_router.callback_query(PageButton.filter())
    async def page_up(
        callback: CallbackQuery, page: int, conn: AsyncConnection, state: FSMContext
    ):
        user_id = callback.from_user.id
        data = await state.get_data()
        page = data.get("page")
        total_pages = await get_total_pages(conn=conn, user_id=user_id)
        if total_pages == 1:
            logger.info("total pages == 1")
            await callback.answer()

        else:
            if page + 1 <= total_pages:
                todos = await get_todo_list(conn=conn, user_id=user_id, page=page + 1)
                if todos:
                    mapped_todos = [
                        {
                            "todo": todo,
                            "reminder_time": reminder_time.isoformat()
                            if reminder_time
                            else None,
                            "done": done,
                            "timezone": timezone,
                        }
                        for todo, reminder_time, done, timezone in todos
                    ]
                    all = data.get("all")
                    await callback.message.edit_text(
                        text=f"page:{page + 1} reminder:",
                        reply_markup=build_todo_keyboard(
                            todos=mapped_todos,
                            show_all=all,
                            user_id=user_id,
                            conn=conn,
                            page=page + 1,
                        ),
                    )
                    await state.update_data(page=page + 1)
            else:
                logger.info("on final page")
                await callback.answer()

    @message_router.callback_query(F.data == "show_only_active")
    async def show_only_active_func(
        callback: CallbackQuery, state: FSMContext, conn: AsyncConnection
    ):
        data = await state.get_data()
        todos = data.get("todos")
        all = False
        await state.update_data(all=all)
        page = data.get("page")  # crutch
        await callback.message.edit_text(
            text="active reminders:",
            reply_markup=build_todo_keyboard(
                todos=todos,
                show_all=False,
                user_id=callback.from_user.id,
                conn=conn,
                page=page,
            ).as_markup(),
        )

    @message_router.callback_query(F.data == "show_all")
    async def show_all_func(
        callback: CallbackQuery, state: FSMContext, conn: AsyncConnection
    ):
        data = await state.get_data()
        todos = data.get("todos")
        all = True
        await state.update_data(all=all)
        page = data.get("page")
        await callback.message.edit_text(
            text="all reminders:",
            reply_markup=build_todo_keyboard(
                todos=todos,
                show_all=True,
                user_id=callback.from_user.id,
                conn=conn,
                page=page,
            ).as_markup(),
        )

    @message_router.callback_query(TodoFactory.filter())
    async def done_button_pressed(
        callback: CallbackQuery, conn: AsyncConnection, state: FSMContext
    ):
        boolean = None
        user_id = callback.from_user.id
        data = await state.get_data()
        todos = data.get("todos")
        all = data.get("all")

        text = callback.data
        todo = str(callback.data.split(":")[1])

        if "True" in str(text):
            boolean = False

        elif "False" in str(text):
            boolean = True

        await change_todo_status(conn=conn, boolean=boolean, user_id=user_id, todo=todo)
        # new todos
        get_todos = await get_todo_list(conn=conn, user_id=callback.from_user.id)
        if get_todos:
            mapped_todos = [
                {
                    "todo": todo,
                    "reminder_time": reminder_time.isoformat()
                    if reminder_time
                    else None,
                    "done": done,
                    "timezone": timezone,
                }
                for todo, reminder_time, done, timezone in get_todos
            ]

            await state.update_data(todos=mapped_todos)
        else:
            await callback.message.edit_text(
                text=f"User with id {user_id} currently has no todos. To create one, use /remind "
            )

        data = await state.get_data()
        todos = data.get("todos")
        page = data.get("page")

        task = scheduled_tasks.pop((user_id, todo), None)
        if task:
            task.cancel()
            logger.info(f"task: {todo} cancelled")
        else:
            logger.info(f"task: {todo} does not exist")

        await callback.message.edit_text(
            text="all reminders",
            reply_markup=build_todo_keyboard(
                todos=todos,
                show_all=all,
                user_id=callback.from_user.id,
                conn=conn,
                page=page,
            ).as_markup(),
        )

    @message_router.callback_query(TodoDeleteFactory.filter())
    async def delete_button_pressed(
        callback: CallbackQuery, conn: AsyncConnection, state: FSMContext
    ):
        user_id = callback.from_user.id
        data = await state.get_data()

        all = data.get("all")

        text = callback.data
        todo = str(text.split(":")[1])

        await remove_todo(conn=conn, user_id=user_id, todo=todo)
        # new todos

        get_todos = await get_todo_list(conn=conn, user_id=callback.from_user.id)
        if len(get_todos) > 0:
            mapped_todos = [
                {
                    "todo": todo,
                    "reminder_time": reminder_time.isoformat()
                    if reminder_time
                    else None,
                    "done": done,
                    "timezone": timezone,
                }
                for todo, reminder_time, done, timezone in get_todos
            ]
            await state.update_data(todos=mapped_todos)
        else:
            await callback.message.edit_text(
                text=f"User with id {user_id} currently has no todos. To create one, use /remind "
            )
            await state.update_data(todos=[])

        data = await state.get_data()
        todos = data.get("todos")
        page = data.get("page")  # crutch
        await callback.message.edit_text(
            text="all reminders",
            reply_markup=build_todo_keyboard(
                todos=todos,
                show_all=all,
                user_id=callback.from_user.id,
                conn=conn,
                page=page,
            ).as_markup(),
        )
        task = scheduled_tasks.pop((user_id, todo), None)
        if task:
            task.cancel()
            logger.info(f"task: {todo} cancelled")
        else:
            logger.info(f"task: {todo} does not exist")

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
        month = data.get("current_month")
        day = data.get("day")
        year = data.get("current_year")
        hour = data.get("hour")
        minutes = data.get("minutes")
        todo = data.get("todo")
        reminder_datetime = datetime.strptime(
            f"{year}-{month}-{day} {hour}:{minutes}", "%Y-%m-%d %H:%M"
        )
        region = data.get("region")
        country = data.get("country")
        if not region:
            user_timezone = defaut_timezone
        else:
            user_timezone = f"{region}/{country}"

        reminder_datetime = reminder_datetime.replace(tzinfo=ZoneInfo(user_timezone))

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
            user_timezone=user_timezone,
        )

        await message.answer(
            f"Will remind you to {todo} at {reminder_datetime.strftime('%Y-%m-%d %H:%M')}"
        )

        task = asyncio.create_task(
            schedule_reminder(
                bot=bot,
                chat_id=message.from_user.id,
                todo=todo,
                reminder_datetime=reminder_datetime.astimezone(timezone.utc),
            )
        )
        if task not in scheduled_tasks:
            scheduled_tasks[(message.from_user.id, todo)] = task
        else:
            logger.info("this task already exist")

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
