from fastapi import FastAPI
from contextlib import asynccontextmanager
from webhook.webhook import router as webhook_router
from bot.bot import bot
from config.url import WEBHOOK_URL

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.set_webhook(WEBHOOK_URL)
    yield
    await bot.delete_webhook()

app = FastAPI(lifespan=lifespan)
app.include_router(webhook_router)