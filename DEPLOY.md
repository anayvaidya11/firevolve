# Deploy Firevolv to Vercel

The **whole app** deploys from the **repo root** as a single Vercel project —
FastAPI backend + the single-page UI, served by one Python **serverless function**
([api/index.py](api/index.py)). It serves both the UI (at `/`) and the JSON API
(`/analyze`, `/label`, `/corpus`, `/reset`, `/health`) from one origin, so the
frontend's same-origin `fetch` calls just work. There is no separate build step
and no second deploy folder — the repo root *is* the deploy unit.

## The layout (everything at repo root)

```
vercel.json          # routes all paths to the function; bundles backend/ + frontend/
requirements.txt     # lean runtime deps (fastapi, pydantic, httpx, numpy)
api/index.py         # Vercel auto-detects /api; imports backend.main:app
backend/  frontend/  # pulled into the function bundle via functions.includeFiles
.vercelignore        # keeps eval/benchmark/tooling out of the upload
```

## ⚠️ #1 thing to get right: Root Directory = repo root

In Vercel → **Settings → Build & Deployment → Root Directory**, leave it
**empty / `./`**. Do **not** set it to a subfolder — the function needs
`backend/` and `frontend/`, which are pulled into the bundle via `includeFiles`
in [vercel.json](vercel.json). Rooting anywhere else cuts them off and the
function crashes with `ModuleNotFoundError: backend`.

## Deploy

**Option A — GitHub integration (recommended, auto-deploys on push):**
1. Vercel dashboard → **Add New → Project → Import** your repo.
2. **Root Directory:** leave empty (repo root). **Framework Preset:** Other.
3. Deploy. Every push to `main` redeploys.

**Option B — CLI:**
```bash
npm i -g vercel
vercel            # from the repo root; first run links the project
vercel --prod
```

## Environment variables (Vercel → Settings → Environment Variables)

The app **boots and detects with zero config** (heuristics only). Add keys to
light up the other layers — same names as [.env.example](.env.example):

| Var | Enables | Without it |
|---|---|---|
| `PIONEER_API_KEY` | Claude judge (Layer 3) | `judge` reports `false`; heuristics still run |
| `PIONEER_GLIGUARD_API_KEY` | GliGuard overt-threat lane (Layer 2) | `gliguard` reports `false` |
| `PIONEER_BASE_URL` | Pioneer endpoint (`https://api.pioneer.ai/v1`) | judge + guard off |
| `PIONEER_JUDGE_MODEL` | `claude-opus-4-8` | judge off |
| `PIONEER_GUARD_MODEL` | `fastino/gliguard-LLMGuardrails-300M` | guard off |
| `ACTIAN_URL`, `ACTIAN_API_KEY` | Persistent vector store | falls back to in-memory (see caveat) |

`.env` is gitignored and is **not** uploaded — configure secrets in Vercel only.

## ⚠️ Caveat: the learning loop needs a persistent store

Vercel serverless functions **don't share in-memory state between invocations**.
The default `FIREVOLV_STORE=memory` corpus resets per request, so the
"label a span → next document catches the same-family attack" demo won't persist
across separate requests on Vercel. **Per-document detection is unaffected** — all
of the injection demos in [DEMO_SCRIPT.md](DEMO_SCRIPT.md) work. To make the
learning loop persist, point it at Actian via the env vars above, or run the
learning-loop demo locally (`uvicorn backend.main:app`).
