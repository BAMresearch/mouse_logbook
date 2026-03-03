from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any

import attrs
import pandas as pd

from .adapters.project_xlsx import ProjectXlsxParser
from .environment_repo import SampleEnvironmentRepository
from .io_excel import LogbookExcelReader
from .models import EnrichedLogbookEntry, LogbookEntry
from .project_repo import ProjectFileLocator, ProjectRepository
from .services import LogbookEnricher


def _ts_to_iso(ts: pd.Timestamp | None) -> str | None:
    if ts is None:
        return None
    return ts.isoformat()


@attrs.define(slots=True)
class Logbook2MouseEntry:
    """
    Compatibility entry object matching historical `logbook2mouse` usage.

    Why this is *mutable*:
    - legacy measurement-script generation uses `copy.deepcopy(entry)` and then mutates
      `entry.additional_parameters[...]` to expand configurations.

    Use `models.LogbookEntry` for immutable records.
    """

    row_index: int
    date: pd.Timestamp
    proposal: str
    sampleid: int
    user: str
    batchnum: int
    sampos: str

    matrixfraction: float
    samplethickness: float

    protocol: str
    procpipeline: str | None = None
    notes: str | None = None

    bgdate: pd.Timestamp | None = None
    bgnumber: int | None = None
    dbgdate: pd.Timestamp | None = None
    dbgnumber: int | None = None

    additional_parameters: dict[str, str] = attrs.field(factory=dict)

    # enrichment
    project: Any = None
    sample: Any = None
    positions: Mapping[str, float] = attrs.field(factory=dict)

    ymd: str = attrs.field(init=False)

    def __attrs_post_init__(self) -> None:
        self.ymd = self.date.strftime("%Y%m%d")

    @classmethod
    def from_enriched(cls, enriched: EnrichedLogbookEntry) -> Logbook2MouseEntry:
        e = enriched.entry
        return cls(
            row_index=e.row_index,
            date=e.date,
            proposal=e.proposal_id,
            sampleid=e.sample_id,
            user=e.user,
            batchnum=e.batch_num,
            sampos=e.sample_position_id,
            matrixfraction=e.matrix_fraction,
            samplethickness=e.sample_thickness,
            protocol=e.protocol,
            procpipeline=e.processing_pipeline,
            notes=e.notes,
            bgdate=e.bg_date,
            bgnumber=e.bg_number,
            dbgdate=e.dbg_date,
            dbgnumber=e.dbg_number,
            additional_parameters=dict(e.additional_parameters),
            project=enriched.project,
            sample=enriched.sample,
            positions=enriched.sample_position,
        )

    def __repr__(self) -> str:
        """
        Script-friendly representation.

        The legacy generator writes `entry = {entry}` into a python script. That pattern is brittle,
        but we keep it workable by serializing only primitive/logbook fields (no `project`/`sample`/`positions`).
        """

        def ts_expr(s: str | None) -> str:
            return "None" if s is None else f"pd.Timestamp({s!r})"

        return (
            "Logbook2MouseEntry("
            f"row_index={self.row_index}, "
            f"date={ts_expr(_ts_to_iso(self.date))}, "
            f"proposal={self.proposal!r}, "
            f"sampleid={self.sampleid}, "
            f"user={self.user!r}, "
            f"batchnum={self.batchnum}, "
            f"sampos={self.sampos!r}, "
            f"matrixfraction={self.matrixfraction}, "
            f"samplethickness={self.samplethickness}, "
            f"protocol={self.protocol!r}, "
            f"procpipeline={self.procpipeline!r}, "
            f"notes={self.notes!r}, "
            f"bgdate={ts_expr(_ts_to_iso(self.bgdate))}, "
            f"bgnumber={self.bgnumber!r}, "
            f"dbgdate={ts_expr(_ts_to_iso(self.dbgdate))}, "
            f"dbgnumber={self.dbgnumber!r}, "
            f"additional_parameters={dict(self.additional_parameters)!r}"
            ")"
        )


@attrs.define(slots=True)
class Logbook2MouseReader:
    """
    Legacy-compatible façade preserving the downstream initialization pattern:

    ```python
    reader = Logbook2MouseReader(logbook_path, project_base_path=project_base_path)
    for entry in reader:
        ...
    ```
    """

    logbook_path: Path = attrs.field(converter=Path)
    project_base_path: Path = attrs.field(converter=Path)

    load_all: bool = attrs.field(default=False)
    project_parser: Callable[[Path], Any] | None = attrs.field(default=None)

    _entries: list[LogbookEntry] = attrs.field(init=False, factory=list)
    _enriched: list[EnrichedLogbookEntry] = attrs.field(init=False, factory=list)
    _legacy: list[Logbook2MouseEntry] = attrs.field(init=False, factory=list)

    def __attrs_post_init__(self) -> None:
        reader = LogbookExcelReader(self.logbook_path)
        self._entries = reader.read_entries(load_all=self.load_all)

        parser = self.project_parser or ProjectXlsxParser(strict=True).parse
        projects = ProjectRepository(ProjectFileLocator(self.project_base_path), parser)
        environments = SampleEnvironmentRepository(self.logbook_path)
        enricher = LogbookEnricher(projects=projects, environments=environments)

        self._enriched = enricher.enrich_many(self._entries)
        self._legacy = [Logbook2MouseEntry.from_enriched(e) for e in self._enriched]

    @property
    def entries(self) -> list[Logbook2MouseEntry]:
        return self._legacy

    def __iter__(self) -> Iterator[Logbook2MouseEntry]:
        return iter(self._legacy)
