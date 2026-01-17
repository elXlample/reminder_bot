from fastapi import APIRouter, Request, FastAPI
from aiogram.types import Update
from contextlib import asynccontextmanager
import os
from aiogram import Bot, Dispatcher

router = APIRouter()


@router.post("/webhook")
async def telegram_webhook(request: Request):
    bot: Bot = request.app.state.bot
    dp: Dispatcher = request.app.state.dp
    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}
