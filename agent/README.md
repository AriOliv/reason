# agent

The per-person agent image: [Hermes Agent](https://github.com/NousResearch/hermes-agent) (pinned by digest) plus `reason_flow`, the code that makes it chat like a person.

## What `reason_flow` does

| Behaviour | What the owner sees | Switch |
|---|---|---|
| Reactions | 👀 on their message while the agent works, removed at the end; a real reaction only when it means something (`[react: ❤️]`), and "thanks" gets only a reaction | `REASON_REACTIONS` |
| Quotes | a reply quotes their message only when a newer one arrived in between | `REASON_REACTIONS` |
| Natural typing | no "typing…" during a minute of tool work; "typing…" right before each message, for a time sized to its length | `REASON_NATURAL_TYPING` |
| Follow-ups | "order snacks", then "doritos and water": the second message joins the running task (redirect, else steer) instead of becoming its own turn | `REASON_FOLLOWUPS` |
| Short messages | a reply arrives as up to 5 short messages, never cutting a list, code or a link | `REASON_SPLIT_REPLIES` |

All switches are `1` in the image. WhatsApp reactions need the `POST /react` route that the build adds to Hermes' WhatsApp bridge.

## How it is wired

`patches/apply.py` inserts small calls into Hermes at exact anchors, at build time. If Hermes changes and an anchor is missing, the build fails, so an upgrade is always reviewed. Then the tests run inside the image, against the real patched Hermes:

- `tests/test_flow.py`: the `reason_flow` logic, standard library only (also runs on your laptop: `python3 -m unittest discover -s agent/tests`);
- `tests/test_hermes.py`: the hooks inside the real Hermes (turn hooks, final send, typing gate, follow-ups on the session authority path), the WhatsApp bridge route, and the boot seed.

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

The build applies the patches and runs the 25 tests; a failing test fails the build.

## Next (issue #1)

The computer: the browser desktop and the Android phone, plus a local `compose.yaml` to run the whole agent on one machine.
