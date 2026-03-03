from __future__ import annotations

from pathlib import Path
from typing import Any

import attrs
import pandas as pd

from ..exceptions import ProjectSheetFormatError


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
    return v is None or (isinstance(v, float) and pd.isna(v)) or (isinstance(v, str) and not v.strip())


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

    # ---- schema requirements ----
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
        file_path = Path(file_path)

        info = self._read_project_info(file_path)
        proposal_id = _normalize_proposal_id(info.get("proposal")) or _normalize_proposal_id(file_path.stem)

        name = str(info.get("name", "")).strip()
        organisation = str(info.get("organisation", "")).strip()
        email = str(info.get("email", "")).strip()
        title = str(info.get("title", "")).strip()
        description = str(info.get("what", "")).strip()

        self._validate_project_info(
            proposal_id=proposal_id,
            name=name,
            organisation=organisation,
            email=email,
            title=title,
            description=description,
            file_path=file_path,
        )

        samples = self._read_samples(file_path)

        return ProjectInfo(
            proposal_id=proposal_id,
            name=name,
            email=email,
            organisation=organisation,
            title=title,
            description=description,
            samples=samples,
        )

    # ---- Project_Info ----

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
        file_path: Path,
    ) -> None:
        problems: list[str] = []
        if _is_blank(proposal_id):
            problems.append("missing proposal id (expected in filename or 'proposal' field)")

        if _is_blank(name):
            problems.append("Project_Info: missing Name")
        if _is_blank(organisation):
            problems.append("Project_Info: missing Organisation")
        if _is_blank(email):
            problems.append("Project_Info: missing Email")
        if _is_blank(title):
            problems.append("Project_Info: missing Title")
        if _is_blank(description):
            problems.append("Project_Info: missing What/Description")

        if not _is_blank(email):
            try:
                _validate_email(email)
            except ProjectSheetFormatError as e:
                problems.append(str(e))

        if problems and self.strict:
            raise ProjectSheetFormatError(f"{file_path.name}: invalid Project_Info: " + "; ".join(problems))

    # ---- Sample_Info ----

    def _read_samples(self, file_path: Path) -> dict[int, Sample]:
        df = pd.read_excel(
            file_path,
            sheet_name=self.sample_info_sheet,
            header=self.sample_header_row,
            engine="openpyxl",
        ).dropna(axis=0, thresh=2)

        # validate presence of required columns (support capitalization variants)
        cols = {c.lower(): c for c in df.columns}
        def col(name: str) -> str:
            key = name.lower()
            if key not in cols:
                raise ProjectSheetFormatError(
                    f"{file_path.name}: Sample_Info missing required column {name!r}. "
                    f"Found columns={list(df.columns)!r}"
                )
            return cols[key]

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

        # group rows into sample blocks: start when sampleId is present
        samples: dict[int, Sample] = {}
        current_id: int | None = None
        current_name: str = ""
        components: list[SampleComponent] = []

        def finalize_sample() -> None:
            nonlocal current_id, current_name, components
            if current_id is None:
                return

            # schema checks per sample
            problems: list[str] = []
            if _is_blank(current_name):
                problems.append(f"sampleId={current_id}: missing sampleName")

            # at least one component with composition
            if not components:
                problems.append(f"sampleId={current_id}: no component rows found (expected at least one)")
            else:
                for comp in components:
                    if _is_blank(comp.component_id):
                        problems.append(f"sampleId={current_id}: component row missing componentId")
                    if _is_blank(comp.composition):
                        problems.append(f"sampleId={current_id}: component {comp.component_id!r} missing composition")
                    if comp.density is not None and comp.density <= 0:
                        problems.append(
                            f"sampleId={current_id}: component {comp.component_id!r} has non-positive density"
                        )
                    if comp.vol_frac is not None and not (0.0 <= comp.vol_frac <= 1.0):
                        problems.append(
                            f"sampleId={current_id}: component {comp.component_id!r} volFrac out of range"
                        )
                    if comp.mass_frac is not None and not (0.0 <= comp.mass_frac <= 1.0):
                        problems.append(
                            f"sampleId={current_id}: component {comp.component_id!r} massFrac out of range"
                        )

                # if all vol_frac are provided, check they sum to ~1
                vfs = [c.vol_frac for c in components if c.vol_frac is not None]
                if len(vfs) == len(components):
                    s = sum(vfs)
                    if abs(s - 1.0) > 1e-3:
                        problems.append(f"sampleId={current_id}: volFrac sums to {s:.6f}, expected ~1.0")

                # if all mass_frac are provided, check they sum to ~1
                mfs = [c.mass_frac for c in components if c.mass_frac is not None]
                if len(mfs) == len(components):
                    s = sum(mfs)
                    if abs(s - 1.0) > 1e-3:
                        problems.append(f"sampleId={current_id}: massFrac sums to {s:.6f}, expected ~1.0")

                # ensure at least one of volFrac/massFrac is provided somewhere (otherwise components are unusable)
                if all(c.vol_frac is None for c in components) and all(c.mass_frac is None for c in components):
                    problems.append(f"sampleId={current_id}: neither volFrac nor massFrac provided for any component")

            if problems and self.strict:
                raise ProjectSheetFormatError(f"{file_path.name}: invalid Sample_Info: " + "; ".join(problems))

            # derive a human-readable composition summary from components
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
                # start new sample block
                finalize_sample()
                try:
                    sid = int(float(sid_raw))
                except Exception as e:
                    raise ProjectSheetFormatError(f"{file_path.name}: invalid sampleId value {sid_raw!r}") from e
                if sid in samples:
                    raise ProjectSheetFormatError(f"{file_path.name}: duplicate sampleId={sid}")
                current_id = sid
                current_name = str(row.get(c_sample_name, "")).strip()
                continue

            # component rows belong to current sample
            if current_id is None:
                # ignore leading/stray rows before first sample
                continue

            comp_id = str(row.get(c_comp_id, "")).strip()
            composition = str(row.get(c_comp, "")).strip()
            density = _as_float(row.get(c_density, None))
            vol_frac = _as_float(row.get(c_vf, None))
            mass_frac = _as_float(row.get(c_mf, None))
            connection = str(row.get(c_conn, "")).strip() if c_conn else None
            connected_to = str(row.get(c_conn_to, "")).strip() if c_conn_to else None
            component_name = str(row.get(c_comp_name, "")).strip() if c_comp_name else None

            # if the row is effectively blank, skip
            if _is_blank(comp_id) and _is_blank(composition) and density is None and vol_frac is None and mass_frac is None:
                continue

            components.append(
                SampleComponent(
                    component_id=comp_id,
                    composition=composition,
                    density=density,
                    vol_frac=vol_frac,
                    mass_frac=mass_frac,
                    connection=connection or None,
                    connected_to=connected_to or None,
                    component_name=component_name or None,
                )
            )

        finalize_sample()

        if not samples and self.strict:
            raise ProjectSheetFormatError(f"{file_path.name}: no samples found in Sample_Info")
        return samples
