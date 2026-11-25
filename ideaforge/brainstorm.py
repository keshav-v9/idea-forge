"""Stage A: generate an idea pool, curate it, and refine the shortlist into briefs."""
from __future__ import annotations

import asyncio
import json

from .config import Settings
from .llm import LLM
from .methods import GENERATION_METHODS, curate_prompt, generation_prompt, refine_prompt, revise_prompt
from .session import Idea, Session
from .util import extract_json


def _coerce(item: dict, sources: list[str]) -> dict | None:
    title = str(item.get("title", "")).strip()
    pitch = str(item.get("pitch", "")).strip()
    if not title or not pitch:
        return None
    return {
        "title": title,
        "pitch": pitch,
        "description": str(item.get("description", "")).strip(),
        "customer": str(item.get("customer", "")).strip(),
        "problem": str(item.get("problem", "")).strip(),
        "sources": [str(s) for s in item.get("sources", sources)] or sources,
    }


async def generate_pool(
    llm: LLM, settings: Settings, profile: str, methods: list[str], per_method: int
) -> list[dict]:
    async def one(method: str) -> list[dict]:
        text = await llm.complete(
            settings.brainstorm_model, generation_prompt(method, profile, per_method), task=f"brainstorm:{method}"
        )
        data = extract_json(text or "")
        if not isinstance(data, list):
            print(f"  ! method '{method}' returned nothing usable; skipping it")
            return []
        return [c for c in (_coerce(i, [method]) for i in data if isinstance(i, dict)) if c]

    results = await asyncio.gather(*(one(m) for m in methods))
    return [idea for batch in results for idea in batch]


def _local_dedupe(pool: list[dict], n: int) -> list[dict]:
    seen: dict[str, dict] = {}
    for idea in pool:
        key = " ".join(idea["title"].lower().split())
        if key in seen:
            seen[key]["sources"] = sorted(set(seen[key]["sources"]) | set(idea["sources"]))
        else:
            seen[key] = dict(idea)
    return list(seen.values())[:n]


async def curate(llm: LLM, settings: Settings, profile: str, pool: list[dict], n: int) -> list[dict]:
    text = await llm.complete(
        settings.brainstorm_model, curate_prompt(profile, json.dumps(pool, indent=1), n), task="curate"
    )
    data = extract_json(text or "")
    if isinstance(data, list):
        cleaned = [c for c in (_coerce(i, ["curated"]) for i in data if isinstance(i, dict)) if c]
        if cleaned:
            return cleaned[:n]
    print("  ! curation failed; falling back to simple de-duplication")
    return _local_dedupe(pool, n)


async def run_brainstorm(
    llm: LLM,
    settings: Settings,
    profile: str,
    methods: list[str] | None = None,
    per_method: int = 6,
    keep: int = 15,
) -> Session:
    methods = methods or list(GENERATION_METHODS)
    pool = await generate_pool(llm, settings, profile, methods, per_method)
    if not pool:
        reason = getattr(llm, "last_error", "") or "The models returned nothing usable."
        raise RuntimeError(f"No ideas were generated. {reason}")
    curated = await curate(llm, settings, profile, pool, keep)
    ideas = [Idea(id=i, **c) for i, c in enumerate(curated, start=1)]
    return Session(profile=profile, ideas=ideas)


async def revise_ideas(llm: LLM, settings: Settings, session: Session, feedback: str) -> None:
    """Rewrite session.ideas per the feedback. Leaves the session untouched if the model fails."""
    keys = ("title", "pitch", "description", "customer", "problem", "sources")
    current = [{k: getattr(i, k) for k in keys} for i in session.ideas]
    prompt = revise_prompt(session.profile, json.dumps(current, indent=1), feedback, len(current))
    data = extract_json(await llm.complete(settings.brainstorm_model, prompt, task="revise") or "")
    items = data if isinstance(data, list) else []
    cleaned = [c for c in (_coerce(i, ["revised"]) for i in items if isinstance(i, dict)) if c]
    if not cleaned:
        reason = getattr(llm, "last_error", "") or "The model did not return a usable revision."
        raise RuntimeError(f"Your list is unchanged. {reason}")
    session.ideas = [Idea(id=i, **c) for i, c in enumerate(cleaned, start=1)]
    session.picks, session.council, session.overall = [], {}, ""
    session.feedback.append(feedback)


async def refine_picks(llm: LLM, settings: Settings, session: Session) -> None:
    async def one(idea: Idea) -> None:
        text = await llm.complete(
            settings.brainstorm_model,
            refine_prompt(session.profile, idea.title, idea.pitch, idea.customer, idea.problem, idea.description),
            task="refine",
        )
        # If refinement fails, the council still gets the raw pitch rather than nothing.
        idea.brief = (text or "").strip() or f"{idea.pitch}\n\n{idea.description}\n\nCustomer: {idea.customer}\nProblem: {idea.problem}"

    todo = [session.idea(i) for i in session.picks if not session.idea(i).brief]  # skip briefs already written
    await asyncio.gather(*(one(idea) for idea in todo))
