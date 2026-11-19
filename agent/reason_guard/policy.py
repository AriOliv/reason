"""Every tool the agent has, tagged, and the decision for one call: allow, ask or deny.

- **allow**: reading, navigating, typing, everyday clicks. Most calls.
- **ask**: the action spends money, speaks for the owner, publishes or deletes. The owner's
  "ok" is required for *this* call, and it applies to the owner too: there is no
  "the owner is always yes".
- **deny**: tools that would route around the guard (arbitrary page JavaScript, raw key
  events, files), tools the product does not use yet, any tool not in this table, and clicks
  the guard cannot judge (a target that is not a ref from the latest screen).

Closed list: a new tool (a Hermes upgrade, a new MCP server) is denied until it is tagged
here, and the image tests fail the build if the agent's real tool list has an untagged tool.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from urllib.parse import urlsplit

from . import labels
from .screen import Screen

ALLOW, ASK, DENY = "allow", "ask", "deny"

BROWSER = "mcp__browser__"
PHONE = "mcp__phone__"


@dataclass(frozen=True)
class Decision:
    action: str
    reason: str = ""
    category: str = ""  # purchase / send / publish / delete for ASK; the tool's tag otherwise


def _allow(tag: str) -> Decision:
    return Decision(ALLOW, category=tag)


def _deny(reason: str, tag: str = "denied") -> Decision:
    return Decision(DENY, reason, tag)


# -- built-in Hermes tools left on by config.yaml -------------------------------------------
BUILTIN: dict[str, Decision] = {
    "clarify": _allow("ask_owner"),
    "memory": _allow("memory"),
    "session_search": _allow("memory"),
    "skills_list": _allow("read"),
    "skill_view": _allow("read"),
    "skill_manage": _deny("The agent does not rewrite its own skills.", "self_modify"),
    "computer_use": _deny("Use the browser tools (mcp__browser__*) instead.", "computer"),
    "manage_connections": _deny("Connectors are not enabled for this agent yet.", "connectors"),
}

# -- browser (Playwright MCP) -----------------------------------------------------------------
BROWSER_READ = {
    "browser_snapshot", "browser_take_screenshot", "browser_find", "browser_wait_for", "browser_resize",
    "browser_close", "browser_navigate_back", "browser_hover",
}
BROWSER_TARGETED = {"browser_click", "browser_select_option", "browser_type", "browser_drag", "browser_fill_form"}
BROWSER_OTHER = {"browser_navigate", "browser_tabs", "browser_press_key", "browser_handle_dialog"}
BROWSER_DENIED = {
    "browser_evaluate": "Running JavaScript in the page is not allowed: use snapshot, click and type.",
    "browser_run_code_unsafe": "Running code in the browser is not allowed: use snapshot, click and type.",
    "browser_keydown": "Raw key events are not allowed: use browser_press_key or browser_type.",
    "browser_keyup": "Raw key events are not allowed: use browser_press_key or browser_type.",
    "browser_press_sequentially": "Use browser_type on a ref from the latest snapshot.",
    "browser_file_upload": "Uploading files is not enabled for this agent yet.",
    "browser_drop": "Dropping files or data on a page is not enabled for this agent yet.",
    "browser_webmcp_call": "Page-provided tools are not allowed.",
}
# What the agent's browser exposes (config.yaml mcp_servers.browser.tools.include).
BROWSER_TOOLS = sorted(BROWSER_READ | BROWSER_TARGETED | BROWSER_OTHER)

# -- phone (mobile-mcp) -------------------------------------------------------------------------
PHONE_ALLOWED = {
    "mobile_list_available_devices", "mobile_get_screen_size", "mobile_get_orientation", "mobile_set_orientation",
    "mobile_list_apps", "mobile_launch_app", "mobile_terminate_app", "mobile_get_foreground_app",
    "mobile_list_elements_on_screen", "mobile_take_screenshot", "mobile_swipe_on_screen", "mobile_type_keys",
    "mobile_press_button",
}
PHONE_TARGETED = {"mobile_click_on_screen_at_coordinates", "mobile_double_tap_on_screen",
                  "mobile_long_press_on_screen_at_coordinates", "mobile_drag_on_screen"}
PHONE_OTHER = {"mobile_open_url"}
PHONE_TOOLS = sorted(PHONE_ALLOWED | PHONE_TARGETED | PHONE_OTHER)

# Pages where pressing Enter commits a payment, and where "send"/"submit" only signs in.
_PAY_PAGE = re.compile(r"checkout|payment|pagamento|pagar|billing|/pay\b|/order/confirm|finalizar", re.I)
_LOGIN_PAGE = re.compile(r"login|signin|sign-in|sign_in|auth|verify|verification|otp|entrar|acesso|account/access", re.I)
# Text boxes where Enter sends what was typed.
_COMPOSER = labels._pattern((
    "mensagem", "message", "mensaje", "reply", "responder", "comentario", "comment", "post", "tweet",
    "whats happening", "o que esta acontecendo", "que esta pasando", "chat", "escreva", "write", "compose",
))
_REF = re.compile(r"^(?:f\d+)?e\d+$")
_PHONE_REF = re.compile(r"^@e\d+$")


def _language() -> str:
    return (os.environ.get("REASON_LANGUAGE") or "pt").split("-")[0].lower()


def _ask(category: str, label: str, where: str = "") -> Decision:
    text = f"{labels.verb(category, _language())}: “{label[:120]}”"
    return Decision(ASK, text + (f" ({where})" if where else ""), category)


def _host(url: str) -> str:
    try:
        return urlsplit(url).hostname or ""
    except ValueError:
        return ""


def _web_url_ok(url: str) -> bool:
    if not url or url == "about:blank":
        return True
    try:
        return urlsplit(url.strip()).scheme.lower() in ("http", "https")
    except ValueError:
        return False


def _judge_label(label: str, screen_url: str, where: str) -> Decision | None:
    category = labels.classify(label)
    if category is None:
        return None
    if category == "send" and _LOGIN_PAGE.search(screen_url or ""):
        return None  # "Enviar" / "Submit" on a sign-in page sends the login, not a message
    return _ask(category, label, where)


def _browser(tool: str, args: dict, screen: Screen) -> Decision:
    if tool in BROWSER_DENIED:
        return _deny(BROWSER_DENIED[tool])
    if tool in BROWSER_READ:
        return _allow("browse")
    host = _host(screen.url)
    if tool == "browser_navigate":
        url = str(args.get("url") or "")
        return _allow("browse") if _web_url_ok(url) else _deny("Only http(s) pages can be opened.")
    if tool == "browser_tabs":
        url = str(args.get("url") or "")
        return _allow("browse") if _web_url_ok(url) else _deny("Only http(s) pages can be opened.")
    if tool == "browser_press_key":
        if str(args.get("key") or "").lower() not in ("enter", "numpadenter"):
            return _allow("input")
        return _enter(screen, screen.last_typed, host)
    if tool == "browser_handle_dialog":
        if not args.get("accept"):
            return _allow("input")
        if screen.dialog is None:
            return _deny("No dialog text is known: take a snapshot first, then handle the dialog.")
        return _judge_label(screen.dialog, screen.url, host) or _allow("input")
    if tool not in BROWSER_TARGETED:
        return _deny(f"The browser tool {tool} is not enabled for this agent.")

    if tool == "browser_fill_form":
        targets = [str((f or {}).get("target") or "") for f in (args.get("fields") or []) if isinstance(f, dict)]
    elif tool == "browser_drag":
        targets = [str(args.get("startTarget") or ""), str(args.get("endTarget") or "")]
    else:
        targets = [str(args.get("target") or "")]
    if not targets:
        return _deny("No target given.")
    found = []
    for target in targets:
        if not _REF.match(target):
            return _deny("Target elements by their ref from the latest browser_snapshot (e.g. e12), not by selector.")
        label = screen.refs.get(target)
        if label is None:
            return _deny(f"Ref {target} is not in the latest snapshot: take a browser_snapshot, then use its refs.")
        found.append(label)

    if tool == "browser_type":
        if args.get("submit"):
            return _enter(screen, found[0], host)
        return _allow("input")
    if tool in ("browser_fill_form", "browser_select_option"):
        return _allow("input")  # filling is not committing; the click or Enter that submits is judged
    for label in found:  # click, drag
        decision = _judge_label(label, screen.url, host)
        if decision:
            return decision
    return _allow("input")


def _enter(screen: Screen, label: str | None, where: str) -> Decision:
    """Enter submits: a payment page, a message box or a risky field asks; search and sign-in don't."""
    if _PAY_PAGE.search(screen.url or ""):
        return _ask("purchase", label or "Enter", where)
    if label:
        decision = _judge_label(label, screen.url, where)
        if decision:
            return decision
        if _COMPOSER.search(labels.normalize(label)) and not _LOGIN_PAGE.search(screen.url or ""):
            return _ask("send", label, where)
    return _allow("input")


def _phone(tool: str, args: dict, screen: Screen) -> Decision:
    if tool in PHONE_ALLOWED:
        return _allow("phone")
    if tool == "mobile_open_url":
        url = str(args.get("url") or "")
        return _allow("phone") if url.lower().startswith(("http://", "https://")) else _deny(
            "Only http(s) links can be opened on the phone.")
    if tool not in PHONE_TARGETED:
        return _deny(f"The phone tool {tool} is not enabled for this agent.")
    if tool == "mobile_drag_on_screen":
        ref, x, y = args.get("fromRef"), args.get("x1"), args.get("y1")
    else:
        ref, x, y = args.get("ref"), args.get("x"), args.get("y")
    if ref is not None:
        if not _PHONE_REF.match(str(ref)) or str(ref) not in screen.phone_refs:
            return _deny(f"Ref {ref} is not in the latest element list: call mobile_list_elements_on_screen first.")
        label = screen.phone_refs[str(ref)]
    else:
        try:
            label = screen.phone_label_at(float(x), float(y))
        except (TypeError, ValueError):
            return _deny("Give a ref from mobile_list_elements_on_screen, or x and y.")
        if label is None:
            return _deny("The screen may have changed: call mobile_list_elements_on_screen, then tap by ref.")
        if label == "":
            return _deny("Nothing listed at that point: tap a listed element by its ref. If what you need is not "
                         "listed, tell the owner what you are trying to do.")
    return _judge_label(label, "", "") or _allow("phone")


def decide(tool: str, args: dict | None, screen: Screen) -> Decision:
    """The decision for one tool call. Pure: no Hermes, no I/O."""
    args = args if isinstance(args, dict) else {}
    if tool in BUILTIN:
        return BUILTIN[tool]
    if tool.startswith(BROWSER):
        return _browser(tool[len(BROWSER):], args, screen)
    if tool.startswith(PHONE):
        return _phone(tool[len(PHONE):], args, screen)
    return _deny(f"The tool {tool} is not on this agent's list.", "unknown")


def known(tool: str) -> bool:
    """Whether the closed list tags this tool (used by the image test on the real tool list)."""
    if tool in BUILTIN:
        return True
    if tool.startswith(BROWSER):
        name = tool[len(BROWSER):]
        return name in BROWSER_TOOLS or name in BROWSER_DENIED
    if tool.startswith(PHONE):
        return tool[len(PHONE):] in PHONE_TOOLS
    return False
