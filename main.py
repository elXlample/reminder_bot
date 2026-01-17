from fastapi import FastAPI
from contextlib import asynccontextmanager
from polling.polling import set_main_menu_commands
from config.config import load_config
import logging
from bot.bot import create_dispatcher
from webhook.webhook import router as tg_router
from locales.cmd import commands_ru, commands_en, commands_set_ru, commands_set_en
from config.config import Config, load_config
from handlers.handlers import restore_tasks
import asyncio
import os
from sql.connection import get_pg_pool
from redis.asyncio import Redis
import psycopg_pool
from aiogram.fsm.storage.redis import RedisStorage
from middlewares.db_middlewares import DataBaseMiddleware
from middlewares.activity_middleware import ActivityCounterMiddleware
from aiogram import Bot, Dispatcher
from aiogram.types import BotCommand, BotCommandScopeAllPrivateChats
from aiogram.client.default import DefaultBotProperties


@asynccontextmanager
async def lifespan(app: FastAPI):
    bot = Bot(
        token=os.getenv("BOT_TOKEN"),
    )
    app.state.bot = bot
    logger = logging.getLogger(__name__)
    app.state.logger = logger
    config = load_config()
    app.state.config = config
    storage = RedisStorage(
        redis=Redis(
            host=config.redis.host,
            port=config.redis.port,
            db=config.redis.db,
            password=config.redis.password,
            username=config.redis.username,
        )
    )
    db_pool: psycopg_pool.AsyncConnectionPool = await get_pg_pool(
        db_name=config.db.name,
        host=config.db.host,
        port=config.db.port,
        user=config.db.user,
        password=config.db.password,
    )
    app.state.db_pool = db_pool

    # async with db_pool.connection() as conn:
    #  await restore_tasks(bot=bot, conn=conn)
    # logger.debug("restore_tasks is running")
    dp = create_dispatcher(storage=storage, bot=bot)
    logger.info("Including middlewares...")
    dp.update.middleware(DataBaseMiddleware())
    dp.update.middleware(ActivityCounterMiddleware())
    app.state.storage = storage
    app.state.dp = dp
    await bot.set_my_commands([])
    await set_main_menu_commands(bot=bot, lang="ru")
    WEBHOOK_URL = os.getenv("WEBHOOK_URL")
    await bot.set_webhook(WEBHOOK_URL)

    yield
    await bot.delete_webhook()
    await bot.session.close()
    await storage.close()
    await app.state.db_pool.close()


app = FastAPI(lifespan=lifespan)
app.include_router(tg_router)


@app.api_route("/ping", methods=["GET", "HEAD"])
async def ping():
    return {"status": "alive"}


@app.on_event("startup")
async def schedule_restore_tasks():
    if hasattr(app.state, "bot") and hasattr(app.state, "db_pool"):

        async def run_restore():
            async with app.state.db_pool.connection() as conn:
                await restore_tasks(bot=app.state.bot, conn=conn)

        # можно через asyncio.create_task
        asyncio.create_task(run_restore())


async def main(app: FastAPI):
    #

    # await bot.delete_webhook(drop_pending_updates=True)
    """try:
        await dp.start_polling(bot, db_pool=db_pool, admin_id=config.bot.admin_id)
    except Exception as e:
        logger.exception(e)
    finally:
        await db_pool.close()
        logger.info("Connection to Postgres closed")"""


# if __name__ == "__main__":
#   asyncio.run(main())
