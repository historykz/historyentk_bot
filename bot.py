import asyncio
import logging
import os
from html import escape
from itertools import count
from typing import Final, Optional

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.constants import ParseMode
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# =========================================
# НАСТРОЙКИ
# =========================================

BOT_TOKEN = os.getenv("BOT_TOKEN", "").strip()
ADMINS_RAW = os.getenv("ADMINS", "").strip()

if not BOT_TOKEN:
    raise ValueError("Не найден BOT_TOKEN в переменных окружения")

if not ADMINS_RAW:
    raise ValueError("Не найден ADMINS в переменных окружения")

try:
    ADMINS: Final[set[int]] = {
        int(admin_id.strip())
        for admin_id in ADMINS_RAW.split(",")
        if admin_id.strip()
    }
except ValueError as exc:
    raise ValueError("ADMINS должен содержать только числовые Telegram ID через запятую") from exc

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

# =========================================
# ХРАНИЛИЩА В ПАМЯТИ
# =========================================

REQUESTS: dict[int, dict] = {}
RESPONSES: dict[int, dict] = {}

REQUEST_SEQ = count(1001)
RESPONSE_SEQ = count(5001)

BLOCKED_USERS: set[int] = set()
FINISHED_USERS: set[int] = set()

# =========================================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================================

def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


def safe_username(user) -> str:
    if user.username:
        return f"@{escape(user.username)}"
    return escape(user.first_name or "пользователь")


def admin_name(user) -> str:
    if user.username:
        return f"@{escape(user.username)}"
    return escape(user.first_name or "Администратор")


def get_reason_title(reason_code: str) -> str:
    return {
        "block": "🔐 Вопрос по блокировке аккаунта",
        "coop": "🤝 Вопрос по сотрудничеству",
        "tests": "🧠 Покупка тестов",
        "other": "📕 Свой вопрос",
    }.get(reason_code, "Не выбрано")


def get_reason_text(reason_code: str) -> str:
    if reason_code == "block":
        return "Напишите жалобу"

    if reason_code == "coop":
        return (
            "Хорошо ☺️\n"
            "Для размещения рекламы, пожалуйста, ответьте на несколько вопросов:\n\n"
            "1️⃣ Укажите тематику рекламы.\n"
            "2️⃣ Отправьте готовый рекламный пост (обязательно).\n"
            "3️⃣ На какой срок планируете размещение рекламы?\n"
            "4️⃣ Есть ли дополнительные просьбы или условия со стороны рекламодателя?\n\n"
            "📩 После получения информации мы рассчитаем стоимость и предложим подходящие варианты размещения."
        )

    if reason_code == "tests":
        return "платные тесты еще не доступны 🥹"

    return "Напишите ваш вопрос, и мы обязательно ответим вам."


def reason_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔐 A) Вопрос по блокировке аккаунта", callback_data="reason:block")],
        [InlineKeyboardButton("🤝 B) Вопрос по сотрудничеству", callback_data="reason:coop")],
        [InlineKeyboardButton("🧠 C) Покупка тестов", callback_data="reason:tests")],
        [InlineKeyboardButton("📕 Д) свой вопрос", callback_data="reason:other")],
    ])


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Назад", callback_data="reason:back")]
    ])


def user_response_keyboard(response_id: int, selected: Optional[str] = None) -> InlineKeyboardMarkup:
    left = "👍"
    right = "🫶🏻"

    if selected == "👍":
        left = "✅ 👍"
    elif selected == "🫶🏻":
        right = "✅ 🫶🏻"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(left, callback_data=f"userreact:{response_id}:👍"),
            InlineKeyboardButton(right, callback_data=f"userreact:{response_id}:🫶🏻"),
        ]
    ])


def detect_message_type(message) -> str:
    if message.text:
        return "текст"
    if message.voice:
        return "голосовое сообщение"
    if message.photo:
        return "фото"
    if message.video:
        return "видео"
    if message.document:
        return "документ"
    if message.audio:
        return "аудио"
    if message.sticker:
        return "стикер"
    if message.video_note:
        return "видеосообщение"
    if message.animation:
        return "GIF"
    return "другое"


def user_mention_html(user_info: dict) -> str:
    if user_info.get("username"):
        return f"@{escape(user_info['username'])}"
    user_id = user_info["id"]
    first_name = escape(user_info.get("first_name") or "Открыть профиль")
    return f'<a href="tg://user?id={user_id}">{first_name}</a>'


def admin_card_keyboard(request_id: int) -> InlineKeyboardMarkup:
    req = REQUESTS[request_id]
    like_count = len(req["admin_reactions"].get("👍", set()))
    heart_count = len(req["admin_reactions"].get("🫶🏻", set()))
    user_id = req["user"]["id"]
    is_blocked_user = user_id in BLOCKED_USERS

    second_row = [
        InlineKeyboardButton("✅ Завершить диалог", callback_data=f"finish:{request_id}")
    ]

    if is_blocked_user:
        second_row.append(
            InlineKeyboardButton("🔓 Разблокировать", callback_data=f"unblock:{request_id}")
        )
    else:
        second_row.append(
            InlineKeyboardButton("🚫 Заблокировать", callback_data=f"block:{request_id}")
        )

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Ответить", callback_data=f"reply:{request_id}")],
        second_row,
        [
            InlineKeyboardButton(f"👍 {like_count}", callback_data=f"adminreact:{request_id}:👍"),
            InlineKeyboardButton(f"🫶🏻 {heart_count}", callback_data=f"adminreact:{request_id}:🫶🏻"),
        ]
    ])


def build_admin_card_text(request_id: int) -> str:
    req = REQUESTS[request_id]
    user = req["user"]

    first_name = escape(user.get("first_name") or "Без имени")
    last_name = escape(user.get("last_name") or "")
    full_name = f"{first_name} {last_name}".strip()

    if user.get("username"):
        username_or_link = f"@{escape(user['username'])}"
    else:
        username_or_link = user_mention_html(user)

    user_id = user["id"]
    reason = escape(req["reason_title"])
    status_text = escape(req["status_text"])
    message_type = escape(req.get("message_type", "сообщение"))

    meta_block = (
        "<blockquote>"
        f"👤 Имя: {full_name}\n"
        f"🔹 Username: {username_or_link}\n"
        f"🆔 ID: <code>{user_id}</code>\n"
        f"📌 Причина: {reason}\n"
        f"📍 Статус: {status_text}\n"
        f"📨 Тип сообщения: {message_type}"
        "</blockquote>"
    )

    parts = [
        "📩 <b>Новое обращение</b>",
        "",
        meta_block,
    ]

    if req.get("message_text"):
        parts.extend([
            "",
            "<b>💬 Сообщение:</b>",
            escape(req["message_text"]),
        ])

    if req.get("caption"):
        parts.extend([
            "",
            "<b>📝 Подпись:</b>",
            escape(req["caption"]),
        ])

    if req.get("voice_duration"):
        parts.extend([
            "",
            f"<b>🎤 Длительность голосового:</b> {req['voice_duration']} сек.",
        ])

    if req.get("user_reaction"):
        parts.extend([
            "",
            f"<b>🙋 Реакция пользователя на ответ:</b> {escape(req['user_reaction'])}",
        ])

    admin_reacts = req.get("admin_reactions", {})
    react_parts = []
    if admin_reacts.get("👍"):
        react_parts.append(f"👍 {len(admin_reacts['👍'])}")
    if admin_reacts.get("🫶🏻"):
        react_parts.append(f"🫶🏻 {len(admin_reacts['🫶🏻'])}")

    if react_parts:
        parts.extend([
            "",
            "<b>🧷 Реакции админов:</b> " + " | ".join(react_parts),
        ])

    return "\n".join(parts)


async def delete_message_later(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    message_id: int,
    delay: int = 5,
):
    try:
        await asyncio.sleep(delay)
        await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except Exception:
        pass


async def try_delete_user_message(message):
    try:
        await message.delete()
    except Exception:
        pass


async def refresh_admin_cards(context: ContextTypes.DEFAULT_TYPE, request_id: int):
    if request_id not in REQUESTS:
        return

    req = REQUESTS[request_id]
    text = build_admin_card_text(request_id)
    markup = admin_card_keyboard(request_id)

    for item in req["admin_message_refs"]:
        try:
            await context.bot.edit_message_text(
                chat_id=item["chat_id"],
                message_id=item["message_id"],
                text=text,
                parse_mode=ParseMode.HTML,
                reply_markup=markup,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"Не удалось обновить карточку обращения у админа {item['chat_id']}: {e}")


async def notify_admins_about_user_reaction(
    context: ContextTypes.DEFAULT_TYPE,
    request_id: int,
    reaction: str,
):
    req = REQUESTS[request_id]
    user = req["user"]
    target = user_mention_html(user)

    text = (
        "🔔 <b>Пользователь отреагировал на ответ</b>\n\n"
        "<blockquote>"
        f"👤 Пользователь: {target}\n"
        f"📌 Причина: {escape(req['reason_title'])}\n"
        f"💬 Реакция: {escape(reaction)}"
        "</blockquote>"
    )

    for admin_id in ADMINS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")


async def notify_admins_about_admin_reply(
    context: ContextTypes.DEFAULT_TYPE,
    request_id: int,
    admin_user,
    reply_text: str,
):
    req = REQUESTS[request_id]
    target_user = req["user"]

    admin_nick = escape(admin_user.first_name or "Администратор")
    admin_username = f"@{escape(admin_user.username)}" if admin_user.username else "нет username"
    target_user_line = user_mention_html(target_user)

    text = (
        "👨‍💼 <b>Ответ администратора</b>\n\n"
        "<blockquote>"
        f"Кто ответил: {admin_nick}\n"
        f"Username: {admin_username}\n"
        f"Кому ответил: {target_user_line}\n\n"
        f"Текст ответа:\n{escape(reply_text or 'Медиа/вложение')}"
        "</blockquote>"
    )

    for admin_id in ADMINS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")


def find_user_info_by_id(user_id: int) -> dict:
    for req in reversed(list(REQUESTS.values())):
        if req["user"]["id"] == user_id:
            return req["user"]
    return {
        "id": user_id,
        "username": None,
        "first_name": "Пользователь",
        "last_name": "",
    }

# =========================================
# КОМАНДЫ
# =========================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message:
        return

    user = update.effective_user

    if is_admin(user.id):
        await update.message.reply_text(
            "✅ <b>Вы вошли как админ</b>\n\n"
            "Нажмите <b>✍️ Ответить</b> под нужным обращением,\n"
            "и ваше следующее сообщение уйдёт пользователю анонимно.\n\n"
            "Команды:\n"
            "• <code>/id</code> — узнать свой ID\n"
            "• <code>/cancel</code> — отменить режим ответа\n"
            "• <code>/banlist</code> — посмотреть банлист",
            parse_mode=ParseMode.HTML,
        )
        return

    if user.id in FINISHED_USERS:
        FINISHED_USERS.discard(user.id)

    context.user_data["started"] = True
    context.user_data["reason_selected"] = False
    context.user_data.pop("reason_code", None)
    context.user_data.pop("reason_title", None)

    await update.message.reply_text(
        f"Здравствуйте, {safe_username(user)}!",
        parse_mode=ParseMode.HTML,
    )

    await update.message.reply_text(
        "Выберите причину обращения:",
        reply_markup=reason_keyboard(),
    )


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Ваш Telegram ID: <code>{user.id}</code>",
        parse_mode=ParseMode.HTML,
    )


async def cancel_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Команда доступна только администраторам.")
        return

    context.user_data.pop("reply_request_id", None)
    reply_prompt_msg_id = context.user_data.pop("reply_prompt_message_id", None)

    if reply_prompt_msg_id and update.message:
        try:
            await context.bot.delete_message(
                chat_id=update.effective_chat.id,
                message_id=reply_prompt_msg_id,
            )
        except Exception:
            pass

    await update.message.reply_text("✅ Режим ответа отменён.")


async def banlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    if not is_admin(user.id):
        await update.message.reply_text("⛔ Команда доступна только администраторам.")
        return

    if not BLOCKED_USERS:
        await update.message.reply_text("✅ Банлист пуст.")
        return

    blocks = ["🚫 <b>Банлист</b>"]

    for blocked_id in BLOCKED_USERS:
        info = find_user_info_by_id(blocked_id)
        first_name = escape(info.get("first_name") or "Пользователь")
        if info.get("username"):
            username_line = f"@{escape(info['username'])}"
        else:
            username_line = user_mention_html(info)

        blocks.append(
            "<blockquote>"
            f"👤 Имя: {first_name}\n"
            f"🔹 Username: {username_line}\n"
            f"🆔 ID: <code>{blocked_id}</code>"
            "</blockquote>"
        )

    await update.message.reply_text(
        "\n\n".join(blocks),
        parse_mode=ParseMode.HTML,
        disable_web_page_preview=True,
    )

# =========================================
# CALLBACK ОБРАБОТЧИКИ
# =========================================

async def handle_reason_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user

    if not query:
        return

    await query.answer()

    if is_admin(user.id):
        return

    if user.id in BLOCKED_USERS:
        return

    data = query.data or ""

    if data == "reason:back":
        context.user_data["reason_selected"] = False
        context.user_data.pop("reason_code", None)
        context.user_data.pop("reason_title", None)

        await query.edit_message_text(
            "Выберите причину обращения:",
            reply_markup=reason_keyboard(),
        )
        return

    if not data.startswith("reason:"):
        return

    reason_code = data.split(":", 1)[1]
    reason_title = get_reason_title(reason_code)

    context.user_data["started"] = True
    context.user_data["reason_selected"] = True
    context.user_data["reason_code"] = reason_code
    context.user_data["reason_title"] = reason_title

    await query.edit_message_text(
        f"✅ Причина обращения: {reason_title}"
    )

    await query.message.reply_text(
        get_reason_text(reason_code),
        reply_markup=back_keyboard(),
    )


async def handle_reply_button(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = update.effective_user

    if not query:
        return

    await query.answer()

    if not is_admin(admin.id):
        await query.answer("Только для админов", show_alert=True)
        return

    parts = (query.data or "").split(":")
    if len(parts) != 2:
        return

    request_id = int(parts[1])

    if request_id not in REQUESTS:
        await query.answer("Обращение не найдено", show_alert=True)
        return

    context.user_data["reply_request_id"] = request_id

    old_prompt_id = context.user_data.pop("reply_prompt_message_id", None)
    if old_prompt_id:
        try:
            await context.bot.delete_message(
                chat_id=query.message.chat_id,
                message_id=old_prompt_id,
            )
        except Exception:
            pass

    prompt_msg = await query.message.reply_text(
        "✍️ Режим ответа включён.\n"
        "Отправьте следующее сообщение — оно уйдёт пользователю анонимно."
    )
    context.user_data["reply_prompt_message_id"] = prompt_msg.message_id


async def handle_admin_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = update.effective_user

    if not query:
        return

    await query.answer()

    if not is_admin(admin.id):
        return

    parts = (query.data or "").split(":")
    if len(parts) != 3:
        return

    request_id = int(parts[1])
    reaction = parts[2]

    if request_id not in REQUESTS:
        return

    req = REQUESTS[request_id]
    req["admin_reactions"].setdefault("👍", set())
    req["admin_reactions"].setdefault("🫶🏻", set())

    if admin.id in req["admin_reactions"].get(reaction, set()):
        req["admin_reactions"][reaction].discard(admin.id)
    else:
        req["admin_reactions"]["👍"].discard(admin.id)
        req["admin_reactions"]["🫶🏻"].discard(admin.id)
        req["admin_reactions"][reaction].add(admin.id)

    await refresh_admin_cards(context, request_id)


async def handle_user_reaction(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user

    if not query:
        return

    await query.answer()

    if is_admin(user.id):
        return

    parts = (query.data or "").split(":")
    if len(parts) != 3:
        return

    response_id = int(parts[1])
    reaction = parts[2]

    if response_id not in RESPONSES:
        await query.answer("Сообщение не найдено", show_alert=True)
        return

    response_info = RESPONSES[response_id]
    if response_info["user_id"] != user.id:
        await query.answer("Это не ваше сообщение", show_alert=True)
        return

    if response_info.get("reaction") is not None:
        await query.answer("Реакцию можно поставить только один раз", show_alert=True)
        return

    response_info["reaction"] = reaction
    request_id = response_info["request_id"]

    if request_id in REQUESTS:
        REQUESTS[request_id]["user_reaction"] = reaction
        await refresh_admin_cards(context, request_id)

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=user_response_keyboard(response_id, selected=reaction),
        )
    except Exception as e:
        logger.warning(f"Не удалось обновить реакцию пользователя: {e}")

    await notify_admins_about_user_reaction(context, request_id, reaction)


async def handle_block_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = update.effective_user

    if not query:
        return

    await query.answer()

    if not is_admin(admin.id):
        return

    parts = (query.data or "").split(":")
    if len(parts) != 2:
        return

    request_id = int(parts[1])

    if request_id not in REQUESTS:
        return

    req = REQUESTS[request_id]
    user_info = req["user"]
    user_id = user_info["id"]

    if user_info.get("username"):
        username = f"@{user_info['username']}"
    else:
        username = user_info.get("first_name") or "Пользователь"

    BLOCKED_USERS.add(user_id)
    req["status"] = "blocked"
    req["status_text"] = f"ЗАБЛОКИРОВАН 🚫, админом: {admin_name(admin)}"

    await refresh_admin_cards(context, request_id)

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=f"{escape(username)}, вы заблокированы администрацией",
            parse_mode=ParseMode.HTML,
        )
    except Exception as e:
        logger.warning(f"Не удалось уведомить пользователя о блокировке: {e}")


async def handle_unblock_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = update.effective_user

    if not query:
        return

    await query.answer()

    if not is_admin(admin.id):
        return

    parts = (query.data or "").split(":")
    if len(parts) != 2:
        return

    request_id = int(parts[1])

    if request_id not in REQUESTS:
        return

    req = REQUESTS[request_id]
    user_info = req["user"]
    user_id = user_info["id"]

    BLOCKED_USERS.discard(user_id)
    req["status"] = "unblocked"
    req["status_text"] = f"РАЗБЛОКИРОВАН ✅, админом: {admin_name(admin)}"

    await refresh_admin_cards(context, request_id)

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text="✅ Вы разблокированы администрацией. Можете снова нажать /start",
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить уведомление о разблокировке: {e}")


async def handle_finish_dialog(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    admin = update.effective_user

    if not query:
        return

    await query.answer()

    if not is_admin(admin.id):
        return

    parts = (query.data or "").split(":")
    if len(parts) != 2:
        return

    request_id = int(parts[1])

    if request_id not in REQUESTS:
        return

    req = REQUESTS[request_id]
    user_id = req["user"]["id"]

    FINISHED_USERS.add(user_id)
    req["status"] = "finished"
    req["status_text"] = f"ДИАЛОГ ЗАВЕРШЁН ✅, админом: {admin_name(admin)}"

    await refresh_admin_cards(context, request_id)

    try:
        await context.bot.send_message(
            chat_id=user_id,
            text=(
                "Спасибо за обращение! 😊\n"
                "Если у вас появятся дополнительные вопросы, нажмите /start, "
                "и мы с радостью вам поможем"
            ),
        )
    except Exception as e:
        logger.warning(f"Не удалось отправить сообщение о завершении диалога: {e}")


async def callback_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if not query or not query.data:
        return

    data = query.data

    if data.startswith("reason:"):
        await handle_reason_choice(update, context)
    elif data.startswith("reply:"):
        await handle_reply_button(update, context)
    elif data.startswith("adminreact:"):
        await handle_admin_reaction(update, context)
    elif data.startswith("userreact:"):
        await handle_user_reaction(update, context)
    elif data.startswith("block:"):
        await handle_block_user(update, context)
    elif data.startswith("unblock:"):
        await handle_unblock_user(update, context)
    elif data.startswith("finish:"):
        await handle_finish_dialog(update, context)
    else:
        await query.answer()

# =========================================
# ОБРАБОТКА СООБЩЕНИЙ
# =========================================

async def handle_admin_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    admin = update.effective_user

    if not message or not is_admin(admin.id):
        return

    request_id = context.user_data.get("reply_request_id")
    if not request_id:
        return

    if request_id not in REQUESTS:
        context.user_data.pop("reply_request_id", None)
        await message.reply_text("❌ Обращение не найдено.")
        return

    req = REQUESTS[request_id]
    target_user_id = req["user"]["id"]

    if target_user_id in BLOCKED_USERS:
        warn = await message.reply_text("⛔ Пользователь заблокирован.")
        context.application.create_task(
            delete_message_later(context, warn.chat_id, warn.message_id, 5)
        )
        return

    text_to_send = message.text or message.caption
    has_media = any([
        message.photo,
        message.document,
        message.video,
        message.voice,
        message.audio,
        message.video_note,
        message.animation,
        message.sticker,
    ])

    if not text_to_send and not has_media:
        warn = await message.reply_text("❌ Отправьте текст или медиа с подписью.")
        context.application.create_task(
            delete_message_later(context, warn.chat_id, warn.message_id, 5)
        )
        return

    sent_message = None

    try:
        reply_caption = (
            "📨 <b>Ответ от администрации</b>\n\n"
            f"{escape(text_to_send or '')}"
        )

        if message.text:
            sent_message = await context.bot.send_message(
                chat_id=target_user_id,
                text=reply_caption,
                parse_mode=ParseMode.HTML,
            )
        elif message.photo:
            sent_message = await context.bot.send_photo(
                chat_id=target_user_id,
                photo=message.photo[-1].file_id,
                caption=reply_caption,
                parse_mode=ParseMode.HTML,
            )
        elif message.document:
            sent_message = await context.bot.send_document(
                chat_id=target_user_id,
                document=message.document.file_id,
                caption=reply_caption,
                parse_mode=ParseMode.HTML,
            )
        elif message.video:
            sent_message = await context.bot.send_video(
                chat_id=target_user_id,
                video=message.video.file_id,
                caption=reply_caption,
                parse_mode=ParseMode.HTML,
            )
        elif message.voice:
            sent_message = await context.bot.send_voice(
                chat_id=target_user_id,
                voice=message.voice.file_id,
                caption=reply_caption,
                parse_mode=ParseMode.HTML,
            )
        elif message.audio:
            sent_message = await context.bot.send_audio(
                chat_id=target_user_id,
                audio=message.audio.file_id,
                caption=reply_caption,
                parse_mode=ParseMode.HTML,
            )
        else:
            copied = await context.bot.copy_message(
                chat_id=target_user_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id,
                caption=reply_caption if text_to_send else None,
                parse_mode=ParseMode.HTML if text_to_send else None,
            )
            sent_message = copied

        response_id = next(RESPONSE_SEQ)

        if sent_message:
            RESPONSES[response_id] = {
                "request_id": request_id,
                "user_id": target_user_id,
                "message_id": sent_message.message_id,
                "chat_id": target_user_id,
                "reaction": None,
            }

            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=target_user_id,
                    message_id=sent_message.message_id,
                    reply_markup=user_response_keyboard(response_id),
                )
            except Exception as e:
                logger.warning(f"Не удалось добавить кнопки реакции пользователю: {e}")

        req["status"] = "answered"
        req["answered_by"] = admin_name(admin)
        req["status_text"] = f"ОТВЕЧЕНО ✅, админом: {req['answered_by']}"

        await refresh_admin_cards(context, request_id)

        await notify_admins_about_admin_reply(
            context=context,
            request_id=request_id,
            admin_user=admin,
            reply_text=text_to_send or "Медиа/вложение",
        )

        context.user_data.pop("reply_request_id", None)

        reply_prompt_msg_id = context.user_data.pop("reply_prompt_message_id", None)
        if reply_prompt_msg_id:
            try:
                await context.bot.delete_message(
                    chat_id=message.chat_id,
                    message_id=reply_prompt_msg_id,
                )
            except Exception:
                pass

        ok_msg = await message.reply_text("✅ Ответ отправлен анонимно.")
        context.application.create_task(
            delete_message_later(context, ok_msg.chat_id, ok_msg.message_id, 5)
        )

    except Exception as e:
        logger.exception("Ошибка при отправке ответа пользователю")
        err = await message.reply_text(f"❌ Не удалось отправить сообщение.\n{e}")
        context.application.create_task(
            delete_message_later(context, err.chat_id, err.message_id, 5)
        )


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user

    if not message or is_admin(user.id):
        return

    if user.id in BLOCKED_USERS:
        username = f"@{user.username}" if user.username else "Пользователь"
        warn = await message.reply_text(f"{username}, вы заблокированы администрацией")
        context.application.create_task(
            delete_message_later(context, warn.chat_id, warn.message_id, 5)
        )
        context.application.create_task(try_delete_user_message(message))
        return

    if user.id in FINISHED_USERS:
        warn = await message.reply_text(
            "Диалог завершён.\n"
            "Чтобы написать снова, нажмите /start"
        )
        context.application.create_task(
            delete_message_later(context, warn.chat_id, warn.message_id, 5)
        )
        context.application.create_task(try_delete_user_message(message))
        return

    started = context.user_data.get("started", False)
    reason_selected = context.user_data.get("reason_selected", False)
    reason_code = context.user_data.get("reason_code")
    reason_title = context.user_data.get("reason_title")

    if not started:
        warn = await message.reply_text(
            "⚠️ Сначала нажмите /start, затем выберите причину обращения."
        )
        context.application.create_task(
            delete_message_later(context, warn.chat_id, warn.message_id, 5)
        )
        context.application.create_task(try_delete_user_message(message))
        return

    if not reason_selected or not reason_code or not reason_title:
        warn = await message.reply_text(
            "⚠️ Сначала выберите причину обращения.",
            reply_markup=reason_keyboard(),
        )
        context.application.create_task(
            delete_message_later(context, warn.chat_id, warn.message_id, 5)
        )
        context.application.create_task(try_delete_user_message(message))
        return

    request_id = next(REQUEST_SEQ)
    msg_type = detect_message_type(message)

    REQUESTS[request_id] = {
        "reason_code": reason_code,
        "reason_title": reason_title,
        "status": "open",
        "status_text": "НЕ ОТВЕЧЕНО ❌",
        "answered_by": None,
        "user_reaction": None,
        "admin_reactions": {"👍": set(), "🫶🏻": set()},
        "user": {
            "id": user.id,
            "username": user.username,
            "first_name": user.first_name,
            "last_name": user.last_name,
        },
        "message_type": msg_type,
        "message_text": message.text if message.text else None,
        "caption": message.caption if message.caption else None,
        "voice_duration": message.voice.duration if message.voice else None,
        "admin_message_refs": [],
    }

    admin_text = build_admin_card_text(request_id)
    admin_markup = admin_card_keyboard(request_id)

    for admin_id in ADMINS:
        try:
            sent = await context.bot.send_message(
                chat_id=admin_id,
                text=admin_text,
                parse_mode=ParseMode.HTML,
                reply_markup=admin_markup,
                disable_web_page_preview=True,
            )

            REQUESTS[request_id]["admin_message_refs"].append({
                "chat_id": admin_id,
                "message_id": sent.message_id,
            })

            if not message.text:
                await message.forward(chat_id=admin_id)

        except Exception as e:
            logger.warning(f"Не удалось отправить обращение админу {admin_id}: {e}")

    ok_msg = await message.reply_text("✅ Ваше сообщение отправлено администрации.")
    context.application.create_task(
        delete_message_later(context, ok_msg.chat_id, ok_msg.message_id, 5)
    )

# =========================================
# ЗАПУСК
# =========================================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("cancel", cancel_reply))
    app.add_handler(CommandHandler("banlist", banlist_command))

    app.add_handler(CallbackQueryHandler(callback_router))

    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_admin_message), group=0)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_user_message), group=1)

    logger.info("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
