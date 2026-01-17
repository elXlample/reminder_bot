from bot.bot import create_dispatcher
from fastapi import FastAPI
from webhook.webhook import router as tg_router
from locales.cmd import commands_ru, commands_en, commands_set_ru, commands_set_en
from config.config import Config, load_config
from handlers.handlers import restore_tasks
import asyncio
import logging
import os
import sys
from sql.connection import get_pg_pool
from redis.asyncio import Redis
import psycopg_pool
from aiogram.fsm.storage.redis import RedisStorage
from middlewares.db_middlewares import DataBaseMiddleware
from middlewares.activity_middleware import ActivityCounterMiddleware
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode


logger = logging.getLogger(__name__)


config: Config = load_config()
logging.basicConfig(
    level=config.log.level,
    format=config.log.format,
)
if sys.platform.startswith("win") or os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def set_main_menu_commands(bot: Bot, lang: str | None):
    if lang == "ru":
        main_menu_commands = [
            BotCommand(command=command, description=description)
            for command, description in commands_set_ru.items()
        ]
    elif lang == "en":
        main_menu_commands = [
            BotCommand(command=command, description=description)
            for command, description in commands_set_en.items()
        ]
    await bot.set_my_commands(
        commands=main_menu_commands, scope=BotCommandScopeAllPrivateChats()
    )


async def main(config: Config):
    bot = Bot(
        token=os.getenv("BOT_TOKEN"),
    )
    await set_main_menu_commands(bot=bot, lang="ru")
    commands = await bot.get_my_commands()
    print(commands)
    app = FastAPI()

    storage = RedisStorage(
        redis=Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password,
            username=config.redis.username,
        )
    )
    dp = create_dispatcher(storage=storage, bot=bot)
    tg_router.bot = bot
    tg_router.dp = dp
    app.include_router(tg_router)
    db_pool: psycopg_pool.AsyncConnectionPool = await get_pg_pool(
        db_name=config.db.name,
        host=config.db.host,
        port=config.db.port,
        user=config.db.user,
        password=config.db.password,
    )
    async with db_pool.connection() as conn:
        await restore_tasks(bot=bot, conn=conn)
        logger.debug("restore_tasks is running")

    logger.info("Including middlewares...")
    dp.update.middleware(DataBaseMiddleware())
    dp.update.middleware(ActivityCounterMiddleware())

   

    # удаляем webhook, если он был установлен
    ###await bot.delete_webhook(drop_pending_updates=True)
    # запускаем polling
    """ try:
        await dp.start_polling(bot, db_pool=db_pool, admin_id=config.bot.admin_id)
    except Exception as e:
        logger.exception(e)
    finally:
        await db_pool.close()
        logger.info("Connection to Postgres closed")"""


if __name__ == "__main__":
    asyncio.run(main(config=config))
