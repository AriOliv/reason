"""What the agent last saw, learned from tool *results*: the source of truth for labels.

The model names an element when it clicks it ("the button"), but that description is its own
words and can be wrong or chosen to look harmless. So the guard never trusts it: it looks the
target up in what the screen actually showed.

Browser (Playwright MCP): every snapshot line ``- button "Place order" [ref=e45]`` maps the ref
to its role, name and the text under it; ``- Page URL:`` gives the page; a ``Modal state``
gives the text of an open dialog. Refs are kept per page and reset when the URL changes or
the browser closes. Playwright MCP returns the snapshot inline only for ``browser_snapshot``
(after a click or navigation it goes to a file in the computer container), so that is where
the guard, like the model, learns the refs.

Phone (mobile-mcp): ``mobile_list_elements_on_screen`` lines ``@e5 Button text="Pay" at=x,y
size=WxH`` map refs and rectangles to labels. A coordinate tap is only judged against a list
taken *after* the last phone action; otherwise the guard asks the agent to list again.
"""

from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field

MAX_LABEL = 400

_NODE = re.compile(r"^(?P<indent>\s*)- (?P<head>.*?)\s*\[ref=(?P<ref>(?:f\d+)?e\d+)\](?P<tail>.*)$")
_LINE = re.compile(r"^(?P<indent>\s*)- (?P<body>.*)$")
_URL = re.compile(r"^- Page URL: (\S+)", re.M)
_DIALOG = re.compile(r'"\w+" dialog with message "(.*)"')
_PHONE_LINE = re.compile(r"^(?P<ref>@e\d+)\s+(?P<rest>.*?)\s+at=(?P<x>-?\d+),(?P<y>-?\d+)\s+size=(?P<w>\d+)x(?P<h>\d+)")
_PHONE_VALUE = re.compile(r'\b(?:text|label|name|id)=("(?:[^"\\]|\\.)*")')


def texts(result: object) -> str:
    """All text inside a tool result (Hermes hands MCP results over as JSON strings)."""
    out: list[str] = []

    def walk(value: object) -> None:
        if isinstance(value, str):
            out.append(value)
        elif isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                walk(v)

    if isinstance(result, str):
        try:
            walk(json.loads(result))
        except (ValueError, TypeError):
            out.append(result)
    else:
        walk(result)
    return "\n".join(out)


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("[cursor=pointer]", "")).strip()[:MAX_LABEL]


def snapshot_refs(text: str) -> dict[str, str]:
    """ref -> label (role, name and the text of its subtree) from a Playwright snapshot."""
    lines = text.splitlines()
    refs: dict[str, str] = {}
    for i, line in enumerate(lines):
        node = _NODE.match(line)
        if not node:
            continue
        indent = len(node["indent"])
        parts = [node["head"], node["tail"].lstrip(":")]
        size = 0
        for child in lines[i + 1:]:
            m = _LINE.match(child)
            if not m or len(m["indent"]) <= indent:
                break
            body = re.sub(r"\[ref=[^\]]*\]", "", m["body"])
            parts.append(body)
            size += len(body)
            if size > MAX_LABEL:
                break
        refs[node["ref"]] = _clean(" ".join(parts))
    return refs


def phone_elements(text: str) -> list[tuple[str, int, int, int, int, str]]:
    """[(ref, x, y, w, h, label)] from a mobile-mcp element list (text or json format)."""
    found: list[tuple[str, int, int, int, int, str]] = []
    marker = "Found these elements on screen: "
    if marker in text:
        try:
            for el in json.loads(text.split(marker, 1)[1]):
                c = el.get("coordinates") or {}
                label = " ".join(str(el.get(k) or "") for k in ("type", "text", "label", "name", "identifier"))
                found.append((str(el.get("ref") or ""), int(c.get("x", 0)), int(c.get("y", 0)),
                              int(c.get("width", 0)), int(c.get("height", 0)), _clean(label)))
        except (ValueError, TypeError, AttributeError):
            pass
        return found
    for line in text.splitlines():
        m = _PHONE_LINE.match(line.strip())
        if not m:
            continue
        values = []
        for raw in _PHONE_VALUE.findall(m["rest"]):
            try:
                values.append(json.loads(raw))
            except ValueError:
                values.append(raw.strip('"'))
        kind = m["rest"].split(" ", 1)[0]
        found.append((m["ref"], int(m["x"]), int(m["y"]), int(m["w"]), int(m["h"]), _clean(" ".join([kind, *values]))))
    return found


@dataclass
class Screen:
    url: str = ""
    refs: dict[str, str] = field(default_factory=dict)
    dialog: str | None = None
    last_typed: str | None = None  # label of the field typed into last: what Enter would submit
    phone_refs: dict[str, str] = field(default_factory=dict)
    phone_boxes: list[tuple[str, int, int, int, int, str]] = field(default_factory=list)
    phone_fresh: bool = False

    # -- learning -------------------------------------------------------------------------
    def saw_browser(self, tool: str, args: dict, text: str) -> None:
        if tool == "browser_type":
            self.last_typed = self.refs.get(str(args.get("target") or ""))
        if tool == "browser_close":
            self.refs.clear()
            self.last_typed = None
        url = _URL.search(text)
        if url and url.group(1) != self.url:
            self.url = url.group(1)
            self.refs.clear()
            self.last_typed = None
        dialog = _DIALOG.search(text)
        if dialog:
            self.dialog = dialog.group(1)
        elif tool == "browser_handle_dialog":
            self.dialog = None
        self.refs.update(snapshot_refs(text))

    def saw_phone(self, tool: str, text: str) -> None:
        if tool == "mobile_list_elements_on_screen":
            boxes = phone_elements(text)
            self.phone_boxes = boxes
            self.phone_refs = {ref: label for ref, *_, label in boxes if ref}
            self.phone_fresh = True
        elif tool not in PHONE_READ_ONLY:
            self.phone_fresh = False  # the screen may have changed: coordinates need a new list

    # -- looking up -----------------------------------------------------------------------
    def phone_label_at(self, x: float, y: float) -> str | None:
        """Label of the smallest listed element containing the point, if the list is fresh."""
        if not self.phone_fresh:
            return None
        hits = [(w * h, label) for _, bx, by, w, h, label in self.phone_boxes
                if bx <= x <= bx + w and by <= y <= by + h]
        return min(hits)[1] if hits else ""


PHONE_READ_ONLY = frozenset({
    "mobile_list_available_devices", "mobile_get_screen_size", "mobile_get_orientation", "mobile_list_apps",
    "mobile_get_foreground_app", "mobile_take_screenshot", "mobile_list_elements_on_screen",
})

# One agent per person, with one browser and one phone: one screen, whatever the session
# (a new session or a compaction must not make the guard forget what is on the screen).
_screen = Screen()
_lock = threading.RLock()


def get() -> Screen:
    return _screen


def lock() -> threading.RLock:
    return _lock


def reset() -> None:
    global _screen
    with _lock:
        _screen = Screen()
