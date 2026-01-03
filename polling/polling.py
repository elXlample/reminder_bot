from bot.bot import create_dispatcher
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


logger = logging.getLogger(__name__)


config: Config = load_config()
logging.basicConfig(
    level=config.log.level,
    format=config.log.format,
)
if sys.platform.startswith("win") or os.name == "nt":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())


async def main(config: Config):
    bot = Bot(token=os.getenv("BOT_TOKEN"))

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
    await bot.delete_webhook(drop_pending_updates=True)
    # запускаем polling
    try:
        await dp.start_polling(bot, db_pool=db_pool, admin_id=config.bot.admin_id)
    except Exception as e:
        logger.exception(e)
    finally:
        await db_pool.close()
        logger.info("Connection to Postgres closed")


if __name__ == "__main__":
    asyncio.run(main(config=config))
