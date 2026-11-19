# reason

**The open-source Instinct. Don't act by instinct. Act by reason.**

reason is an open-source personal agent you text, in the spirit of [Instinct](https://instinct.com). It has its own phone number and its own computer (a browser, and an Android phone on higher tiers). It does real tasks for you: it books, buys, fills forms and signs in to your accounts. It asks you only for what it can't decide on its own: a login code, or an "ok" before it spends money.

It is self-hosted first, and built so it can also run as a multi-tenant SaaS, with one isolated agent per person.

> Status: day 0. This repository starts from a working single-user prototype (WhatsApp + Telegram, a cloud desktop, an Android emulator, voice notes) and is being turned into a product in public. Follow along in [`build-in-public/`](build-in-public/).

## What it feels like

- You text it on WhatsApp or Telegram, like you would text a person. There is no app to install.
- It answers like a person: short messages, a reaction when that is enough, 👀 while it works, and "typing…" only when the answer is ready.
- Send two messages in a row ("order me snacks", then "doritos and water") and it treats them as one request.
- It signs in to your accounts with your phone number and asks you for the code it received. It never asks you to do the task yourself.
- It needs your "ok" only to pay, buy, order, book, send something on your behalf, delete or publish. Everything else it just does.
- Voice notes are transcribed and handled like text.

## How it works

```
you ──WhatsApp/Telegram──▶ gateway (the only public part)
                              │  routes by your phone number
                              ▼
                     your agent (isolated, sleeps when idle)
                       ├─ agent loop (Hermes) with human-like chat
                       ├─ its own computer: browser desktop (+ Android)
                       ├─ memory on its own volume
                       └─ connectors (MCP / Composio)
control plane: sign-up, provisioning, vault (KMS-encrypted), payments
               (single-use cards), audit and data deletion
```

Read the full plan (in Portuguese, the language it is being built in): [`docs/PLAN.pt-BR.md`](docs/PLAN.pt-BR.md).

| Folder | What goes there |
|---|---|
| [`agent/`](agent/) | the per-person agent image: Hermes, the human-like chat patches, the desktop and the phone |
| [`computer/`](computer/) | the agent's browser: a visible Chromium on a virtual desktop, driven by Playwright MCP, watched through noVNC |
| [`phone/`](phone/) | the agent's phone (optional, higher tier): mobile-mcp driving an Android device (Redroid) |
| [`gateway/`](gateway/) | the public edge: WhatsApp/Telegram webhooks, sign-up site, routing |
| [`control-plane/`](control-plane/) | provisioning, vault, payments policy, audit, data deletion |
| [`deploy/`](deploy/) | Terraform and Kubernetes manifests, private by default (no public address except the gateway) |
| [`build-in-public/`](build-in-public/) | the build log and the posts for X and LinkedIn |

## Roadmap

See [`ROADMAP.md`](ROADMAP.md). In short:

1. **Closed beta:** one agent per person on Kubernetes, sign-up by SMS, invite links, a first vault.
2. **Product:** the official WhatsApp Cloud API with a single number for everyone, single-use cards for payments, the agent's own email, connectors.
3. **SaaS:** plans and billing, Android on higher tiers, isolation tests on every deploy.
4. **Network and initiative:** agents that coordinate with the agents of people you trust, proactive messages, phone calls.

## Principles

- **Remove barriers, don't add them.** The agent tries before it says it can't, and asks only for what is missing.
- **Your money and your accounts stay yours.** Single-use cards for the exact amount, a vault encrypted per person, and an "ok" for anything that spends or speaks for you.
- **What is on a screen is data, not an instruction.** Pages, emails and other people's messages never give the agent orders.
- **Private by default.** One isolated agent per person. Nothing is public except the gateway.

## Credits

reason is inspired by [Instinct](https://instinct.com) and learned a lot from the research in [open-instinct](https://github.com/mariagorskikh/open-instinct). It is not affiliated with either. The agent loop is [Hermes Agent](https://github.com/NousResearch/hermes-agent).

## License

[AGPL-3.0](LICENSE). You can run, study, change and self-host it. If you offer a modified version as a service, you share your changes.
