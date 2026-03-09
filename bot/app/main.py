import os
import asyncio
import httpx

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import Message

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

dp = Dispatcher()
pending_file_by_user: dict[tuple[int, int], dict] = {}


def _pending_key(message: Message) -> tuple[int, int] | None:
    if not message.from_user:
        return None
    return (message.chat.id, message.from_user.id)


def _build_attachment_payload(message: Message) -> dict | None:
    if not message.document:
        return None
    return {
        "telegram_file_id": message.document.file_id,
        "filename": message.document.file_name,
        "mime_type": message.document.mime_type,
        "file_size": message.document.file_size,
        "telegram_chat_id": message.chat.id,
        "telegram_user_id": message.from_user.id if message.from_user else None,
    }


async def _create_task(
    message: Message,
    task_text: str,
    attachment: dict | None = None,
    reply_to_message_id: int | None = None,
):
    payload = {
        "input_text": task_text,
        "telegram_chat_id": message.chat.id,
        "telegram_user_id": message.from_user.id if message.from_user else None,
        "telegram_message_id": message.message_id,
        "reply_to_message_id": reply_to_message_id if reply_to_message_id is not None else message.message_id,
    }
    if attachment is not None:
        payload["attachment"] = attachment

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{BACKEND_URL}/tasks", json=payload)
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


@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer(
        "AI Assistant bot is running.\n\n"
        "Отправь /health для проверки backend."
    )


@dp.message(Command("help"))
async def help_handler(message: Message):
    await message.answer(
        "Как отправлять задачи:\n"
        "1) Документ + caption -> задача создается сразу.\n"
        "2) Документ без caption -> бот попросит отдельную инструкцию.\n"
        "3) Текстовое сообщение -> задача из текста.\n"
        "4) Legacy: /task <инструкция>."
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
    pending_key = _pending_key(message)
    pending_attachment = pending_file_by_user.pop(pending_key, None) if pending_key is not None else None
    await _create_task(
        message=message,
        task_text=task_text,
        attachment=pending_attachment,
        reply_to_message_id=message.message_id,
    )


@dp.message(F.document)
async def document_handler(message: Message):
    attachment = _build_attachment_payload(message)
    if attachment is None:
        await message.answer("Не удалось прочитать metadata файла.")
        return

    caption = (message.caption or "").strip()
    if caption:
        await _create_task(
            message=message,
            task_text=caption,
            attachment=attachment,
            reply_to_message_id=message.message_id,
        )
        return

    pending_key = _pending_key(message)
    if pending_key is None:
        await message.answer("Не удалось определить пользователя для привязки файла.")
        return
    pending_file_by_user[pending_key] = attachment
    await message.answer("Файл получен. Пришлите следующим сообщением инструкцию для анализа.")


@dp.message(F.text & ~F.text.startswith("/"))
async def text_task_handler(message: Message):
    task_text = (message.text or "").strip()
    if not task_text:
        await message.answer("Пожалуйста, отправьте текст задачи.")
        return

    pending_key = _pending_key(message)
    pending_attachment = pending_file_by_user.pop(pending_key, None) if pending_key is not None else None
    await _create_task(
        message=message,
        task_text=task_text,
        attachment=pending_attachment,
        reply_to_message_id=message.message_id,
    )


async def main():
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
