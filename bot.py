import logging
import os
from html import escape
from itertools import count
from typing import Final, Optional

from telegram import (
    Update,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
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
except ValueError:
    raise ValueError("ADMINS должен содержать только числовые Telegram ID через запятую")

logging.basicConfig(
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# =========================================
# ХРАНИЛИЩА
# =========================================

# internal_request_id -> данные обращения
REQUESTS: dict[int, dict] = {}

# response_id -> данные ответа пользователю
RESPONSES: dict[int, dict] = {}

REQUEST_SEQ = count(1001)
RESPONSE_SEQ = count(5001)

# =========================================
# ВСПОМОГАТЕЛЬНОЕ
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
    return escape(user.first_name or "Admin")


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
    keyboard = [
        [InlineKeyboardButton("🔐 A) Вопрос по блокировке аккаунта", callback_data="reason:block")],
        [InlineKeyboardButton("🤝 B) Вопрос по сотрудничеству", callback_data="reason:coop")],
        [InlineKeyboardButton("🧠 C) Покупка тестов", callback_data="reason:tests")],
        [InlineKeyboardButton("📕 Д) свой вопрос", callback_data="reason:other")],
    ]
    return InlineKeyboardMarkup(keyboard)


def back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("⬅️ Назад", callback_data="reason:back")]]
    )


def user_response_keyboard(response_id: int, selected: Optional[str] = None) -> InlineKeyboardMarkup:
    left = "👍"
    right = "🫶🏻"

    if selected == "👍":
        left = "✅ 👍"
    if selected == "🫶🏻":
        right = "✅ 🫶🏻"

    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton(left, callback_data=f"userreact:{response_id}:👍"),
            InlineKeyboardButton(right, callback_data=f"userreact:{response_id}:🫶🏻"),
        ]
    ])


def admin_card_keyboard(request_id: int) -> InlineKeyboardMarkup:
    req = REQUESTS[request_id]
    like_count = len(req["admin_reactions"].get("👍", set()))
    heart_count = len(req["admin_reactions"].get("🫶🏻", set()))

    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✍️ Ответить", callback_data=f"reply:{request_id}")],
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

    username = f"@{escape(user['username'])}" if user.get("username") else "нет username"
    user_id = user["id"]
    reason = escape(req["reason_title"])
    status_text = req["status_text"]

    lines = [
        "📩 <b>Новое обращение</b>",
        "",
        "<blockquote>",
        f"👤 Имя: {full_name}",
        f"🔹 Username: {username}",
        f"🆔 ID: <code>{user_id}</code>",
        f"📌 Причина: {reason}",
        f"📍 Статус: {status_text}",
    ]

    if req.get("message_text"):
        lines.append("")
        lines.append("💬 Сообщение:")
        lines.append(escape(req["message_text"]))

    if req.get("caption"):
        lines.append("")
        lines.append("📝 Подпись:")
        lines.append(escape(req["caption"]))

    if req.get("user_reaction"):
        lines.append("")
        lines.append(f"🙋 Реакция пользователя на ответ: {escape(req['user_reaction'])}")

    admin_reacts = req.get("admin_reactions", {})
    react_parts = []
    if len(admin_reacts.get("👍", set())) > 0:
        react_parts.append(f"👍 {len(admin_reacts['👍'])}")
    if len(admin_reacts.get("🫶🏻", set())) > 0:
        react_parts.append(f"🫶🏻 {len(admin_reacts['🫶🏻'])}")

    if react_parts:
        lines.append("")
        lines.append("🧷 Реакции админов: " + " | ".join(react_parts))

    lines.append("</blockquote>")

    return "\n".join(lines)


async def refresh_admin_cards(context: ContextTypes.DEFAULT_TYPE, request_id: int):
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
            )
        except Exception as e:
            logger.warning(f"Не удалось обновить карточку обращения у админа {item['chat_id']}: {e}")


async def notify_admins_about_user_reaction(
    context: ContextTypes.DEFAULT_TYPE,
    request_id: int,
    reaction: str
):
    req = REQUESTS[request_id]
    user = req["user"]
    uname = f"@{user['username']}" if user.get("username") else f"ID {user['id']}"

    text = (
        "🔔 <b>Пользователь отреагировал на ответ</b>\n\n"
        "<blockquote>"
        f"👤 Пользователь: {escape(uname)}\n"
        f"📌 Причина: {escape(req['reason_title'])}\n"
        f"💬 Реакция: {escape(reaction)}"
        "</blockquote>"
    )

    for admin_id in ADMINS:
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=text,
                parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.warning(f"Не удалось отправить уведомление админу {admin_id}: {e}")


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
            "• <code>/cancel</code> — отменить режим ответа",
            parse_mode=ParseMode.HTML
        )
        return

    context.user_data["reason_selected"] = False
    context.user_data.pop("reason_code", None)
    context.user_data.pop("reason_title", None)

    await update.message.reply_text(
        f"Здравствуйте, {safe_username(user)}!",
        parse_mode=ParseMode.HTML
    )

    await update.message.reply_text(
        "Выберите причину обращения:",
        reply_markup=reason_keyboard()
    )


async def my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_text(
        f"Ваш Telegram ID: <code>{user.id}</code>",
        parse_mode=ParseMode.HTML
    )


async def cancel_reply(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not is_admin(user.id):
        await update.message.reply_text("⛔ Команда доступна только администраторам.")
        return

    context.user_data.pop("reply_request_id", None)
    await update.message.reply_text("✅ Режим ответа отменён.")


# =========================================
# CALLBACK
# =========================================

async def handle_reason_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user = update.effective_user

    if not query:
        return

    await query.answer()

    if is_admin(user.id):
        return

    data = query.data or ""

    if data == "reason:back":
        context.user_data["reason_selected"] = False
        context.user_data.pop("reason_code", None)
        context.user_data.pop("reason_title", None)

        await query.edit_message_text(
            "Выберите причину обращения:",
            reply_markup=reason_keyboard()
        )
        return

    if not data.startswith("reason:"):
        return

    reason_code = data.split(":", 1)[1]
    reason_title = get_reason_title(reason_code)

    context.user_data["reason_selected"] = True
    context.user_data["reason_code"] = reason_code
    context.user_data["reason_title"] = reason_title

    await query.edit_message_text(
        f"✅ Причина обращения: {reason_title}"
    )

    await query.message.reply_text(
        get_reason_text(reason_code),
        reply_markup=back_keyboard()
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

    await query.message.reply_text(
        "✍️ Режим ответа включён.\n"
        "Отправьте следующее сообщение — оно уйдёт пользователю анонимно.",
    )


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

    response_info["reaction"] = reaction
    request_id = response_info["request_id"]

    if request_id in REQUESTS:
        REQUESTS[request_id]["user_reaction"] = reaction
        await refresh_admin_cards(context, request_id)

    try:
        await context.bot.edit_message_reply_markup(
            chat_id=query.message.chat_id,
            message_id=query.message.message_id,
            reply_markup=user_response_keyboard(response_id, selected=reaction)
        )
    except Exception as e:
        logger.warning(f"Не удалось обновить реакцию пользователя: {e}")

    await notify_admins_about_user_reaction(context, request_id, reaction)


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

    text_to_send = message.text or message.caption
    if not text_to_send and not message.effective_attachment:
        await message.reply_text("❌ Отправьте текст или медиа с подписью.")
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
        else:
            sent_message = await context.bot.copy_message(
                chat_id=target_user_id,
                from_chat_id=message.chat_id,
                message_id=message.message_id,
            )

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
                    reply_markup=user_response_keyboard(response_id)
                )
            except Exception as e:
                logger.warning(f"Не удалось добавить кнопки реакции пользователю: {e}")

        req["status"] = "answered"
        req["answered_by"] = admin_name(admin)
        req["status_text"] = f"ОТВЕЧЕНО ✅, админом: {req['answered_by']}"

        await refresh_admin_cards(context, request_id)

        context.user_data.pop("reply_request_id", None)
        await message.reply_text("✅ Ответ отправлен анонимно.")

    except Exception as e:
        logger.exception("Ошибка при отправке ответа пользователю")
        await message.reply_text(f"❌ Не удалось отправить сообщение.\n{e}")


async def handle_user_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    user = update.effective_user

    if not message or is_admin(user.id):
        return

    reason_selected = context.user_data.get("reason_selected", False)
    reason_code = context.user_data.get("reason_code")
    reason_title = context.user_data.get("reason_title")

    if not reason_selected or not reason_code or not reason_title:
        await message.reply_text(
            "⚠️ Сначала выберите причину обращения.",
            reply_markup=reason_keyboard()
        )
        return

    request_id = next(REQUEST_SEQ)

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
        "message_text": message.text if message.text else None,
        "caption": message.caption if message.caption else None,
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
            )

            REQUESTS[request_id]["admin_message_refs"].append({
                "chat_id": admin_id,
                "message_id": sent.message_id
            })

            if not message.text:
                await message.forward(chat_id=admin_id)

        except Exception as e:
            logger.warning(f"Не удалось отправить обращение админу {admin_id}: {e}")

    await message.reply_text("✅ Ваше сообщение отправлено администрации.")


# =========================================
# ЗАПУСК
# =========================================

def main():
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", my_id))
    app.add_handler(CommandHandler("cancel", cancel_reply))

    app.add_handler(CallbackQueryHandler(callback_router))

    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_admin_message), group=0)
    app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, handle_user_message), group=1)

    logger.info("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()
