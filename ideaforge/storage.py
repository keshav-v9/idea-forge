"""Local storage under runs/ (gitignored): saved runs, the last profile, and every model response."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .llm import LLM
from .session import Session
from .util import slugify

ROOT = Path("runs")


def new_run_dir(tag: str, root: Path | str = ROOT) -> Path:
    base = Path(root) / f"{datetime.now():%Y%m%d-%H%M%S}-{slugify(tag)}"
    path, n = base, 2
    while path.exists():
        path, n = base.with_name(f"{base.name}-{n}"), n + 1
    return path


def list_runs() -> list[Path]:
    """Saved runs, newest first."""
    return sorted((p.parent for p in ROOT.glob("*/session.json")), reverse=True)


def run_label(path: Path) -> str:
    """Short menu label; unreadable runs are labelled rather than hidden."""
    try:
        session = Session.load(path)
        when = datetime.strptime(path.name[:15], "%Y%m%d-%H%M%S").strftime("%b %d %H:%M:%S")
    except (ValueError, TypeError, OSError):
        return f"{path.name} (unreadable)"
    stage = "report" if session.council else f"{len(session.ideas)} ideas"
    title = session.ideas[0].title if session.ideas else path.name
    return f"{when} - {title} ({'mock ' if session.mock else ''}{stage})"


def save_profile(answers: list[str]) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    (ROOT / "profile.json").write_text(json.dumps(answers, indent=2))


def load_profile(count: int) -> list[str]:
    try:
        answers = json.loads((ROOT / "profile.json").read_text())
        answers = [str(a) for a in answers]
    except (OSError, ValueError, TypeError):
        answers = []
    return (answers + [""] * count)[:count]


class RecordingLLM:
    """Appends each prompt and response to runs/calls/<day>.jsonl as soon as it arrives."""

    def __init__(self, inner: LLM):
        self.inner = inner

    @property
    def last_error(self) -> str:
        return getattr(self.inner, "last_error", "")

    async def complete(self, model: str, prompt: str, *, task: str = "") -> str | None:
        text = await self.inner.complete(model, prompt, task=task)
        now = datetime.now()
        record = {
            "time": now.isoformat(timespec="seconds"),
            "task": task,
            "model": model,
            "mock": type(self.inner).__name__ == "MockLLM",
            "prompt": prompt,
            "response": text,
            "error": None if text is not None else self.last_error,
        }
        folder = ROOT / "calls"
        folder.mkdir(parents=True, exist_ok=True)
        with (folder / f"{now:%Y%m%d}.jsonl").open("a") as f:
            f.write(json.dumps(record) + "\n")
        return text
