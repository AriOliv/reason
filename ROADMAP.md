# Roadmap

Each phase starts only when the previous gate passes. Durations are estimates.

## Phase 1 · Closed beta (about 6 weeks)

- [ ] Agent image: extract the working prototype (Hermes + human-like chat patches + desktop + Android) into [`agent/`](agent/), with no personal data
- [ ] One agent per person on Kubernetes, created by an API call, sleeping when idle
- [ ] Gateway v0: route WhatsApp and Telegram messages to the right agent by phone number
- [ ] Sign-up site: phone + SMS code, invite links, a "connect your WhatsApp" link
- [ ] Vault v1: logins and addresses, encrypted per person (KMS), read by the agent through one tool
- [ ] Data screen: export and delete everything
- [ ] 10 to 20 people using it

**Gate:** 10 people using it for 2 weeks in a row; cost per active person measured.

## Phase 2 · Product (about 8 weeks)

- [ ] Official WhatsApp Cloud API, one number for everyone
- [ ] Payments: Stripe Link single-use cards and a spend policy
- [ ] The agent's own email address
- [ ] Connectors: Google Workspace and Outlook
- [ ] Residential exit for the agent's browser: from a cloud IP, Cloudflare's "Verify you are human" check keeps looping even after a correct click; from a home IP the same click passes. Route only the sites that need it, to keep the cost low
- [ ] Public v0.1 release

**Gate:** Meta approves the number; first purchase paid with a single-use card.

## Phase 3 · SaaS (about 8 weeks)

- [ ] Plans and billing, priced from the measured cost
- [ ] Android on higher tiers
- [ ] Metrics, alerts and autoscaling
- [ ] Isolation tests between people on every deploy

**Gate:** price covers the cost of an active person; zero leaks in the isolation tests.

## Phase 4 · Network and initiative

- [ ] Agents that talk to the agents of people you trust, with trust levels
- [ ] Proactive messages (flight changed, deadline coming, unanswered invite)
- [ ] Phone calls
