"""Configuration, read from the environment (and an optional .env file)."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

# Defaults mirror a typical 4-vendor council. Model IDs go stale quickly:
# run `python -m ideaforge check` and override via env vars if any are missing.
DEFAULT_COUNCIL = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
]
DEFAULT_CHAIRMAN = "google/gemini-3-pro-preview"
DEFAULT_BRAINSTORM_MODEL = "anthropic/claude-sonnet-4.5"


def load_dotenv(path: Path | str = ".env") -> None:
    """Tiny .env loader (KEY=VALUE lines). Existing environment variables win."""
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _split(value: str | None, default: list[str]) -> list[str]:
    if not value:
        return list(default)
    return [m.strip() for m in value.split(",") if m.strip()]


@dataclass
class Settings:
    api_key: str | None = None
    council_models: list[str] = field(default_factory=lambda: list(DEFAULT_COUNCIL))
    chairman: str = DEFAULT_CHAIRMAN
    brainstorm_model: str = DEFAULT_BRAINSTORM_MODEL
    max_concurrency: int = 6
    timeout: float = 180.0

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv()
        return cls(
            api_key=os.getenv("OPENROUTER_API_KEY") or None,
            council_models=_split(os.getenv("IDEAFORGE_COUNCIL_MODELS"), DEFAULT_COUNCIL),
            chairman=os.getenv("IDEAFORGE_CHAIRMAN") or DEFAULT_CHAIRMAN,
            brainstorm_model=os.getenv("IDEAFORGE_BRAINSTORM_MODEL") or DEFAULT_BRAINSTORM_MODEL,
        )
