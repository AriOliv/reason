# computer

The agent's computer: a virtual desktop (Xvfb + Openbox) with a **visible Chromium**, driven by [Playwright MCP](https://github.com/microsoft/playwright-mcp) through the DOM and accessibility tree (no pixel guessing), and watched through noVNC.

- **Logins survive restarts:** the browser profile lives on the `/data` volume.
- **Take over when you need to:** open noVNC (`http://127.0.0.1:6080/vnc.html`), sign in somewhere, hand it back.
- **CDP never leaves the container:** Playwright MCP launches Chromium locally; only the MCP endpoint (8931) is reachable, on the agent's internal network. VNC listens on the container's loopback and is reached only through noVNC.
- **Browser policy:** no password manager, no saved cards or addresses, no sign-in or sync, no extensions (`policy.json`).
- The Chromium build comes from the MCP's own Playwright (`npx playwright install chromium`), so its revision always matches. Works on amd64 and arm64.

| Variable | Meaning |
|---|---|
| `COMPUTER_VNC_PASSWORD` | required; the noVNC password |
| `COMPUTER_ALLOWED_HOSTS` | hosts (with port) the MCP accepts; default `computer:8931,localhost:8931,computer,localhost` |

Smoke-tested on arm64: the MCP answers `initialize`, lists 25 tools, and `browser_navigate` to a real page succeeds.
