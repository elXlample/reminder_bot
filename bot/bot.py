from aiogram import Bot, Dispatcher
from config.config import load_config
from handlers.handlers import message_router
import os

config = load_config()

bot = Bot(token=os.getenv("BOT_TOKEN"))
dp = Dispatcher()
dp.include_router(message_router)
