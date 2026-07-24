"""
Firevolv eval harness (PRD §9). Runs the full pipeline over the frozen benchmark
and logs document-level P/R/F1 per corpus version.

Scoring (PRD §9.2): predicted band in {BLOCK, UNCERTAIN} = positive vs gold
"injection"; PASS = negative. UNCERTAIN counts as positive (it routes to human
review). Writes results/{version}.json.

Runs IN-PROCESS by default (FastAPI TestClient — no server needed), which is the
robust path for CI / verification. Use --url to hit a live server instead.

Guild wraps this: `guild run bench corpus_version=v0|v1|v2` (see eval/guild.yml).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from eval.seeds import seeds_for  # noqa: E402

BENCH = ROOT / "benchmark" / "firevolv_bench.jsonl"
RESULTS = ROOT / "results"


def load_bench() -> list[dict]:
    docs = []
    for line in BENCH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            docs.append(json.loads(line))
    return docs


class InProcessClient:
    """Thin wrapper over FastAPI TestClient with the same .post/.get shape we use."""

    def __init__(self):
        from fastapi.testclient import TestClient
        from backend.main import app
        self._c = TestClient(app)

    def post(self, path, json=None):
        return self._c.post(path, json=json)

    def get(self, path):
        return self._c.get(path)


class HttpClient:
    def __init__(self, url: str):
        import httpx
        self._base = url.rstrip("/")
        self._c = httpx.Client(timeout=60.0)

    def post(self, path, json=None):
        return self._c.post(self._base + path, json=json)

    def get(self, path):
        return self._c.get(self._base + path)


def score(docs: list[dict], preds: list[str]) -> dict:
    tp = fp = tn = fn = 0
    for d, band in zip(docs, preds):
        gold_pos = d["gold_label"] == "injection"
        pred_pos = band in ("BLOCK", "UNCERTAIN")
        if gold_pos and pred_pos:
            tp += 1
        elif gold_pos and not pred_pos:
            fn += 1
        elif not gold_pos and pred_pos:
            fp += 1
        else:
            tn += 1
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    acc = (tp + tn) / max(1, len(docs))
    return {"tp": tp, "fp": fp, "tn": tn, "fn": fn,
            "precision": round(prec, 4), "recall": round(rec, 4),
            "f1": round(f1, 4), "accuracy": round(acc, 4)}


def run_version(client, docs: list[dict], version: str) -> dict:
    client.post("/reset")
    for body in seeds_for(version):
        client.post("/label", json={"doc_id": f"seed-{version}", "spans": [body]})
    preds, per_doc = [], []
    for d in docs:
        r = client.post("/analyze", json={"text": d["text"]})
        res = r.json()
        band = res.get("band", "UNCERTAIN")
        preds.append(band)
        per_doc.append({"id": d["id"], "gold": d["gold_label"], "band": band,
                        "score": res.get("score"), "n_spans": len(res.get("spans", []))})
    metrics = score(docs, preds)
    return {"version": version, "metrics": metrics, "per_doc": per_doc}


def print_table(result: dict):
    m = result["metrics"]
    print(f"\n=== corpus {result['version']} ===")
    print(f"  P={m['precision']:.3f}  R={m['recall']:.3f}  F1={m['f1']:.3f}  "
          f"acc={m['accuracy']:.3f}  (tp={m['tp']} fp={m['fp']} tn={m['tn']} fn={m['fn']})")


def write_result(result: dict):
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{result['version']}.json").write_text(
        json.dumps(result, indent=2), encoding="utf-8")


def make_client(url: str | None):
    return HttpClient(url) if url else InProcessClient()


def svg_chart(points: list[tuple[str, float]], out: Path):
    """Zero-dependency F1-over-versions line chart (the money chart)."""
    W, H, pad = 520, 300, 50
    xs = [pad + i * (W - 2 * pad) / max(1, len(points) - 1) for i in range(len(points))]
    ys = [H - pad - v * (H - 2 * pad) for _, v in points]
    poly = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    dots = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="#4c8dff"/>'
        f'<text x="{x:.1f}" y="{y - 12:.1f}" fill="#e6edf3" font-size="12" text-anchor="middle">{v:.2f}</text>'
        f'<text x="{x:.1f}" y="{H - pad + 20:.1f}" fill="#9aa7b4" font-size="12" text-anchor="middle">{lbl}</text>'
        for (lbl, v), x, y in zip(points, xs, ys)
    )
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">
<rect width="{W}" height="{H}" fill="#0e1116"/>
<text x="{W/2}" y="26" fill="#e6edf3" font-size="15" text-anchor="middle" font-family="sans-serif">Firevolv — F1 across corpus versions</text>
<line x1="{pad}" y1="{H-pad}" x2="{W-pad}" y2="{H-pad}" stroke="#2a3140"/>
<line x1="{pad}" y1="{pad}" x2="{pad}" y2="{H-pad}" stroke="#2a3140"/>
<polyline points="{poly}" fill="none" stroke="#4c8dff" stroke-width="2.5"/>
{dots}
</svg>'''
    out.write_text(svg, encoding="utf-8")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", default="all", help="v0 | v1 | v2 | all")
    ap.add_argument("--url", default=None, help="live server URL; omit for in-process")
    args = ap.parse_args()

    docs = load_bench()
    client = make_client(args.url)

    versions = ["v0", "v1", "v2"] if args.version == "all" else [args.version]
    points = []
    for v in versions:
        result = run_version(client, docs, v)
        write_result(result)
        print_table(result)
        points.append((v, result["metrics"]["f1"]))

    if len(points) > 1:
        RESULTS.mkdir(exist_ok=True)
        svg_chart(points, RESULTS / "f1_over_versions.svg")
        print("\nF1 over versions:", "  ".join(f"{v}={f:.3f}" for v, f in points))
        print(f"chart -> {RESULTS / 'f1_over_versions.svg'}")
        # Sanity: the demo requires a non-decreasing climb.
        f1s = [f for _, f in points]
        if f1s == sorted(f1s) and f1s[-1] >= f1s[0]:
            print("✓ F1 is non-decreasing across versions")
        else:
            print("✗ WARNING: F1 did not climb monotonically:", f1s)


if __name__ == "__main__":
    main()
