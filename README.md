# Relay

FastAPI backend on **Cloudflare Python Workers** that turns Discord and Slack
`/issue` slash commands into Linear issues.

Free to run: Cloudflare Workers free tier (`*.workers.dev`, 100k requests/day),
plus free Discord, Slack, and Linear API usage.

## How it works

```
/issue bug   →  POST /hooks/…  →  (optional Groq rewrite)  →  Linear issueCreate
             ←  "Created ENG-123 — https://…"
```

Adapters are pluggable and enable themselves from config:

| Adapter  | Enabled when                 |
|----------|------------------------------|
| Discord  | `DISCORD_PUBLIC_KEY` set     |
| Slack    | `SLACK_SIGNING_SECRET` set   |

Linear credentials (`LINEAR_API_KEY`, `LINEAR_TEAM_ID`) are always required.

### Unclear message enrichment (Groq)

If `GROQ_API_KEY` is set and the slash-command text looks short or vague
(e.g. `bug`, `fix it`, a 2-word title with no description), Relay calls
[Groq](https://console.groq.com/keys) (free tier, OpenAI-compatible API) to
rewrite a clearer title and description before creating the Linear issue.

- Clear, detailed messages skip Groq (no extra latency).
- If Groq fails or rate-limits, Relay falls back to the original text.
- The Linear description keeps the **original title** for auditability.
- Default model: `llama-3.1-8b-instant` (override with `GROQ_MODEL`).

## Prerequisites

- Python **≥ 3.13**
- [uv](https://docs.astral.sh/uv/)
- Node.js / npm (for Wrangler)
- Cloudflare account (`npx wrangler login`)

## Setup

```bash
cp .env.example .env
# fill in credentials in .env
cp .env .dev.vars          # Wrangler local bindings (same keys)

uv sync
uv run ruff check src tests scripts
uv run mypy src
uv run pytest
uv run pywrangler dev      # http://localhost:8787
```

### `.env` keys

| Variable                 | Required | Used by                          |
|--------------------------|----------|----------------------------------|
| `LINEAR_API_KEY`         | yes      | Worker                           |
| `LINEAR_TEAM_ID`         | yes      | Worker (Linear team UUID)        |
| `DISCORD_PUBLIC_KEY`     | no       | Worker (enables Discord)         |
| `DISCORD_APPLICATION_ID` | no       | `scripts/register_discord.py`    |
| `DISCORD_BOT_TOKEN`      | no       | `scripts/register_discord.py`    |
| `SLACK_SIGNING_SECRET`   | no       | Worker (enables Slack)           |
| `GROQ_API_KEY`           | no       | Worker (enables AI rewrite)      |
| `GROQ_MODEL`             | no       | Worker (default `llama-3.1-8b-instant`) |

Never commit `.env` or `.dev.vars`. Production uses the **same variable names**
via `wrangler secret put` — the Worker reads bindings from `request.scope["env"]`
at request time (not at import, so secrets are not snapshotted into the deploy).

## Deploy

```bash
uv run pywrangler deploy

npx wrangler secret put LINEAR_API_KEY
npx wrangler secret put LINEAR_TEAM_ID
npx wrangler secret put DISCORD_PUBLIC_KEY      # if using Discord
npx wrangler secret put SLACK_SIGNING_SECRET   # if using Slack
npx wrangler secret put GROQ_API_KEY           # if using enrichment
```

Wrangler prints a URL like `https://relay.<account>.workers.dev`.

## Connect Discord

1. Create an application at [Discord Developer Portal](https://discord.com/developers/applications).
2. Copy the **Public Key** → `DISCORD_PUBLIC_KEY`.
3. Set **Interactions Endpoint URL** to `https://<your-worker>/hooks/discord`.
4. Create a Bot, copy the token → `DISCORD_BOT_TOKEN`, and note the Application ID.
5. Register the slash command (local, once):

   ```bash
   uv run python scripts/register_discord.py
   ```

6. Invite the bot to your server (OAuth2 → `applications.commands` scope).

Usage: `/issue title:Fix login description:users cannot SSO`

## Connect Slack

1. Create a Slack app at [api.slack.com/apps](https://api.slack.com/apps).
2. Add a Slash Command `/issue` with Request URL `https://<your-worker>/hooks/slack`.
3. Copy **Signing Secret** → `SLACK_SIGNING_SECRET`.
4. Install the app to your workspace.

Usage:

```
/issue Fix login
/issue Fix login | users cannot SSO
```

## Connect Linear

1. Linear → Settings → API → create a Personal API key → `LINEAR_API_KEY`.
2. Open your team → copy the team UUID → `LINEAR_TEAM_ID`
   (or query teams via the GraphQL API explorer).

## Project layout

```
src/relay/
  main.py           # create_app() + Workers ASGI entrypoint
  config.py         # pydantic-settings Settings
  deps.py           # FastAPI Depends (settings, Linear client)
  crypto.py         # Discord Ed25519 (Web Crypto) + Slack HMAC
  enrich.py         # Groq rewrite for short/unclear drafts
  api/              # routers
  adapters/         # Discord + Slack (ChatAdapter protocol)
  linear/           # GraphQL issueCreate client
scripts/
  register_discord.py
```

## Slash command reply

On success the chat gets something like:

`Created ENG-123 — https://linear.app/...`

The Linear issue description includes source, author, and channel for traceability.
