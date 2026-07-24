"""
Router (PRD §3.4): merge candidate spans, compute a document score, assign a band.

Score = 1 - Π(1 - severity_weight[s]) over merged spans (probabilistic OR, so
multiple weak signals still add up). Bands from one config block (tune against
the benchmark, not by feel).
"""

from __future__ import annotations

from .config import get_settings
from .schemas import (
    SEVERITY_WEIGHT,
    AnalysisResult,
    Band,
    CandidateSpan,
    severity_rank,
)


def _overlap_ratio(a: CandidateSpan, b: CandidateSpan) -> float:
    lo = max(a.start, b.start)
    hi = min(a.end, b.end)
    inter = max(0, hi - lo)
    shorter = min(a.end - a.start, b.end - b.start)
    if shorter <= 0:
        return 0.0
    return inter / shorter


# Prefer the judge's semantics, then retrieval, then heuristic/gliguard.
_SOURCE_PRIORITY = {"judge": 3, "retrieval": 2, "heuristic": 1, "gliguard": 0}


def merge_spans(spans: list[CandidateSpan]) -> list[CandidateSpan]:
    """Merge spans overlapping >50% (of the shorter). Keep highest severity,
    union sources, prefer the judge's category/rationale when present."""
    if not spans:
        return []
    ordered = sorted(spans, key=lambda s: (s.start, s.end))
    merged: list[CandidateSpan] = []
    for sp in ordered:
        placed = False
        for i, m in enumerate(merged):
            if _overlap_ratio(sp, m) > 0.5:
                merged[i] = _combine(m, sp)
                placed = True
                break
        if not placed:
            merged.append(sp.model_copy(deep=True))
    return sorted(merged, key=lambda s: s.start)


def _combine(a: CandidateSpan, b: CandidateSpan) -> CandidateSpan:
    # Widest span wins the offsets so the highlight covers both.
    start, end = min(a.start, b.start), max(a.end, b.end)
    hi_sev = a if severity_rank(a.severity) >= severity_rank(b.severity) else b
    # Category/rationale/addressed_to from the highest-priority source.
    lead = a if _SOURCE_PRIORITY.get(a.source, 0) >= _SOURCE_PRIORITY.get(b.source, 0) else b
    sources = sorted(set(a.sources + b.sources + [a.source, b.source]))
    return CandidateSpan(
        start=start, end=end, text=(hi_sev.text or a.text or b.text),
        source=lead.source, sources=sources,
        category=lead.category if lead.category != "benign" else hi_sev.category,
        severity=hi_sev.severity,
        addressed_to=lead.addressed_to if lead.addressed_to != "unknown" else hi_sev.addressed_to,
        rationale=lead.rationale or hi_sev.rationale,
        raw_score=a.raw_score if a.raw_score is not None else b.raw_score,
        similar_to_label=a.similar_to_label or b.similar_to_label,
    )


def compute_score(spans: list[CandidateSpan]) -> float:
    prod = 1.0
    for s in spans:
        prod *= (1.0 - SEVERITY_WEIGHT.get(s.severity, 0.0))
    return round(1.0 - prod, 4)


def decide_band(score: float, tripwire: bool, force_uncertain: bool) -> Band:
    s = get_settings()
    if score >= s.block_threshold:
        base: Band = "BLOCK"
    elif score <= s.pass_threshold:
        base = "PASS"
    else:
        base = "UNCERTAIN"
    # Fail closed: a tripwire or a judge that was expected but errored must never
    # let a document drop to PASS. Escalate PASS -> UNCERTAIN; keep BLOCK.
    if (tripwire or force_uncertain) and base == "PASS":
        return "UNCERTAIN"
    return base


def route(
    doc_id: str,
    candidates: list[CandidateSpan],
    retrieved_examples: list[dict],
    tripwire: bool,
    force_uncertain: bool,
    layers: dict[str, bool],
    corpus_version: int,
    latency_ms: int,
) -> AnalysisResult:
    merged = merge_spans(candidates)
    score = compute_score(merged)
    band = decide_band(score, tripwire, force_uncertain)
    from .schemas import RetrievedExample

    return AnalysisResult(
        doc_id=doc_id,
        band=band,
        score=score,
        spans=merged,
        retrieved_examples=[RetrievedExample(**e) for e in retrieved_examples],
        tripwire_triggered=tripwire,
        latency_ms=latency_ms,
        corpus_version=corpus_version,
        layers=layers,
    )
