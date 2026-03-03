from __future__ import annotations

from collections.abc import Iterable

import attrs

from .environment_repo import SampleEnvironmentRepository
from .models import EnrichedLogbookEntry, LogbookEntry
from .project_repo import ProjectRepository


@attrs.define(slots=True)
class LogbookEnricher:
    """Joins logbook entries with project/sample/environment metadata."""

    projects: ProjectRepository
    environments: SampleEnvironmentRepository

    def enrich_one(self, entry: LogbookEntry) -> EnrichedLogbookEntry:
        project = self.projects.get(entry.proposal_id)
        sample = self.projects.get_sample(entry.proposal_id, entry.sample_id)
        position = self.environments.get(entry.sample_position_id)
        return EnrichedLogbookEntry(entry=entry, project=project, sample=sample, sample_position=position)

    def enrich_many(self, entries: Iterable[LogbookEntry]) -> list[EnrichedLogbookEntry]:
        return [self.enrich_one(e) for e in entries]
