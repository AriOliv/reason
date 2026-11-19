"""Integration tests against the real, patched Hermes. They run in the image build (cd /opt/hermes)
and are skipped elsewhere."""

from __future__ import annotations

import asyncio
import importlib.machinery
import json
import importlib.util
import os
import pathlib
import subprocess
import unittest
from unittest import mock

try:
    from gateway.config import Platform
    from gateway.platforms.event import MessageEvent, MessageType, ProcessingOutcome
    from gateway.reason_flow import state
    from gateway.reason_guard import hook as guard_hook, policy as guard_policy, screen as guard_screen
    from gateway.run import GatewayRunner
    from gateway.session import SessionSource
    from plugins.platforms.telegram.adapter import TelegramAdapter
    IN_IMAGE = True
except ImportError:
    IN_IMAGE = False

ON = {"REASON_REACTIONS": "1", "REASON_SPLIT_REPLIES": "1", "REASON_SPLIT_PAUSE": "0", "REASON_FOLLOWUPS": "1",
      "REASON_NATURAL_TYPING": "0"}


class Sent:
    success, error, retryable, raw_response = True, None, False, None

    def __init__(self, message_id):
        self.message_id = message_id


def telegram():
    """A real TelegramAdapter with no network: sends, reactions and typing are recorded."""
    adapter = object.__new__(TelegramAdapter)
    adapter.platform = Platform.TELEGRAM
    adapter.config = type("Cfg", (), {"typing_indicator": True})()
    adapter._pending_messages = {}
    adapter.log = []

    async def _send_with_retry(chat_id, content, reply_to=None, metadata=None, **_):
        adapter.log.append(("send", content, reply_to))
        return Sent(str(len(adapter.log)))

    async def _set_reaction(chat_id, message_id, emoji):
        adapter.log.append(("react", message_id, emoji))
        return True

    adapter._send_with_retry, adapter._set_reaction = _send_with_retry, _set_reaction
    return adapter


def source():
    return SessionSource(platform=Platform.TELEGRAM, chat_id="42", chat_type="dm", user_id="7")


def msg(text, message_id):
    return MessageEvent(text=text, message_type=MessageType.TEXT, source=source(), message_id=message_id)


@unittest.skipUnless(IN_IMAGE, "outside the Hermes image")
@mock.patch.dict(os.environ, ON)
class Patched(unittest.TestCase):
    def setUp(self):
        state.reset()

    def test_turn_hooks_drive_reactions(self):
        adapter, ev = telegram(), msg("thanks", "9")
        asyncio.run(adapter._run_processing_hook("on_processing_start", ev))
        asyncio.run(adapter._run_processing_hook("on_processing_complete", ev, ProcessingOutcome.SUCCESS))
        self.assertEqual(adapter.log, [("react", "9", "👀"), ("react", "9", None)])

    def test_final_send_goes_through_reason_flow(self):
        adapter = telegram()
        adapter._final_delivery_adapter = lambda src: adapter
        adapter._record_delivery_obligation = mock.AsyncMock(return_value=None)
        adapter._finalize_delivery_obligation = mock.AsyncMock()
        ev = msg("find milk", "m1")
        result, used = asyncio.run(adapter.send_final_ledgered(ev, "s", "Found it.\n\nR$ 6,49.", {}, reply_to="m1"))
        self.assertTrue(result.success)
        self.assertEqual(adapter.log, [("send", "Found it.", None), ("send", "R$ 6,49.", None)])

    def test_typing_loop_off_and_gated(self):
        adapter = telegram()
        with mock.patch.dict(os.environ, {"REASON_NATURAL_TYPING": "1"}):
            self.assertIsNone(adapter._start_typing_refresh(msg("hi", "1"), asyncio.Event(), {}))
            self.assertTrue(TelegramAdapter.__dict__.get("_reason_typing_gated"))
            adapter._bot = mock.MagicMock()
            self.assertIsNone(asyncio.run(adapter.send_typing("42")))
            adapter._bot.send_chat_action.assert_not_called()

    def runner(self, adapter, agent):
        runner = object.__new__(GatewayRunner)
        runner.__dict__["_sessions"] = {}
        runner.__dict__["_draining"] = False
        runner._effective_busy_input_mode = lambda src: "queue"
        runner._effective_busy_text_mode = lambda src: "queue"
        runner._delivery_adapter_for = lambda src: adapter
        runner._reply_anchor_for_event = lambda e: e.message_id
        runner._busy_interrupt_and_ack = mock.AsyncMock()
        turn = runner._session_state("s").turn
        turn.agent, turn.event = agent, msg("order snacks", "1")
        return runner

    def test_follow_up_redirects_the_running_turn(self):
        class Agent:
            _supports_active_turn_redirect = True
            got: list = []

            def redirect(self, text):
                self.got.append(text)
                return True

        adapter, agent = telegram(), Agent()
        runner = self.runner(adapter, agent)
        self.assertTrue(asyncio.run(runner._hm_busy_preempt(msg("doritos and water", "2"), source(), "s")))
        self.assertEqual(len(agent.got), 1)
        self.assertIn(("react", "2", "👀"), adapter.log)
        runner._busy_interrupt_and_ack.assert_not_called()  # no text ack, no interrupt

    def test_follow_up_steers_without_redirect(self):
        class Agent:
            got: list = []

            def steer(self, text, ticket=None):
                self.got.append(text)
                return True

        adapter, agent = telegram(), Agent()
        self.assertTrue(asyncio.run(self.runner(adapter, agent)._hm_busy_preempt(msg("and water", "3"), source(), "s")))
        self.assertEqual(len(agent.got), 1)

    def test_follow_up_switch_off_keeps_hermes_queue(self):
        adapter = telegram()
        with mock.patch.dict(os.environ, {"REASON_FOLLOWUPS": "0"}):
            self.assertFalse(asyncio.run(self.runner(adapter, object())._hm_busy_preempt(msg("hi", "4"), source(), "s")))


@unittest.skipUnless(IN_IMAGE, "outside the Hermes image")
class Image(unittest.TestCase):
    def test_bridge_has_react_and_parses(self):
        bridge = pathlib.Path("/opt/hermes/scripts/whatsapp-bridge/bridge.js")
        self.assertIn("app.post('/react'", bridge.read_text())
        self.assertEqual(subprocess.run(["node", "--check", str(bridge)], capture_output=True).returncode, 0)

    def test_bridge_dependencies_and_stamp(self):
        from plugins.platforms.whatsapp.adapter import _file_content_hash
        bridge = pathlib.Path("/opt/hermes/scripts/whatsapp-bridge")
        self.assertTrue((bridge / "node_modules" / "@whiskeysockets" / "baileys").is_dir())
        self.assertEqual((bridge / "node_modules" / ".hermes-pkg-hash").read_text(), _file_content_hash(bridge / "package.json"))

    def seed(self):
        loader = importlib.machinery.SourceFileLoader("reason_seed", "/etc/cont-init.d/005-reason-seed")
        spec = importlib.util.spec_from_loader("reason_seed", loader)
        module = importlib.util.module_from_spec(spec)
        loader.exec_module(module)
        return module

    def test_seed_renders_without_personal_data_in_the_image(self):
        import hermes_yaml as yaml
        seed = self.seed()
        env = {"OWNER_NAME": "Maria", "WHATSAPP_ALLOWED_USERS": "5511999990000", "WHATSAPP_ENABLED": "false",
               "REASON_MODEL_BASE_URL": "https://llm.example/v1"}
        with mock.patch.dict(os.environ, env):
            v = seed.values()
            config, soul = yaml.safe_load(seed.render("config.yaml", v)), seed.render("SOUL.md", v)
        self.assertNotIn("whatsapp", config)  # stripped while WhatsApp is off
        self.assertEqual(config["model"]["api_key"], "${REASON_MODEL_API_KEY}")  # secret not rendered
        self.assertEqual(config["compression"]["threshold_tokens"], 100000)
        self.assertNotIn("phone", config["mcp_servers"])  # no phone configured -> no phone tools
        self.assertIn("a browser)", soul)
        with mock.patch.dict(os.environ, {**env, "REASON_PHONE_MCP_URL": "http://phone:3000/mcp"}):
            v2 = seed.values()
            phone = yaml.safe_load(seed.render("config.yaml", v2))["mcp_servers"]["phone"]
            soul2 = seed.render("SOUL.md", v2)
        self.assertEqual(phone["headers"]["Authorization"], "Bearer ${REASON_PHONE_MCP_TOKEN}")  # token not rendered
        for risky in ("mobile_install_app", "mobile_uninstall_app", "mobile_batch_commands", "mobile_clear_app_data",
                      "mobile_clipboard", "mobile_login_to_cloud_provider", "mobile_set_location"):
            self.assertNotIn(risky, phone["tools"]["include"])
        self.assertIn("an Android phone", soul2)
        self.assertIn("+5511999990000", soul)
        self.assertIn("Maria", soul)
        for template in ("config.yaml", "SOUL.md"):
            self.assertIn("{{", pathlib.Path("/opt/reason/config", template).read_text())  # placeholders, not values


CART = """### Page
- Page URL: https://shop.example/cart
### Snapshot
```yaml
- main [ref=e1]:
  - link "See details" [ref=e3]
  - button "Place order" [ref=e4]
```"""
HUMAN_PRESENT = (None, False, True, True)  # tools.approval._presence(): a gateway owner can answer


@unittest.skipUnless(IN_IMAGE, "outside the Hermes image")
class Guard(unittest.TestCase):
    """The guard inside the real Hermes: the one pre-tool path, the dispatch, the approval rules."""

    def setUp(self):
        guard_screen.reset()

    def directive(self, tool, args, call="c1"):
        from hermes_cli.plugins import _get_pre_tool_call_directive_details
        return _get_pre_tool_call_directive_details(tool, args, session_id="s", tool_call_id=call)

    def ask_context(self, yolo=False, mode="manual", presence=HUMAN_PRESENT):
        return (mock.patch("tools.approval._yolo_active", return_value=yolo),
                mock.patch("tools.approval_context._get_approval_mode", return_value=mode),
                mock.patch("tools.approval._presence", return_value=presence))

    def test_unknown_tools_and_route_arounds_are_blocked(self):
        for tool, args in (("mcp__evil__steal", {}), ("terminal", {"command": "id"}),
                           ("mcp__browser__browser_evaluate", {"function": "() => 1"}), ("skill_manage", {})):
            d = self.directive(tool, args)
            self.assertEqual(d.action, "block", tool)
            self.assertIn("reason guard", d.message)
        self.assertIsNone(self.directive("memory", {"action": "read"}).action)

    def test_purchase_asks_the_owner_once_per_call(self):
        guard_hook.observe("mcp__browser__browser_snapshot", {}, json.dumps({"result": CART}))
        a, b, c = self.ask_context()
        with a, b, c:
            first = self.directive("mcp__browser__browser_click", {"target": "e4", "element": "a link"}, "c1")
            again = self.directive("mcp__browser__browser_click", {"target": "e4", "element": "a link"}, "c1")
            harmless = self.directive("mcp__browser__browser_click", {"target": "e3", "element": "Place order"})
        self.assertEqual(first.action, "approve")
        self.assertIn("Place order", first.message)
        self.assertNotEqual(first.rule_key, again.rule_key)  # "always"/"session" can't pre-approve the next one
        self.assertIsNone(harmless.action)

    def test_asks_are_never_auto_approved(self):
        guard_hook.observe("mcp__browser__browser_snapshot", {}, json.dumps({"result": CART}))
        for ctx, why in ((dict(yolo=True), "yolo"), (dict(mode="off"), "approvals"), (dict(mode="smart"), "approvals"),
                         (dict(presence=(None, False, False, False)), "no owner")):
            a, b, c = self.ask_context(**ctx)
            with a, b, c:
                d = self.directive("mcp__browser__browser_click", {"target": "e4"})
            self.assertEqual(d.action, "block", ctx)
            self.assertIn(why, d.message)

    def test_a_broken_guard_blocks(self):
        with mock.patch.object(guard_policy, "decide", side_effect=RuntimeError("boom")):
            self.assertEqual(self.directive("memory", {}).action, "block")

    def test_a_blocked_call_never_reaches_the_tool(self):
        import model_tools
        with mock.patch.object(model_tools, "_execute_tool") as execute:
            out = model_tools.handle_function_call("mcp__browser__browser_evaluate", {"function": "() => 1"},
                                                   session_id="s", tool_call_id="c9")
        execute.assert_not_called()
        self.assertIn("reason guard", out)

    def test_results_teach_the_guard(self):
        import model_tools
        with mock.patch.object(model_tools, "_execute_tool", return_value=json.dumps({"result": CART})):
            model_tools.handle_function_call("mcp__browser__browser_snapshot", {}, session_id="s", tool_call_id="c2")
        self.assertIn("Place order", guard_screen.get().refs["e4"])

    def test_the_real_tool_list_is_tagged(self):
        import hermes_yaml as yaml
        import model_tools
        seed = Image.seed(self)
        env = {"OWNER_NAME": "Maria", "WHATSAPP_ALLOWED_USERS": "5511999990000", "WHATSAPP_ENABLED": "true",
               "REASON_MODEL_BASE_URL": "https://llm.example/v1", "REASON_PHONE_MCP_URL": "http://phone:3000/mcp"}
        with mock.patch.dict(os.environ, env):
            config = yaml.safe_load(seed.render("config.yaml", seed.values()))
        self.assertEqual(config["approvals"]["mode"], "manual")
        for key in ("cron_mode", "unattended_mode", "single_query_mode"):
            self.assertEqual(config["approvals"][key], "deny")
        for platform in ("hermes-telegram", "hermes-whatsapp"):
            names = model_tools._select_tool_names([platform], config["agent"]["disabled_toolsets"], True)
            self.assertTrue(names)
            for name in names:
                self.assertTrue(guard_policy.known(name), f"{name} is not tagged in reason_guard.policy")
            self.assertFalse({"computer_use", "manage_connections", "terminal", "execute_code"} & names)
        servers = config["mcp_servers"]
        self.assertEqual(sorted(servers["browser"]["tools"]["include"]), guard_policy.BROWSER_TOOLS)
        self.assertEqual(sorted(servers["phone"]["tools"]["include"]), guard_policy.PHONE_TOOLS)


if __name__ == "__main__":
    unittest.main()
