from pathlib import Path

import pandas as pd
import pytest

from mouse_logbook.exceptions import LogbookFormatError
from mouse_logbook.io_excel import LogbookExcelReader, LogbookExcelSpec


def _valid_logbook_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "converttoscript": 1,
        "date": "2026-03-03",
        "Proposal": "2025001",
        "sampleid": 1,
        "User": "user",
        "batchnum": 1,
        "matrixfraction": 0.5,
        "samplethickness": 1.2,
        "sampos": "P1",
        "protocol": "prot",
        "procpipeline": pd.NA,
        "notes": pd.NA,
        "bgdate": pd.NA,
        "bgnumber": pd.NA,
        "dbgdate": pd.NA,
        "dbgnumber": pd.NA,
        "key1": "exposure",
        "val1": "5s",
    }
    row.update(overrides)
    return row


def _make_reader(tmp_path: Path, rows: list[dict[str, object]]) -> LogbookExcelReader:
    p = tmp_path / "logbook.xlsx"
    pd.DataFrame(rows).to_excel(p, index=False)
    return LogbookExcelReader(file_path=p, spec=LogbookExcelSpec(header_row=0))


def test_missing_required_columns_raises(tmp_path: Path) -> None:
    p = tmp_path / "logbook.xlsx"
    pd.DataFrame({"foo": [1], "bar": [2]}).to_excel(p, index=False)
    reader = LogbookExcelReader(file_path=p, spec=LogbookExcelSpec(header_row=0))
    with pytest.raises(LogbookFormatError):
        reader.read_entries(load_all=True)


def test_inspect_entries_reports_missing_required_columns(tmp_path: Path) -> None:
    p = tmp_path / "logbook.xlsx"
    pd.DataFrame({"foo": [1], "bar": [2]}).to_excel(p, index=False)
    reader = LogbookExcelReader(file_path=p, spec=LogbookExcelSpec(header_row=0))

    report = reader.inspect_entries(load_all=True)

    assert report.has_errors
    assert not report.value
    assert str(report.issues[0]) == "Logbook: Missing required columns: ['converttoscript', 'date', 'Proposal', 'sampleid', 'User', 'batchnum', 'matrixfraction', 'samplethickness', 'sampos', 'protocol', 'procpipeline', 'notes', 'bgdate', 'bgnumber', 'dbgdate', 'dbgnumber']"


def test_read_entries_parses_valid_rows_and_filters_by_convert_to_script(tmp_path: Path) -> None:
    reader = _make_reader(
        tmp_path,
        [
            _valid_logbook_row(converttoscript=1, Proposal=2025001.0),
            _valid_logbook_row(converttoscript=0, sampleid=2, sampos="P2"),
        ],
    )

    selected = reader.read_entries(load_all=False)
    all_entries = reader.read_entries(load_all=True)

    assert [entry.sample_id for entry in selected] == [1]
    assert [entry.sample_id for entry in all_entries] == [1, 2]
    assert selected[0].proposal_id == "2025001"
    assert selected[0].additional_parameters == {"exposure": "5s"}


def test_read_entries_invalid_convert_to_script_raises_with_row_and_field(tmp_path: Path) -> None:
    reader = _make_reader(tmp_path, [_valid_logbook_row(converttoscript="maybe")])

    with pytest.raises(LogbookFormatError, match=r"Row 2: converttoscript: expected 0 or 1, got 'maybe'"):
        reader.read_entries(load_all=False)


def test_read_entries_invalid_sample_id_raises_with_row_and_field(tmp_path: Path) -> None:
    reader = _make_reader(tmp_path, [_valid_logbook_row(sampleid="abc")])

    with pytest.raises(LogbookFormatError, match=r"Row 2: sampleid: expected integer, got 'abc'"):
        reader.read_entries(load_all=True)


def test_read_entries_invalid_optional_background_field_raises_with_row_and_field(tmp_path: Path) -> None:
    reader = _make_reader(tmp_path, [_valid_logbook_row(bgnumber="bad-bg")])

    with pytest.raises(LogbookFormatError, match=r"Row 2: bgnumber: expected integer, got 'bad-bg'"):
        reader.read_entries(load_all=True)


def test_inspect_entries_collects_multiple_row_errors_and_keeps_valid_entries(tmp_path: Path) -> None:
    reader = _make_reader(
        tmp_path,
        [
            _valid_logbook_row(sampleid=1),
            _valid_logbook_row(sampleid="abc"),
            _valid_logbook_row(Proposal="", matrixfraction="oops"),
            _valid_logbook_row(date="not-a-date"),
        ],
    )

    report = reader.inspect_entries(load_all=True)

    assert report.has_errors
    assert [entry.sample_id for entry in report.value] == [1]
    messages = {str(issue) for issue in report.issues}
    assert "Row 3: sampleid: expected integer, got 'abc'" in messages
    assert "Row 4: Proposal: value is required" in messages
    assert "Row 4: matrixfraction: expected number, got 'oops'" in messages
    assert "Row 5: date: expected datetime, got 'not-a-date'" in messages
