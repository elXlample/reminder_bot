import asyncio
from bot.bot import bot, dp


async def main():
    # удаляем webhook, если он был установлен
    await bot.delete_webhook(drop_pending_updates=True)
    # запускаем polling
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
