"""Per-chat bookkeeping, in memory, bounded.

A chat is identified by the gateway's ``chat_id``; a message by the platform's
``message_id``. Nothing here survives a restart, and nothing needs to: it only
shapes how the next reply looks.
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any, Optional

MAX_TRACKED = 1000


@dataclass
class Chat:
    newest: Optional[str] = None                   # last message received in this chat
    working_on: Optional[str] = None               # message whose turn is running
    joined: set = field(default_factory=set)       # messages folded into the running turn
    reaction_for: dict = field(default_factory=dict)  # message -> reaction chosen by the model


_chats: "OrderedDict[str, Chat]" = OrderedDict()
_seen: "OrderedDict[tuple, None]" = OrderedDict()


def chat(chat_id: str) -> Chat:
    key = str(chat_id)
    if key not in _chats:
        _chats[key] = Chat()
        while len(_chats) > MAX_TRACKED:
            _chats.popitem(last=False)
    return _chats[key]


def ids_of(event: Any) -> tuple:
    """(chat_id, message_id) of a gateway MessageEvent, as strings ("" when missing)."""
    source = getattr(event, "source", None)
    return str(getattr(source, "chat_id", "") or ""), str(getattr(event, "message_id", "") or "")


def received(chat_id: str, message_id: str) -> None:
    """Record an incoming message once, in arrival order."""
    if not chat_id or not message_id or (chat_id, message_id) in _seen:
        return
    _seen[(chat_id, message_id)] = None
    while len(_seen) > MAX_TRACKED:
        _seen.popitem(last=False)
    chat(chat_id).newest = message_id


def reset() -> None:
    """Tests only."""
    _chats.clear()
    _seen.clear()
