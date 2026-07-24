"""
Retrieval layer (PRD §3.5) — the self-evolution.

Two jobs:
  1. Doc-level query -> top-k labeled examples, injected into the judge prompt
     and shown in the UI ("similar to an example you labeled").
  2. Retrieval-as-detector: segment the doc, embed each segment, and if a
     segment is highly similar to a labeled INJECTION, emit a candidate span.
     This makes the learning loop catch same-family variants LIVE even when the
     judge is unavailable — the applause moment does not depend on billing.

Calibration on hard negatives: an existing candidate whose context is highly
similar to a labeled BENIGN example gets its severity knocked down one step
(teaching the system what's normal so it isn't a paranoid string-matcher).
"""

from __future__ import annotations

import re

from .config import get_settings
from .embeddings import embed_one, embed_texts
from .memory import MemoryStore
from .schemas import SEVERITIES, CandidateSpan, severity_rank

_SENT_SPLIT = re.compile(r"(?<=[.!?\n])\s+")


def _segments(document: str, max_segments: int = 60) -> list[tuple[int, int, str]]:
    """Split into sentence-ish segments, tracking (start, end, text) offsets."""
    segs: list[tuple[int, int, str]] = []
    pos = 0
    for piece in _SENT_SPLIT.split(document):
        if not piece:
            continue
        idx = document.find(piece, pos)
        if idx == -1:
            idx = pos
        start = idx
        end = idx + len(piece)
        pos = end
        stripped = piece.strip()
        if len(stripped) >= 12:  # ignore trivially short fragments
            segs.append((start, end, piece))
        if len(segs) >= max_segments:
            break
    return segs


def retrieve_examples(store: MemoryStore, document: str, k: int) -> list[dict]:
    """Top-k labeled examples nearest the whole document."""
    matches = store.query(embed_one(document), k)
    return [
        {
            "quote": m.quote,
            "label": m.label,
            "category": m.category,
            "similarity": round(m.similarity, 4),
        }
        for m in matches
    ]


def _nearest_by_label(matches) -> tuple[float, str, object | None]:
    """From a match list, return (inj_sim, ben_sim, best_injection_match)."""
    inj_sim = ben_sim = 0.0
    best_inj = None
    for m in matches:
        if m.label == "injection":
            if m.similarity > inj_sim:
                inj_sim, best_inj = m.similarity, m
        elif m.label == "benign":
            ben_sim = max(ben_sim, m.similarity)
    return inj_sim, ben_sim, best_inj


def _context(document: str, start: int, end: int, radius: int = 120) -> str:
    lo = max(0, start - radius)
    hi = min(len(document), end + radius)
    return document[lo:hi]


def detect_by_retrieval(
    store: MemoryStore, document: str, existing: list[CandidateSpan]
) -> list[CandidateSpan]:
    """Emit retrieval candidates for injection-similar segments; return new spans.
    Also mutates `existing` in place: clear false positives that match a benign
    example, and tag/confirm those that match an injection example."""
    s = get_settings()
    counts = store.count()
    if counts.get("injection", 0) == 0 and counts.get("benign", 0) == 0:
        return []

    thresh = s.retrieval_hit_threshold
    margin = s.retrieval_margin
    k = max(5, s.retrieval_k)
    new_spans: list[CandidateSpan] = []

    # 1. Retrieval-as-detector over segments: a segment closer to a labeled
    #    injection than to any benign example (and above threshold) is flagged.
    segs = _segments(document)
    if segs:
        vecs = embed_texts([t for _, _, t in segs])
        for (start, end, text), vec in zip(segs, vecs):
            inj_sim, ben_sim, best = _nearest_by_label(store.query(vec, k))
            if best is None or inj_sim < thresh or inj_sim < ben_sim + margin:
                continue
            sev = "critical" if inj_sim >= 0.90 else "high"
            cat = best.category if best.category in {
                "instruction_override", "exfiltration", "obfuscation",
                "jailbreak", "tool_abuse", "social_engineering",
            } else "instruction_override"
            new_spans.append(CandidateSpan(
                start=start, end=end, text=text.strip(),
                source="retrieval", sources=["retrieval"],
                category=cat, severity=sev, addressed_to="agent",
                rationale=f"Closely matches a previously-labeled injection (sim={inj_sim:.2f}).",
                raw_score=round(inj_sim, 4), similar_to_label=True,
            ))

    # 2. Calibration of existing candidates against nearest labeled neighbors,
    #    using each candidate's surrounding context window.
    for cand in existing:
        if not cand.text.strip():
            continue
        ctx = _context(document, cand.start, cand.end)
        inj_sim, ben_sim, _ = _nearest_by_label(store.query(embed_one(ctx), k))
        if inj_sim >= thresh and inj_sim >= ben_sim:
            cand.similar_to_label = True
        elif ben_sim >= thresh and ben_sim >= inj_sim + margin and cand.source in ("heuristic", "gliguard"):
            # Known-normal content -> clear it (learned what's normal for this job).
            cand.severity = "none"
            cand.category = "benign"
            cand.rationale = (cand.rationale + " [cleared: matches a benign example you labeled]").strip()

    return new_spans
