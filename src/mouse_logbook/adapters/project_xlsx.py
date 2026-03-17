from __future__ import annotations

from pathlib import Path
from typing import Any

import attrs
import pandas as pd

from ..exceptions import ProjectSheetFormatError
from ..validation import ValidationIssue, ValidationReport


def _normalize_proposal_id(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    try:
        if isinstance(value, (int, float)):
            return str(int(value))
    except Exception:
        pass
    s = str(value).strip()
    if s.endswith(".0"):
        s = s[:-2]
    return s


def _norm_key(s: Any) -> str:
    return str(s).strip().lower().replace(" ", "_")


def _is_blank(v: Any) -> bool:
    if v is None:
        return True
    try:
        if pd.isna(v):
            return True
    except TypeError:
        pass
    return isinstance(v, str) and not v.strip()


def _as_text(v: Any) -> str:
    return "" if _is_blank(v) else str(v).strip()


def _as_optional_text(v: Any) -> str | None:
    s = _as_text(v)
    return s or None


def _as_float(v: Any) -> float | None:
    if _is_blank(v):
        return None
    try:
        return float(v)
    except Exception as e:
        raise ProjectSheetFormatError(f"Expected a number, got {v!r}") from e


def _validate_email(email: str) -> None:
    # Keep it simple; we mainly want to catch empty/mistyped fields early.
    if "@" not in email or "." not in email.split("@")[-1]:
        raise ProjectSheetFormatError(f"Invalid email address: {email!r}")


def _error(location: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity="error", location=location, message=message)


def _warning(location: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity="warning", location=location, message=message)


@attrs.frozen(kw_only=True, slots=True)
class SampleComponent:
    component_id: str
    composition: str
    density: float | None = None
    vol_frac: float | None = None
    mass_frac: float | None = None
    connection: str | None = None
    connected_to: str | None = None
    component_name: str | None = None


@attrs.frozen(kw_only=True, slots=True)
class Sample:
    """Minimal sample model used by the default project-sheet parser."""

    sample_id: int
    sample_name: str
    composition: str
    components: tuple[SampleComponent, ...] = attrs.field(factory=tuple)


@attrs.frozen(kw_only=True, slots=True)
class ProjectInfo:
    """Minimal project model used by the default project-sheet parser."""

    proposal_id: str
    name: str
    email: str
    organisation: str
    title: str
    description: str
    samples: dict[int, Sample]


@attrs.define(slots=True)
class ProjectXlsxParser:
    """
    Default parser for your current proposal-sheet convention.

    Sheets expected:
    - `Project_Info`: key/value pairs in first two columns
    - `Sample_Info`: table with header at row 3 (0-based header=2)

    Validation is intentionally strict by default because these files are user-authored and commonly wrong.
    """

    project_info_sheet: str = "Project_Info"
    sample_info_sheet: str = "Sample_Info"
    sample_header_row: int = 2
    strict: bool = True

    required_project_fields: tuple[str, ...] = ("name", "organisation", "email", "title", "what")
    required_sample_columns: tuple[str, ...] = (
        "sampleId",
        "sampleName",
        "componentId",
        "composition",
        "density",
        "volFrac",
        "massFrac",
    )

    def parse(self, file_path: Path) -> ProjectInfo:
        report = self.inspect(file_path)
        if report.has_errors and self.strict:
            raise ProjectSheetFormatError(
                f"{Path(file_path).name}: " + "; ".join(str(issue) for issue in report.issues_for("error"))
            )
        return report.value

    def inspect(self, file_path: Path) -> ValidationReport[ProjectInfo]:
        file_path = Path(file_path)
        issues: list[ValidationIssue] = []

        try:
            info = self._read_project_info(file_path)
        except ValueError as e:
            info = {}
            issues.append(_error("Project_Info", str(e)))

        proposal_id = _normalize_proposal_id(info.get("proposal")) or _normalize_proposal_id(file_path.stem)

        name = _as_text(info.get("name", ""))
        organisation = _as_text(info.get("organisation", ""))
        email = _as_text(info.get("email", ""))
        title = _as_text(info.get("title", ""))
        description = _as_text(info.get("what", ""))

        issues.extend(
            self._validate_project_info(
                proposal_id=proposal_id,
                name=name,
                organisation=organisation,
                email=email,
                title=title,
                description=description,
            )
        )

        sample_report = self._read_samples(file_path)
        issues.extend(sample_report.issues)

        return ValidationReport(
            value=ProjectInfo(
                proposal_id=proposal_id,
                name=name,
                email=email,
                organisation=organisation,
                title=title,
                description=description,
                samples=sample_report.value,
            ),
            issues=tuple(issues),
        )

    def _read_project_info(self, file_path: Path) -> dict[str, Any]:
        df = pd.read_excel(
            file_path, sheet_name=self.project_info_sheet, header=0, engine="openpyxl", usecols=[0, 1]
        )
        info: dict[str, Any] = {}
        for k, v in zip(df.iloc[:, 0], df.iloc[:, 1], strict=False):
            if _is_blank(k):
                continue
            info[_norm_key(k)] = v
        return info

    def _validate_project_info(
        self,
        *,
        proposal_id: str,
        name: str,
        organisation: str,
        email: str,
        title: str,
        description: str,
    ) -> tuple[ValidationIssue, ...]:
        problems: list[str] = []
        if _is_blank(proposal_id):
            problems.append("missing proposal id (expected in filename or 'proposal' field)")

        if _is_blank(name):
            problems.append("missing Name")
        if _is_blank(organisation):
            problems.append("missing Organisation")
        if _is_blank(email):
            problems.append("missing Email")
        if _is_blank(title):
            problems.append("missing Title")
        if _is_blank(description):
            problems.append("missing What/Description")

        if not _is_blank(email):
            try:
                _validate_email(email)
            except ProjectSheetFormatError as e:
                problems.append(str(e))

        return tuple(_error("Project_Info", problem) for problem in problems)

    def _read_samples(self, file_path: Path) -> ValidationReport[dict[int, Sample]]:
        issues: list[ValidationIssue] = []

        try:
            df = pd.read_excel(
                file_path,
                sheet_name=self.sample_info_sheet,
                header=self.sample_header_row,
                engine="openpyxl",
            ).dropna(axis=0, thresh=2)
        except ValueError as e:
            issues.append(_error("Sample_Info", str(e)))
            return ValidationReport(value={}, issues=tuple(issues))

        cols = {str(c).lower(): c for c in df.columns}
        missing_columns = [name for name in self.required_sample_columns if name.lower() not in cols]
        if missing_columns:
            issues.append(
                _error(
                    "Sample_Info",
                    f"missing required columns {missing_columns!r}. Found columns={list(df.columns)!r}",
                )
            )
            return ValidationReport(value={}, issues=tuple(issues))

        def col(name: str) -> str:
            return cols[name.lower()]

        c_sample_id = col("sampleId")
        c_sample_name = col("sampleName")
        c_comp_id = col("componentId")
        c_comp_name = cols.get("componentname")
        c_comp = col("composition")
        c_density = col("density")
        c_vf = col("volFrac")
        c_mf = col("massFrac")
        c_conn = cols.get("componentconnection")
        c_conn_to = cols.get("componentconnectedto")

        samples: dict[int, Sample] = {}
        current_id: int | None = None
        current_name: str = ""
        components: list[SampleComponent] = []

        def append_sample_issue(message: str) -> None:
            issues.append(_error("Sample_Info", message))

        def append_sample_warning(message: str) -> None:
            issues.append(_warning("Sample_Info", message))

        def component_float(field_name: str, value: Any, *, sample_id: int | None, component_id: str) -> float | None:
            try:
                return _as_float(value)
            except ProjectSheetFormatError as e:
                sample_label = "?" if sample_id is None else str(sample_id)
                component_label = component_id or "<missing componentId>"
                append_sample_issue(
                    f"sampleId={sample_label}: component {component_label!r} invalid {field_name}: {e}"
                )
                return None

        def normalize_component_fractions(
            field_name: str,
            attribute_name: str,
            sample_components: list[SampleComponent],
        ) -> list[SampleComponent]:
            provided = [
                (index, getattr(component, attribute_name))
                for index, component in enumerate(sample_components)
                if getattr(component, attribute_name) is not None
            ]
            if len(provided) != len(sample_components):
                return sample_components

            values = [float(value) for _, value in provided]
            if any(not (0.0 <= value <= 1.0) for value in values):
                return sample_components

            total = sum(values)
            if total <= 0:
                append_sample_issue(f"sampleId={current_id}: {field_name} sums to {total:.6f}, expected > 0")
                return sample_components

            if abs(total - 1.0) <= 1e-3:
                return sample_components

            append_sample_warning(f"sampleId={current_id}: {field_name} sums to {total:.6f}; renormalizing to 1.0")
            normalized_values = {index: value / total for (index, value) in provided}
            return [
                attrs.evolve(component, **{attribute_name: normalized_values[index]})
                if index in normalized_values
                else component
                for index, component in enumerate(sample_components)
            ]

        def finalize_sample() -> None:
            nonlocal current_id, current_name, components
            if current_id is None:
                return

            problems: list[str] = []
            if _is_blank(current_name):
                problems.append(f"sampleId={current_id}: missing sampleName")

            if not components:
                problems.append(f"sampleId={current_id}: no component rows found (expected at least one)")
            else:
                for comp in components:
                    if _is_blank(comp.component_id):
                        problems.append(f"sampleId={current_id}: component row missing componentId")
                    if _is_blank(comp.composition):
                        problems.append(f"sampleId={current_id}: component {comp.component_id!r} missing composition")
                    if comp.density is not None and comp.density <= 0:
                        problems.append(f"sampleId={current_id}: component {comp.component_id!r} has non-positive density")
                    if comp.vol_frac is not None and not (0.0 <= comp.vol_frac <= 1.0):
                        problems.append(f"sampleId={current_id}: component {comp.component_id!r} volFrac out of range")
                    if comp.mass_frac is not None and not (0.0 <= comp.mass_frac <= 1.0):
                        problems.append(f"sampleId={current_id}: component {comp.component_id!r} massFrac out of range")

                components = normalize_component_fractions("volFrac", "vol_frac", components)
                components = normalize_component_fractions("massFrac", "mass_frac", components)

                if all(c.vol_frac is None for c in components) and all(c.mass_frac is None for c in components):
                    problems.append(f"sampleId={current_id}: neither volFrac nor massFrac provided for any component")

            for problem in problems:
                append_sample_issue(problem)

            comp_summary = ", ".join([c.composition for c in components if not _is_blank(c.composition)])
            samples[current_id] = Sample(
                sample_id=current_id,
                sample_name=current_name,
                composition=comp_summary,
                components=tuple(components),
            )

            current_id = None
            current_name = ""
            components = []

        for _, row in df.iterrows():
            sid_raw = row.get(c_sample_id, None)
            if not _is_blank(sid_raw):
                finalize_sample()
                try:
                    sid = int(float(sid_raw))
                except Exception:
                    append_sample_issue(f"invalid sampleId value {sid_raw!r}")
                    current_id = None
                    current_name = ""
                    components = []
                    continue
                if sid in samples:
                    append_sample_issue(f"duplicate sampleId={sid}")
                    current_id = None
                    current_name = ""
                    components = []
                    continue
                current_id = sid
                current_name = _as_text(row.get(c_sample_name, ""))

            if current_id is None:
                continue

            comp_id = _as_text(row.get(c_comp_id, ""))
            composition = _as_text(row.get(c_comp, ""))
            density = component_float("density", row.get(c_density, None), sample_id=current_id, component_id=comp_id)
            vol_frac = component_float("volFrac", row.get(c_vf, None), sample_id=current_id, component_id=comp_id)
            mass_frac = component_float("massFrac", row.get(c_mf, None), sample_id=current_id, component_id=comp_id)
            connection = _as_optional_text(row.get(c_conn, "")) if c_conn else None
            connected_to = _as_optional_text(row.get(c_conn_to, "")) if c_conn_to else None
            component_name = _as_optional_text(row.get(c_comp_name, "")) if c_comp_name else None

            if _is_blank(comp_id) and _is_blank(composition) and density is None and vol_frac is None and mass_frac is None:
                continue

            components.append(
                SampleComponent(
                    component_id=comp_id,
                    composition=composition,
                    density=density,
                    vol_frac=vol_frac,
                    mass_frac=mass_frac,
                    connection=connection,
                    connected_to=connected_to,
                    component_name=component_name,
                )
            )

        finalize_sample()

        if not samples:
            append_sample_issue("no samples found in Sample_Info")

        return ValidationReport(value=samples, issues=tuple(issues))
