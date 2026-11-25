import asyncio
import json
from pathlib import Path

import pytest

from ideaforge.angles import ANGLES, parse_angle_score
from ideaforge.brainstorm import refine_picks, revise_ideas, run_brainstorm
from ideaforge.config import Settings
from ideaforge.council import run_council
from ideaforge.mock import MockLLM
from ideaforge.report import render
from ideaforge.storage import new_run_dir

APP = str(Path(__file__).parent.parent / "streamlit_app.py")


def settings():
    return Settings(api_key="x", council_models=["m/a", "m/b"], chairman="m/c", brainstorm_model="m/d")


def test_descriptions_revision_and_angles():
    async def go():
        llm, cfg = MockLLM(), settings()
        s = await run_brainstorm(llm, cfg, "p")
        assert all(i.description for i in s.ideas)
        await revise_ideas(llm, cfg, s, "change [the first] one")
        assert s.ideas[0].title.endswith("(revised)")
        s.picks = [1]
        await refine_picks(llm, cfg, s)
        await run_council(llm, cfg, s)
        return s

    s = asyncio.run(go())
    assert [a["key"] for a in s.council["1"]["angles"]] == list(ANGLES)
    assert all(a["score"] is not None for a in s.council["1"]["angles"])
    assert "Long-term growth" in render(s)


def test_failed_revision_keeps_ideas():
    class Bad(MockLLM):
        async def complete(self, model, prompt, *, task=""):
            return None if task == "revise" else await super().complete(model, prompt, task=task)

    async def go():
        s = await run_brainstorm(Bad(), settings(), "p")
        before = list(s.ideas)
        with pytest.raises(RuntimeError):
            await revise_ideas(Bad(), settings(), s, "x")
        assert s.ideas == before

    asyncio.run(go())


def test_parse_angle_score():
    assert parse_angle_score("ANGLE SCORE: 3\nANGLE SCORE: **7.5**") == 7.5
    assert parse_angle_score("none") is None


def test_streamlit_flow(tmp_path, monkeypatch):
    testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    def click(app, label):
        next(b for b in app.button if b.label == label).click()
        app.run()
        assert not app.exception

    app = testing.AppTest.from_file(APP, default_timeout=30).run()
    assert not app.exception and app.toggle[0].value
    app.text_area[0].input("CS student")
    click(app, "Brainstorm ideas")
    app.text_area[0].input("change the first")
    click(app, "Revise ideas")
    assert app.session_state.session.ideas[0].title.endswith("(revised)")
    click(app, "Undo last revision")
    assert not app.session_state.session.ideas[0].title.endswith("(revised)")
    app.checkbox[0].check().run()
    click(app, "Run council")
    assert len(app.session_state.session.council["1"]["angles"]) == len(ANGLES)
    assert list(Path("runs").glob("*/report.md"))
    click(app, "Back to ideas")
    click(app, "New run / open saved run")

    app.selectbox[0].select_index(len(app.selectbox[0].options) - 1)
    click(app, "Open saved run")
    assert app.session_state.session.ideas and app.session_state.session.mock

    # a brand-new app process sees the same saved work
    again = testing.AppTest.from_file(APP, default_timeout=30).run()
    assert again.text_area[0].value == "CS student"
    reports = [i for i, label in enumerate(again.selectbox[0].options) if "report" in label]
    again.selectbox[0].select_index(reports[0])
    click(again, "Open saved run")
    assert again.session_state.session.council

    log = next(Path("runs/calls").glob("*.jsonl")).read_text().splitlines()
    tasks = {json.loads(line)["task"] for line in log}
    assert {"brainstorm:reverse", "curate", "revise", "refine", "angle:growth", "council_s3", "overall"} <= tasks


def test_run_dirs_never_collide(tmp_path):
    first = new_run_dir("same", tmp_path)
    first.mkdir()
    assert new_run_dir("same", tmp_path) != first
