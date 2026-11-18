# agent

The per-person agent image. It will be extracted from the working prototype (Phase 1):

- [Hermes Agent](https://github.com/NousResearch/hermes-agent) as the agent loop, pinned by digest;
- human-like chat patches: reactions, natural "typing…", follow-up messages folded into the running task, short replies split into a few messages;
- WhatsApp (Baileys bridge in the beta, Cloud API later) and Telegram;
- voice notes transcribed by any OpenAI-compatible speech-to-text endpoint;
- its own computer: a browser desktop (Cua + Chromium, driven by Playwright MCP) and, on higher tiers, an Android emulator (Redroid + mobile-mcp);
- the "personal agent" posture: sign in with the owner's code, ask "ok" only to spend or speak on their behalf.

Nothing personal or company-specific lives here: the owner's phone, keys and allowlists come from the environment at boot.
