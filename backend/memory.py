"""
Aegis learning-loop memory.

Backend-swappable vector store for labeled spans. All callers use the
`MemoryStore` interface only, so switching from the in-memory backend to
Actian (once login works) is a one-line change in `get_store()` — no caller
changes.

Contract:
    store.insert(record: LabelRecord) -> None
    store.query(vector: list[float], k: int) -> list[Match]   # nearest first
    store.count() -> dict   # {"injection": n, "benign": n}
    store.reset() -> None

Embeddings are computed by the caller (pioneer.py) and passed in as `vector`.
This module never calls an embedding model — it only stores/retrieves vectors.
"""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from typing import Literal, Protocol

import numpy as np


# ─────────────────────────── data models ───────────────────────────

@dataclass
class LabelRecord:
    vector: list[float]
    quote: str
    context_window: str
    label: Literal["injection", "benign"]
    category: str
    severity: str
    persona: str = "Executive Assistant Agent"
    source_doc_id: str = ""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class Match:
    quote: str
    label: str
    category: str
    severity: str
    similarity: float          # cosine similarity in [-1, 1]
    context_window: str = ""


# ─────────────────────────── interface ───────────────────────────

class MemoryStore(Protocol):
    def insert(self, record: LabelRecord) -> None: ...
    def query(self, vector: list[float], k: int) -> list[Match]: ...
    def count(self) -> dict: ...
    def reset(self) -> None: ...


# ─────────────────────── in-memory backend ───────────────────────

class InMemoryStore:
    """Zero-dependency numpy cosine k-NN. Ideal for demo scale.

    Corpus lives in process memory; lost on restart (that's fine — the demo
    calls reset() for a clean run, and labels are re-added live on stage).
    """

    def __init__(self) -> None:
        self._vectors: list[np.ndarray] = []   # each L2-normalized
        self._records: list[LabelRecord] = []

    def insert(self, record: LabelRecord) -> None:
        v = np.asarray(record.vector, dtype=np.float32)
        norm = np.linalg.norm(v)
        if norm > 0:
            v = v / norm
        self._vectors.append(v)
        self._records.append(record)

    def query(self, vector: list[float], k: int) -> list[Match]:
        if not self._vectors:
            return []
        q = np.asarray(vector, dtype=np.float32)
        norm = np.linalg.norm(q)
        if norm > 0:
            q = q / norm
        mat = np.vstack(self._vectors)          # (N, D), already normalized
        sims = mat @ q                          # cosine similarity
        top = np.argsort(-sims)[:k]
        out = []
        for i in top:
            r = self._records[int(i)]
            out.append(Match(
                quote=r.quote,
                label=r.label,
                category=r.category,
                severity=r.severity,
                similarity=float(sims[int(i)]),
                context_window=r.context_window,
            ))
        return out

    def count(self) -> dict:
        c = {"injection": 0, "benign": 0}
        for r in self._records:
            c[r.label] = c.get(r.label, 0) + 1
        return c

    def reset(self) -> None:
        self._vectors.clear()
        self._records.clear()


# ─────────────────────── Actian backend (stub) ───────────────────────

class ActianStore:
    """Drop-in for when Actian login works. Same interface as InMemoryStore.

    Fill in the client calls against ACTIAN_URL / ACTIAN_API_KEY. Keep the
    method signatures identical so no caller changes.
    """

    def __init__(self, url: str, api_key: str, collection: str) -> None:
        raise NotImplementedError(
            "ActianStore not wired yet — using InMemoryStore. "
            "Implement insert/query/count/reset against the Actian client, "
            "then flip AEGIS_STORE=actian."
        )

    def insert(self, record: LabelRecord) -> None: ...
    def query(self, vector: list[float], k: int) -> list[Match]: ...
    def count(self) -> dict: ...
    def reset(self) -> None: ...


# ─────────────────────────── factory ───────────────────────────

_store: MemoryStore | None = None


def get_store() -> MemoryStore:
    """Singleton store. Swap backends via AEGIS_STORE env (default: memory)."""
    global _store
    if _store is not None:
        return _store
    backend = os.getenv("AEGIS_STORE", "memory").lower()
    if backend == "actian":
        _store = ActianStore(
            url=os.environ["ACTIAN_URL"],
            api_key=os.environ["ACTIAN_API_KEY"],
            collection=os.getenv("ACTIAN_COLLECTION", "aegis_labels"),
        )
    else:
        _store = InMemoryStore()
    return _store
