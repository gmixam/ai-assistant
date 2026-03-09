import os
import asyncio
import httpx

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import Message

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

dp = Dispatcher()


@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "AI Assistant bot is running.\n\n"
        "Отправь /health для проверки backend."
    )


@dp.message(Command("health"))
async def health_handler(message: Message):
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{BACKEND_URL}/health")
            response.raise_for_status()
            data = response.json()
        await message.answer(f"Backend status: {data}")
    except Exception as e:
        await message.answer(f"Backend error: {str(e)}")


@dp.message(Command("task"))
async def task_handler(message: Message):
    text = (message.text or "").strip()
    parts = text.split(maxsplit=1)

    if len(parts) < 2 or not parts[1].strip():
        await message.answer("Пожалуйста, укажите описание задачи после команды /task")
        return

    task_text = parts[1].strip()

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{BACKEND_URL}/tasks",
                json={"input_text": task_text},
            )
    except httpx.RequestError:
        await message.answer("Backend недоступен. Попробуйте позже.")
        return

    if response.status_code in (200, 201):
        try:
            data = response.json()
        except ValueError:
            data = {}
        task_id = data.get("id")
        if task_id:
            await message.answer(f"Задача создана. ID: {task_id}")
        else:
            await message.answer("Задача создана")
        return

    await message.answer("Не удалось создать задачу")


async def main():
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
