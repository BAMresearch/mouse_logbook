from __future__ import annotations

from pathlib import Path

from mouse_logbook.adapters.project_xlsx import ProjectXlsxParser


def test_project_xlsx_parser_parses_samples() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    project_file = data_dir / "projects" / "2025" / "2025001.xlsx"
    project = ProjectXlsxParser().parse(project_file)

    assert project.proposal_id == "2025001"
    assert project.samples, "Expected samples to be parsed"
    first_sample_id = sorted(project.samples.keys())[0]
    assert project.samples[first_sample_id].sample_id == first_sample_id
