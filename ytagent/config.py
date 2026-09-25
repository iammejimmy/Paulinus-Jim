"""Loads config.toml (falling back to defaults) and .env."""

from __future__ import annotations

import copy
import os
import tomllib
from pathlib import Path

DEFAULTS: dict = {
    "research": {
        "interests": ["history", "psychology", "personal finance", "science"],
        "format_preference": "animated stick-figure storytelling explainers (faceless, AI narration)",
        "avoid": ["gambling", "medical advice", "politics"],
        "language": "English",
        "region": "US",
        "niche_count": 10,
        "keywords_per_niche": 2,
        "lookback_days": 90,
    },
    "channel": {
        "niche": "",
        "format": "long",
        "target_minutes": 7,
        "voice": "en-US-AndrewNeural",
        "visual_style": "ai",
        "image_model": "gemini-2.5-flash-image",
        "image_style": "",
        "music_path": "",
        "music_volume": 0.08,
    },
    "publish": {
        "review_required": True,
        "privacy": "public",
        "category_id": "27",
        "timezone": "America/New_York",
        "days": ["mon", "wed", "fri"],
        "times": ["15:00"],
        "videos_per_run": 1,
        "disclose_synthetic_media": True,
    },
    "llm": {"model": "claude-opus-5", "effort": "high"},
    "paths": {"data_dir": "data", "output_dir": "output"},
}


def load_dotenv(path: str | Path = ".env") -> None:
    """Minimal .env loader; existing environment variables win."""
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


def load_config(path: str | Path = "config.toml") -> dict:
    load_dotenv()
    p = Path(path)
    user = tomllib.loads(p.read_text()) if p.exists() else {}
    cfg = _merge(DEFAULTS, user)
    Path(cfg["paths"]["data_dir"]).mkdir(parents=True, exist_ok=True)
    Path(cfg["paths"]["output_dir"]).mkdir(parents=True, exist_ok=True)
    return cfg
