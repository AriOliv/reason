"""Reactions on the owner's messages, and when a reply should quote.

People react instead of answering "ok", and they quote only when replying to
something that is no longer the latest message. The agent does the same:

- 👀 on a message while it is being worked on, removed at the end;
- in its place, a reaction only when the model chose one (``[react: ❤️]``);
- a reply quotes its message only if a newer one arrived and was not folded in.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from . import enabled, is_chat, platform_of, state

log = logging.getLogger("gateway.reason_flow")

WORKING = "\U0001f440"  # 👀

# A Telegram bot may react only with a fixed set of emoji.
TELEGRAM_ALLOWED = frozenset(
    "👍 👎 ❤ 🔥 🥰 👏 😁 🤔 🤯 😱 😢 🎉 🤩 🙏 👌 💯 🤣 ⚡ 🏆 💔 🤨 😐 😭 🤓 👀 🙈 😇 🤝 ✍ 🤗 🫡 😎 😘 🆒 💘 🤷".split()
)
TELEGRAM_EQUIVALENT = {
    "❤️": "❤", "😂": "🤣", "😅": "😁", "😄": "😁", "😃": "😁", "😊": "🥰",
    "✅": "👌", "👋": "🤗", "💪": "🔥", "✨": "🎉", "🙌": "👏", "✍️": "✍",
}

_MARKER = r"\[\s*(?:react|reaction|rea[cç][aã]o)\s*:\s*([^\]\s]{1,16})\s*\]"
_LEADING = re.compile(r"^\s*" + _MARKER + r"\s*", re.IGNORECASE)
_TRAILING = re.compile(r"\s*" + _MARKER + r"\s*$", re.IGNORECASE)
_SILENT = frozenset({"NO_REPLY", "NO REPLY", "[SILENT]", "SILENT"})


def active(adapter: Any) -> bool:
    return enabled("REACTIONS") and is_chat(adapter)


def split_reaction(text: str) -> tuple:
    """(reaction or None, text without the marker). A bare silence marker means 👍 and no text."""
    body = (text or "").strip()
    if body.strip(".*_`'\" ").upper() in _SILENT:
        return "\U0001f44d", ""
    for pattern in (_LEADING, _TRAILING):
        found = pattern.search(body)
        if found:
            return found.group(1), (body[: found.start()] + body[found.end():]).strip()
    return None, text


def for_telegram(emoji: Optional[str]) -> Optional[str]:
    if emoji is None:
        return None
    emoji = TELEGRAM_EQUIVALENT.get(emoji, emoji)
    return emoji if emoji in TELEGRAM_ALLOWED else None


async def react(adapter: Any, chat_id: str, message_id: str, emoji: Optional[str]) -> bool:
    """Set the bot's reaction on a message (``None`` clears it). Never raises."""
    if not chat_id or not message_id:
        return False
    try:
        platform = platform_of(adapter)
        if platform == "telegram":
            mapped = for_telegram(emoji)
            if emoji is not None and mapped is None:
                log.info("reason_flow: %r is not a Telegram reaction; skipped", emoji)
                return False
            return bool(await adapter._set_reaction(chat_id, message_id, mapped))
        if platform == "whatsapp":
            import aiohttp
            from gateway.whatsapp_identity import to_whatsapp_jid

            session = getattr(adapter, "_http_session", None)
            if session is None:
                return False
            body = {"chatId": to_whatsapp_jid(chat_id), "messageId": message_id, "emoji": emoji or ""}
            async with session.post(adapter._bridge_url("react"), json=body,
                                    timeout=aiohttp.ClientTimeout(total=5)) as resp:
                return resp.status == 200
    except Exception:  # a reaction is decoration: it must never break the conversation
        log.debug("reason_flow: reaction failed", exc_info=True)
    return False


def should_quote(chat_id: str, reply_to: Optional[str]) -> Optional[str]:
    """Quote ``reply_to`` only when a newer message arrived and was not folded into this turn."""
    if not reply_to:
        return None
    c = state.chat(chat_id)
    if c.newest is None or c.newest == str(reply_to) or c.newest in c.joined:
        return None
    return reply_to


async def turn_started(adapter: Any, event: Any) -> None:
    chat_id, message_id = state.ids_of(event)
    state.received(chat_id, message_id)
    if chat_id and message_id:
        state.chat(chat_id).working_on = message_id
        await react(adapter, chat_id, message_id, WORKING)


async def turn_finished(adapter: Any, event: Any, outcome: Any = None) -> None:
    """Swap 👀 for the reaction the model chose (or nothing), here and on folded messages."""
    chat_id, message_id = state.ids_of(event)
    c = state.chat(chat_id)
    if c.working_on == message_id:
        c.working_on = None
    await react(adapter, chat_id, message_id, c.reaction_for.pop(message_id, None))
    folded, c.joined = c.joined - {message_id}, set()
    for other in sorted(folded):
        await react(adapter, chat_id, other, None)
