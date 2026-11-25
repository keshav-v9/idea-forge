"""Streamlit UI for idea-forge. Run with: streamlit run streamlit_app.py"""
from __future__ import annotations

import asyncio
import copy
from pathlib import Path

import streamlit as st

from ideaforge.angles import ANGLES, council_calls
from ideaforge.brainstorm import refine_picks, revise_ideas, run_brainstorm
from ideaforge.cli import PROFILE_QUESTIONS
from ideaforge.config import Settings
from ideaforge.council import ranked_ideas, run_council
from ideaforge.llm import LLM, OpenRouterClient
from ideaforge.methods import GENERATION_METHODS
from ideaforge.mock import MockLLM
from ideaforge.report import render
from ideaforge.session import Session
from ideaforge.storage import RecordingLLM, list_runs, load_profile, new_run_dir, run_label, save_profile

st.set_page_config(page_title="Idea Forge", layout="wide")

ss = st.session_state
ss.setdefault("session", None)
ss.setdefault("out_dir", None)
ss.setdefault("previous", None)
settings = Settings.from_env()


def client() -> LLM:
    return RecordingLLM(MockLLM() if ss.mock else OpenRouterClient(settings))


def md(text: str) -> None:
    # Streamlit treats paired dollar signs as LaTeX, which mangles prices.
    st.markdown(text.replace("$", "\\$"))


def fmt(value) -> str:
    return "n/a" if value is None else str(value)


def clear_picks() -> None:
    for key in [k for k in ss if str(k).startswith("pick_")]:
        del ss[key]


def open_run(labels: dict[str, Path]) -> None:
    path = labels[ss.saved_run]
    try:
        session = Session.load(path)
    except (ValueError, TypeError, OSError) as e:
        ss.open_error = f"Could not open {path.name}: {e}"
        return
    clear_picks()
    ss.session, ss.out_dir, ss.previous = session, path, None
    ss.mock = session.mock


def show_profile_form() -> None:
    st.header("1. About you")
    with st.form("profile"):
        saved = load_profile(len(PROFILE_QUESTIONS))
        answers = [st.text_area(q, value=v) for (q, _), v in zip(PROFILE_QUESTIONS, saved)]
        submitted = st.form_submit_button("Brainstorm ideas", type="primary")
    if not submitted:
        return
    if not any(a.strip() for a in answers):
        st.error("Fill in at least one box.")
        return
    save_profile(answers)
    if not ss.methods:
        st.error("Choose at least one brainstorm method in the sidebar.")
        return
    profile = "\n\n".join(f"{q}:\n{a.strip()}" for (q, _), a in zip(PROFILE_QUESTIONS, answers))
    try:
        with st.spinner("Brainstorming..."):
            session = asyncio.run(
                run_brainstorm(client(), settings, profile, ss.methods, ss.per_method, ss.keep)
            )
    except RuntimeError as e:
        st.error(str(e))
        return
    clear_picks()
    ss.out_dir = new_run_dir(session.ideas[0].title)
    session.mock = ss.mock
    session.save(ss.out_dir)
    ss.session, ss.previous = session, None
    st.rerun()


def show_revision(session: Session) -> None:
    st.subheader("Change the list")
    with st.form("revise", clear_on_submit=True):
        feedback = st.text_area(
            "What should change?",
            placeholder="Drop the healthcare ideas, make #3 for students instead, add two B2B ideas",
        )
        submitted = st.form_submit_button("Revise ideas")
    if submitted:
        if not feedback.strip():
            st.error("Say what you want changed.")
            return
        revised = copy.deepcopy(session)
        try:
            with st.spinner("Revising ideas..."):
                asyncio.run(revise_ideas(client(), settings, revised, feedback.strip()))
        except RuntimeError as e:
            st.error(str(e))
            return
        ss.previous = (session, ss.out_dir)
        ss.out_dir = new_run_dir(revised.ideas[0].title)
        revised.save(ss.out_dir)
        ss.session = revised
        clear_picks()
        st.rerun()
    if ss.previous and st.button("Undo last revision"):
        ss.session, ss.out_dir = ss.previous
        ss.previous = None
        clear_picks()
        st.rerun()


def show_ideas(session: Session) -> None:
    st.header("2. Ideas")
    st.caption("Tick the ideas you want the council to test.")
    picks = []
    for idea in session.ideas:
        with st.container(border=True):
            if st.checkbox(f"{idea.id}. {idea.title}".replace("$", "\\$"), key=f"pick_{idea.id}"):
                picks.append(idea.id)
            md(f"*{idea.pitch}*")
            if idea.description:
                md(idea.description)
            md(f"**Customer:** {idea.customer}  \n**Problem:** {idea.problem}")

    show_revision(session)

    st.header("3. Council")
    angle_keys = st.multiselect(
        "Specialist angles", list(ANGLES), default=list(ANGLES), format_func=lambda k: ANGLES[k][0]
    )
    calls = council_calls(len(picks), len(settings.council_models), len(angle_keys)) + len(picks) if picks else 0
    st.caption(f"{len(picks)} selected, up to {calls} model calls.")
    if st.button("Run council", type="primary", disabled=not picks):
        judged = copy.deepcopy(session)
        judged.picks = picks

        async def judge() -> None:
            llm = client()
            await refine_picks(llm, settings, judged)
            judged.save(ss.out_dir)
            await run_council(llm, settings, judged, angle_keys)

        try:
            with st.spinner("The council is deliberating. This can take several minutes..."):
                asyncio.run(judge())
        except RuntimeError as e:
            st.error(str(e))
            return
        judged.save(ss.out_dir)
        (ss.out_dir / "report.md").write_text(render(judged))
        ss.session = judged
        st.rerun()


def show_report(session: Session) -> None:
    st.header("Council report")
    ranked = ranked_ideas(session)
    st.dataframe(
        [
            {
                "Idea": idea.title,
                "Verdict": fmt((res.get("chairman") or {}).get("verdict")),
                "Chairman score": (res.get("chairman") or {}).get("score"),
                "Member mean": res.get("mean_score"),
            }
            for idea, res in ranked
        ],
        hide_index=True,
    )
    if session.overall:
        st.subheader("Overall recommendation")
        md(session.overall)

    for idea, res in ranked:
        st.subheader(idea.title.replace("$", "\\$"))
        md(idea.description or idea.pitch)
        if res.get("error"):
            st.error(f"Council failed: {res['error']}. See the terminal for details.")
        ruling, specialists, members, brief = st.tabs(["Ruling", "All angles", "Council members", "Brief"])
        with ruling:
            md(res["chairman"]["text"] if res.get("chairman") else "The chairman did not respond.")
        with specialists:
            for a in res.get("angles", []):
                with st.expander(f"{a['name']}: {fmt(a['score'])}/10"):
                    st.caption(a["model"])
                    md(a["text"])
        with members:
            for o in res.get("opinions", []):
                with st.expander(f"{o['model']}: {fmt(o['verdict'])} {fmt(o['score'])}"):
                    md(o["text"])
            for r in res.get("reviews", []):
                with st.expander(f"Peer review by {r['model']}"):
                    md(r["text"])
        with brief:
            md(idea.brief)

    st.download_button("Download report", render(session), file_name="report.md")
    if st.button("Back to ideas"):
        fresh = copy.deepcopy(session)
        fresh.picks, fresh.council, fresh.overall = [], {}, ""
        clear_picks()
        ss.out_dir = new_run_dir(fresh.ideas[0].title)
        fresh.save(ss.out_dir)
        ss.session, ss.previous = fresh, None
        st.rerun()


st.title("Idea Forge")
with st.sidebar:
    st.header("Settings")
    st.toggle(
        "Mock mode (free, canned ideas)", value=not settings.api_key, key="mock", disabled=ss.session is not None
    )
    if not ss.mock and not settings.api_key:
        st.error("Add OPENROUTER_API_KEY to .env or use mock mode.")
    st.multiselect("Brainstorm methods", GENERATION_METHODS, default=GENERATION_METHODS, key="methods")
    st.slider("Ideas per method", 2, 12, 6, key="per_method")
    st.slider("Ideas to keep", 5, 25, 15, key="keep")
    if ss.session is not None:
        st.caption(f"Saved in {ss.out_dir}")
        if st.button("New run / open saved run"):
            ss.session = ss.out_dir = ss.previous = None
            clear_picks()
            st.rerun()

    runs = list_runs() if ss.session is None else []
    if runs:
        st.header("Saved runs")
        labels = {f"{n}. {run_label(p)}": p for n, p in enumerate(runs, start=1)}
        st.selectbox("Saved runs", list(labels), key="saved_run", label_visibility="collapsed")
        st.button("Open saved run", on_click=open_run, args=(labels,))

if error := ss.pop("open_error", None):
    st.error(error)

if ss.mock:
    st.warning("Mock mode: these are canned ideas and fake scores, not based on your profile.")

if ss.session is None:
    show_profile_form()
elif ss.session.council:
    show_report(ss.session)
else:
    show_ideas(ss.session)
