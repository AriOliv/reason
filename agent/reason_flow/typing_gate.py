""""typing…" the way a person types.

Hermes shows "typing…" from the moment a message arrives until the reply is sent,
even during a minute of tool work. A person reads, does the task, and types only
when there is something to say. So:

- the turn's typing loop does not start, and the adapter's ``send_typing`` is
  gated: it works only inside :func:`show`;
- right before each outgoing message, "typing…" is shown for a time proportional
  to its length (a floor and a cap, so short and long replies both feel natural).
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

from . import enabled, is_chat

log = logging.getLogger("gateway.reason_flow")

_open: set = set()  # chats whose send_typing is allowed right now


def active(adapter: Any) -> bool:
    return enabled("NATURAL_TYPING") and is_chat(adapter)


def seconds_for(text: str, first: bool) -> float:
    per_char = float(os.environ.get("REASON_TYPING_MS_PER_CHAR", "30") or 30) / 1000
    floor, cap = (1.0, 4.0) if first else (0.6, 3.0)
    return max(floor, min(cap, len((text or "").strip()) * per_char))


def gate(adapter: Any) -> None:
    """Wrap the adapter class's ``send_typing`` once, so every Hermes call site obeys the gate."""
    cls = type(adapter)
    if cls.__dict__.get("_reason_typing_gated"):
        return
    original = cls.send_typing

    async def send_typing(self, chat_id, *args, **kwargs):
        if active(self) and str(chat_id) not in _open:
            return None
        return await original(self, chat_id, *args, **kwargs)

    cls.send_typing = send_typing
    cls._reason_typing_gated = True


async def show(adapter: Any, chat_id: str, seconds: float, metadata: Any = None) -> None:
    """Show "typing…" for ``seconds``, refreshing every 4 s (platforms expire it after ~5 s)."""
    key, left = str(chat_id), max(0.0, seconds)
    while True:
        _open.add(key)
        try:
            await adapter.send_typing(chat_id, metadata=metadata)
        except Exception:
            log.debug("reason_flow: typing failed", exc_info=True)
        finally:
            _open.discard(key)
        step = min(4.0, left)
        await asyncio.sleep(step)
        left -= step
        if left <= 0:
            return
