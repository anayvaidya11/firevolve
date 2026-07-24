"""
Firevolv FastAPI app (PRD §7). One process, JSON everywhere, CORS open for the
local frontend. Serves the single-page UI from /.

/analyze pipeline: retrieve top-k labeled examples -> run heuristics +
GliGuard + judge (the two API calls fire concurrently) -> retrieval detector
-> router -> AnalysisResult. Degrade gracefully; never fail open.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from .config import get_settings
from .embeddings import embed_one
from .heuristics import run_heuristics
from .memory import LabelRecord, get_store
from .pioneer import call_gliguard, call_judge, judge_spans_to_candidates
from .retrieval import detect_by_retrieval, retrieve_examples
from .router import route
from .schemas import (
    DEFAULT_PROFILE,
    AnalysisResult,
    AnalyzeRequest,
    LabelRequest,
)

app = FastAPI(title="Firevolv", version="1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


def _corpus_version() -> int:
    c = get_store().count()
    return int(c.get("injection", 0) + c.get("benign", 0))


def _context_window(text: str, start: int, end: int, radius: int = 200) -> str:
    lo = max(0, start - radius)
    hi = min(len(text), end + radius)
    return text[lo:hi]


@app.get("/health")
def health() -> dict:
    s = get_settings()
    return {
        "ok": True,
        "layers": {
            "heuristic": True,
            "gliguard": s.guard_enabled,
            "judge": s.judge_enabled,
        },
        "store": s.firevolv_store,
        "corpus_version": _corpus_version(),
    }


@app.get("/corpus")
def corpus() -> dict:
    counts = get_store().count()
    return {
        "version": _corpus_version(),
        "counts": {
            "injection": int(counts.get("injection", 0)),
            "benign": int(counts.get("benign", 0)),
        },
    }


@app.post("/reset")
def reset() -> dict:
    get_store().reset()
    return {"ok": True, "version": 0, "counts": {"injection": 0, "benign": 0}}


@app.post("/analyze", response_model=AnalysisResult)
async def analyze(req: AnalyzeRequest) -> AnalysisResult:
    t0 = time.perf_counter()
    text = req.text or ""
    profile = req.profile or DEFAULT_PROFILE
    doc_id = str(uuid.uuid4())
    store = get_store()
    s = get_settings()
    corpus_version = _corpus_version()

    # Retrieval of labeled few-shot examples (local embed -> fast).
    examples = retrieve_examples(store, text, s.retrieval_k) if text.strip() else []

    # Layer 1 (instant) + fire judge & guard concurrently.
    heur_spans = run_heuristics(text)
    judge_result, guard_spans = await asyncio.gather(
        asyncio.to_thread(call_judge, text, profile, examples),
        asyncio.to_thread(call_gliguard, text),
    )

    candidates = list(heur_spans) + list(guard_spans)
    if judge_result.output is not None:
        candidates += judge_spans_to_candidates(text, judge_result.output)

    # Retrieval-as-detector (also calibrates existing candidates in place).
    candidates += detect_by_retrieval(store, text, candidates)

    # Fail closed only when the judge was expected to work but errored/tripped.
    judge_ran = judge_result.available
    tripwire = judge_result.tripwire
    force_uncertain = tripwire or (
        s.judge_enabled and not judge_ran and not judge_result.degraded
    )

    layers = {
        "heuristic": True,
        "gliguard": bool(guard_spans) or (s.guard_enabled and not judge_result.degraded),
        "judge": judge_ran,
    }

    latency_ms = int((time.perf_counter() - t0) * 1000)
    return route(
        doc_id=doc_id,
        candidates=candidates,
        retrieved_examples=examples,
        tripwire=tripwire,
        force_uncertain=force_uncertain,
        layers=layers,
        corpus_version=corpus_version,
        latency_ms=latency_ms,
    )


@app.post("/label")
def label(req: LabelRequest) -> dict:
    store = get_store()
    inserted = 0
    for sp in req.spans:
        ctx = sp.context_window
        if not ctx and req.text:
            ctx = _context_window(req.text, sp.start, sp.end)
        if not ctx:
            ctx = sp.quote
        vector = embed_one(ctx)
        store.insert(LabelRecord(
            vector=vector,
            quote=sp.quote,
            context_window=ctx,
            label=sp.label,
            category=sp.category or ("benign" if sp.label == "benign" else "instruction_override"),
            severity=sp.severity or ("none" if sp.label == "benign" else "high"),
            source_doc_id=req.doc_id,
        ))
        inserted += 1
    return {"inserted": inserted, "corpus_version": _corpus_version()}


# ─────────────────────────── frontend ───────────────────────────


@app.get("/", response_model=None)
def index() -> FileResponse | JSONResponse:
    idx = FRONTEND_DIR / "index.html"
    if idx.exists():
        return FileResponse(str(idx))
    return JSONResponse({"detail": "frontend not built"}, status_code=404)
