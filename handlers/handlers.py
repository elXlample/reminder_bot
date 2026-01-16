from aiogram import Router, F, Bot
from locales.cmd import commands_en, commands_ru
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
    build_activity_kb,
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
from aiogram.enums import ParseMode
from sql.actions import get_statistics


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
        if datetime.fromisoformat(reminder_time) < datetime.now().astimezone(
            timezone.utc
        ):
            logger.info(f"{todo} expired")
            continue
        else:
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
            text=commands_ru["start"], parse_mode=ParseMode.MARKDOWN_V2
        )

    @message_router.message(Command(commands="help"))
    async def help_user(message: Message, state: FSMContext):
        await message.answer(
            text=commands_ru["help"],
        )

    @message_router.message(Command(commands="activity"))
    async def show_activity(message: Message, conn: AsyncConnection):
        stats = await get_statistics(conn=conn, user_id=message.from_user.id)
        builder = build_activity_kb(stats=stats)
        await message.answer(
            text=commands_ru["activity"],
            reply_markup=builder.as_markup(),
            parse_mode=ParseMode.MARKDOWN_V2,
        )

    @message_router.message(Command(commands="list"), StateFilter(default_state))
    async def check_todos(message: Message, state: FSMContext, conn: AsyncConnection):
        # total_pages = await get_total_pages(conn=conn, user_id=message.from_user.id)
        data = await state.get_data()
        present_page = data.get("page")
        if present_page:
            page = present_page
        else:
            page = 1
        todos = await get_todo_list(conn=conn, user_id=message.from_user.id, page=page)
        total_pages = await get_total_pages(conn=conn, user_id=message.from_user.id)
        await state.update_data(total_pages=total_pages)

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
            total_pages = data.get("total_pages")
            await message.answer(
                text="Все активные напоминания:",
                reply_markup=build_todo_keyboard(
                    todos=mapped_todos,
                    show_all=True,
                    user_id=message.from_user.id,
                    conn=conn,
                    page=page,
                    total_pages=total_pages,
                ).as_markup(),
            )

        else:
            await message.answer(text=commands_ru["no_todos"])

    @message_router.callback_query(PageButton.filter())
    async def page_up(
        callback: CallbackQuery,
        conn: AsyncConnection,
        state: FSMContext,
        callback_data: PageButton,
    ):
        user_id = callback.from_user.id
        data = await state.get_data()
        page = data.get("page", 1)
        total_pages = data.get("total_pages")
        if total_pages == 1:
            logger.info("total pages == 1")
            await callback.answer()
        if callback_data.page_up == 1:
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
                            total_pages=total_pages,
                        ).as_markup(),
                    )
                    await state.update_data(page=page + 1)
            else:
                logger.info("on final page")
                await callback.answer()
        elif callback_data.page_down == 1:
            if page - 1 >= 1:
                todos = await get_todo_list(conn=conn, user_id=user_id, page=page - 1)
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
                        text=f"page:{page - 1} reminder:",
                        reply_markup=build_todo_keyboard(
                            todos=mapped_todos,
                            show_all=all,
                            user_id=user_id,
                            conn=conn,
                            page=page - 1,
                            total_pages=total_pages,
                        ).as_markup(),
                    )
                    await state.update_data(page=page - 1)
            else:
                logger.info("on first page")
                await callback.answer()

    @message_router.callback_query(F.data == "cancel", StateFilter(None))
    async def cancel_show_todos(callback: CallbackQuery):
        await callback.message.edit_text(text=commands_ru["cancel_check_todo"])

    @message_router.callback_query(F.data == "show_only_active")
    async def show_only_active_func(
        callback: CallbackQuery, state: FSMContext, conn: AsyncConnection
    ):
        data = await state.get_data()
        todos = data.get("todos")
        all = False
        await state.update_data(all=all)
        page = data.get("page")
        total_pages = data.get("total_pages")  # crutch
        await callback.message.edit_text(
            text="Активные напоминания:",
            reply_markup=build_todo_keyboard(
                todos=todos,
                show_all=False,
                user_id=callback.from_user.id,
                conn=conn,
                page=page,
                total_pages=total_pages,
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
        total_pages = data.get("total_pages")
        await callback.message.edit_text(
            text="Все напоминания:",
            reply_markup=build_todo_keyboard(
                todos=todos,
                show_all=True,
                user_id=callback.from_user.id,
                conn=conn,
                page=page,
                total_pages=total_pages,
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
        page = data.get("page")
        if not page:
            page = 1

        get_todos = await get_todo_list(
            conn=conn, user_id=callback.from_user.id, page=page
        )
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
            await callback.message.edit_text(text=commands_ru["no_todos"])

        data = await state.get_data()
        todos = data.get("todos")
        page = data.get("page")
        total_pages = await get_total_pages(conn=conn, user_id=user_id)
        await state.update_data(total_pages=total_pages)

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
                total_pages=total_pages,
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
        page = data.get("page")
        if not page:
            page = 1
        # new todos

        get_todos = await get_todo_list(
            conn=conn, user_id=callback.from_user.id, page=page
        )
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
            await callback.message.edit_text(text=commands_ru["no_todos"])
            await state.update_data(todos=[])

        data = await state.get_data()
        todos = data.get("todos")
        page = data.get("page")
        total_pages = await get_total_pages(conn=conn, user_id=user_id)
        await state.update_data(total_pages=total_pages)  # crutch
        await callback.message.edit_text(
            text="Все напоминания:",
            reply_markup=build_todo_keyboard(
                todos=todos,
                show_all=all,
                user_id=callback.from_user.id,
                conn=conn,
                page=page,
                total_pages=total_pages,
            ).as_markup(),
        )
        task = scheduled_tasks.pop((user_id, todo), None)
        if task:
            task.cancel()
            logger.info(f"task: {todo} cancelled")
        else:
            logger.info(f"task: {todo} does not exist")

    @message_router.message(Command(commands="time"), StateFilter(None))
    async def pick_timezone(message: Message, state: FSMContext):
        await message.answer(
            commands_ru["pick_region"],
            parse_mode=ParseMode.MARKDOWN_V2,
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
        await callback.message.edit_text(commands_ru["write_country"])

    @message_router.callback_query(
        StateFilter(DatePicker.pick_timezone), F.data == "cancel"
    )
    async def cancel_timezone(callback: CallbackQuery, state: FSMContext):
        await state.set_state(None)
        await callback.message.edit_text(commands_ru["cancel_pick_timezone"])

    @message_router.message(
        Command(commands="cancel"),
        StateFilter(DatePicker.pick_timezone),
    )
    async def cancel_timezone_command(message: Message, state: FSMContext):
        await state.set_state(None)
        await message.answer(commands_ru["cancel_pick_timezone"])

    @message_router.message(StateFilter(DatePicker.pick_timezone))
    async def wrong_timezone(message: Message):
        await message.answer(
            "Пожалуйста, выберите ваш регион с помощью встроенной клавиатуры или используйте команду /cancel",
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
            await state.set_state(None)
            await state.update_data(country=country)
            await message.answer(f"Параметры {region}/{country} успешно установлены!")

        else:
            await message.answer(
                f"К сожалению для ({region}/{country}) нет настроек часового пояса в базе данных. \n Пожалуйста, напишите другой город или используйте команду /cancel"
            )

    @message_router.message(
        Command(commands="cancel"), StateFilter(DatePicker.pick_country)
    )
    async def cancel_country(message: Message, state: FSMContext):
        await state.set_state(None)
        await message.answer(commands_ru["pick_country_cancel"])

    @message_router.message(StateFilter(DatePicker.pick_country))
    async def wrong_country(message: Message):
        await message.answer(
            "Пожалуйста, напишите корректное название города (на английском языке)"
        )

    @message_router.message(Command(commands="r"), StateFilter(default_state))
    async def remind_message(
        message: Message, command: CommandObject, state: FSMContext
    ):
        text = command.args
        print(message.from_user.id)
        if text:
            await state.update_data(todo=text)

            await message.answer(text="Выберите дату:", reply_markup=keyboard_markup)
            await state.set_state(DatePicker.pick_date)
        else:
            await message.answer("Напоминание не может быть пустым!")

    @message_router.message(Command(commands="cancel"), ~StateFilter(default_state))
    async def cancel_reminder(message: Message, state: FSMContext):
        await state.set_state(None)
        await message.answer(text=commands_ru["cancel_r"])

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
        await callback.message.edit_text(text="Теперь напишите время \n(Формат: 14:29)")
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
            "Пожалуйста, используйте встроенную клавиатуру для выбора даты или используйте команду /cancel"
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
        await state.set_state(None)
        await callback.message.edit_text(
            text="Выбор даты отменен. Чтобы создать напоминание, используйте команду /r"
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

        await callback.message.answer(text="Теперь напишите время \n(Формат: 14:29)")

    @message_router.message(
        StateFilter(DatePicker.pick_time),
        lambda message: (
            message.text
            and len(message.text) == 5
            and message.text[2] == ":"
            and message.text[:2].isdigit()
            and message.text[3:].isdigit()
        ),
        lambda message: (
            int(message.text[:2]) in range(0, 25)
            and int(message.text[3:]) in range(0, 25)
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

        await message.answer(f"Напомню {todo} в {hour}:{minutes}  {day}.{month}.{year}")
        total_pages = await get_total_pages(conn=conn, user_id=message.from_user.id)
        await state.update_data(total_pages=total_pages)

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
        await state.set_state(None)
        await message.answer(
            text="Выбор времени отменен. Чтобы создать напоминание, используйте команду /r"
        )
        await state.clear()

    @message_router.message(StateFilter(DatePicker.pick_time))
    async def wrong_date(message: Message):
        await message.answer("Пожалуйста, укажите время в формате 23:15")

    @message_router.message()
    async def echo(message: Message):
        user_text = message.text
        await message.answer(
            f"Не понял, что вы имели в виду под {user_text}.Чтобы получить список команд, отправьте /help"
        )
