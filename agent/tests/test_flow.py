"""reason_flow unit tests, standard library only. Run: python3 -m unittest discover -s agent/tests"""

from __future__ import annotations

import asyncio
import os
import pathlib
import sys
import types
import unittest
from unittest import mock

try:  # inside the image, the installed copy
    from gateway import reason_flow  # noqa: F401
    from gateway.reason_flow import delivery, followups, signals, state, typing_gate
except ImportError:  # in the repository
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
    from reason_flow import delivery, followups, signals, state, typing_gate

ON = {"REASON_REACTIONS": "1", "REASON_SPLIT_REPLIES": "1", "REASON_SPLIT_PAUSE": "0", "REASON_FOLLOWUPS": "1"}


def run(coro):
    return asyncio.run(coro)


class Sent:
    def __init__(self, ok=True, message_id="1", error=None):
        self.success, self.message_id, self.error = ok, message_id, error


def chat_adapter(platform="telegram", fail_on=()):
    """A Telegram-like adapter that records sends, reactions and typing."""

    class Adapter:
        def __init__(self):
            self.platform = types.SimpleNamespace(value=platform)
            self.log: list = []

        async def _send_with_retry(self, chat_id, content, reply_to=None, metadata=None):
            self.log.append(("send", content, reply_to))
            n = sum(1 for e in self.log if e[0] == "send")
            return Sent(False, None, "boom") if n in fail_on else Sent(True, str(n))

        async def _set_reaction(self, chat_id, message_id, emoji):
            self.log.append(("react", message_id, emoji))
            return True

        async def send_typing(self, chat_id, metadata=None):
            self.log.append(("typing", chat_id))

    return Adapter()


def event(text, message_id, chat_id="c"):
    return types.SimpleNamespace(text=text, message_id=message_id, source=types.SimpleNamespace(chat_id=chat_id),
                                 media_urls=None)


def sends(adapter):
    return [(e[1], e[2]) for e in adapter.log if e[0] == "send"]


def reactions(adapter):
    return [(e[1], e[2]) for e in adapter.log if e[0] == "react"]


class Split(unittest.TestCase):
    def test_paragraphs_become_messages(self):
        self.assertEqual(delivery.split("Found it.\n\nR$ 6,49.\n\nAdd to cart?"), ["Found it.", "R$ 6,49.", "Add to cart?"])

    def test_code_lists_and_intros_stay_whole(self):
        self.assertEqual(delivery.split("Run:\n\n```\na\n\nb\n```\n\nDone."), ["Run:\n\n```\na\n\nb\n```", "Done."])
        self.assertEqual(delivery.split("Options:\n\n- a\n\n- b"), ["Options:\n\n- a\n\n- b"])

    def test_at_most_five(self):
        parts = delivery.split("\n\n".join(str(i) for i in range(8)))
        self.assertEqual(len(parts), 5)
        self.assertEqual(parts[-1], "4\n\n5\n\n6\n\n7")


class Reactions(unittest.TestCase):
    def test_marker_parsing(self):
        self.assertEqual(signals.split_reaction("[react: ❤️]"), ("❤️", ""))
        self.assertEqual(signals.split_reaction("[reação: 😂] Classic."), ("😂", "Classic."))
        self.assertEqual(signals.split_reaction("Done.\n[react: 👍]"), ("👍", "Done."))
        self.assertEqual(signals.split_reaction("NO_REPLY"), ("👍", ""))
        self.assertEqual(signals.split_reaction("I said [react] here"), (None, "I said [react] here"))

    def test_telegram_only_takes_its_own_set(self):
        self.assertEqual(signals.for_telegram("❤️"), "❤")
        self.assertEqual(signals.for_telegram("😂"), "🤣")
        self.assertIsNone(signals.for_telegram("🦖"))


@mock.patch.dict(os.environ, ON)
class Delivery(unittest.TestCase):
    def setUp(self):
        state.reset()

    def turn(self, adapter, ev, reply):
        run(signals.turn_started(adapter, ev))
        result = run(delivery.deliver(adapter, chat_id="c", content=reply, reply_to=ev.message_id, metadata={}))
        run(signals.turn_finished(adapter, ev))
        return result

    def test_direct_chat_does_not_quote_and_eyes_go_away(self):
        adapter = chat_adapter()
        self.turn(adapter, event("find milk", "m1"), "Found it.\n\nR$ 6,49.")
        self.assertEqual(sends(adapter), [("Found it.", None), ("R$ 6,49.", None)])
        self.assertEqual(reactions(adapter), [("m1", "👀"), ("m1", None)])

    def test_thanks_gets_only_a_reaction(self):
        adapter = chat_adapter()
        result = self.turn(adapter, event("thanks!", "m1"), "[react: ❤️]")
        self.assertTrue(result.success)
        self.assertEqual(sends(adapter), [])
        self.assertEqual(reactions(adapter)[-1], ("m1", "❤"))

    def test_quotes_when_a_newer_message_arrived(self):
        adapter = chat_adapter()
        run(signals.turn_started(adapter, event("weather?", "m1")))
        state.received("c", "m2")  # queued while m1 was running
        run(delivery.deliver(adapter, chat_id="c", content="Sunny.", reply_to="m1", metadata={}))
        self.assertEqual(sends(adapter), [("Sunny.", "m1")])

    def test_no_quote_when_the_newer_message_joined_the_turn(self):
        adapter = chat_adapter()
        run(signals.turn_started(adapter, event("order snacks", "m1")))
        state.received("c", "m2")
        state.chat("c").joined.add("m2")
        run(delivery.deliver(adapter, chat_id="c", content="Doritos and water, done.", reply_to="m1", metadata={}))
        self.assertEqual(sends(adapter), [("Doritos and water, done.", None)])
        run(signals.turn_finished(adapter, event("order snacks", "m1")))
        self.assertEqual(reactions(adapter)[-2:], [("m1", None), ("m2", None)])

    def test_failure_midway_sends_the_rest_together(self):
        adapter = chat_adapter(fail_on=(2,))
        run(delivery.deliver(adapter, chat_id="c", content="a\n\nb\n\nc", reply_to=None, metadata={}))
        self.assertEqual([s[0] for s in sends(adapter)], ["a", "b", "b\n\nc"])

    def test_switches_off(self):
        adapter = chat_adapter()
        with mock.patch.dict(os.environ, {"REASON_REACTIONS": "0", "REASON_SPLIT_REPLIES": "0"}):
            run(delivery.deliver(adapter, chat_id="c", content="[react: 👍] Hi\n\nthere", reply_to="m1", metadata={}))
        self.assertEqual(sends(adapter), [("[react: 👍] Hi\n\nthere", "m1")])
        self.assertEqual(reactions(adapter), [])


@mock.patch.dict(os.environ, {"REASON_NATURAL_TYPING": "1", "REASON_SPLIT_REPLIES": "1"})
class NaturalTyping(unittest.TestCase):
    def test_gated_outside_replies_and_sized_inside(self):
        adapter = chat_adapter("whatsapp")
        typing_gate.gate(adapter)
        run(adapter.send_typing("c"))  # Hermes calling mid-turn
        self.assertEqual(adapter.log, [])
        with mock.patch.object(typing_gate.asyncio, "sleep", new=mock.AsyncMock()) as sleep:
            run(delivery.deliver(adapter, chat_id="c", content="Ok.\n\n" + "x" * 50, reply_to=None, metadata={}))
        self.assertEqual([e[0] for e in adapter.log], ["typing", "send", "typing", "send"])
        self.assertEqual([c.args[0] for c in sleep.await_args_list], [1.0, 1.5])  # floor, then 50 x 30 ms

    def test_long_reply_is_capped(self):
        self.assertEqual(typing_gate.seconds_for("x" * 1000, True), 4.0)
        self.assertEqual(typing_gate.seconds_for("x", False), 0.6)


class Runner:
    def __init__(self, redirected=False, steered=False):
        self.modes: list = []
        self.redirected, self.steered = redirected, steered

    async def _resolve_busy_steer_or_redirect(self, ev, key, mode, agent):
        self.modes.append(mode)
        return types.SimpleNamespace(redirected=self.redirected and mode == "interrupt",
                                     steered=self.steered and mode == "steer")


@mock.patch.dict(os.environ, ON)
class FollowUps(unittest.TestCase):
    def setUp(self):
        state.reset()

    def test_text_tries_redirect_first(self):
        agent = types.SimpleNamespace(_supports_active_turn_redirect=True, redirect=lambda t: True)
        runner = Runner(redirected=True)
        out = run(followups.join_running_turn(runner, event("not yet", "m2"), "s", agent))
        self.assertTrue(out.redirected)
        self.assertEqual(runner.modes, ["interrupt"])

    def test_falls_back_to_steer(self):
        agent = types.SimpleNamespace(_supports_active_turn_redirect=True, redirect=lambda t: False)
        runner = Runner(steered=True)
        out = run(followups.join_running_turn(runner, event("doritos", "m2"), "s", agent))
        self.assertEqual(runner.modes, ["interrupt", "steer"])
        self.assertTrue(out.steered)

    def test_acknowledge_marks_and_joins(self):
        adapter = chat_adapter()
        run(followups.acknowledge(adapter, event("doritos", "m2"), types.SimpleNamespace(steered=True, redirected=False)))
        self.assertEqual(reactions(adapter), [("m2", "👀")])
        self.assertIn("m2", state.chat("c").joined)


if __name__ == "__main__":
    unittest.main()
