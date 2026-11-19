"""reason_flow: human-like chat behaviour for the Hermes gateway.

Installed into the Hermes image as ``gateway/reason_flow`` and wired in by
``patches/apply.py`` at build time. Pure standard library at import time, so the
unit tests run outside the image.

Modules
    state       per-chat bookkeeping shared by the others (who said what, in which order)
    signals     reactions on the owner's messages and the decision to quote or not
    typing_gate "typing…" only while the reply is being "typed", sized to its length
    followups   a message that arrives mid-task joins the running task (redirect / steer)
    delivery    the final send: model-chosen reaction, quote decision, split into short messages

Every behaviour has its own switch (``REASON_*`` environment variables, all "1" in the
image) so it can be turned off without a rebuild.
"""

from __future__ import annotations

import os

CHAT_PLATFORMS = frozenset({"telegram", "whatsapp"})


def enabled(name: str) -> bool:
    """``REASON_<NAME>=1`` turns a behaviour on."""
    return os.environ.get(f"REASON_{name}", "") == "1"


def platform_of(adapter: object) -> str:
    platform = getattr(adapter, "platform", None)
    return str(getattr(platform, "value", platform) or "").lower()


def is_chat(adapter: object) -> bool:
    return platform_of(adapter) in CHAT_PLATFORMS
