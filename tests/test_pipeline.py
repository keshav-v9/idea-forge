import asyncio
import json
from pathlib import Path

import pytest

from ideaforge.brainstorm import refine_picks, run_brainstorm
from ideaforge.cli import main
from ideaforge.config import Settings
from ideaforge.council import parse_ranking, parse_verdict, run_council
from ideaforge.mock import MockLLM
from ideaforge.report import render
from ideaforge.session import Session
from ideaforge.util import extract_json, parse_selection


def settings():
    return Settings(api_key="x", council_models=["m/a", "m/b", "m/c"], chairman="m/chair", brainstorm_model="m/brain")


# ---- parsers -------------------------------------------------------------
def test_extract_json_handles_fences_and_chatter():
    assert extract_json('Sure!\n```json\n[{"a": 1}]\n```\nHope that helps') == [{"a": 1}]
    assert extract_json('prefix [1, 2, 3] suffix') == [1, 2, 3]
    assert extract_json("no json here") is None
    assert extract_json("") is None


def test_parse_verdict_takes_last_line_and_clamps():
    text = "Format is VERDICT: GO | SCORE: 9 as asked.\nVERDICT: no-go | SCORE: 2.5"
    assert parse_verdict(text) == ("NO-GO", 2.5)
    assert parse_verdict("VERDICT: GO | SCORE: 99") == ("GO", 10.0)
    assert parse_verdict("nothing") == (None, None)


def test_parse_ranking_dedupes_and_ignores_text_before_marker():
    text = "Assessment B was best.\n\nFINAL RANKING:\n1. Assessment C\n2. Assessment A\n3. Assessment C\n"
    assert parse_ranking(text) == ["C", "A"]
    assert parse_ranking("no marker") == []


def test_parse_selection():
    assert parse_selection("1,3,5-7", 10) == [1, 3, 5, 6, 7]
    assert parse_selection("2, 2, 1", 5) == [2, 1]
    with pytest.raises(ValueError):
        parse_selection("11", 10)


# ---- pipeline ------------------------------------------------------------
def test_full_pipeline_with_mock(tmp_path):
    llm, st = MockLLM(), settings()

    async def go():
        s = await run_brainstorm(llm, st, "CS student, likes fintech", per_method=3, keep=15)
        s.picks = [1, 2]
        await refine_picks(llm, st, s)
        await run_council(llm, st, s)
        return s

    s = asyncio.run(go())
    assert len(s.ideas) >= 5
    # duplicate seed ("Invoice chaser...") from two methods must be merged with both sources
    dup = [i for i in s.ideas if i.title == "Invoice chaser for freelancers"]
    assert len(dup) == 1 and set(dup[0].sources) == {"reverse", "mind-map"}
    for pid in s.picks:
        r = s.council[str(pid)]
        assert len(r["opinions"]) == 3 and len(r["reviews"]) == 3
        assert r["chairman"]["verdict"] in {"GO", "MAYBE", "NO-GO"}
        assert sum(r["verdict_counts"].values()) == 3
        assert all(a["votes"] == 3 for a in r["aggregate_rankings"])
    assert s.overall
    assert s.idea(1).brief.startswith("## Customer")
    # call volume: per idea 3 + 3 + 1 council calls
    council_calls = [c for c in llm.calls if c[1].startswith("council")]
    assert len(council_calls) == 2 * (3 + 3 + 1)

    report = render(s)
    assert "## Scoreboard" in report and s.idea(1).title in report

    # session round-trips through JSON
    s.save(tmp_path)
    again = Session.load(tmp_path)
    assert again.picks == s.picks and again.council.keys() == s.council.keys()


def test_council_survives_a_failed_member():
    class Flaky(MockLLM):
        async def complete(self, model, prompt, *, task=""):
            if model == "m/b":
                return None
            return await super().complete(model, prompt, task=task)

    llm, st = Flaky(), settings()

    async def go():
        s = await run_brainstorm(llm, st, "p", per_method=2, keep=5)
        s.picks = [1]
        await refine_picks(llm, st, s)
        await run_council(llm, st, s)
        return s

    r = asyncio.run(go()).council["1"]
    assert {o["model"] for o in r["opinions"]} == {"m/a", "m/c"}
    assert r["chairman"] is not None


def test_brainstorm_falls_back_when_curation_is_garbage():
    class BadCurator(MockLLM):
        async def complete(self, model, prompt, *, task=""):
            if task == "curate":
                return "I refuse to answer in JSON"
            return await super().complete(model, prompt, task=task)

    s = asyncio.run(run_brainstorm(BadCurator(), settings(), "p", per_method=3, keep=15))
    assert len(s.ideas) >= 5  # local de-dupe fallback kept the pool


def test_missing_api_key_gives_clear_error(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)  # no .env here
    profile = tmp_path / "p.txt"
    profile.write_text("hello")
    assert main(["run", "--profile", str(profile), "--yes"]) == 1
    assert "OPENROUTER_API_KEY" in capsys.readouterr().err


def test_cli_end_to_end_mock(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    profile = tmp_path / "p.txt"
    profile.write_text("CS + econ student")
    assert main(["run", "--mock", "--profile", str(profile), "--pick", "1,2", "--out", "runs"]) == 0
    run_dir = next(Path("runs").glob("*/session.json")).parent
    assert (run_dir / "report.md").is_file() and (run_dir / "session.json").is_file()
    data = json.loads((run_dir / "session.json").read_text())
    assert data["picks"] == [1, 2] and len(data["council"]) == 2

    # re-run the council from the saved session, picking different ideas
    assert main(["council", str(run_dir), "--mock", "--pick", "3"]) == 0
    assert json.loads((run_dir / "session.json").read_text())["picks"] == [3]
