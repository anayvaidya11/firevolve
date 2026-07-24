# Firevolv on Vercel (`site/`)

Deploys the **whole app** — FastAPI backend + the single-page UI — as one Vercel
project. The backend runs as a Python **serverless function**
([site/api/index.py](api/index.py)) that serves both the UI (at `/`) and the JSON
API (`/analyze`, `/label`, `/corpus`, `/reset`, `/health`) from one origin, so
the frontend's same-origin `fetch` calls just work.

## How the pieces fit

```
vercel.json          # repo root — builds site/api/index.py, pulls backend/ + frontend/ into the bundle
requirements.txt     # repo root — lean runtime deps (fastapi, pydantic, httpx, numpy)
site/api/index.py    # ASGI entry: imports backend.main:app; @vercel/python serves it
backend/  frontend/  # included in the function bundle via `includeFiles`
```

The Vercel **project root must be the repo root** (the default) — `vercel.json`
uses `includeFiles` to bundle `backend/` and `frontend/`, which sit above this
folder, so setting the root to `site/` would cut them off.

## Deploy

**Option A — GitHub integration (recommended, auto-deploys on push):**
1. In the Vercel dashboard: **Add New → Project → Import** `anayvaidya11/firevolve`.
2. Leave **Root Directory** as the repo root. Framework preset: **Other**.
3. Deploy. Every push to `main` redeploys.

**Option B — CLI:**
```bash
npm i -g vercel
vercel            # from the repo root; first run links the project
vercel --prod
```

## Environment variables (set in Vercel → Settings → Environment Variables)

The app **boots and detects with zero config** (heuristics + retrieval). Add keys
to light up the other layers — same names as [.env.example](../.env.example):

| Var | Enables | Without it |
|---|---|---|
| `PIONEER_API_KEY` | Claude judge + GliGuard (Layer 2/3) | `gliguard`/`judge` report `false`; heuristics still run |
| `ACTIAN_URL`, `ACTIAN_API_KEY` | Persistent vector store | falls back to in-memory (see caveat) |

`.env` is gitignored and is **not** uploaded — configure secrets in Vercel only.

## ⚠️ Caveat: the learning loop needs a persistent store

Vercel serverless functions **don't share in-memory state between invocations**.
The default `store: memory` corpus resets per request, so the "label a span →
next document catches the same-family attack" demo (PRD §11.3) won't persist
across separate requests here. Per-document detection is unaffected. To make the
learning loop work on Vercel, point it at **Actian** (or another persistent
store) via the env vars above.
