"""
Aegis configuration (PRD §12) via pydantic-settings.

Reads .env automatically. Secrets never hardcoded. All thresholds and model
IDs live here so they can be tuned against the benchmark in one place.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # --- Pioneer ---
    pioneer_api_key: str = ""
    pioneer_gliguard_api_key: str = ""
    pioneer_base_url: str = "https://api.pioneer.ai/v1"
    pioneer_judge_model: str = "claude-opus-4-8"
    pioneer_guard_model: str = "gliguard"
    pioneer_embed_model: str = ""  # blank -> local deterministic fallback

    # --- Vector store ---
    aegis_store: str = "memory"
    actian_url: str = ""
    actian_api_key: str = ""
    actian_collection: str = "aegis_labels"

    # --- Router thresholds ---
    block_threshold: float = 0.80
    pass_threshold: float = 0.20
    retrieval_k: int = 3

    # --- Retrieval-as-detector (learning loop works even without the judge) ---
    # If a doc span is at least this cosine-similar to a labeled INJECTION span,
    # emit a retrieval candidate. This is what makes the "similar to an example
    # you labeled" applause moment fire live.
    retrieval_hit_threshold: float = 0.70
    # A benign/injection nearest-neighbor must beat the other by this margin
    # before it decides (clear a false positive / confirm an injection).
    retrieval_margin: float = 0.10

    # --- Networking ---
    judge_timeout_s: float = 45.0
    guard_timeout_s: float = 20.0
    embed_timeout_s: float = 20.0

    @property
    def judge_enabled(self) -> bool:
        return bool(self.pioneer_api_key and self.pioneer_base_url and self.pioneer_judge_model)

    @property
    def guard_enabled(self) -> bool:
        key = self.pioneer_gliguard_api_key or self.pioneer_api_key
        return bool(key and self.pioneer_base_url and self.pioneer_guard_model)


@lru_cache
def get_settings() -> Settings:
    return Settings()
