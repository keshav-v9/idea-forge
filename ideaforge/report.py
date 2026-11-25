"""Render a Markdown report from a finished session."""
from __future__ import annotations

from .council import ranked_ideas
from .session import Session


def _fmt(x) -> str:
    return "n/a" if x is None else str(x)


def render(session: Session) -> str:
    out = ["# Idea Forge report", "", "## Founder profile", "", session.profile.strip(), ""]
    out += ["## Scoreboard", "", "| Rank | Idea | Chairman | Member mean | GO / MAYBE / NO-GO |", "|---|---|---|---|---|"]
    ranked = ranked_ideas(session)
    for n, (idea, res) in enumerate(ranked, 1):
        ch = res.get("chairman") or {}
        vc = res.get("verdict_counts") or {}
        out.append(
            f"| {n} | {idea.title} | {_fmt(ch.get('verdict'))} {_fmt(ch.get('score'))} | "
            f"{_fmt(res.get('mean_score'))} | {vc.get('GO', 0)} / {vc.get('MAYBE', 0)} / {vc.get('NO-GO', 0)} |"
        )
    if session.overall:
        out += ["", "## Overall recommendation", "", session.overall.strip()]

    out += ["", "## Rulings"]
    for idea, res in ranked:
        out += ["", f"### {idea.title}", f"*{idea.pitch}*", "", idea.description, "", f"Sources: {', '.join(idea.sources) or 'n/a'}", ""]
        if res.get("error"):
            out += [f"Council failed: {res['error']}"]
            continue
        ch = res.get("chairman")
        out += [ch["text"].strip().replace("### ", "#### ") if ch else "_Chairman did not respond._", ""]
        angles = res.get("angles", [])
        if angles:
            out += ["#### Scores by angle", "", "| Angle | Score |", "|---|---|"]
            out += [f"| {a['name']} | {_fmt(a['score'])} |" for a in angles]
            out += ["", "<details><summary>Specialist reports</summary>", ""]
            for a in angles:
                out += [f"**{a['name']}** ({a['model']})", "", a["text"].strip(), ""]
            out += ["</details>", ""]
        out += ["<details><summary>Individual member assessments</summary>", ""]
        for op in res.get("opinions", []):
            out += [f"**{op['model']}** ({_fmt(op['verdict'])} {_fmt(op['score'])})", "", op["text"].strip(), ""]
        out += ["</details>", "", "<details><summary>Brief the council saw</summary>", "", idea.brief.strip(), "", "</details>"]

    out += ["", "## Ideas that were not shortlisted", ""]
    picked = set(session.picks)
    out += [f"- {i.title}: {i.pitch}" for i in session.ideas if i.id not in picked] or ["- none"]
    return "\n".join(out) + "\n"
