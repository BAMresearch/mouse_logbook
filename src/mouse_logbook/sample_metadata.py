from __future__ import annotations

from collections.abc import Iterable, Mapping

import attrs

from .adapters.project_xlsx import ProjectInfo as ParsedProjectInfo
from .adapters.project_xlsx import Sample as ParsedSample
from .adapters.project_xlsx import SampleComponent as ParsedSampleComponent
from .models import EnrichedLogbookEntry, LogbookEntry
from .validation import ValidationIssue, ValidationReport


def _error(location: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity="error", location=location, message=message)


@attrs.frozen(kw_only=True, slots=True)
class SampleMetadataComponent:
    component_id: str
    composition: str
    density: float | None = None
    volume_fraction: float | None = None
    mass_fraction: float | None = None
    connection: str | None = None
    connected_to: str | None = None
    component_name: str | None = None


@attrs.frozen(kw_only=True, slots=True)
class SampleMetadataSample:
    sample_id: int
    sample_name: str
    composition_summary: str
    components: tuple[SampleMetadataComponent, ...] = attrs.field(factory=tuple)


@attrs.frozen(kw_only=True, slots=True)
class SampleMetadataProject:
    proposal_id: str
    name: str
    email: str
    organisation: str
    title: str
    description: str
    samples: dict[int, SampleMetadataSample]


@attrs.frozen(kw_only=True, slots=True)
class SampleMetadataEnrichedLogbookEntry:
    entry: LogbookEntry
    project: SampleMetadataProject
    sample: SampleMetadataSample
    sample_position: Mapping[str, float] = attrs.field(factory=dict)


@attrs.define(slots=True)
class SampleMetadataBuilder:
    """Maps parsed proposal-sheet samples into richer extension models."""

    def build_component(self, component: ParsedSampleComponent) -> ValidationReport[SampleMetadataComponent]:
        return ValidationReport(
            value=SampleMetadataComponent(
                component_id=component.component_id,
                composition=component.composition,
                density=component.density,
                volume_fraction=component.vol_frac,
                mass_fraction=component.mass_frac,
                connection=component.connection,
                connected_to=component.connected_to,
                component_name=component.component_name,
            )
        )

    def build_sample(self, sample: ParsedSample) -> ValidationReport[SampleMetadataSample]:
        issues: list[ValidationIssue] = []
        components: list[SampleMetadataComponent] = []
        seen_component_ids: set[str] = set()

        for component in sample.components:
            component_report = self.build_component(component)
            issues.extend(component_report.issues)
            metadata_component = component_report.value
            components.append(metadata_component)
            component_id = metadata_component.component_id.strip()
            if component_id:
                if component_id in seen_component_ids:
                    issues.append(
                        _error(
                            f"Sample_Metadata sampleId={sample.sample_id}",
                            f"duplicate component_id {component_id!r}",
                        )
                    )
                else:
                    seen_component_ids.add(component_id)

        return ValidationReport(
            value=SampleMetadataSample(
                sample_id=sample.sample_id,
                sample_name=sample.sample_name,
                composition_summary=sample.composition,
                components=tuple(components),
            ),
            issues=tuple(issues),
        )

    def build_project(self, project: ParsedProjectInfo) -> ValidationReport[SampleMetadataProject]:
        issues: list[ValidationIssue] = []
        samples: dict[int, SampleMetadataSample] = {}

        for sample_id, sample in project.samples.items():
            sample_report = self.build_sample(sample)
            issues.extend(sample_report.issues)
            samples[sample_id] = sample_report.value

        return ValidationReport(
            value=SampleMetadataProject(
                proposal_id=project.proposal_id,
                name=project.name,
                email=project.email,
                organisation=project.organisation,
                title=project.title,
                description=project.description,
                samples=samples,
            ),
            issues=tuple(issues),
        )


@attrs.define(slots=True)
class SampleMetadataEnricher:
    """Builds sample-metadata extension objects from core enriched entries."""

    builder: SampleMetadataBuilder = attrs.field(factory=SampleMetadataBuilder)

    def enrich_one(self, enriched: EnrichedLogbookEntry) -> ValidationReport[SampleMetadataEnrichedLogbookEntry]:
        project_report = self.builder.build_project(enriched.project)
        issues = list(project_report.issues)

        project_sample = project_report.value.samples.get(enriched.entry.sample_id)
        metadata_sample: SampleMetadataSample
        if project_sample is None:
            sample_report = self.builder.build_sample(enriched.sample)
            issues.extend(sample_report.issues)
            metadata_sample = sample_report.value
            issues.append(
                _error(
                    "Sample_Metadata",
                    f"sampleId={enriched.entry.sample_id} missing from metadata project for proposal {enriched.entry.proposal_id}",
                )
            )
        else:
            metadata_sample = project_sample

        return ValidationReport(
            value=SampleMetadataEnrichedLogbookEntry(
                entry=enriched.entry,
                project=project_report.value,
                sample=metadata_sample,
                sample_position=enriched.sample_position,
            ),
            issues=tuple(issues),
        )

    def enrich_many(self, entries: Iterable[EnrichedLogbookEntry]) -> ValidationReport[list[SampleMetadataEnrichedLogbookEntry]]:
        values: list[SampleMetadataEnrichedLogbookEntry] = []
        issues: list[ValidationIssue] = []

        for enriched in entries:
            report = self.enrich_one(enriched)
            values.append(report.value)
            issues.extend(report.issues)

        return ValidationReport(value=values, issues=tuple(issues))
