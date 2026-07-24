# How Firevolv Uses Pioneer, Actian & Guild

Firevolv is a **prompt-injection detector**. It reads a document, flags the spans it
believes are hidden instructions meant to hijack an AI agent, lets a human
accept or reject those flags, and *learns* from those corrections so it gets
better over time.

Three services each own one stage of that loop:

| Service | Role | Status in code |
|---|---|---|
| **Pioneer** | Inference provider — serves the Claude Opus judge + the GliGuard guard model | **Live** ([backend/pioneer.py](backend/pioneer.py)) |
| **Actian** | Vector store for labeled spans → k-NN retrieval (the learning loop) | **Stubbed**, falls back to in-memory ([backend/memory.py](backend/memory.py)) |
| **Guild** | Eval harness that produces the F1-over-versions chart | **External CLI** ([eval/guild.yml](eval/guild.yml)) |

---

## 🧠 Pioneer — the brain (inference)

Pioneer is the **AI provider**. It serves the two models that do the actual
detection:

- **Claude Opus judge** — the main reasoning layer. Firevolv sends it the document
  (plus a few similar past examples) and Claude returns the spans it thinks are
  injection attempts, as structured JSON.
- **GliGuard** — a fast guard model for *overt* threats (jailbreaks, obvious
  payloads). It runs alongside Claude as a second opinion.

Both are called over HTTP from [backend/pioneer.py](backend/pioneer.py): Claude
via an Anthropic-style `/messages` endpoint, GliGuard via an OpenAI-style
`/chat/completions` endpoint. If Pioneer is unreachable (or billing isn't
enabled), both layers gracefully degrade and detection continues on heuristics +
retrieval.

> **In short:** Pioneer answers *"is this text an attack?"*

---

## 📚 Actian — the memory (learning loop)

Actian is a **vector database**. It's what lets Firevolv get smarter without
retraining any model:

1. A human reviews Firevolv's flags and clicks **accept** or **reject**.
2. Each reviewed span (plus ±200 chars of context) is turned into an embedding
   and **stored in Actian** with its human label — both injections *and* benign
   examples.
3. On the **next** document, Firevolv searches Actian for the most similar past
   examples and feeds them to the Claude judge as hints, and flags any segment
   that closely matches a labeled injection.

The system's "knowledge" is just the growing pile of labeled examples — no model
weights change, which is why it improves in seconds.

> ⚠️ In the current code this is **not connected yet**:
> [backend/memory.py](backend/memory.py) uses an in-process numpy k-NN store and
> the `ActianStore` is a stub. Switching over is a one-line change
> (`FIREVOLV_STORE=actian`) once credentials are provisioned.

> **In short:** Actian remembers past corrections so the judge learns from them.

---

## 📈 Guild — the scoreboard (proof it works)

Guild.ai is an **evaluation harness**. It's how the team *proves* the learning
loop actually works:

- It runs the full Firevolv pipeline over a fixed 30-doc benchmark.
- It does this at different memory states — e.g. 0 labels, then 5, then 17
  stored examples.
- It measures precision / recall / **F1** at each state and logs it as a
  versioned, comparable run.

Plot F1 across those versions and the line **climbs** — visual proof that more
human corrections mean better detection.

| version | corpus | P | R | F1 |
|---|---|---|---|---|
| v0 | empty | 0.71 | 0.80 | **0.750** |
| v1 | 5 labels | 0.74 | 0.93 | **0.824** |
| v2 | 17 labels | 1.00 | 0.93 | **0.966** |

Driven by [eval/run_bench.py](eval/run_bench.py); Guild wraps the same script
(`guild run bench corpus_version=v1`) for logged runs.

> **In short:** Guild produces the rising-accuracy chart that shows the system is
> learning.

---

## Putting it together

```
          ┌─────────────────────────────────────────────┐
Document ─▶│  PIONEER: Claude judge + GliGuard flag spans │─▶ flagged spans
          └─────────────────────────────────────────────┘
                          ▲                    │
        similar past      │                    ▼  human accepts / rejects
        examples ─────────┘            ┌──────────────────┐
                                       │ ACTIAN: store the │
                                       │  labeled example  │
                                       └──────────────────┘
                                                │
                                                ▼
                                 ┌──────────────────────────┐
                                 │ GUILD: re-run benchmark,  │
                                 │  chart F1 rising over time│
                                 └──────────────────────────┘
```

- **Pioneer** = detects (brain)
- **Actian** = remembers (memory)
- **Guild** = proves it's improving (scoreboard)
