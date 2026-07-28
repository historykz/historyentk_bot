from __future__ import annotations

from decimal import Decimal

from aiogram.types import Message

from app.db.models import MessageKind


def fmt_money(amount: Decimal | float | int | None) -> str:
    if amount is None:
        return "-"
    value = Decimal(amount)
    return f"{value:,.0f}".replace(",", " ") + " ₸"


def detect_message_kind(message: Message) -> MessageKind:
    if message.text is not None:
        return MessageKind.TEXT
    if message.photo:
        return MessageKind.PHOTO
    if message.video:
        return MessageKind.VIDEO
    if message.document:
        return MessageKind.DOCUMENT
    if message.voice:
        return MessageKind.VOICE
    if message.video_note:
        return MessageKind.VIDEO_NOTE
    if message.audio:
        return MessageKind.AUDIO
    if message.sticker:
        return MessageKind.STICKER
    return MessageKind.OTHER


def extract_file_id(message: Message) -> str | None:
    if message.photo:
        return message.photo[-1].file_id
    if message.video:
        return message.video.file_id
    if message.document:
        return message.document.file_id
    if message.voice:
        return message.voice.file_id
    if message.video_note:
        return message.video_note.file_id
    if message.audio:
        return message.audio.file_id
    if message.sticker:
        return message.sticker.file_id
    return None


def extract_text_or_caption(message: Message) -> str | None:
    return message.text or message.caption
