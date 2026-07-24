"""Router merge/score/band tests (PRD §3.4)."""

from backend.router import compute_score, decide_band, merge_spans
from backend.schemas import CandidateSpan


def span(start, end, source="heuristic", sev="high", cat="exfiltration"):
    return CandidateSpan(start=start, end=end, text="x" * (end - start),
                         source=source, sources=[source], category=cat, severity=sev)


def test_merge_overlapping_keeps_highest_severity_and_unions_sources():
    a = span(0, 20, source="heuristic", sev="medium")
    b = span(5, 25, source="judge", sev="high")
    merged = merge_spans([a, b])
    assert len(merged) == 1
    assert merged[0].severity == "high"
    assert set(merged[0].sources) == {"heuristic", "judge"}


def test_non_overlapping_kept_separate():
    merged = merge_spans([span(0, 10), span(50, 60)])
    assert len(merged) == 2


def test_judge_category_preferred_on_merge():
    a = span(0, 20, source="heuristic", cat="exfiltration", sev="high")
    b = span(0, 20, source="judge", cat="instruction_override", sev="high")
    merged = merge_spans([a, b])
    assert merged[0].category == "instruction_override"


def test_score_probabilistic_or():
    # two medium spans (0.55 each) -> 1 - 0.45*0.45 = 0.7975
    s = compute_score([span(0, 5, sev="medium"), span(10, 15, sev="medium")])
    assert abs(s - 0.7975) < 1e-3


def test_score_none_is_zero():
    assert compute_score([span(0, 5, sev="none")]) == 0.0


def test_bands():
    assert decide_band(0.95, tripwire=False, force_uncertain=False) == "BLOCK"
    assert decide_band(0.05, tripwire=False, force_uncertain=False) == "PASS"
    assert decide_band(0.5, tripwire=False, force_uncertain=False) == "UNCERTAIN"


def test_fail_closed_escalates_pass_to_uncertain():
    # A tripwire or expected-but-errored judge must never allow PASS.
    assert decide_band(0.05, tripwire=True, force_uncertain=False) == "UNCERTAIN"
    assert decide_band(0.05, tripwire=False, force_uncertain=True) == "UNCERTAIN"
    # ...but a clear BLOCK stays BLOCK (already more severe than UNCERTAIN).
    assert decide_band(0.95, tripwire=True, force_uncertain=False) == "BLOCK"
