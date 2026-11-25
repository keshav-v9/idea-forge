"""Stage B: a 3-stage council per idea (independent opinions, anonymized peer review, chairman).

Same overall shape as Karpathy's llm-council, but the prompts are startup-specific and
adversarial: members are asked to find reasons the idea will fail and to give a scored verdict.
"""
from __future__ import annotations

import asyncio
import random
import re
import statistics

from .config import Settings
from .llm import LLM
from .session import Idea, Session

VERDICT_RE = re.compile(r"VERDICT:\s*(NO-GO|MAYBE|GO)\s*\|\s*SCORE:\s*(\d+(?:\.\d+)?)", re.I)


def parse_verdict(text: str) -> tuple[str | None, float | None]:
    """Return the LAST 'VERDICT: X | SCORE: n' line in the text (models sometimes quote the format earlier)."""
    matches = VERDICT_RE.findall(text or "")
    if not matches:
        return None, None
    verdict, score = matches[-1]
    return verdict.upper(), max(0.0, min(10.0, float(score)))


def parse_ranking(text: str) -> list[str]:
    """Labels listed after 'FINAL RANKING', best first, no duplicates."""
    if "FINAL RANKING" not in (text or ""):
        return []
    tail = text.split("FINAL RANKING")[-1]
    out: list[str] = []
    for label in re.findall(r"Assessment ([A-Z])", tail):
        if label not in out:
            out.append(label)
    return out


def _opinion_prompt(profile: str, idea: Idea) -> str:
    return f"""You are a member of a startup review panel. Your job is to find out whether this idea deserves
the founder's next three months, and to be honest, not encouraging. Most startup ideas should not be built.

FOUNDER PROFILE
{profile}

IDEA BRIEF: {idea.title}
{idea.brief}

Assess it. Be specific and cite concrete competitors, customer behaviors, or numbers where you can.
Cover, in this order:
1. Who exactly pays, and what do they do about the problem today?
2. The three most likely reasons this fails.
3. The strongest argument that it could work.
4. Can this founder build a first version in about 8 weeks, and will they find customers?
5. The cheapest test (under two weeks, under $100) that would show whether people really want it.

Finish with exactly one last line in this format, with GO, MAYBE, or NO-GO and a score from 1 to 10:
VERDICT: <GO|MAYBE|NO-GO> | SCORE: <number>"""


def _review_prompt(idea: Idea, labeled: dict[str, str]) -> str:
    body = "\n\n".join(f"Assessment {label}:\n{text}" for label, text in labeled.items())
    return f"""Several reviewers assessed the startup idea "{idea.title}". Their assessments are anonymized below.

{body}

Judge the assessments, not the idea. Reward specificity, correct reasoning, and honest identification of risks.
Do not reward an assessment for being positive or negative. First write a short critique of each assessment
(what it got right, what it missed or got wrong). Then finish with a ranking from best to worst in exactly this form:

FINAL RANKING:
1. Assessment X
2. Assessment Y
(and so on, one per line, nothing else after the list)"""


def _chairman_prompt(profile: str, idea: Idea, opinions: list[dict], reviews: list[dict]) -> str:
    ops = "\n\n".join(f"[{o['model']}] (verdict {o['verdict']}, score {o['score']})\n{o['text']}" for o in opinions)
    revs = "\n\n".join(f"[{r['model']}]\n{r['text']}" for r in reviews)
    return f"""You chair a startup review panel. Members assessed an idea, then critiqued each other's assessments.

FOUNDER PROFILE
{profile}

IDEA BRIEF: {idea.title}
{idea.brief}

MEMBER ASSESSMENTS
{ops}

PEER CRITIQUES
{revs}

Write the panel's final ruling in Markdown with these sections:
### Decision (one sentence)
### Top three reasons it could fail
### Strongest case for it
### Where the panel disagreed
### Cheapest test and what result would count as a pass
### What would change the panel's mind

Weigh the critiques; do not simply average the members. Finish with exactly one last line:
VERDICT: <GO|MAYBE|NO-GO> | SCORE: <number from 1 to 10>"""


async def run_idea(llm: LLM, settings: Settings, profile: str, idea: Idea) -> dict:
    models = settings.council_models

    # Stage 1: independent opinions
    raw = await asyncio.gather(*(llm.complete(m, _opinion_prompt(profile, idea), task="council_s1") for m in models))
    opinions = []
    for model, text in zip(models, raw):
        if text:
            verdict, score = parse_verdict(text)
            opinions.append({"model": model, "text": text, "verdict": verdict, "score": score})
    if not opinions:
        return {"error": "no council member responded", "opinions": [], "reviews": [], "chairman": None}

    # Stage 2: anonymized peer review (labels shuffled deterministically per idea)
    order = list(range(len(opinions)))
    random.Random(idea.id).shuffle(order)
    labels = {chr(65 + pos): opinions[idx] for pos, idx in enumerate(order)}
    label_to_model = {lab: op["model"] for lab, op in labels.items()}
    review_prompt = _review_prompt(idea, {lab: op["text"] for lab, op in labels.items()})
    raw = await asyncio.gather(*(llm.complete(m, review_prompt, task="council_s2") for m in models))
    reviews = []
    for model, text in zip(models, raw):
        if text:
            reviews.append({"model": model, "text": text, "ranking": parse_ranking(text)})

    positions: dict[str, list[int]] = {}
    for r in reviews:
        for pos, label in enumerate(r["ranking"], start=1):
            if label in label_to_model:
                positions.setdefault(label_to_model[label], []).append(pos)
    aggregate = sorted(
        ({"model": m, "average_rank": round(sum(p) / len(p), 2), "votes": len(p)} for m, p in positions.items()),
        key=lambda x: x["average_rank"],
    )

    # Stage 3: chairman
    text = await llm.complete(
        settings.chairman, _chairman_prompt(profile, idea, opinions, reviews), task="council_s3"
    )
    chairman = None
    if text:
        verdict, score = parse_verdict(text)
        chairman = {"model": settings.chairman, "text": text, "verdict": verdict, "score": score}

    scores = [o["score"] for o in opinions if o["score"] is not None]
    return {
        "opinions": opinions,
        "reviews": reviews,
        "aggregate_rankings": aggregate,
        "chairman": chairman,
        "mean_score": round(statistics.mean(scores), 2) if scores else None,
        "verdict_counts": {v: sum(1 for o in opinions if o["verdict"] == v) for v in ("GO", "MAYBE", "NO-GO")},
    }


async def run_council(llm: LLM, settings: Settings, session: Session) -> None:
    ideas = [session.idea(i) for i in session.picks]
    results = await asyncio.gather(*(run_idea(llm, settings, session.profile, idea) for idea in ideas))
    for idea, result in zip(ideas, results):
        session.council[str(idea.id)] = result
    session.overall = await overall_recommendation(llm, settings, session)


def ranked_ideas(session: Session) -> list[tuple[Idea, dict]]:
    """Picked ideas, best first. Chairman score wins; mean member score breaks ties/fills gaps."""
    def key(pair):
        _, res = pair
        ch = (res.get("chairman") or {}).get("score")
        return (ch if ch is not None else -1, res.get("mean_score") or -1)

    pairs = [(session.idea(i), session.council.get(str(i), {})) for i in session.picks]
    return sorted(pairs, key=key, reverse=True)


async def overall_recommendation(llm: LLM, settings: Settings, session: Session) -> str:
    lines = []
    for idea, res in ranked_ideas(session):
        ch = res.get("chairman") or {}
        lines.append(
            f"- {idea.title}: chairman {ch.get('verdict')} / {ch.get('score')}, "
            f"member mean {res.get('mean_score')}, votes {res.get('verdict_counts')}\n"
            f"  Ruling excerpt: {(ch.get('text') or '')[:600]}"
        )
    prompt = f"""You chair a startup review panel that has ruled on several ideas for one founder.

FOUNDER PROFILE
{session.profile}

RULINGS
{chr(10).join(lines)}

In Markdown, no more than 200 words: say which single idea the founder should test first and why, which
ideas to drop, and the one concrete thing to do this week. If every idea is weak, say so plainly and
describe what a better idea would need."""
    return (await llm.complete(settings.chairman, prompt, task="overall")) or ""
