"""The final reply: reaction, quote decision, short messages, natural typing.

Called instead of the adapter's single ``_send_with_retry`` for a turn's final
text. Hermes' delivery ledger stays around it (it records before and finalises
with the returned result).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Optional

from . import enabled, is_chat, signals, state, typing_gate as typing

log = logging.getLogger("gateway.reason_flow")

MAX_MESSAGES = 5
_FENCE = re.compile(r"^\s*(```|~~~)")
_ITEM = re.compile(r"^\s*([-*•]|\d+[.)])\s+")


def split(text: str, limit: int = MAX_MESSAGES) -> list:
    """Paragraphs become messages; code blocks, lists and "intro:" lines stay whole; at most ``limit``."""
    text = (text or "").strip()
    if not text:
        return []
    blocks, current, fenced = [], [], False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
            current.append(line)
        elif line.strip() or fenced:
            current.append(line)
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))

    merged: list = []
    for block in blocks:
        previous = merged[-1] if merged else ""
        continues_list = previous and _ITEM.match(previous.rsplit("\n", 1)[-1]) and _ITEM.match(block.split("\n", 1)[0])
        if previous and (continues_list or previous.rstrip().endswith(":")):
            merged[-1] = previous + "\n\n" + block
        else:
            merged.append(block)
    if len(merged) > limit:
        merged = merged[: limit - 1] + ["\n\n".join(merged[limit - 1:])]
    return merged


def _no_text_result() -> Any:
    try:
        from gateway.platforms.base import SendResult
    except ImportError:  # unit tests outside the image
        import types
        return types.SimpleNamespace(success=True, message_id=None, error=None)
    return SendResult(success=True, message_id=None)


async def deliver(adapter: Any, *, chat_id: str, content: str, reply_to: Optional[str], metadata: Any) -> Any:
    chat_key = str(chat_id)
    if signals.active(adapter):
        target = str(reply_to or state.chat(chat_key).working_on or "")
        emoji, content = signals.split_reaction(content)
        if emoji and target:
            state.chat(chat_key).reaction_for[target] = emoji
        reply_to = signals.should_quote(chat_key, reply_to)
        if not (content or "").strip():
            return _no_text_result()  # the reaction is the whole reply

    parts = split(content) if enabled("SPLIT_REPLIES") and is_chat(adapter) else [content]
    natural = typing.active(adapter)
    pause = float(os.environ.get("REASON_SPLIT_PAUSE", "0.8") or 0)
    first = None
    for index, part in enumerate(parts):
        if natural:
            await typing.show(adapter, chat_id, typing.seconds_for(part, index == 0), metadata)
        elif index:
            await asyncio.sleep(pause)
        result = await adapter._send_with_retry(
            chat_id=chat_id, content=part, reply_to=reply_to if index == 0 else None, metadata=metadata)
        if result.success:
            first = first or result
            continue
        if index == 0:
            return result  # nothing went out: Hermes' ledger retries the whole reply
        log.warning("reason_flow: part %d/%d failed (%s); sending the rest together",
                    index + 1, len(parts), getattr(result, "error", ""))
        rest = await adapter._send_with_retry(
            chat_id=chat_id, content="\n\n".join(parts[index:]), reply_to=None, metadata=metadata)
        return first if rest.success else rest
    return first
