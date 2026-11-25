"""Model clients: a real OpenRouter client (stdlib only) and a deterministic mock."""
from __future__ import annotations

import asyncio
import json
import urllib.error
import urllib.request
from typing import Protocol

from .config import OPENROUTER_MODELS_URL, OPENROUTER_URL, Settings


class LLM(Protocol):
    async def complete(self, model: str, prompt: str, *, task: str = "") -> str | None:
        """Return the model's text, or None if the call failed."""


class OpenRouterClient:
    def __init__(self, settings: Settings):
        if not settings.api_key:
            raise RuntimeError(
                "OPENROUTER_API_KEY is not set. Copy .env.example to .env and add your key, "
                "or run with --mock to try the flow without API calls."
            )
        self.settings = settings
        self._sem = asyncio.Semaphore(settings.max_concurrency)

    def _post(self, model: str, prompt: str) -> str:
        body = json.dumps({"model": model, "messages": [{"role": "user", "content": prompt}]}).encode()
        req = urllib.request.Request(
            OPENROUTER_URL,
            data=body,
            headers={
                "Authorization": f"Bearer {self.settings.api_key}",
                "Content-Type": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=self.settings.timeout) as resp:
            data = json.load(resp)
        return data["choices"][0]["message"]["content"] or ""

    async def complete(self, model: str, prompt: str, *, task: str = "") -> str | None:
        async with self._sem:
            for attempt in (1, 2):  # one retry on transient failure
                try:
                    return await asyncio.to_thread(self._post, model, prompt)
                except urllib.error.HTTPError as e:
                    detail = e.read().decode(errors="replace")[:200]
                    print(f"  ! {model} [{task}] HTTP {e.code}: {detail}")
                    if e.code in (400, 401, 402, 403, 404):  # not retryable
                        return None
                except Exception as e:  # network, timeout, bad JSON
                    print(f"  ! {model} [{task}] attempt {attempt} failed: {e}")
                await asyncio.sleep(2)
        return None


def list_available_models(settings: Settings) -> set[str]:
    """Fetch model IDs currently offered by OpenRouter (public endpoint)."""
    req = urllib.request.Request(OPENROUTER_MODELS_URL)
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
    return {m["id"] for m in data.get("data", [])}
