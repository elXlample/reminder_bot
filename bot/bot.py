from aiogram import Bot, Dispatcher, Router

# from config.config import load_config
from handlers.handlers import register_handlers
import os

# config = load_config()

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
message_router = Router()
register_handlers(message_router=message_router, bot=bot)
dp.include_router(message_router)
