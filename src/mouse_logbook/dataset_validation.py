from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import attrs

from .adapters.project_xlsx import ProjectXlsxParser
from .environment_repo import SampleEnvironmentRepository
from .io_excel import LogbookExcelReader, LogbookExcelSpec
from .models import EnrichedLogbookEntry, LogbookEntry
from .project_repo import ProjectFileLocator
from .sample_metadata import SampleMetadataEnricher
from .sample_metadata_chemistry import ChemistryValidatedEnrichedLogbookEntry, SampleMetadataChemistryValidator
from .sample_metadata_materials import MaterialEnrichedLogbookEntry, SampleMetadataMaterialsCalculator
from .sample_metadata_xray import SampleMetadataXrayCalculator, XrayEnrichedLogbookEntry
from .validation import ValidationIssue, ValidationReport

ValidationLevel = Literal["core", "chemistry", "materials", "xray"]
_LEVEL_ORDER: dict[ValidationLevel, int] = {
    "core": 0,
    "chemistry": 1,
    "materials": 2,
    "xray": 3,
}


def _error(location: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity="error", location=location, message=message)


def _prefix_issue(prefix: str, issue: ValidationIssue) -> ValidationIssue:
    location = prefix if not issue.location else f"{prefix} {issue.location}"
    return ValidationIssue(severity=issue.severity, location=location, message=issue.message)


@attrs.frozen(kw_only=True, slots=True)
class DatasetValidationResult:
    level: ValidationLevel
    entries: tuple[LogbookEntry, ...] = attrs.field(factory=tuple, converter=tuple)
    projects: dict[str, Any] = attrs.field(factory=dict, converter=dict)
    enriched_entries: tuple[EnrichedLogbookEntry, ...] = attrs.field(factory=tuple, converter=tuple)
    chemistry_entries: tuple[ChemistryValidatedEnrichedLogbookEntry, ...] = attrs.field(factory=tuple, converter=tuple)
    material_entries: tuple[MaterialEnrichedLogbookEntry, ...] = attrs.field(factory=tuple, converter=tuple)
    xray_entries: tuple[XrayEnrichedLogbookEntry, ...] = attrs.field(factory=tuple, converter=tuple)


@attrs.define(slots=True)
class DatasetValidator:
    """Runs staged validation across the logbook, proposal, and optional materials layers."""

    logbook_file: Path = attrs.field(converter=Path)
    project_base_dir: Path = attrs.field(converter=Path)
    logbook_spec: LogbookExcelSpec = attrs.field(factory=LogbookExcelSpec)
    project_parser: ProjectXlsxParser = attrs.field(factory=ProjectXlsxParser)
    metadata_enricher: SampleMetadataEnricher = attrs.field(factory=SampleMetadataEnricher)
    chemistry_validator: SampleMetadataChemistryValidator = attrs.field(factory=SampleMetadataChemistryValidator)
    materials_calculator: SampleMetadataMaterialsCalculator = attrs.field(factory=SampleMetadataMaterialsCalculator)
    xray_calculator: SampleMetadataXrayCalculator = attrs.field(factory=SampleMetadataXrayCalculator)

    def validate(
        self,
        *,
        level: ValidationLevel = "core",
        load_all: bool = False,
    ) -> ValidationReport[DatasetValidationResult]:
        issues: list[ValidationIssue] = []
        entries = self._read_logbook_entries(load_all=load_all, issues=issues)

        projects = self._inspect_projects(entries=entries, issues=issues)
        positions, environment_available = self._load_positions(issues=issues)
        enriched_entries = self._enrich_core(entries=entries, projects=projects, positions=positions, environment_available=environment_available, issues=issues)

        chemistry_entries: list[ChemistryValidatedEnrichedLogbookEntry] = []
        material_entries: list[MaterialEnrichedLogbookEntry] = []
        xray_entries: list[XrayEnrichedLogbookEntry] = []

        if _LEVEL_ORDER[level] >= _LEVEL_ORDER["chemistry"] and enriched_entries:
            chemistry_entries = self._validate_chemistry(enriched_entries=enriched_entries, issues=issues)

        if _LEVEL_ORDER[level] >= _LEVEL_ORDER["materials"] and chemistry_entries:
            material_entries = self._validate_materials(chemistry_entries=chemistry_entries, issues=issues)

        if _LEVEL_ORDER[level] >= _LEVEL_ORDER["xray"] and chemistry_entries:
            xray_entries = self._validate_xray(chemistry_entries=chemistry_entries, issues=issues)

        return ValidationReport(
            value=DatasetValidationResult(
                level=level,
                entries=entries,
                projects=projects,
                enriched_entries=enriched_entries,
                chemistry_entries=chemistry_entries,
                material_entries=material_entries,
                xray_entries=xray_entries,
            ),
            issues=tuple(issues),
        )

    def _read_logbook_entries(
        self,
        *,
        load_all: bool,
        issues: list[ValidationIssue],
    ) -> list[LogbookEntry]:
        reader = LogbookExcelReader(file_path=self.logbook_file, spec=self.logbook_spec)
        try:
            report = reader.inspect_entries(load_all=load_all)
        except FileNotFoundError as e:
            issues.append(_error(f"Logbook {self.logbook_file}", str(e)))
            return []

        issues.extend(_prefix_issue(f"Logbook {self.logbook_file}", issue) for issue in report.issues)
        return list(report.value)

    def _inspect_projects(
        self,
        *,
        entries: list[LogbookEntry],
        issues: list[ValidationIssue],
    ) -> dict[str, Any]:
        locator = ProjectFileLocator(self.project_base_dir)
        projects: dict[str, Any] = {}

        for proposal_id in sorted({entry.proposal_id for entry in entries}):
            try:
                project_file = locator.find_project_file(proposal_id)
            except Exception as e:
                issues.append(_error(f"Proposal {proposal_id}", str(e)))
                continue

            try:
                report = self.project_parser.inspect(project_file)
            except Exception as e:
                issues.append(_error(f"Project {proposal_id} {project_file}", str(e)))
                continue

            issues.extend(_prefix_issue(f"Project {proposal_id} {project_file}", issue) for issue in report.issues)
            projects[proposal_id] = report.value

        return projects

    def _load_positions(
        self,
        *,
        issues: list[ValidationIssue],
    ) -> tuple[dict[str, dict[str, float]], bool]:
        repo = SampleEnvironmentRepository(self.logbook_file)
        try:
            positions = repo.load_all()
        except Exception as e:
            issues.append(_error(f"Sample_Environments {self.logbook_file}", str(e)))
            return {}, False
        return {str(key): dict(value) for key, value in positions.items()}, True

    def _enrich_core(
        self,
        *,
        entries: list[LogbookEntry],
        projects: dict[str, Any],
        positions: dict[str, dict[str, float]],
        environment_available: bool,
        issues: list[ValidationIssue],
    ) -> list[EnrichedLogbookEntry]:
        enriched: list[EnrichedLogbookEntry] = []

        for entry in entries:
            project = projects.get(entry.proposal_id)
            if project is None:
                continue

            sample = getattr(project, "samples", {}).get(entry.sample_id)
            if sample is None:
                issues.append(
                    _error(
                        f"Enrichment proposal_id={entry.proposal_id} sampleId={entry.sample_id}",
                        f"Sample {entry.sample_id} not found in project {entry.proposal_id}",
                    )
                )
                continue

            if not environment_available:
                continue

            position = positions.get(entry.sample_position_id)
            if position is None:
                issues.append(
                    _error(
                        f"Enrichment proposal_id={entry.proposal_id} sampleId={entry.sample_id}",
                        f"sampos {entry.sample_position_id!r} not found in sample environments",
                    )
                )
                continue

            enriched.append(EnrichedLogbookEntry(entry=entry, project=project, sample=sample, sample_position=position))

        return enriched

    def _validate_chemistry(
        self,
        *,
        enriched_entries: list[EnrichedLogbookEntry],
        issues: list[ValidationIssue],
    ) -> list[ChemistryValidatedEnrichedLogbookEntry]:
        metadata_report = self.metadata_enricher.enrich_many(enriched_entries)
        issues.extend(_prefix_issue("Sample_Metadata", issue) for issue in metadata_report.issues)

        chemistry_report = self.chemistry_validator.validate_enriched_entries(metadata_report.value)
        issues.extend(_prefix_issue("Chemistry", issue) for issue in chemistry_report.issues)
        return list(chemistry_report.value)

    def _validate_materials(
        self,
        *,
        chemistry_entries: list[ChemistryValidatedEnrichedLogbookEntry],
        issues: list[ValidationIssue],
    ) -> list[MaterialEnrichedLogbookEntry]:
        materials_report = self.materials_calculator.estimate_enriched_entries(chemistry_entries)
        issues.extend(_prefix_issue("Materials", issue) for issue in materials_report.issues)
        return list(materials_report.value)

    def _validate_xray(
        self,
        *,
        chemistry_entries: list[ChemistryValidatedEnrichedLogbookEntry],
        issues: list[ValidationIssue],
    ) -> list[XrayEnrichedLogbookEntry]:
        xray_report = self.xray_calculator.precompute_enriched_entries(chemistry_entries)
        issues.extend(_prefix_issue("Xray", issue) for issue in xray_report.issues)
        return list(xray_report.value)
