"""Wire reason_flow into Hermes, at image build time.

Each edit inserts a small call into Hermes at one anchor (an exact snippet of the
pinned Hermes source). If an anchor is missing or appears twice, the build fails:
a new Hermes version must be reviewed, never patched blindly. Running it twice is
a no-op.

    base.py  _run_processing_hook   turn start/end -> reactions          (REASON_REACTIONS)
    base.py  _start_typing_refresh  no typing loop, gate send_typing     (REASON_NATURAL_TYPING)
    base.py  final text send        reason_flow.delivery.deliver         (reactions, quotes, split, typing)
    run_inbound.py _hm_busy_preempt follow-up joins the running turn     (REASON_FOLLOWUPS)
    bridge.js                       POST /react for WhatsApp reactions
    plugins.py  pre_tool_call       reason_guard decides first: allow / ask / deny (no switch)
    model_tools.py  after dispatch  reason_guard learns the screen from each result
"""

from __future__ import annotations

import os
import pathlib
import sys
from dataclasses import dataclass

HERMES = pathlib.Path(os.environ.get("REASON_HERMES_ROOT", "/opt/hermes"))
GATEWAY = HERMES / "gateway"
MARK = "reason: patches/apply.py"


@dataclass(frozen=True)
class Edit:
    path: pathlib.Path
    anchor: str
    insert_after: str  # inserted right after the anchor ("" when REPLACE rewrites it)


EDITS = [
    Edit(
        GATEWAY / "platforms" / "base.py",
        '''    async def _run_processing_hook(self, hook_name: str, *args: Any, **kwargs: Any) -> None:
        """Run a lifecycle hook without letting failures break message flow."""
''',
        f'''        # {MARK}: 👀 while working, a meaningful reaction at the end
        if hook_name in ("on_processing_start", "on_processing_complete"):
            from gateway.reason_flow import signals as _reason_signals
            if _reason_signals.active(self):
                try:
                    if hook_name == "on_processing_start":
                        await _reason_signals.turn_started(self, *args)
                    else:
                        await _reason_signals.turn_finished(self, *args)
                except Exception as _reason_error:
                    logger.warning("[%s] reason_flow %s failed: %s", self.name, hook_name, _reason_error)
                return
''',
    ),
    Edit(
        GATEWAY / "platforms" / "base.py",
        '''        if not getattr(self.config, "typing_indicator", True) or getattr(event, "_heartbeat_session_id", None):
            return None
''',
        f'''        # {MARK}: no typing loop; "typing…" only right before each reply message
        from gateway.reason_flow import typing_gate as _reason_typing
        if _reason_typing.active(self):
            _reason_typing.gate(self)
            return None
''',
    ),
    Edit(
        GATEWAY / "platforms" / "base.py",
        '''        result = await delivery_adapter._send_with_retry(
            chat_id=event.source.chat_id, content=text_content, reply_to=reply_to, metadata=metadata)
''',
        "",  # handled by REPLACE: the send itself is swapped
    ),
    Edit(
        GATEWAY / "run_inbound.py",
        '''        adapter = self._delivery_adapter_for(source)
        if (self._draining or adapter is None or running_agent is None or running_agent is _AGENT_PENDING_SENTINEL
''',
        "",  # handled by REPLACE: the insertion has to go between the two anchor lines
    ),
    Edit(
        HERMES / "scripts" / "whatsapp-bridge" / "bridge.js",
        "app.post('/typing', async (req, res) => {\n",
        "",
    ),
    Edit(
        HERMES / "hermes_cli" / "plugins.py",
        '''    from hermes_cli.lifecycle import invoke_hook as invoke_lifecycle_hook
    hook_results = invoke_lifecycle_hook(
        "pre_tool_call", tool_name=tool_name, args=args if isinstance(args, dict) else {},
''',
        "",  # handled by REPLACE: the guard goes before the plugin hooks
    ),
    Edit(
        HERMES / "model_tools.py",
        '''        result = _execute_tool(function_name, function_args, original_args, ids, user_task=user_task,
                               enabled_tools=enabled_tools, skip_tool_execution_middleware=skip_tool_execution_middleware)
''',
        f'''        # {MARK}: the reason guard learns what the screen shows from the result
        from gateway.reason_guard import hook as _reason_guard
        _reason_guard.observe(function_name, function_args, result)
''',
    ),
]

# Edits that must replace (not just follow) their anchor: anchor -> replacement.
REPLACE = {
    EDITS[2].anchor: f'''        # {MARK}: final reply through reason_flow (reaction, quote decision, short messages, typing)
        from gateway.reason_flow import delivery as _reason_delivery
        result = await _reason_delivery.deliver(
            delivery_adapter, chat_id=event.source.chat_id, content=text_content, reply_to=reply_to, metadata=metadata)
''',
    EDITS[3].anchor: f'''        adapter = self._delivery_adapter_for(source)
        # {MARK}: a message that arrives mid-task joins the running turn (redirect, else steer), with 👀
        from gateway.reason_flow import followups as _reason_followups
        if (_reason_followups.active() and not self._draining and adapter is not None
                and running_agent is not None and running_agent is not _AGENT_PENDING_SENTINEL
                and not event.get_command()):
            _reason_outcome = await _reason_followups.join_running_turn(self, event, _quick_key, running_agent)
            note_busy_outcome(event, _reason_outcome)
            await _reason_followups.acknowledge(adapter, event, _reason_outcome)
            return bool(_reason_outcome.steered or _reason_outcome.redirected)
        if (self._draining or adapter is None or running_agent is None or running_agent is _AGENT_PENDING_SENTINEL
''',
    EDITS[5].anchor: f'''    # {MARK}: the reason guard decides first, in code. It fails closed (Hermes treats a
    # failing hook as "allow") and no config or plugin can switch it off.
    try:
        from gateway.reason_guard import hook as _reason_guard
        _reason = _reason_guard.directive(tool_name, args, session_id=session_id, tool_call_id=tool_call_id)
    except Exception:
        _reason = {{"action": "block", "message": "BLOCKED by the reason guard: unavailable, the action did not run."}}
    if _reason is not None:
        if _reason.get("action") == "approve":
            return _PreToolCallDirective(action="approve", message=_reason.get("message"),
                                         rule_key=_reason.get("rule_key"))
        return _PreToolCallDirective(action="block", message=_reason.get("message") or "BLOCKED by the reason guard.")
''' + EDITS[5].anchor,
    EDITS[4].anchor: f"""// {MARK}: native WhatsApp reaction on a received message (empty emoji removes it)
app.post('/react', async (req, res) => {{
  if (!sock || connectionState !== 'connected') {{
    return res.status(503).json({{ error: 'Not connected' }});
  }}
  const {{ chatId, messageId, emoji }} = req.body || {{}};
  if (!chatId || typeof messageId !== 'string' || !messageId || (emoji && String(emoji).length > 16)) {{
    return res.status(400).json({{ error: 'chatId and messageId are required' }});
  }}
  const known = messageStore.get(messageId);
  const key = known?.key || {{ remoteJid: chatId, id: messageId, fromMe: false }};
  try {{
    await sock.sendMessage(key.remoteJid || chatId, {{ react: {{ text: emoji ? String(emoji) : '', key }} }});
    res.json({{ success: true }});
  }} catch (err) {{
    res.status(500).json({{ error: err.message }});
  }}
}});

app.post('/typing', async (req, res) => {{
""",
}


def main() -> int:
    sources = {e.path: e.path.read_text(encoding="utf-8") for e in EDITS}
    already = [p for p, s in sources.items() if MARK in s]
    if len(already) == len(sources):
        print("reason patches: already applied")
        return 0
    if already:
        print("reason patches: half applied (dirty image?)", file=sys.stderr)
        return 1
    for edit in EDITS:
        text = sources[edit.path]
        if text.count(edit.anchor) != 1:
            print(f"reason patches: anchor not found exactly once in {edit.path.name} "
                  f"(Hermes changed?): {edit.anchor.strip()[:70]!r}", file=sys.stderr)
            return 1
        new = REPLACE.get(edit.anchor, edit.anchor + edit.insert_after)
        sources[edit.path] = text.replace(edit.anchor, new, 1)
    for path, text in sources.items():
        path.write_text(text, encoding="utf-8")
    print("reason patches: applied")
    return 0


if __name__ == "__main__":
    sys.exit(main())
