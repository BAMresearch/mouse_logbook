from __future__ import annotations

from pathlib import Path

import pandas as pd

from mouse_logbook.adapters.project_xlsx import ProjectXlsxParser


def test_project_xlsx_parser_parses_samples() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "data"
    project_file = data_dir / "projects" / "2025" / "2025001.xlsx"
    project = ProjectXlsxParser().parse(project_file)

    assert project.proposal_id == "2025001"
    assert project.samples, "Expected samples to be parsed"
    first_sample_id = sorted(project.samples.keys())[0]
    assert project.samples[first_sample_id].sample_id == first_sample_id


def _write_project_file(path: Path, sample_rows: list[dict[str, object]]) -> None:
    df_proj = pd.DataFrame(
        {
            "k": ["Name", "Organisation", "Email", "Title", "What"],
            "v": ["N", "O", "a@b.de", "T", "D"],
        }
    )
    df_samples = pd.DataFrame(sample_rows)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df_proj.to_excel(writer, sheet_name="Project_Info", index=False)
        df_samples.to_excel(writer, sheet_name="Sample_Info", index=False, startrow=2)


def test_project_xlsx_parser_keeps_component_on_sample_start_row(tmp_path: Path) -> None:
    project_file = tmp_path / "2025125.xlsx"
    _write_project_file(
        project_file,
        [
            {
                "sampleId": 1.0,
                "sampleName": "S1",
                "componentId": "c1",
                "composition": "H2O",
                "density": 1.0,
                "volFrac": 1.0,
                "massFrac": pd.NA,
            }
        ],
    )

    project = ProjectXlsxParser().parse(project_file)

    sample = project.samples[1]
    assert len(sample.components) == 1
    assert sample.components[0].component_id == "c1"
    assert sample.components[0].composition == "H2O"
    assert sample.components[0].vol_frac == 1.0


def test_project_xlsx_parser_supports_both_sample_block_layouts(tmp_path: Path) -> None:
    project_start_row = tmp_path / "2025126.xlsx"
    _write_project_file(
        project_start_row,
        [
            {
                "sampleId": 1.0,
                "sampleName": "S1",
                "componentId": "c1",
                "composition": "H2O",
                "density": 1.0,
                "volFrac": 0.25,
                "massFrac": pd.NA,
            },
            {
                "sampleId": pd.NA,
                "sampleName": pd.NA,
                "componentId": "c2",
                "composition": "SiO2",
                "density": 2.2,
                "volFrac": 0.75,
                "massFrac": pd.NA,
            },
        ],
    )

    project_continuation_row = tmp_path / "2025127.xlsx"
    _write_project_file(
        project_continuation_row,
        [
            {
                "sampleId": 1.0,
                "sampleName": "S1",
                "componentId": pd.NA,
                "composition": pd.NA,
                "density": pd.NA,
                "volFrac": pd.NA,
                "massFrac": pd.NA,
            },
            {
                "sampleId": pd.NA,
                "sampleName": pd.NA,
                "componentId": "c1",
                "composition": "H2O",
                "density": 1.0,
                "volFrac": 0.25,
                "massFrac": pd.NA,
            },
            {
                "sampleId": pd.NA,
                "sampleName": pd.NA,
                "componentId": "c2",
                "composition": "SiO2",
                "density": 2.2,
                "volFrac": 0.75,
                "massFrac": pd.NA,
            },
        ],
    )

    project_a = ProjectXlsxParser().parse(project_start_row)
    project_b = ProjectXlsxParser().parse(project_continuation_row)

    sample_a = project_a.samples[1]
    sample_b = project_b.samples[1]

    assert sample_a.sample_name == sample_b.sample_name == "S1"
    assert sample_a.composition == sample_b.composition == "H2O, SiO2"
    assert sample_a.components == sample_b.components
