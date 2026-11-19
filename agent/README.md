# agent

The per-person agent image: [Hermes Agent](https://github.com/NousResearch/hermes-agent) (pinned by digest) plus `reason_flow`, the code that makes it chat like a person, and `reason_guard`, the safety rules in code.

## What `reason_flow` does

| Behaviour | What the owner sees | Switch |
|---|---|---|
| Reactions | 👀 on their message while the agent works, removed at the end; a real reaction only when it means something (`[react: ❤️]`), and "thanks" gets only a reaction | `REASON_REACTIONS` |
| Quotes | a reply quotes their message only when a newer one arrived in between | `REASON_REACTIONS` |
| Natural typing | no "typing…" during a minute of tool work; "typing…" right before each message, for a time sized to its length | `REASON_NATURAL_TYPING` |
| Follow-ups | "order snacks", then "doritos and water": the second message joins the running task (redirect, else steer) instead of becoming its own turn | `REASON_FOLLOWUPS` |
| Short messages | a reply arrives as up to 5 short messages, never cutting a list, code or a link | `REASON_SPLIT_REPLIES` |

All switches are `1` in the image. WhatsApp reactions need the `POST /react` route that the build adds to Hermes' WhatsApp bridge.

## What `reason_guard` does

A guard outside the model decides every tool call before it runs: **allow**, **ask** the owner, or **deny**. It is wired into the one place every Hermes tool call passes through, ahead of any plugin, and it has no switch.

| Call | Decision |
|---|---|
| reading, navigating, typing, filling a form, everyday clicks | allow |
| a click, tap, drag, Enter or dialog "OK" that **buys, sends, publishes or deletes** | ask the owner, for this call only |
| running JavaScript in the page, raw key events, file upload, page-provided tools, rewriting its own skills | deny |
| a click whose target is not a ref from the latest screen | deny, with "take a snapshot first" |
| any tool not in the closed list | deny |

How it judges a click: by what the **screen** shows, never by the model's words. The guard reads the label of the target from the last browser snapshot (`button "Place order" [ref=e4]`, or the text inside a nameless button) or from the phone's element list. If the model calls it "a harmless link", the guard still sees "Place order". Labels are matched in Portuguese, English and Spanish. Signing in stays free: "Enviar código" or "Send code" are not "send". Buying and deleting are never exempted.

What Hermes would allow and the guard refuses:

- a guard error blocks the call (Hermes treats a failing hook as "allow");
- an "ask" is never auto-approved: with `/yolo`, approvals off or "smart", or nobody to answer (cron), the call is blocked;
- an "ok" never carries over: each approval has its own key, so "always" on the card cannot pre-approve the next purchase.

Known limits, for the next issues: on WhatsApp the ask arrives as Hermes' text prompt (`/approve`), and a natural "ok" bound to the exact call is #9; Enter on the phone is not judged (taps are); clicking a large container that holds a "Pay" button asks too (on purpose).

## How it is wired

`patches/apply.py` inserts small calls into Hermes at exact anchors, at build time. If Hermes changes and an anchor is missing, the build fails, so an upgrade is always reviewed. Then the tests run inside the image, against the real patched Hermes:

- `tests/test_flow.py`: the `reason_flow` logic, standard library only (also runs on your laptop: `python3 -m unittest discover -s agent/tests`);
- `tests/test_guard.py`: the guard's rules, standard library only (also runs on your laptop);
- `tests/test_hermes.py`: the hooks inside the real Hermes (turn hooks, final send, typing gate, follow-ups on the session authority path, the guard on the pre-tool path and in the dispatch, the approval rules, every real tool tagged), the WhatsApp bridge route, and the boot seed.

## Configuration

Nothing personal is in this folder. At boot, `cont-init.d/005-reason-seed` renders `config/config.yaml` and `config/SOUL.md` into the agent's volume from the environment:

| Variable | Meaning |
|---|---|
| `OWNER_NAME`, `OWNER_PHONE` | who the agent works for (the phone defaults to the first WhatsApp allowed number) |
| `REASON_MODEL`, `REASON_MODEL_BASE_URL`, `REASON_MODEL_API_KEY` | any OpenAI-compatible endpoint (the key is expanded by Hermes at runtime, never written to disk) |
| `REASON_STT_MODEL`, `REASON_LANGUAGE` | voice-note transcription model and the reply language (`pt`, `en`, `es`) |
| `REASON_BROWSER_MCP_URL` | the browser MCP the agent drives |
| `WHATSAPP_ENABLED`, `WHATSAPP_ALLOWED_USERS`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_ALLOWED_USERS` | channels and who may talk to the agent |

## Build

```bash
docker build -t reason-agent agent/
```

The build applies the patches and runs the 52 tests; a failing test fails the build.

## Next

Approvals in the chat: the owner answers "ok" in the conversation, bound to the exact call (#9).
