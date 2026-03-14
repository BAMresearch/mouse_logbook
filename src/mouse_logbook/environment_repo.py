from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import attrs
import pandas as pd

from .exceptions import SampleEnvironmentFormatError, SampleEnvironmentNotFoundError


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except TypeError:
        pass
    return isinstance(value, str) and not value.strip()


def _norm_col_name(value: Any) -> str:
    return str(value).strip().lower()


def _is_ignored_column_name(value: Any) -> bool:
    name = _norm_col_name(value)
    return not name or name.startswith("unnamed:")


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

        normalized_columns: dict[str, str] = {}
        for column in df.columns:
            if _is_ignored_column_name(column):
                continue
            normalized = _norm_col_name(column)
            if normalized in normalized_columns:
                raise SampleEnvironmentFormatError(
                    f"Duplicate Sample Environments column after normalization: {column!r} and {normalized_columns[normalized]!r}"
                )
            normalized_columns[normalized] = str(column)

        sampos_column = normalized_columns.get("sampos")
        if sampos_column is None:
            raise SampleEnvironmentFormatError("Sample Environments missing required column 'sampos'")

        df = df[[column for column in normalized_columns.values()]]
        df = df[~df[sampos_column].apply(_is_blank)]

        motor_names = [column for normalized, column in normalized_columns.items() if normalized != "sampos"]
        cache: dict[str, dict[str, float]] = {}

        for _, row in df.iterrows():
            sampos = str(row[sampos_column]).strip()
            motor_values: dict[str, float] = {}
            for motor_name in motor_names:
                value = row[motor_name]
                if _is_blank(value):
                    continue
                try:
                    motor_values[str(motor_name)] = float(value)
                except (TypeError, ValueError) as e:
                    raise SampleEnvironmentFormatError(
                        f"Sample Environments sampos {sampos!r} has non-numeric value for motor {motor_name!r}: {value!r}"
                    ) from e
            cache[sampos] = motor_values

        self._cache = cache
        return cache

    def get(self, sample_position_id: str) -> Mapping[str, float]:
        all_pos = self.load_all()
        if sample_position_id not in all_pos:
            raise SampleEnvironmentNotFoundError(f"sampos {sample_position_id!r} not found in sample environments")
        return all_pos[sample_position_id]
