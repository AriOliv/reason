"""The guard inside Hermes: one directive per tool call, and learning from each result.

``directive`` runs first in ``_get_pre_tool_call_directive_details``, the one place every tool
call passes through (sequential, concurrent and bridged calls alike). It returns Hermes' own
directive shapes:

- ``None``: allow;
- ``{"action": "block", "message"}``: the message becomes the tool result the model reads;
- ``{"action": "approve", "message", "rule_key"}``: Hermes asks the owner on the chat and waits.

Three things Hermes would otherwise allow, refused here:

- a guard error never lets the call through (Hermes treats a failing hook as "allow");
- "ask" is never auto-approved: with /yolo on, approvals off or "smart", or nobody present to
  answer (cron, single query), the call is blocked instead;
- an "ok" never carries over: each approval has a unique rule key, so "always" or "this
  session" on the approval card cannot pre-approve the next purchase.
"""

from __future__ import annotations

import logging
import uuid

from . import policy, screen

logger = logging.getLogger("reason.guard")


def _why_no_owner_answer() -> str | None:
    """Why an "ask" cannot reach the owner right now, or None when it can."""
    from tools import approval, approval_context

    if approval._yolo_active():
        return "yolo mode is on"
    mode = approval_context._get_approval_mode()
    if mode != "manual":
        return f"approvals are set to {mode!r}, not 'manual'"
    _, is_cli, is_gateway, _ = approval._presence(None)
    if not (is_cli or is_gateway):
        return "no owner is present to answer"
    return None


def directive(tool_name: str, args: object, *, session_id: str = "", tool_call_id: str = "") -> dict | None:
    try:
        with screen.lock():
            decision = policy.decide(tool_name, args if isinstance(args, dict) else {}, screen.get())
        if decision.action == policy.ALLOW:
            return None
        if decision.action == policy.DENY:
            logger.info("reason guard: deny %s (%s)", tool_name, decision.category)
            return {"action": "block", "message": f"BLOCKED by the reason guard: {decision.reason}"}
        why = _why_no_owner_answer()
        if why:
            logger.warning("reason guard: block %s (%s): needs the owner's ok but %s", tool_name, decision.category, why)
            return {"action": "block", "message": f"BLOCKED by the reason guard: this needs the owner's ok "
                                                  f"({decision.reason}), but {why}. Tell the owner instead."}
        logger.info("reason guard: ask %s (%s)", tool_name, decision.category)
        return {"action": "approve", "message": decision.reason,
                "rule_key": f"reason:{tool_call_id or 'call'}:{uuid.uuid4().hex}"}
    except Exception:  # never fail open
        logger.exception("reason guard: error on %s, blocking", tool_name)
        return {"action": "block", "message": "BLOCKED by the reason guard: internal error, the action did not run."}


def observe(tool_name: str, args: object, result: object) -> None:
    """Learn what the screen shows from a browser or phone result. Never raises."""
    try:
        if tool_name.startswith(policy.BROWSER):
            with screen.lock():
                screen.get().saw_browser(tool_name[len(policy.BROWSER):], args if isinstance(args, dict) else {},
                                         screen.texts(result))
        elif tool_name.startswith(policy.PHONE):
            with screen.lock():
                screen.get().saw_phone(tool_name[len(policy.PHONE):], screen.texts(result))
    except Exception:
        logger.exception("reason guard: could not read the result of %s", tool_name)
