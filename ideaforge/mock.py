"""Deterministic fake model used by --mock and the tests. Makes no network calls."""
from __future__ import annotations

import json
import re
import zlib

_SEEDS = {
    "reverse": ["Invoice chaser for freelancers", "Clinic no-show reminder bot", "Lease clause checker"],
    "role-storm": ["Dispatcher route-change alerts", "Compliance evidence collector", "Parent schedule merger"],
    "scamper": ["Lightweight CRM for tutors", "Trade journal auto-tagger", "Expense splitter for clubs"],
    "mind-map": ["Latency dashboard for retail traders", "Campus sublease marketplace", "Invoice chaser for freelancers"],
}


def _h(*parts: str) -> int:
    return zlib.crc32("|".join(parts).encode())


class MockLLM:
    def __init__(self):
        self.calls: list[tuple[str, str]] = []

    async def complete(self, model: str, prompt: str, *, task: str = "") -> str | None:
        self.calls.append((model, task))
        if task.startswith("brainstorm:"):
            method = task.split(":", 1)[1]
            ideas = [
                {"title": t, "pitch": f"{t}: saves its customer hours each week.", "customer": "small teams", "problem": "manual, error-prone busywork"}
                for t in _SEEDS[method]
            ]
            return "Here you go:\n```json\n" + json.dumps(ideas) + "\n```"
        if task == "curate":
            pool = json.loads(prompt[prompt.index("[") : prompt.rindex("]") + 1])
            merged: dict[str, dict] = {}
            for item in pool:
                cur = merged.setdefault(item["title"], {**item, "sources": []})
                cur["sources"] = sorted(set(cur["sources"]) | set(item.get("sources", [])))
            return json.dumps(list(merged.values()))
        if task == "refine":
            return "## Customer and problem\nMock brief.\n## Riskiest assumptions\nCustomers will pay."
        if task == "council_s1":
            score = 3 + _h(model, prompt) % 6  # 3..8
            verdict = "GO" if score >= 7 else "MAYBE" if score >= 5 else "NO-GO"
            return f"Mock assessment from {model}. Likely failure: crowded market.\nVERDICT: {verdict} | SCORE: {score}"
        if task == "council_s2":
            labels = sorted(set(re.findall(r"^Assessment ([A-Z]):", prompt, re.M)))
            order = sorted(labels, key=lambda l: _h(model, l))
            ranking = "\n".join(f"{i}. Assessment {l}" for i, l in enumerate(order, 1))
            return f"Critique: all assessments reasonable.\n\nFINAL RANKING:\n{ranking}"
        if task == "council_s3":
            score = 3 + _h(prompt) % 6
            verdict = "GO" if score >= 7 else "MAYBE" if score >= 5 else "NO-GO"
            return f"### Decision\nMock ruling.\nVERDICT: {verdict} | SCORE: {score}"
        if task == "overall":
            return "Test the highest-scoring idea first; drop the rest. This week: interview 10 customers."
        return "mock"
