from fastapi import APIRouter, Request
from aiogram.types import Update


router = APIRouter()
bot = None
dp = None


@router.post("/webhook")
async def telegram_webhook(request: Request):
    update = Update.model_validate(await request.json())
    await dp.feed_update(bot, update)
    return {"ok": True}
