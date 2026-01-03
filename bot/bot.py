from aiogram import Bot, Dispatcher, Router
import logging
from config.config import Config
from aiogram.fsm.storage.redis import RedisStorage

# from config.config import load_config
from handlers.handlers import register_handlers


logger = logging.getLogger(__name__)
# config = load_config()


def create_dispatcher(storage: RedisStorage, bot: Bot) -> Dispatcher:
    dp = Dispatcher(storage=storage)
    message_router = Router()
    register_handlers(message_router=message_router, bot=bot)
    dp.include_router(message_router)
    return dp
