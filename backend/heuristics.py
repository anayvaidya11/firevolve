"""
Layer 1 — Heuristics (PRD §3.1). Instant, zero-latency, zero-dependency.

Pure regex/Python. Catches the obvious, gives the demo an instant first hit,
and works even if every API is down. Each hit is a CandidateSpan with
source="heuristic". Overlapping hits are allowed; the router dedupes.
"""

from __future__ import annotations

import base64
import re

from .schemas import CandidateSpan

# ─────────────────── 1. invisible / zero-width unicode ───────────────────
# Zero-width + bidi controls + word-joiner + BOM + Unicode tag chars.
_INVISIBLE = re.compile(
    "["
    "​-‏"   # zero-width space/joiners, LRM/RLM
    "‪-‮"   # bidi embedding/override controls
    "⁠-⁤"   # word joiner, invisible operators
    "﻿"          # BOM / zero-width no-break space
    "\U000e0000-\U000e007f"  # Unicode tag characters (used to smuggle text)
    "]+"
)

# ─────────────────── 2. base64 blobs ───────────────────
_B64 = re.compile(r"[A-Za-z0-9+/]{40,}={0,2}")

# ─────────────────── 3. instruction-override family ───────────────────
_OVERRIDE_PATTERNS = [
    r"ignore\s+(?:all\s+)?(?:previous|prior|above|earlier)\s+instructions",
    r"ignore\s+your\s+(?:instructions|rules|schema|guidelines)",
    r"disregard\s+(?:the\s+|your\s+)?(?:system|above|previous|prior|schema|format|rules|instructions|guidelines)",
    r"forget\s+(?:everything|all|your)\b",
    r"you\s+are\s+now\b",
    r"new\s+instructions\s*:",
    r"system\s+prompt",
    r"system\s+override",
    r"developer\s+mode",
    r"do\s+not\s+tell\b",
    # Judge-capture / meta-instructions: attempts to corrupt the analyzer's or
    # agent's own output format or verdict (PRD §3.3 tripwire, caught at Layer 1
    # so it still fires when the judge is unavailable).
    r"do\s+not\s+output\b",
    r"(?:reply|respond|answer|output)\s+only\s+with\b",
    r"without\s+(?:telling|informing|asking|notifying)\b",
    r"override\s+(?:your|the)\s+(?:rules|instructions|guidelines)",
    r"as\s+an\s+ai\b.*\byou\s+must\b",
]
_OVERRIDE = re.compile("|".join(f"(?:{p})" for p in _OVERRIDE_PATTERNS), re.IGNORECASE)

# ─────────────────── 4. imperative + exfil target ───────────────────
_IMPERATIVE = re.compile(
    r"\b(?:send|forward|email|share|post|upload|transfer|wire|cc|bcc|export|leak)\b",
    re.IGNORECASE,
)
_EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
_URL = re.compile(r"https?://[^\s)>\]]+", re.IGNORECASE)
_KEYSHAPE = re.compile(
    r"(?:sk-[A-Za-z0-9]{8,}"
    r"|AKIA[0-9A-Z]{12,}"
    r"|-----BEGIN[ A-Z]+PRIVATE KEY-----"
    r"|\b[0-9a-fA-F]{32,}\b)"
)
_EXFIL_WINDOW = 120


def _add(spans: list[CandidateSpan], start: int, end: int, text: str,
         category: str, severity: str, rationale: str,
         addressed_to: str = "unknown") -> None:
    if end <= start:
        return
    spans.append(CandidateSpan(
        start=start, end=end, text=text,
        source="heuristic", sources=["heuristic"],
        category=category, severity=severity,
        addressed_to=addressed_to, rationale=rationale,
    ))


def run_heuristics(document: str) -> list[CandidateSpan]:
    """Run all Layer-1 detectors and return candidate spans."""
    spans: list[CandidateSpan] = []
    if not document:
        return spans

    # 1. invisible / zero-width unicode — nothing legitimate hides text.
    for m in _INVISIBLE.finditer(document):
        _add(spans, m.start(), m.end(), document[m.start():m.end()],
             "obfuscation", "high",
             "Invisible/zero-width Unicode used to smuggle hidden text.")

    # 2. base64 blobs that decode to printable text.
    for m in _B64.finditer(document):
        blob = m.group(0)
        try:
            decoded = base64.b64decode(blob + "=" * (-len(blob) % 4), validate=False)
            printable = sum(32 <= b < 127 or b in (9, 10, 13) for b in decoded)
            if decoded and printable / max(len(decoded), 1) > 0.85:
                _add(spans, m.start(), m.end(), blob, "obfuscation", "medium",
                     "Base64 blob decoding to readable text — possible hidden payload.")
        except Exception:
            continue

    # 3. instruction-override family.
    for m in _OVERRIDE.finditer(document):
        _add(spans, m.start(), m.end(), m.group(0),
             "instruction_override", "high",
             "Phrase attempts to override the agent's instructions.",
             addressed_to="agent")

    # 4. imperative verb within ~120 chars of an exfil target.
    targets: list[tuple[int, int, str]] = []
    for rx, kind in ((_EMAIL, "email"), (_URL, "URL"), (_KEYSHAPE, "secret")):
        for m in rx.finditer(document):
            targets.append((m.start(), m.end(), kind))
    for im in _IMPERATIVE.finditer(document):
        for ts, te, kind in targets:
            if abs(ts - im.start()) <= _EXFIL_WINDOW or abs(im.start() - te) <= _EXFIL_WINDOW:
                start, end = min(im.start(), ts), max(im.end(), te)
                _add(spans, start, end, document[start:end],
                     "exfiltration", "high",
                     f"Imperative verb near an exfiltration target ({kind}).",
                     addressed_to="agent")
                break

    return spans
