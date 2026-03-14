from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Protocol

import attrs

from .models import LogbookEntry
from .sample_metadata import (
    SampleMetadataComponent,
    SampleMetadataEnrichedLogbookEntry,
    SampleMetadataProject,
    SampleMetadataSample,
)
from .validation import ValidationIssue, ValidationReport


def _error(location: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity="error", location=location, message=message)


@attrs.frozen(kw_only=True, slots=True)
class ParsedChemicalFormula:
    original_input: str
    normalized_formula: str
    atom_counts: Mapping[str, float] = attrs.field(
        converter=lambda value: {str(k): float(v) for k, v in dict(value).items()},
        factory=dict,
    )


@attrs.frozen(kw_only=True, slots=True)
class ChemistryValidatedComponent:
    component_id: str
    composition: str
    density: float | None = None
    volume_fraction: float | None = None
    mass_fraction: float | None = None
    connection: str | None = None
    connected_to: str | None = None
    component_name: str | None = None
    formula: ParsedChemicalFormula | None = None


@attrs.frozen(kw_only=True, slots=True)
class ChemistryValidatedSample:
    sample_id: int
    sample_name: str
    composition_summary: str
    components: tuple[ChemistryValidatedComponent, ...] = attrs.field(factory=tuple)


@attrs.frozen(kw_only=True, slots=True)
class ChemistryValidatedProject:
    proposal_id: str
    name: str
    email: str
    organisation: str
    title: str
    description: str
    samples: dict[int, ChemistryValidatedSample]


@attrs.frozen(kw_only=True, slots=True)
class ChemistryValidatedEnrichedLogbookEntry:
    entry: LogbookEntry
    project: ChemistryValidatedProject
    sample: ChemistryValidatedSample
    sample_position: Mapping[str, float] = attrs.field(factory=dict)


class ChemistryInterpreter(Protocol):
    def parse_formula(self, formula_text: str) -> ParsedChemicalFormula: ...


@attrs.define(slots=True)
class PeriodictableChemistryInterpreter:
    """Optional chemistry interpreter backed by periodictable."""

    def parse_formula(self, formula_text: str) -> ParsedChemicalFormula:
        try:
            import periodictable as pt
        except ModuleNotFoundError as e:
            raise RuntimeError("periodictable is not installed") from e

        formula = pt.formula(formula_text)
        atom_counts = {
            getattr(atom, "symbol", str(atom)): float(count)
            for atom, count in getattr(formula, "atoms", {}).items()
        }
        return ParsedChemicalFormula(
            original_input=formula_text,
            normalized_formula=str(formula),
            atom_counts=atom_counts,
        )


@attrs.define(slots=True)
class SampleMetadataChemistryValidator:
    """Validates chemistry descriptions for the sample-metadata extension layer."""

    interpreter: ChemistryInterpreter = attrs.field(factory=PeriodictableChemistryInterpreter)

    def validate_component(self, component: SampleMetadataComponent) -> ValidationReport[ChemistryValidatedComponent]:
        issues: list[ValidationIssue] = []
        formula: ParsedChemicalFormula | None = None

        if component.density is not None and component.density <= 0:
            issues.append(
                _error(
                    "Sample_Metadata_Chemistry",
                    f"component {component.component_id!r} has non-positive density",
                )
            )

        if not component.composition.strip():
            issues.append(
                _error(
                    "Sample_Metadata_Chemistry",
                    f"component {component.component_id!r} is missing a chemistry description",
                )
            )
        else:
            try:
                formula = self.interpreter.parse_formula(component.composition)
            except Exception as e:
                issues.append(
                    _error(
                        "Sample_Metadata_Chemistry",
                        f"component {component.component_id!r} has invalid chemistry description "
                        f"{component.composition!r}: {e}",
                    )
                )

        return ValidationReport(
            value=ChemistryValidatedComponent(
                component_id=component.component_id,
                composition=component.composition,
                density=component.density,
                volume_fraction=component.volume_fraction,
                mass_fraction=component.mass_fraction,
                connection=component.connection,
                connected_to=component.connected_to,
                component_name=component.component_name,
                formula=formula,
            ),
            issues=tuple(issues),
        )

    def validate_sample(self, sample: SampleMetadataSample) -> ValidationReport[ChemistryValidatedSample]:
        issues: list[ValidationIssue] = []
        components: list[ChemistryValidatedComponent] = []

        for component in sample.components:
            component_report = self.validate_component(component)
            issues.extend(component_report.issues)
            components.append(component_report.value)

        return ValidationReport(
            value=ChemistryValidatedSample(
                sample_id=sample.sample_id,
                sample_name=sample.sample_name,
                composition_summary=sample.composition_summary,
                components=tuple(components),
            ),
            issues=tuple(issues),
        )

    def validate_project(self, project: SampleMetadataProject) -> ValidationReport[ChemistryValidatedProject]:
        issues: list[ValidationIssue] = []
        samples: dict[int, ChemistryValidatedSample] = {}

        for sample_id, sample in project.samples.items():
            sample_report = self.validate_sample(sample)
            issues.extend(sample_report.issues)
            samples[sample_id] = sample_report.value

        return ValidationReport(
            value=ChemistryValidatedProject(
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

    def validate_enriched_entry(
        self,
        enriched: SampleMetadataEnrichedLogbookEntry,
    ) -> ValidationReport[ChemistryValidatedEnrichedLogbookEntry]:
        project_report = self.validate_project(enriched.project)
        issues = list(project_report.issues)

        project_sample = project_report.value.samples.get(enriched.entry.sample_id)
        if project_sample is None:
            sample_report = self.validate_sample(enriched.sample)
            issues.extend(sample_report.issues)
            sample = sample_report.value
            issues.append(
                _error(
                    "Sample_Metadata_Chemistry",
                    f"sampleId={enriched.entry.sample_id} missing from chemistry-validated project for proposal "
                    f"{enriched.entry.proposal_id}",
                )
            )
        else:
            sample = project_sample

        return ValidationReport(
            value=ChemistryValidatedEnrichedLogbookEntry(
                entry=enriched.entry,
                project=project_report.value,
                sample=sample,
                sample_position=enriched.sample_position,
            ),
            issues=tuple(issues),
        )

    def validate_enriched_entries(
        self,
        entries: Iterable[SampleMetadataEnrichedLogbookEntry],
    ) -> ValidationReport[list[ChemistryValidatedEnrichedLogbookEntry]]:
        values: list[ChemistryValidatedEnrichedLogbookEntry] = []
        issues: list[ValidationIssue] = []

        for enriched in entries:
            report = self.validate_enriched_entry(enriched)
            values.append(report.value)
            issues.extend(report.issues)

        return ValidationReport(value=values, issues=tuple(issues))
