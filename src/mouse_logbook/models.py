from __future__ import annotations

from typing import Any, Mapping, Optional

import attrs
import pandas as pd


def _optional(converter):
    def _conv(value):
        return converter(value) if value is not None and pd.notna(value) else None

    return _conv


def _to_timestamp(value: Any) -> pd.Timestamp:
    ts = pd.to_datetime(value)
    if not isinstance(ts, pd.Timestamp):
        raise TypeError("Expected pandas Timestamp after conversion.")
    return ts


def _normalize_proposal_id(value: Any) -> str:
    """Normalize Excel proposal IDs to a stable string (e.g. 2025001.0 -> '2025001')."""
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


def flexible_int(value: Any) -> int:
    """Convert value to int, supporting Excel-ish strings like '1.0'."""
    try:
        return int(float(value))
    except (TypeError, ValueError) as e:
        raise ValueError(f"Cannot convert {value!r} to int.") from e


@attrs.frozen(kw_only=True, slots=True)
class LogbookEntry:
    """
    Immutable representation of one logbook row.

    Contract:
      - No project/sample/environment attached here.
      - Suitable as a stable “source of truth” payload for downstream usage.
    """

    row_index: int = attrs.field(validator=attrs.validators.instance_of(int))
    convert_to_script: bool = attrs.field(converter=bool)

    date: pd.Timestamp = attrs.field(converter=_to_timestamp)
    proposal_id: str = attrs.field(converter=_normalize_proposal_id)
    sample_id: int = attrs.field(converter=flexible_int)
    user: str = attrs.field(converter=str)

    batch_num: int = attrs.field(converter=flexible_int)
    sample_position_id: str = attrs.field(converter=str)  # sampos

    matrix_fraction: float = attrs.field(converter=float)
    sample_thickness: float = attrs.field(converter=float)

    protocol: str = attrs.field(converter=str)
    processing_pipeline: Optional[str] = attrs.field(converter=_optional(str), default=None)
    notes: Optional[str] = attrs.field(converter=_optional(str), default=None)

    bg_date: Optional[pd.Timestamp] = attrs.field(converter=_optional(_to_timestamp), default=None)
    bg_number: Optional[int] = attrs.field(converter=_optional(flexible_int), default=None)
    dbg_date: Optional[pd.Timestamp] = attrs.field(converter=_optional(_to_timestamp), default=None)
    dbg_number: Optional[int] = attrs.field(converter=_optional(flexible_int), default=None)

    additional_parameters: Mapping[str, str] = attrs.field(
        converter=lambda d: {str(k): str(v) for k, v in dict(d).items()},
        factory=dict,
    )

    ymd: str = attrs.field(init=False)

    def __attrs_post_init__(self) -> None:
        object.__setattr__(self, "ymd", self.date.strftime("%Y%m%d"))


@attrs.frozen(kw_only=True, slots=True)
class EnrichedLogbookEntry:
    """A logbook entry enriched with project info, sample definition, and motor positions."""

    entry: LogbookEntry
    project: Any
    sample: Any
    sample_position: Mapping[str, float] = attrs.field(factory=dict)
