"""Command line interface: brainstorm -> shortlist -> refine -> council -> report."""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime
from pathlib import Path

from .brainstorm import refine_picks, run_brainstorm
from .config import Settings
from .council import run_council
from .llm import LLM, OpenRouterClient, list_available_models
from .methods import GENERATION_METHODS
from .mock import MockLLM
from .report import render
from .session import Session
from .util import parse_selection, slugify

PROFILE_QUESTIONS = [
    ("Your background and strengths (skills, experience, unfair advantages)", ""),
    ("Problems you've personally run into, or areas you find interesting", ""),
    ("Constraints (time per week, budget, what you do NOT want to build)", ""),
]


def _client(settings: Settings, mock: bool) -> LLM:
    return MockLLM() if mock else OpenRouterClient(settings)


def _ask_profile(path: str | None) -> str:
    if path:
        return Path(path).read_text().strip()
    print("Tell the brainstormers about yourself. Specific answers give better ideas.\n")
    parts = []
    for question, _ in PROFILE_QUESTIONS:
        answer = input(question + "\n> ").strip()
        parts.append(question + ":\n" + answer)
    return "\n\n".join(parts)


def _show_ideas(session: Session) -> None:
    print()
    for i in session.ideas:
        print(f"{i.id:>2}. {i.title}  [{', '.join(i.sources)}]\n    {i.pitch}\n    Customer: {i.customer} | Problem: {i.problem}")
    print()


def _choose(session: Session, pick: str | None, assume_yes: bool, max_picks: int) -> list[int]:
    n = len(session.ideas)
    if pick:
        return parse_selection(pick, n)
    if assume_yes:
        return list(range(1, min(n, 3) + 1))
    while True:
        raw = input(f"Shortlist up to {max_picks} ideas to stress-test (e.g. 1,4,7 or 2-4): ").strip()
        try:
            picks = parse_selection(raw, n)
        except ValueError as e:
            print(f"  {e}")
            continue
        if not picks:
            print("  Pick at least one.")
        elif len(picks) > max_picks:
            print(f"  Max {max_picks} (each idea costs several model calls).")
        else:
            return picks


def _new_run_dir(root: str, tag: str) -> Path:
    return Path(root) / f"{datetime.now():%Y%m%d-%H%M%S}-{slugify(tag)}"


async def _council_and_report(llm: LLM, settings: Settings, session: Session, out_dir: Path) -> Path:
    calls = len(session.picks) * (2 * len(settings.council_models) + 1) + 1
    print(f"\nRunning council on {len(session.picks)} idea(s): about {calls} model calls...")
    await run_council(llm, settings, session)
    session.save(out_dir)
    report = out_dir / "report.md"
    report.write_text(render(session))
    return report


async def cmd_run(args) -> int:
    settings = Settings.from_env()
    llm = _client(settings, args.mock)
    profile = _ask_profile(args.profile)
    methods = args.methods.split(",") if args.methods else None
    for m in methods or []:
        if m not in GENERATION_METHODS:
            print(f"Unknown method {m!r}. Choose from: {', '.join(GENERATION_METHODS)}")
            return 2

    print("\n[1/4] Brainstorming...")
    session = await run_brainstorm(llm, settings, profile, methods, args.per_method, args.keep)
    out_dir = _new_run_dir(args.out, session.ideas[0].title if session.ideas else "run")
    session.save(out_dir)
    _show_ideas(session)

    session.picks = _choose(session, args.pick, args.yes, args.max_picks)
    print("\n[2/4] Writing briefs for your shortlist...")
    await refine_picks(llm, settings, session)
    session.save(out_dir)

    print("[3/4] Council deliberating...")
    report = await _council_and_report(llm, settings, session, out_dir)
    print(f"\n[4/4] Done. Report: {report}\n")
    print(session.overall)
    return 0


async def cmd_brainstorm(args) -> int:
    settings = Settings.from_env()
    llm = _client(settings, args.mock)
    session = await run_brainstorm(llm, settings, _ask_profile(args.profile), None, args.per_method, args.keep)
    out_dir = _new_run_dir(args.out, session.ideas[0].title)
    session.save(out_dir)
    _show_ideas(session)
    print(f"Saved to {out_dir}. Next: ideaforge council {out_dir} --pick 1,3")
    return 0


async def cmd_council(args) -> int:
    settings = Settings.from_env()
    llm = _client(settings, args.mock)
    out_dir = Path(args.session)
    session = Session.load(out_dir)
    session.picks = _choose(session, args.pick, args.yes, args.max_picks) if (args.pick or args.yes or not session.picks) else session.picks
    await refine_picks(llm, settings, session)
    report = await _council_and_report(llm, settings, session, out_dir)
    print(f"Done. Report: {report}\n\n{session.overall}")
    return 0


async def cmd_check(args) -> int:
    settings = Settings.from_env()
    print("API key:", "set" if settings.api_key else "MISSING (add OPENROUTER_API_KEY to .env)")
    wanted = {
        "council": settings.council_models,
        "chairman": [settings.chairman],
        "brainstorm": [settings.brainstorm_model],
    }
    try:
        available = list_available_models(settings)
    except Exception as e:
        print(f"Could not reach OpenRouter to verify model IDs: {e}")
        return 1
    bad = 0
    for role, models in wanted.items():
        for m in models:
            ok = m in available
            bad += not ok
            print(f"  {'ok     ' if ok else 'MISSING'} {role}: {m}")
    if bad:
        print("\nSet IDEAFORGE_COUNCIL_MODELS / IDEAFORGE_CHAIRMAN / IDEAFORGE_BRAINSTORM_MODEL in .env to valid IDs.")
    return 1 if bad else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="ideaforge", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp, council=False):
        sp.add_argument("--mock", action="store_true", help="use a fake model; no API calls or key needed")
        sp.add_argument("--pick", help="idea numbers to shortlist, e.g. 1,4,7 (skips the prompt)")
        sp.add_argument("--yes", action="store_true", help="non-interactive: shortlist the first 3 ideas if --pick is absent")
        sp.add_argument("--max-picks", type=int, default=5)

    r = sub.add_parser("run", help="full flow: brainstorm, shortlist, council, report")
    common(r)
    r.add_argument("--profile", help="text file with your background/interests/constraints (skips questions)")
    r.add_argument("--methods", help=f"comma-separated subset of: {', '.join(GENERATION_METHODS)}")
    r.add_argument("--per-method", type=int, default=6)
    r.add_argument("--keep", type=int, default=15, help="ideas kept after curation")
    r.add_argument("--out", default="runs")
    r.set_defaults(fn=cmd_run)

    b = sub.add_parser("brainstorm", help="only the brainstorming stage")
    b.add_argument("--mock", action="store_true")
    b.add_argument("--profile")
    b.add_argument("--per-method", type=int, default=6)
    b.add_argument("--keep", type=int, default=15)
    b.add_argument("--out", default="runs")
    b.set_defaults(fn=cmd_brainstorm)

    c = sub.add_parser("council", help="run the council on a saved session directory")
    common(c)
    c.add_argument("session", help="run directory containing session.json")
    c.set_defaults(fn=cmd_council)

    k = sub.add_parser("check", help="verify API key and that configured model IDs exist")
    k.set_defaults(fn=cmd_check)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return asyncio.run(args.fn(args))
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return 130
    except RuntimeError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
