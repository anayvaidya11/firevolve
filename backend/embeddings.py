"""
Embeddings (PRD §4). Same function for insert and query — deterministic & fast.

Order of preference:
  1. Pioneer embeddings endpoint (if PIONEER_EMBED_MODEL is set and billing is on).
  2. Local deterministic hashing embedding (zero-dependency fallback).

The local fallback is a signed feature-hashing bag over word uni/bi-grams and
character 3–5-grams, L2-normalized. It is deterministic (blake2b, not Python's
salted hash), needs no model download, and gives strong cosine similarity for
lexically-similar / same-family spans — exactly what the retrieval loop needs.
"""

from __future__ import annotations

import hashlib
import math
import re
from collections import Counter

import httpx
import numpy as np

from .config import get_settings

DIM = 512
_WORD = re.compile(r"[a-z0-9]+")


def _h(feature: str) -> int:
    d = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(d, "big")


def _local_embed_one(text: str) -> list[float]:
    vec = np.zeros(DIM, dtype=np.float32)
    norm_text = text.lower().strip()
    if not norm_text:
        return vec.tolist()

    words = _WORD.findall(norm_text)
    features: list[str] = []
    features.extend(f"w:{w}" for w in words)
    features.extend(f"b:{a}_{b}" for a, b in zip(words, words[1:]))
    compact = re.sub(r"\s+", " ", norm_text)
    for n in (3, 4, 5):
        if len(compact) >= n:
            features.extend(f"c{n}:{compact[i:i + n]}" for i in range(len(compact) - n + 1))

    counts = Counter(features)
    for feat, cnt in counts.items():
        hv = _h(feat)
        idx = hv % DIM
        sign = 1.0 if (hv >> 20) & 1 else -1.0
        vec[idx] += sign * (1.0 + math.log(cnt))

    norm = float(np.linalg.norm(vec))
    if norm > 0:
        vec /= norm
    return vec.tolist()


def _pioneer_embed(texts: list[str]) -> list[list[float]] | None:
    s = get_settings()
    if not s.pioneer_embed_model or not s.pioneer_api_key or not s.pioneer_base_url:
        return None
    try:
        url = s.pioneer_base_url.rstrip("/") + "/embeddings"
        r = httpx.post(
            url,
            headers={"Authorization": f"Bearer {s.pioneer_api_key}"},
            json={"model": s.pioneer_embed_model, "input": texts},
            timeout=s.embed_timeout_s,
        )
        r.raise_for_status()
        data = r.json()["data"]
        return [item["embedding"] for item in data]
    except Exception:
        # Any failure (incl. card_required) -> deterministic local fallback.
        return None


def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    remote = _pioneer_embed(texts)
    if remote is not None and len(remote) == len(texts):
        return remote
    return [_local_embed_one(t) for t in texts]


def embed_one(text: str) -> list[float]:
    return embed_texts([text])[0]
