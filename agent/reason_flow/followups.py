"""A message that arrives while the agent is working joins the running task.

People send a request in pieces ("order snacks", then "doritos and water"). Hermes'
default is to queue each piece as its own turn, so the first turn answers without
the second piece. Instead, while a turn is running:

- text first tries Hermes' *redirect*: the in-flight model call is cancelled and
  retried with both messages (during a tool call it degrades to a steer);
- otherwise (voice, or redirect not available) a *steer*: the message reaches the
  agent right after its current tool call;
- the message gets 👀 and joins the turn (its reply will not quote, and the 👀 is
  removed when the turn ends). No text acknowledgement, no interruption.

If neither lands, Hermes queues the message as the next turn, as before.
"""

from __future__ import annotations

from typing import Any

from . import enabled, signals, state


def active() -> bool:
    return enabled("FOLLOWUPS")


def _plain_text(event: Any) -> bool:
    return bool((getattr(event, "text", "") or "").strip()) and not getattr(event, "media_urls", None)


async def join_running_turn(runner: Any, event: Any, session_key: str, agent: Any) -> Any:
    """Resolve the follow-up through Hermes' own steer/redirect machinery. Returns its outcome."""
    can_redirect = getattr(agent, "_supports_active_turn_redirect", False) is True and hasattr(agent, "redirect")
    if _plain_text(event) and can_redirect:
        outcome = await runner._resolve_busy_steer_or_redirect(event, session_key, "interrupt", agent)
        if getattr(outcome, "redirected", False):
            return outcome
    return await runner._resolve_busy_steer_or_redirect(event, session_key, "steer", agent)


async def acknowledge(adapter: Any, event: Any, outcome: Any) -> None:
    chat_id, message_id = state.ids_of(event)
    state.received(chat_id, message_id)
    if chat_id and message_id and (getattr(outcome, "steered", False) or getattr(outcome, "redirected", False)):
        state.chat(chat_id).joined.add(message_id)
    if signals.active(adapter):
        await signals.react(adapter, chat_id, message_id, signals.WORKING)
