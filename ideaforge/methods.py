"""Brainstorming methods, adapted as startup-idea prompts.

Generation methods (reverse, role-storm, SCAMPER, mind map) fill the idea pool.
Analysis methods (Six Thinking Hats, Starbursting) are used later to turn a
shortlisted idea into a concrete brief before the council sees it.
All prompt text here is original; the techniques themselves are standard.
"""
from __future__ import annotations

GENERATION_METHODS = ["reverse", "role-storm", "scamper", "mind-map"]

_HEADER = """You are helping a first-time founder find a startup idea worth testing.

FOUNDER PROFILE
{profile}

Rules for every idea:
- Name a specific customer type and a concrete, painful problem they have today.
- A first version must be buildable by one or two people in about 8 weeks.
- It must fit the founder's strengths and constraints above.
- No filler such as "Uber for X" or "an AI platform for Y". Prefer problems the founder
  has seen firsthand or can reach customers for easily.

OUTPUT: Reply with ONLY a JSON array of exactly {n} objects and no other text. Each object
has the keys "title" (8 words or fewer), "pitch" (one sentence), "description" (2-3 plain
sentences: what the product is, what the customer does with it, and how it works), "customer" (who pays),
and "problem" (the painful problem today, one sentence).
"""

_METHODS = {
    "reverse": """METHOD: Reverse brainstorming.
First, privately list ways a saboteur could make daily work or life worse for people in
areas where the founder has insight: more tedious, costlier, riskier, slower, more confusing.
Then flip the {n} most painful sabotages into products that remove that pain.""",
    "role-storm": """METHOD: Role storming.
Take the viewpoint of each of these people and ask what annoys them most and what they would
happily pay to make go away: an overworked small-business owner, a compliance officer, a
freelancer, a college student, a hospital administrator, a retail investor, a parent of
three, a skeptical venture investor, a logistics dispatcher. Turn the strongest {n}
frustrations into products, spreading ideas across different roles.""",
    "scamper": """METHOD: SCAMPER.
Pick a few well-known software products or workflows in areas the founder knows. Apply
Substitute, Combine, Adapt, Modify, Put to another use, Eliminate, and Reverse to find
underserved gaps (for example a product that is too complex, too expensive, or built for
the wrong customer). Turn the best {n} gaps into new products.""",
    "mind-map": """METHOD: Big mind map.
Start from the founder's interests and skills. Branch into broad domains, branch each into
sub-problems, and look for leaves where a small team could ship something useful fast.
Return the {n} best leaves, drawn from at least four different branches.""",
}


def generation_prompt(method: str, profile: str, n: int) -> str:
    if method not in _METHODS:
        raise ValueError(f"unknown method {method!r}; choose from {GENERATION_METHODS}")
    return _HEADER.format(profile=profile, n=n) + "\n" + _METHODS[method].format(n=n)


def curate_prompt(profile: str, pool_json: str, n: int) -> str:
    return f"""You are an experienced startup advisor curating a pool of raw ideas for a first-time founder.

FOUNDER PROFILE
{profile}

RAW POOL (JSON; each item has a "sources" list naming the methods that produced it):
{pool_json}

Merge near-duplicates, drop vague or unbuildable ones, and keep the {n} most distinct, specific, promising
ideas. When you merge, combine their "sources" lists. Do not invent new ideas.

OUTPUT: Reply with ONLY a JSON array of at most {n} objects with the keys "title", "pitch",
"description" (2-3 plain sentences on what the product is and how it works), "customer", "problem", and
"sources". No other text."""


def revise_prompt(profile: str, ideas_json: str, feedback: str, n: int) -> str:
    return f"""You are helping a first-time founder revise a list of startup ideas.

FOUNDER PROFILE
{profile}

CURRENT IDEAS (JSON)
{ideas_json}

FOUNDER FEEDBACK
{feedback}

Apply the feedback faithfully. Ideas the feedback does not affect must be returned unchanged, word for word.
Change, drop, replace, or add ideas only as the feedback asks. Return {n} ideas unless the feedback asks for a
different number. Every new or changed idea needs a specific paying customer and a concrete painful problem, must be
buildable by one or two people in about 8 weeks, and must fit the founder's profile unless the feedback overrides it.

OUTPUT: Reply with ONLY a JSON array of objects with the keys "title", "pitch" (one sentence), "description"
(2-3 plain sentences on what the product is and how it works), "customer", "problem", and "sources" (keep the
existing list for unchanged ideas; add "revised" for changed or new ones). No other text."""


def refine_prompt(
    profile: str, idea_title: str, pitch: str, customer: str, problem: str, description: str = ""
) -> str:
    return f"""Turn this raw startup idea into a concrete one-page brief for a skeptical review panel.

FOUNDER PROFILE
{profile}

IDEA: {idea_title}
Pitch: {pitch}
Description: {description}
Customer: {customer}
Problem: {problem}

Think it through with two techniques before you write:
- Six Thinking Hats: facts (what is known), gut feeling, risks (black hat), benefits (yellow hat),
  creative alternatives (green hat), and process (blue hat).
- Starbursting: ask who, what, where, when, why, and how, and answer what you can.

Then write the brief in Markdown, 350 words maximum, with exactly these sections:
## Customer and problem
## Solution
## Why now
## First 10 customers (how the founder would reach them)
## 8-week MVP
## How it makes money
## Riskiest assumptions
## Open questions (one each for who, what, where, when, why, how)

Be concrete. Where something is unknown, say so instead of guessing."""
