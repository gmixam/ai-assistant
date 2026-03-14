import os
import asyncio
import httpx

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
BACKEND_URL = os.getenv("BACKEND_URL", "http://backend:8000")

dp = Dispatcher()
pending_file_by_user: dict[tuple[int, int], dict] = {}


def _approval_status_label(status: str | None) -> str:
    mapping = {
        "pending": "pending approval",
        "approved": "approved",
        "rejected": "rejected",
        "expired": "expired",
        "edited": "edited",
    }
    return mapping.get((status or "").strip(), status or "unknown")


def _approval_action_type(item: dict) -> str:
    proposed_action = item.get("proposed_action")
    if isinstance(proposed_action, str) and proposed_action.strip():
        return proposed_action.strip()
    structured_result = item.get("structured_result")
    if isinstance(structured_result, str) and structured_result.strip():
        return structured_result.strip()[:120]
    return "review_action"


def _format_approval_summary(item: dict) -> str:
    return (
        f"Approval #{item.get('id')} for task {item.get('task_id')}\n"
        f"Status: {_approval_status_label(item.get('status'))}\n\n"
        f"Summary:\n{item.get('summary') or 'No summary provided.'}\n\n"
        f"Action type: {_approval_action_type(item)}\n"
        f"Suggested next step: "
        f"{'Review details on demand, then approve or reject.' if item.get('status') == 'pending' else 'Review the latest approval state.'}"
    )[:3900]


def _format_approval_details(item: dict) -> str:
    lines = [
        _format_approval_summary(item),
    ]
    if item.get("handoff"):
        lines.extend(["", f"Handoff: {item['handoff']}"])
    if item.get("decision_comment"):
        lines.extend(["", f"Decision comment: {item['decision_comment']}"])
    if item.get("decided_by"):
        lines.append(f"Decided by: {item['decided_by']}")
    if item.get("decided_at"):
        lines.append(f"Decided at: {item['decided_at']}")
    if item.get("expires_at"):
        lines.append(f"Expires at: {item['expires_at']}")
    if item.get("structured_result"):
        lines.extend(["", f"Details: {item['structured_result']}"])
    return "\n".join(lines)[:3900]


def _approval_keyboard(approval_id: int, status: str | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if status == "pending":
        rows.append(
            [
                InlineKeyboardButton(text="Approve", callback_data=f"approval:approve:{approval_id}"),
                InlineKeyboardButton(text="Reject", callback_data=f"approval:reject:{approval_id}"),
            ]
        )
    rows.append([InlineKeyboardButton(text="Show details", callback_data=f"approval:details:{approval_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def _backend_get(path: str) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await client.get(f"{BACKEND_URL}{path}")


async def _backend_post(path: str, payload: dict | None = None) -> httpx.Response:
    async with httpx.AsyncClient(timeout=10.0) as client:
        return await client.post(f"{BACKEND_URL}{path}", json=payload or {})


def _parse_command_id(text: str | None) -> int | None:
    if not text:
        return None
    parts = text.strip().split(maxsplit=1)
    if len(parts) < 2:
        return None
    try:
        return int(parts[1].strip())
    except ValueError:
        return None


async def _fetch_approval(approval_id: int) -> dict | None:
    try:
        response = await _backend_get(f"/approvals/{approval_id}")
    except httpx.RequestError:
        return None
    if response.status_code != 200:
        return None
    try:
        return response.json()
    except ValueError:
        return None


async def _apply_approval_action(approval_id: int, action: str, actor: str | None = None) -> tuple[dict | None, str | None]:
    payload = {"decided_by": actor} if actor else {}
    try:
        response = await _backend_post(f"/approvals/{approval_id}/{action}", payload)
    except httpx.RequestError:
        return None, "Backend недоступен. Попробуйте позже."
    if response.status_code == 404:
        return None, f"Approval #{approval_id} не найден."
    if response.status_code >= 400:
        return None, f"Не удалось выполнить {action} для approval #{approval_id}."
    try:
        return response.json(), None
    except ValueError:
        return None, f"Backend вернул некорректный ответ для approval #{approval_id}."


async def _send_approval_details_message(message: Message, approval_id: int):
    item = await _fetch_approval(approval_id)
    if item is None:
        await message.answer(f"Approval #{approval_id} не найден или backend недоступен.")
        return
    await message.answer(_format_approval_details(item), reply_to_message_id=message.message_id)


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
        "4) Legacy: /task <инструкция>.\n"
        "5) Approval: /approval <id>, /approve <id>, /reject <id>."
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


@dp.message(Command("approval"))
async def approval_details_handler(message: Message):
    approval_id = _parse_command_id(message.text)
    if approval_id is None:
        await message.answer("Используйте: /approval <approval_id>")
        return
    await _send_approval_details_message(message, approval_id)


@dp.message(Command("approve"))
async def approve_handler(message: Message):
    approval_id = _parse_command_id(message.text)
    if approval_id is None:
        await message.answer("Используйте: /approve <approval_id>")
        return
    actor = str(message.from_user.id) if message.from_user else None
    item, error = await _apply_approval_action(approval_id, "approve", actor=actor)
    if error is not None:
        await message.answer(error)
        return
    await message.answer(
        _format_approval_summary(item),
        reply_markup=_approval_keyboard(item["id"], item.get("status")),
        reply_to_message_id=message.message_id,
    )


@dp.message(Command("reject"))
async def reject_handler(message: Message):
    approval_id = _parse_command_id(message.text)
    if approval_id is None:
        await message.answer("Используйте: /reject <approval_id>")
        return
    actor = str(message.from_user.id) if message.from_user else None
    item, error = await _apply_approval_action(approval_id, "reject", actor=actor)
    if error is not None:
        await message.answer(error)
        return
    await message.answer(
        _format_approval_summary(item),
        reply_markup=_approval_keyboard(item["id"], item.get("status")),
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


@dp.callback_query(F.data.startswith("approval:"))
async def approval_callback_handler(callback: CallbackQuery):
    data = (callback.data or "").split(":")
    if len(data) != 3:
        await callback.answer("Некорректное действие approval.", show_alert=True)
        return
    _, action, approval_raw_id = data
    try:
        approval_id = int(approval_raw_id)
    except ValueError:
        await callback.answer("Некорректный approval id.", show_alert=True)
        return

    if action == "details":
        item = await _fetch_approval(approval_id)
        if item is None:
            await callback.answer("Approval не найден.", show_alert=True)
            return
        if callback.message is not None:
            await callback.message.answer(_format_approval_details(item), reply_to_message_id=callback.message.message_id)
        await callback.answer("Details sent.")
        return

    if action not in {"approve", "reject"}:
        await callback.answer("Неизвестное действие.", show_alert=True)
        return

    actor = str(callback.from_user.id) if callback.from_user else None
    item, error = await _apply_approval_action(approval_id, action, actor=actor)
    if error is not None:
        await callback.answer(error, show_alert=True)
        return
    if callback.message is not None:
        await callback.message.edit_text(
            _format_approval_summary(item),
            reply_markup=_approval_keyboard(item["id"], item.get("status")),
        )
    await callback.answer(f"Approval {_approval_status_label(item.get('status'))}.")


async def main():
    if not BOT_TOKEN:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set")

    bot = Bot(token=BOT_TOKEN)
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
