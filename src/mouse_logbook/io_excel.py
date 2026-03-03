from __future__ import annotations

from pathlib import Path
from typing import Mapping, Sequence

import attrs
import pandas as pd

from .exceptions import LogbookFormatError
from .models import LogbookEntry


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
        df = self._read_dataframe()
        entries: list[LogbookEntry] = []

        for row_index, row in df.iterrows():
            if (not load_all) and int(row["converttoscript"]) != 1:
                continue

            additional_parameters = self._extract_additional_parameters(row)
            entries.append(
                LogbookEntry(
                    row_index=int(row_index),
                    convert_to_script=int(row["converttoscript"]) == 1,
                    date=row["date"],
                    proposal_id=row["Proposal"],
                    sample_id=row["sampleid"],
                    user=row["User"],
                    batch_num=row["batchnum"],
                    sample_position_id=row["sampos"],
                    bg_date=row.get("bgdate"),
                    bg_number=row.get("bgnumber"),
                    dbg_date=row.get("dbgdate"),
                    dbg_number=row.get("dbgnumber"),
                    matrix_fraction=row["matrixfraction"],
                    sample_thickness=row["samplethickness"],
                    protocol=row["protocol"],
                    processing_pipeline=row.get("procpipeline"),
                    notes=row.get("notes"),
                    additional_parameters=additional_parameters,
                )
            )
        return entries

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
