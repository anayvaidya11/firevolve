"""
End-to-end eval regression (PRD §9): the F1-over-versions chart must climb.
Slow (runs the whole benchmark twice) -> marked slow; run with `-m slow`.
"""

import pytest

from eval.run_bench import load_bench, run_version
from eval.seeds import seeds_for  # noqa: F401  (ensures import path is valid)


@pytest.mark.slow
def test_f1_climbs_v0_to_v2(client):
    docs = load_bench()
    v0 = run_version(client, docs, "v0")["metrics"]["f1"]
    v2 = run_version(client, docs, "v2")["metrics"]["f1"]
    # Learning must strictly improve F1, and v2 should be strong.
    assert v2 > v0, f"F1 did not climb: v0={v0} v2={v2}"
    assert v2 >= 0.9, f"v2 F1 too low: {v2}"


@pytest.mark.slow
def test_hard_negatives_pass_at_v2(client):
    docs = load_bench()
    run_version(client, docs, "v2")
    # Re-run the 5 hard negatives explicitly; all must PASS after benign labels.
    hard = [d for d in docs if d["id"].startswith("hn")]
    for d in hard:
        band = client.post("/analyze", json={"text": d["text"]}).json()["band"]
        assert band == "PASS", f"{d['id']} should PASS, got {band}"
