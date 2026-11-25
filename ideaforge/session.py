"""Session state, saved as JSON so any stage can be re-run or resumed."""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path


@dataclass
class Idea:
    id: int
    title: str
    pitch: str
    description: str = ""
    customer: str = ""
    problem: str = ""
    sources: list[str] = field(default_factory=list)  # brainstorm methods that produced it
    brief: str = ""  # filled in by the refine step


@dataclass
class Session:
    profile: str
    ideas: list[Idea] = field(default_factory=list)
    picks: list[int] = field(default_factory=list)  # idea ids
    council: dict = field(default_factory=dict)  # idea id (str) -> council result
    overall: str = ""
    feedback: list[str] = field(default_factory=list)  # revision requests, oldest first
    mock: bool = False

    def idea(self, idea_id: int) -> Idea:
        return next(i for i in self.ideas if i.id == idea_id)

    def save(self, directory: Path) -> Path:
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / "session.json"
        path.write_text(json.dumps(asdict(self), indent=2))
        return path

    @classmethod
    def load(cls, directory: Path) -> "Session":
        data = json.loads((Path(directory) / "session.json").read_text())
        ideas = [Idea(**i) for i in data.pop("ideas", [])]
        return cls(ideas=ideas, **data)
