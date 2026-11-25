"""Specialist council agents. Each examines an idea from one angle only."""
from __future__ import annotations

import re

from .session import Idea

ANGLES: dict[str, tuple[str, str]] = {
    "growth": (
        "Long-term growth & market feasibility",
        "Estimate market size bottom-up (customers x price). Is the market growing or shrinking, and why? Describe "
        "a realistic year 1, year 3, and year 5. What caps growth, what could it expand into, and is it still "
        "viable if AI models or incumbents improve a lot?",
    ),
    "customer": (
        "Customer demand",
        "How painful and frequent is the problem? What do customers use today, what triggers a purchase, who "
        "controls the budget, and why might they like it but never pay or stop using it?",
    ),
    "competition": (
        "Competition & moat",
        "Name direct competitors, substitutes, and the do-nothing option. Who could copy this in a month? What "
        "advantage would compound over time, if any?",
    ),
    "economics": (
        "Business model & unit economics",
        "Judge pricing, gross margin, acquisition cost, retention, and payback. How many customers are needed "
        "for $10k a month, and is that reachable?",
    ),
    "go-to-market": (
        "Go-to-market",
        "How exactly does this founder reach the first 10, 100, and 1000 customers? Judge channels, sales cycle "
        "length, trust barriers, and repeatability.",
    ),
    "technical": (
        "Product & technical feasibility",
        "Can the MVP be built in about 8 weeks? Find the hardest component, dependencies on third parties or "
        "data access, quality bar, security, and maintenance burden.",
    ),
    "legal": (
        "Legal, ethical & regulatory risk",
        "Cover licensing, privacy, liability, platform terms, IP, and possible harm to users. Separate "
        "deal-breakers from manageable risks.",
    ),
    "founder": (
        "Founder fit",
        "Does this founder have the skills, access, time, and motivation for this idea? What is missing, and "
        "would someone else have a much better shot?",
    ),
}

_SCORE_RE = re.compile(r"ANGLE SCORE:\s*\**\s*(\d+(?:\.\d+)?)", re.I)


def parse_angle_score(text: str) -> float | None:
    matches = _SCORE_RE.findall(text or "")
    return max(0.0, min(10.0, float(matches[-1]))) if matches else None


def angle_prompt(key: str, profile: str, idea: Idea) -> str:
    name, focus = ANGLES[key]
    return f"""You are the {name} specialist on a startup review panel. Judge only this angle; others cover the rest.

FOUNDER PROFILE
{profile}

IDEA BRIEF: {idea.title}
{idea.description}

{idea.brief}

YOUR FOCUS
{focus}

Be skeptical and specific. Label estimates and state their assumptions; do not invent facts or sources. In
Markdown, 300 words maximum, give: your bottom line, key findings, the biggest risk, the biggest opportunity,
and one change that would improve the idea on this angle.

Finish with exactly one last line, from 1 (fatal) to 10 (excellent):
ANGLE SCORE: <number>"""


def council_calls(n_ideas: int, n_models: int, n_angles: int) -> int:
    return n_ideas * (2 * n_models + n_angles + 1) + 1
