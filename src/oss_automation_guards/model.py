"""Load GitHub Actions workflow files into a checkable shape."""

from __future__ import annotations

from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

import yaml


class WorkflowLoadError(Exception):
    """A workflow file could not be parsed into a workflow mapping."""


@dataclass(frozen=True)
class WorkflowFile:
    path: Path
    text: str
    data: dict[str, Any]

    @classmethod
    def from_text(cls, text: str, path: Path = Path("workflow.yaml")) -> WorkflowFile:
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError as error:
            raise WorkflowLoadError(f"{path}: not parseable as YAML: {error}") from error
        if not isinstance(data, dict):
            raise WorkflowLoadError(
                f"{path}: expected a workflow mapping, got {type(data).__name__}"
            )
        return cls(path=path, text=text, data=data)

    @property
    def triggers(self) -> dict[str, Any]:
        """Trigger names mapped to their configuration (None for bare forms)."""
        # YAML 1.1 reads the unquoted key `on` as the boolean True (the
        # Norway problem), so the trigger block usually sits under True.
        raw = self.data.get("on", self.data.get(True))
        if raw is None:
            return {}
        if isinstance(raw, str):
            return {raw: None}
        if isinstance(raw, list):
            return {name: None for name in raw}
        return raw

    @property
    def jobs(self) -> dict[str, dict[str, Any]]:
        jobs = self.data.get("jobs")
        if not isinstance(jobs, dict):
            return {}
        return {job_id: job for job_id, job in jobs.items() if isinstance(job, dict)}


@cache
def load_workflow(path: Path) -> WorkflowFile:
    return WorkflowFile.from_text(path.read_text(encoding="utf-8"), path=path)


def discover_workflows(tree: Path) -> list[Path]:
    """Workflow files GitHub would read: the tree's top level only, no recursion."""
    return sorted(
        path for path in tree.iterdir() if path.is_file() and path.suffix in {".yml", ".yaml"}
    )
