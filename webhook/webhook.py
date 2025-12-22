from fastapi import APIRouter, Request
from aiogram.types import Update
from main import bot, dp

router = APIRouter()


@router.post("/webhook")
async def telegram_webhook(request: Request):
    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}
