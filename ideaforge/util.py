"""Small helpers: tolerant JSON extraction, slugs, label handling."""
from __future__ import annotations

import json
import re


def extract_json(text: str):
    """Pull the first JSON array/object out of an LLM reply (handles ``` fences and chatter)."""
    if not text:
        return None
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    candidates = [fenced.group(1)] if fenced else []
    candidates.append(text)
    for cand in candidates:
        for opener, closer in (("[", "]"), ("{", "}")):
            start = cand.find(opener)
            end = cand.rfind(closer)
            if start != -1 and end > start:
                try:
                    return json.loads(cand[start : end + 1])
                except json.JSONDecodeError:
                    continue
    return None


def slugify(text: str, limit: int = 40) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:limit].strip("-") or "run"


def parse_selection(raw: str, max_n: int) -> list[int]:
    """'1,3,5-7' -> [1, 3, 5, 6, 7], validated against 1..max_n, order kept, no dupes."""
    out: list[int] = []
    for part in raw.replace(" ", "").split(","):
        if not part:
            continue
        if "-" in part:
            a, _, b = part.partition("-")
            nums = range(int(a), int(b) + 1)
        else:
            nums = [int(part)]
        for n in nums:
            if not 1 <= n <= max_n:
                raise ValueError(f"{n} is outside 1..{max_n}")
            if n not in out:
                out.append(n)
    return out
