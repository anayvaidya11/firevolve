# Firevolv — Dev Setup & Secrets

## Secrets

Real dev keys live in **`.env`** (git-ignored — never commit it).
The committed template is **`.env.example`**. New teammate:

```bash
cp .env.example .env   # then paste the shared keys into .env
```

Load in Python with `pydantic-settings` (reads `.env` automatically) or `python-dotenv`.

### Keys currently stored in `.env`
| Var | Purpose | Notes |
|---|---|---|
| `PIONEER_API_KEY` | Claude judge + embeddings | Pioneer *personal* key (`..._t1g3r_...`) |
| `PIONEER_GLIGUARD_API_KEY` | GliGuard guard-model calls | Pioneer *GliGuard* key (`..._w0lf_...`) |
| `ACTIAN_URL` / `ACTIAN_API_KEY` | Vector store | **TODO — not yet provided** |

> ⚠️ These are shared hackathon keys. Treat as sensitive: don't paste into
> Slack/screenshots, don't hardcode in source, rotate after the event.

### Confirmed against the live Pioneer API (2026-07-24)
- `PIONEER_BASE_URL=https://api.pioneer.ai/v1` — OpenAI-compatible (`/chat/completions`,
  `/embeddings`) **and** Anthropic-compatible (`/messages`). Auth: `Authorization: Bearer <key>`.
- `PIONEER_JUDGE_MODEL=claude-opus-4-8` — confirmed via `GET /v1/models` (best available Opus).
- **Inference needs a billing plan.** The key authenticates and `GET /v1/models` works, but
  every inference call currently returns `card_required` → subscribe to Hobby/Pro at
  https://agent.pioneer.ai/billing. Until then the judge + GliGuard are gracefully degraded
  (heuristics + retrieval carry detection; the app, learning loop, and F1 chart all work).
  Enable billing and restart the server to activate the Claude judge.
- No embeddings model is exposed yet → the app uses a local deterministic embedding by default.

---

## Two different tools, both named `guild` — don't mix them up

Firevolv touches **two unrelated products that share the `guild` command**:

| | What it is | Used for | Version here |
|---|---|---|---|
| **Guild.ai agent CLI** | Agent build/deploy platform (`guild agent`, `guild chat`, `guild mcp`) | Coding-agent tooling — the `.claude/skills/*` + `.mcp.json` | `0.17.0` (Homebrew/npm) |
| **Guild AI (guildai)** | Python ML experiment tracker (`guild run`, `guild compare`) | **The eval harness / F1 chart** — `eval/guild.yml` | `0.9.0` (conda env) |

They collide on `PATH`: the agent CLI usually wins, and it has **no `run`/`compare`**.
So the eval harness must be invoked by the guildai binary's **absolute path**, not
plain `guild` — see the eval-harness section below.

## Guild.ai agent CLI (coding-agent tooling — NOT the eval harness)

Requires **Node.js 18+ and npm**.

```bash
# 1. Install the CLI globally
npm i @guildai/cli -g

# 2. Authenticate (opens browser, configures local npm registry for Guild packages)
guild auth login

# 3. Verify you're signed in
guild auth status

# 4. Set up your coding agent — adds SDK reference + CLI workflow docs to
#    .claude/skills/ so Claude Code / Codex understand Guild
guild setup
```

Full walkthrough: Guild getting-started guide (linked from the install dialog).

> Note: the `guild setup` step writes agent docs into `.claude/skills/` — after
> running it, the coding agent will have Guild's SDK reference available locally.

## Guild AI eval harness (the F1 chart — separate tool)

This is **guildai 0.9.0**, not the agent CLI above. It needs Python 3.11 (it
imports the removed `imp` module), so it lives in its own conda env:

```bash
./eval/setup_guild_env.sh                 # creates conda env `guild`, prints $GUILD
# The script prints the guildai binary's absolute path. Use it directly —
# plain `guild` on PATH resolves to the agent CLI, which has no `run`/`compare`:
GUILD=/opt/anaconda3/envs/guild/bin/guild   # (whatever setup printed)
cd eval
"$GUILD" run bench corpus_version=v0        # or v1 / v2
"$GUILD" compare                            # F1-over-versions table
```

---

## Actian

_TODO — connection details pending. Once provided, fill `ACTIAN_URL` and
`ACTIAN_API_KEY` in `.env` and document the collection setup / client install here._

---

## Quick start (once backend exists)

```bash
python -m venv .venv && source .venv/bin/activate
pip install fastapi uvicorn pydantic-settings python-dotenv httpx sentence-transformers
uvicorn backend.main:app --reload    # http://localhost:8000
```
