from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

import attrs
import pandas as pd

from .exceptions import SampleEnvironmentNotFoundError


@attrs.define(slots=True)
class SampleEnvironmentRepository:
    """
    Reads and caches sample-position motor values from the logbook Excel file.

    Expects a sheet (default: 'Sample Environments') with a column 'sampos' and further motor columns.
    """

    logbook_file: Path = attrs.field(converter=Path)
    sheet_name: str = attrs.field(default="Sample Environments")
    header_row: int = attrs.field(default=2)

    _cache: dict[str, dict[str, float]] | None = attrs.field(init=False, default=None)

    def load_all(self) -> Mapping[str, Mapping[str, float]]:
        if self._cache is not None:
            return self._cache

        if not self.logbook_file.is_file():
            raise FileNotFoundError(f"Logbook file not found: {self.logbook_file}")

        df = pd.read_excel(
            self.logbook_file,
            sheet_name=self.sheet_name,
            header=self.header_row,
            engine="openpyxl",
        )

        df = df.iloc[:, 1:]
        df = df.dropna(subset=["sampos"])

        motor_names = list(df.columns[1:])
        cache: dict[str, dict[str, float]] = {}

        for _, row in df.iterrows():
            sampos = str(row["sampos"])
            motor_values = {str(m): float(row[m]) for m in motor_names if m in row and pd.notna(row[m])}
            cache[sampos] = motor_values

        self._cache = cache
        return cache

    def get(self, sample_position_id: str) -> Mapping[str, float]:
        all_pos = self.load_all()
        if sample_position_id not in all_pos:
            raise SampleEnvironmentNotFoundError(f"sampos {sample_position_id!r} not found in sample environments")
        return all_pos[sample_position_id]
