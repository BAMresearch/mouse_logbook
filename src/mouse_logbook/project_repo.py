from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

import attrs

from .exceptions import ProjectNotFoundError, SampleNotFoundError


@attrs.define(slots=True)
class ProjectFileLocator:
    """
    Locates project/proposal Excel files on disk.

    Contract:
      - project files are under base_dir / YEAR / and match "{proposal_id}*.xlsx"
      - YEAR is the first 4 characters of proposal_id
    """

    base_dir: Path = attrs.field(converter=Path)

    def find_project_file(self, proposal_id: str) -> Path:
        year = proposal_id[:4]
        search_dir = self.base_dir / year
        if not search_dir.is_dir():
            raise ProjectNotFoundError(f"Project year directory not found: {search_dir}")

        matches = sorted(search_dir.glob(f"{proposal_id}*.xlsx"))
        if not matches:
            raise ProjectNotFoundError(
                f"No project file found for {proposal_id!r} in {search_dir} (pattern {proposal_id}*.xlsx)"
            )
        return matches[0]


@attrs.define(slots=True)
class ProjectRepository:
    """
    Loads and caches parsed projects. Parsing is injected to keep this repo decoupled.

    The parser should be a callable: (Path) -> ProjectLike.
    """

    locator: ProjectFileLocator
    parser: Callable[[Path], Any]

    _cache: dict[str, Any] = attrs.field(init=False, factory=dict)

    def get(self, proposal_id: str) -> Any:
        if proposal_id in self._cache:
            return self._cache[proposal_id]

        project_file = self.locator.find_project_file(proposal_id)
        project = self.parser(project_file)
        self._cache[proposal_id] = project
        return project

    def get_sample(self, proposal_id: str, sample_id: int) -> Any:
        project = self.get(proposal_id)
        sample = getattr(project, "samples", {}).get(sample_id)
        if sample is None:
            raise SampleNotFoundError(f"Sample {sample_id} not found in project {proposal_id}")
        return sample
