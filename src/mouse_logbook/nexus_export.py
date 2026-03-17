from __future__ import annotations

from pathlib import Path

import attrs

from .adapters.project_xlsx import ProjectXlsxParser
from .environment_repo import SampleEnvironmentRepository
from .io_excel import LogbookExcelReader, LogbookExcelSpec
from .models import EnrichedLogbookEntry, LogbookEntry
from .nexus_metadata import NexusMetadataUpserter
from .project_repo import ProjectFileLocator
from .sample_metadata import SampleMetadataEnricher
from .sample_metadata_chemistry import ChemistryValidatedEnrichedLogbookEntry, SampleMetadataChemistryValidator
from .sample_metadata_materials import MaterialEnrichedLogbookEntry, SampleMetadataMaterialsCalculator
from .sample_metadata_xray import SampleMetadataXrayCalculator, SampleXrayProperties, XrayEnrichedLogbookEntry
from .validation import ValidationIssue, ValidationReport


def _error(location: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity="error", location=location, message=message)


def _prefix_issue(prefix: str, issue: ValidationIssue) -> ValidationIssue:
    location = prefix if not issue.location else f"{prefix} {issue.location}"
    return ValidationIssue(severity=issue.severity, location=location, message=issue.message)


@attrs.frozen(kw_only=True, slots=True)
class NexusMetadataExportPayload:
    output_file: Path
    entry: LogbookEntry
    enriched_entry: EnrichedLogbookEntry
    chemistry_entry: ChemistryValidatedEnrichedLogbookEntry
    material_entry: MaterialEnrichedLogbookEntry
    xray_entry: XrayEnrichedLogbookEntry
    source_key: str
    energy_kev: float


@attrs.define(slots=True)
class NexusMetadataExportService:
    logbook_file: Path = attrs.field(converter=Path)
    project_base_dir: Path = attrs.field(converter=Path)
    logbook_spec: LogbookExcelSpec = attrs.field(factory=LogbookExcelSpec)
    project_parser: ProjectXlsxParser = attrs.field(factory=ProjectXlsxParser)
    metadata_enricher: SampleMetadataEnricher = attrs.field(factory=SampleMetadataEnricher)
    chemistry_validator: SampleMetadataChemistryValidator = attrs.field(factory=SampleMetadataChemistryValidator)
    materials_calculator: SampleMetadataMaterialsCalculator = attrs.field(factory=SampleMetadataMaterialsCalculator)
    xray_calculator: SampleMetadataXrayCalculator = attrs.field(factory=SampleMetadataXrayCalculator)
    upserter: NexusMetadataUpserter = attrs.field(factory=NexusMetadataUpserter)

    def write_entry(
        self,
        *,
        output_file: str | Path,
        ymd: str | None = None,
        batch_num: int | None = None,
        load_all: bool = False,
        source_key: str | None = None,
        energy_kev: float | None = None,
    ) -> ValidationReport[NexusMetadataExportPayload | None]:
        preparation = self._prepare_entry(ymd=ymd, batch_num=batch_num, load_all=load_all)
        issues = list(preparation.issues)
        if preparation.has_errors or preparation.value is None:
            return ValidationReport(value=None, issues=tuple(issues))

        enriched_entry, chemistry_entry, material_entry, xray_entry = preparation.value
        selected_xray: SampleXrayProperties | None = None
        resolved_source_key = source_key
        resolved_energy_kev: float

        if energy_kev is not None:
            custom_report = self.xray_calculator.calculate_sample_at_energy(chemistry_entry.sample, energy_kev=energy_kev)
            issues.extend(_prefix_issue("Custom_Xray", issue) for issue in custom_report.issues)
            if custom_report.has_errors:
                return ValidationReport(value=None, issues=tuple(issues))
            selected_xray = custom_report.value
            resolved_energy_kev = float(selected_xray.energy_kev)
            if resolved_source_key is None:
                resolved_source_key = self._default_custom_source_key(energy_kev)
        else:
            try:
                standard_key = resolved_source_key or self._infer_source_key(enriched_entry.entry.sample_position_id)
            except ValueError as e:
                issues.append(_error("NeXus", str(e)))
                return ValidationReport(value=None, issues=tuple(issues))
            selected_xray = xray_entry.sample.standard_xray.get(standard_key)
            if selected_xray is None:
                issues.append(_error("NeXus", f"X-ray metadata does not contain a {standard_key!r} entry"))
                return ValidationReport(value=None, issues=tuple(issues))
            resolved_source_key = standard_key
            resolved_energy_kev = float(selected_xray.energy_kev)

        output_path = Path(output_file)
        try:
            self.upserter.upsert_entry(
                output_path,
                material_entry=material_entry,
                xray_entry=xray_entry,
                sample_xray=selected_xray if energy_kev is not None else None,
                source_key=resolved_source_key,
            )
        except Exception as e:
            issues.append(_error(f"NeXus {output_path}", str(e)))
            return ValidationReport(value=None, issues=tuple(issues))

        return ValidationReport(
            value=NexusMetadataExportPayload(
                output_file=output_path,
                entry=enriched_entry.entry,
                enriched_entry=enriched_entry,
                chemistry_entry=chemistry_entry,
                material_entry=material_entry,
                xray_entry=xray_entry,
                source_key=resolved_source_key,
                energy_kev=resolved_energy_kev,
            ),
            issues=tuple(issues),
        )

    def _prepare_entry(
        self,
        *,
        ymd: str | None,
        batch_num: int | None,
        load_all: bool,
    ) -> ValidationReport[
        tuple[
            EnrichedLogbookEntry,
            ChemistryValidatedEnrichedLogbookEntry,
            MaterialEnrichedLogbookEntry,
            XrayEnrichedLogbookEntry,
        ]
        | None
    ]:
        issues: list[ValidationIssue] = []

        reader = LogbookExcelReader(file_path=self.logbook_file, spec=self.logbook_spec)
        try:
            logbook_report = reader.inspect_entries(load_all=load_all)
        except FileNotFoundError as e:
            return ValidationReport(value=None, issues=(_error(f"Logbook {self.logbook_file}", str(e)),))

        selected_entry = self._select_entry(logbook_report, ymd=ymd, batch_num=batch_num)
        if selected_entry is None:
            selection_issues = self._selection_issues(logbook_report, ymd=ymd, batch_num=batch_num)
            if selection_issues:
                issues.extend(selection_issues)
            else:
                issues.append(_error(f"Logbook {self.logbook_file}", "No eligible logbook entry found for export"))
            return ValidationReport(value=None, issues=tuple(issues))

        proposal_id = selected_entry.proposal_id
        sample_id = selected_entry.sample_id
        export_prefix = (
            f"Export proposal_id={proposal_id} sampleId={sample_id} ymd={selected_entry.ymd} batchnum={selected_entry.batch_num}"
        )

        locator = ProjectFileLocator(self.project_base_dir)
        try:
            project_file = locator.find_project_file(proposal_id)
        except Exception as e:
            issues.append(_error(export_prefix, str(e)))
            return ValidationReport(value=None, issues=tuple(issues))

        try:
            project_report = self.project_parser.inspect(project_file)
        except Exception as e:
            issues.append(_error(f"{export_prefix} Project {project_file}", str(e)))
            return ValidationReport(value=None, issues=tuple(issues))

        issues.extend(_prefix_issue(f"{export_prefix} Project {project_file}", issue) for issue in project_report.issues)
        if project_report.has_errors:
            return ValidationReport(value=None, issues=tuple(issues))

        sample = project_report.value.samples.get(sample_id)
        if sample is None:
            issues.append(_error(export_prefix, f"Sample {sample_id} not found in project {proposal_id}"))
            return ValidationReport(value=None, issues=tuple(issues))

        env_repo = SampleEnvironmentRepository(self.logbook_file)
        try:
            sample_position = env_repo.get(selected_entry.sample_position_id)
        except Exception as e:
            issues.append(_error(export_prefix, str(e)))
            return ValidationReport(value=None, issues=tuple(issues))

        enriched_entry = EnrichedLogbookEntry(
            entry=selected_entry,
            project=project_report.value,
            sample=sample,
            sample_position=sample_position,
        )

        metadata_report = self.metadata_enricher.enrich_one(enriched_entry)
        issues.extend(_prefix_issue(export_prefix, issue) for issue in metadata_report.issues)

        chemistry_report = self.chemistry_validator.validate_enriched_entry(metadata_report.value)
        issues.extend(_prefix_issue(export_prefix, issue) for issue in chemistry_report.issues)
        if chemistry_report.has_errors:
            return ValidationReport(value=None, issues=tuple(issues))

        materials_report = self.materials_calculator.estimate_enriched_entry(chemistry_report.value)
        issues.extend(_prefix_issue(export_prefix, issue) for issue in materials_report.issues)
        if materials_report.has_errors:
            return ValidationReport(value=None, issues=tuple(issues))

        xray_report = self.xray_calculator.precompute_enriched_entry(chemistry_report.value)
        issues.extend(_prefix_issue(export_prefix, issue) for issue in xray_report.issues)
        if xray_report.has_errors:
            return ValidationReport(value=None, issues=tuple(issues))

        return ValidationReport(
            value=(enriched_entry, chemistry_report.value, materials_report.value, xray_report.value),
            issues=tuple(issues),
        )

    def _select_entry(
        self,
        report: ValidationReport[list[LogbookEntry]],
        *,
        ymd: str | None,
        batch_num: int | None,
    ) -> LogbookEntry | None:
        if (ymd is None) != (batch_num is None):
            return None

        if ymd is not None and batch_num is not None:
            matches = [entry for entry in report.value if entry.ymd == ymd and entry.batch_num == batch_num]
            if len(matches) == 1:
                return matches[0]
            return None

        if len(report.value) == 1:
            return report.value[0]
        return None

    def _selection_issues(
        self,
        report: ValidationReport[list[LogbookEntry]],
        *,
        ymd: str | None,
        batch_num: int | None,
    ) -> list[ValidationIssue]:
        if (ymd is None) != (batch_num is None):
            return [_error("Logbook", "Pass both ymd and batch_num together to select an entry")]

        if ymd is not None and batch_num is not None:
            matches = [entry for entry in report.value if entry.ymd == ymd and entry.batch_num == batch_num]
            if len(matches) > 1:
                return [_error("Logbook", f"Multiple valid entries found for ymd={ymd} batch_num={batch_num}")]
            return [_error("Logbook", f"No valid entry found for ymd={ymd} batch_num={batch_num}")]

        if not report.value and report.issues:
            return list(report.issues)

        if len(report.value) > 1:
            identifiers = ", ".join(f"{entry.ymd}/{entry.batch_num}" for entry in report.value)
            return [
                _error(
                    "Logbook",
                    "Multiple eligible logbook entries found; pass --ymd and --batch-num to select one of: "
                    f"{identifiers}",
                )
            ]

        return []

    def _default_custom_source_key(self, energy_kev: float) -> str:
        return f"custom_{str(float(energy_kev)).replace('.', 'p')}kev"

    def _infer_source_key(self, sampos: str) -> str:
        lowered = sampos.strip().lower()
        tokens = lowered.replace("_", " ").split()
        for token in tokens:
            if token.startswith("cu"):
                return "cu_ka"
            if token.startswith("mo"):
                return "mo_ka"
        raise ValueError(
            f"could not infer X-ray source from sampos {sampos!r}; pass --source-key or --energy-kev explicitly"
        )
