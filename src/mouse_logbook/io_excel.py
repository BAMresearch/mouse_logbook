from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import attrs
import pandas as pd

from .exceptions import LogbookFormatError
from .models import LogbookEntry
from .validation import ValidationIssue, ValidationReport


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    return isinstance(value, str) and not value.strip()


def _error(location: str, message: str) -> ValidationIssue:
    return ValidationIssue(severity="error", location=location, message=message)


def _as_required_text(value: Any) -> str:
    if _is_blank(value):
        raise ValueError("value is required")
    return str(value).strip()


def _as_optional_text(value: Any) -> str | None:
    if _is_blank(value):
        return None
    return str(value).strip()


def _as_int(value: Any) -> int:
    if _is_blank(value):
        raise ValueError("value is required")
    try:
        return int(float(value))
    except (TypeError, ValueError) as e:
        raise ValueError(f"expected integer, got {value!r}") from e


def _as_optional_int(value: Any) -> int | None:
    if _is_blank(value):
        return None
    return _as_int(value)


def _as_float(value: Any) -> float:
    if _is_blank(value):
        raise ValueError("value is required")
    try:
        return float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"expected number, got {value!r}") from e


def _as_timestamp(value: Any) -> pd.Timestamp:
    if _is_blank(value):
        raise ValueError("value is required")
    try:
        ts = pd.to_datetime(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"expected datetime, got {value!r}") from e
    if pd.isna(ts):
        raise ValueError(f"expected datetime, got {value!r}")
    if not isinstance(ts, pd.Timestamp):
        raise ValueError(f"expected datetime, got {value!r}")
    return ts


def _as_optional_timestamp(value: Any) -> pd.Timestamp | None:
    if _is_blank(value):
        return None
    return _as_timestamp(value)


def _as_convert_to_script(value: Any) -> bool:
    if _is_blank(value):
        raise ValueError("value is required")
    if isinstance(value, bool):
        return value
    try:
        numeric = float(value)
    except (TypeError, ValueError) as e:
        raise ValueError(f"expected 0 or 1, got {value!r}") from e
    if numeric not in (0.0, 1.0):
        raise ValueError(f"expected 0 or 1, got {value!r}")
    return int(numeric) == 1


@attrs.define(frozen=True, slots=True)
class LogbookExcelSpec:
    """Defines how the logbook Excel file is parsed."""

    header_row: int = 2
    sheet_name: int | str = 0

    required_columns: Sequence[str] = (
        "converttoscript",
        "date",
        "Proposal",
        "sampleid",
        "User",
        "batchnum",
        "matrixfraction",
        "samplethickness",
        "sampos",
        "protocol",
        "procpipeline",
        "notes",
        "bgdate",
        "bgnumber",
        "dbgdate",
        "dbgnumber",
    )

    key_prefix: str = "key"
    val_prefix: str = "val"


@attrs.define(slots=True)
class LogbookExcelReader:
    """
    Pure I/O: reads an Excel logbook file into LogbookEntry objects.

    No project/sample lookups happen here.
    """

    file_path: Path = attrs.field(converter=Path)
    spec: LogbookExcelSpec = attrs.field(factory=LogbookExcelSpec)

    def read_entries(self, *, load_all: bool = False) -> list[LogbookEntry]:
        report = self.inspect_entries(load_all=load_all)
        if report.has_errors:
            raise LogbookFormatError("; ".join(str(issue) for issue in report.issues_for("error")))
        return report.value

    def inspect_entries(self, *, load_all: bool = False) -> ValidationReport[list[LogbookEntry]]:
        try:
            df = self._read_dataframe()
        except LogbookFormatError as e:
            return ValidationReport(value=[], issues=(_error("Logbook", str(e)),))

        entries: list[LogbookEntry] = []
        issues: list[ValidationIssue] = []

        for row_index, row in df.iterrows():
            entry, row_issues = self._inspect_row(row_index, row)
            issues.extend(row_issues)
            if row_issues or entry is None:
                continue
            if (not load_all) and not entry.convert_to_script:
                continue
            entries.append(entry)

        return ValidationReport(value=entries, issues=tuple(issues))

    def _read_dataframe(self) -> pd.DataFrame:
        if not self.file_path.is_file():
            raise FileNotFoundError(f"Logbook file not found: {self.file_path}")

        df = pd.read_excel(
            self.file_path,
            sheet_name=self.spec.sheet_name,
            header=self.spec.header_row,
            engine="openpyxl",
            usecols=lambda x: x not in ["Unnamed: 0", None],
        )

        missing = [c for c in self.spec.required_columns if c not in df.columns]
        if missing:
            raise LogbookFormatError(f"Missing required columns: {missing}")

        return df.dropna(axis=0, thresh=2)

    def _inspect_row(
        self,
        row_index: int,
        row: pd.Series,
    ) -> tuple[LogbookEntry | None, tuple[ValidationIssue, ...]]:
        excel_row = self.spec.header_row + 2 + int(row_index)
        location = f"Row {excel_row}"
        issues: list[ValidationIssue] = []

        def capture(field_name: str, parser, value: Any) -> Any | None:
            try:
                return parser(value)
            except ValueError as e:
                issues.append(_error(location, f"{field_name}: {e}"))
                return None

        convert_to_script = capture("converttoscript", _as_convert_to_script, row["converttoscript"])
        date = capture("date", _as_timestamp, row["date"])
        proposal_id = capture("Proposal", _as_required_text, row["Proposal"])
        sample_id = capture("sampleid", _as_int, row["sampleid"])
        user = capture("User", _as_required_text, row["User"])
        batch_num = capture("batchnum", _as_int, row["batchnum"])
        matrix_fraction = capture("matrixfraction", _as_float, row["matrixfraction"])
        sample_thickness = capture("samplethickness", _as_float, row["samplethickness"])
        sample_position_id = capture("sampos", _as_required_text, row["sampos"])
        protocol = capture("protocol", _as_required_text, row["protocol"])
        processing_pipeline = capture("procpipeline", _as_optional_text, row.get("procpipeline"))
        notes = capture("notes", _as_optional_text, row.get("notes"))
        bg_date = capture("bgdate", _as_optional_timestamp, row.get("bgdate"))
        bg_number = capture("bgnumber", _as_optional_int, row.get("bgnumber"))
        dbg_date = capture("dbgdate", _as_optional_timestamp, row.get("dbgdate"))
        dbg_number = capture("dbgnumber", _as_optional_int, row.get("dbgnumber"))

        if issues:
            return None, tuple(issues)

        additional_parameters = self._extract_additional_parameters(row)
        entry = LogbookEntry(
            row_index=int(row_index),
            convert_to_script=convert_to_script,
            date=date,
            proposal_id=proposal_id,
            sample_id=sample_id,
            user=user,
            batch_num=batch_num,
            sample_position_id=sample_position_id,
            bg_date=bg_date,
            bg_number=bg_number,
            dbg_date=dbg_date,
            dbg_number=dbg_number,
            matrix_fraction=matrix_fraction,
            sample_thickness=sample_thickness,
            protocol=protocol,
            processing_pipeline=processing_pipeline,
            notes=notes,
            additional_parameters=additional_parameters,
        )
        return entry, ()

    def _extract_additional_parameters(self, row: pd.Series) -> Mapping[str, str]:
        key_cols = [c for c in row.index if str(c).startswith(self.spec.key_prefix)]
        val_cols = [c for c in row.index if str(c).startswith(self.spec.val_prefix)]

        keys = [row[c] for c in key_cols]
        vals = [row[c] for c in val_cols]

        extras: dict[str, str] = {}
        for k, v in zip(keys, vals, strict=False):
            if pd.isna(k) or pd.isna(v):
                continue
            extras[str(k)] = str(v)
        return extras
