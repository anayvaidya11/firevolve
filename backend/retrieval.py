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


def _overlaps(a_start: int, a_end: int, regions: list[tuple[int, int]]) -> bool:
    for rs, re_ in regions:
        if a_start < re_ and rs < a_end:
            return True
    return False


def detect_by_retrieval(
    store: MemoryStore, document: str, existing: list[CandidateSpan]
) -> list[CandidateSpan]:
    """Sentence-granularity retrieval, then region-based calibration.

    Seeds are sentence-shaped, so we classify each sentence as an injection or
    benign region by its nearest labeled neighbor, emit candidates for injection
    regions, and clear heuristic false positives that overlap a benign region.
    Region overlap decouples the benign signal from the (often boundary-crossing)
    heuristic span text, which is what makes hard negatives reliably clear."""
    s = get_settings()
    counts = store.count()
    if counts.get("injection", 0) == 0 and counts.get("benign", 0) == 0:
        return []

    thresh = s.retrieval_hit_threshold
    margin = s.retrieval_margin
    k = max(5, s.retrieval_k)
    new_spans: list[CandidateSpan] = []
    inj_regions: list[tuple[int, int]] = []
    ben_regions: list[tuple[int, int]] = []

    segs = _segments(document)
    if not segs:
        return []
    vecs = embed_texts([t for _, _, t in segs])
    for (start, end, text), vec in zip(segs, vecs):
        inj_sim, ben_sim, best = _nearest_by_label(store.query(vec, k))
        # Injection region -> flag it.
        if best is not None and inj_sim >= thresh and inj_sim >= ben_sim + margin:
            inj_regions.append((start, end))
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
        # Benign region -> known-normal content.
        elif ben_sim >= thresh and ben_sim >= inj_sim + margin:
            ben_regions.append((start, end))

    # Calibrate existing candidates by region overlap.
    for cand in existing:
        if not cand.text.strip():
            continue
        in_inj = _overlaps(cand.start, cand.end, inj_regions)
        in_ben = _overlaps(cand.start, cand.end, ben_regions)
        if in_inj:
            cand.similar_to_label = True
        elif in_ben and cand.source in ("heuristic", "gliguard"):
            # Learned this is normal for this job -> clear the false positive.
            cand.severity = "none"
            cand.category = "benign"
            cand.rationale = (cand.rationale + " [cleared: matches a benign example you labeled]").strip()

    return new_spans
