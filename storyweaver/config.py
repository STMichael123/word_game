from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlparse


@dataclass(frozen=True)
class Settings:
    llm_api_key: Optional[str]
    base_url: str
    model: str
    provider_hint: str

    story_seed: Optional[int]
    max_history_events: int

    temperature: float
    top_p: float
    max_tokens: int


def load_settings() -> Settings:
    def _get_first(*names: str) -> Optional[str]:
        for name in names:
            raw = os.getenv(name)
            if raw is not None and raw.strip() != "":
                return raw.strip()
        return None

    def _get_int(name: str, default: int) -> int:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    def _get_float(name: str, default: float) -> float:
        raw = os.getenv(name)
        if raw is None or raw.strip() == "":
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    story_seed_raw = os.getenv("STORY_SEED")
    try:
        story_seed = int(story_seed_raw) if story_seed_raw and story_seed_raw.strip() else None
    except ValueError:
        story_seed = None

    base_url = _get_first("LLM_BASE_URL", "OPENAI_BASE_URL", "NVIDIA_BASE_URL") or "https://api.openai-proxy.org/v1"
    model = _get_first("LLM_MODEL", "OPENAI_MODEL", "NVIDIA_MODEL") or "gpt-5.4"
    api_key = _get_first("LLM_API_KEY", "OPENAI_API_KEY", "NVIDIA_API_KEY")

    host = urlparse(base_url).netloc.lower()
    if "nvidia" in host:
        provider_hint = "nvidia"
    elif "openai" in host:
        provider_hint = "openai-compatible"
    else:
        provider_hint = host or "custom-openai-compatible"

    return Settings(
        llm_api_key=api_key,
        base_url=base_url,
        model=model,
        provider_hint=provider_hint,
        story_seed=story_seed,
        max_history_events=_get_int("MAX_HISTORY_EVENTS", 20),
        temperature=_get_float("TEMPERATURE", 0.9),
        top_p=_get_float("TOP_P", 0.9),
        max_tokens=_get_int("MAX_TOKENS", 700),
    )

