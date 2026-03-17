from pathlib import Path

import pandas as pd

from mouse_logbook.dataset_validation import DatasetValidator


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


def _write_logbook_file(path: Path, rows: list[dict[str, object]], env_rows: list[dict[str, object]]) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(rows).to_excel(writer, sheet_name="Logbook", index=False, startrow=2)
        pd.DataFrame(env_rows).to_excel(writer, sheet_name="Sample Environments", index=False, startrow=2)


def _write_project_file(path: Path, sample_rows: list[dict[str, object]]) -> None:
    df_proj = pd.DataFrame(
        {
            "k": ["Proposal", "Name", "Organisation", "Email", "Title", "What"],
            "v": [path.stem, "N", "O", "a@b.de", "T", "D"],
        }
    )
    df_samples = pd.DataFrame(sample_rows)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df_proj.to_excel(writer, sheet_name="Project_Info", index=False)
        df_samples.to_excel(writer, sheet_name="Sample_Info", index=False, startrow=2)


def test_dataset_validator_returns_staged_entries_for_xray_level(tmp_path: Path) -> None:
    project_base = tmp_path / "projects"
    year_dir = project_base / "2025"
    year_dir.mkdir(parents=True)
    _write_project_file(
        year_dir / "2025001.xlsx",
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

    logbook_file = tmp_path / "logbook.xlsx"
    _write_logbook_file(
        logbook_file,
        [_valid_logbook_row()],
        [{"sampos": "P1", "motor_a": 1.0}],
    )

    report = DatasetValidator(logbook_file=logbook_file, project_base_dir=project_base).validate(level="xray")

    assert not report.has_errors
    assert report.value.level == "xray"
    assert len(report.value.entries) == 1
    assert len(report.value.projects) == 1
    assert len(report.value.enriched_entries) == 1
    assert len(report.value.chemistry_entries) == 1
    assert len(report.value.material_entries) == 1
    assert len(report.value.xray_entries) == 1
    assert report.value.material_entries[0].sample.sample_density.kind == "apparent_density"
    assert report.value.xray_entries[0].sample.standard_xray["cu_ka"].overall_absorption_coefficient_m_inv is not None


def test_dataset_validator_stage_gates_optional_chemistry_checks(tmp_path: Path) -> None:
    project_base = tmp_path / "projects"
    year_dir = project_base / "2025"
    year_dir.mkdir(parents=True)
    _write_project_file(
        year_dir / "2025001.xlsx",
        [
            {
                "sampleId": 1.0,
                "sampleName": "S1",
                "componentId": "c1",
                "composition": "NotChem",
                "density": 1.0,
                "volFrac": 1.0,
                "massFrac": pd.NA,
            }
        ],
    )

    logbook_file = tmp_path / "logbook.xlsx"
    _write_logbook_file(
        logbook_file,
        [_valid_logbook_row()],
        [{"sampos": "P1", "motor_a": 1.0}],
    )

    core_report = DatasetValidator(logbook_file=logbook_file, project_base_dir=project_base).validate(level="core")
    chemistry_report = DatasetValidator(logbook_file=logbook_file, project_base_dir=project_base).validate(
        level="chemistry"
    )

    assert not core_report.has_errors
    assert not core_report.value.chemistry_entries
    assert chemistry_report.has_errors
    assert any("invalid chemistry description 'NotChem'" in str(issue) for issue in chemistry_report.issues)


def test_dataset_validator_reports_joined_core_errors(tmp_path: Path) -> None:
    project_base = tmp_path / "projects"
    year_dir = project_base / "2025"
    year_dir.mkdir(parents=True)
    _write_project_file(
        year_dir / "2025001.xlsx",
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

    logbook_file = tmp_path / "logbook.xlsx"
    _write_logbook_file(
        logbook_file,
        [
            _valid_logbook_row(Proposal="2025009"),
            _valid_logbook_row(sampleid=2, sampos="P1"),
            _valid_logbook_row(sampleid=1, sampos="P9", batchnum=2),
        ],
        [{"sampos": "P1", "motor_a": 1.0}],
    )

    report = DatasetValidator(logbook_file=logbook_file, project_base_dir=project_base).validate(level="core")

    assert report.has_errors
    assert len(report.value.entries) == 3
    assert not report.value.enriched_entries
    messages = {str(issue) for issue in report.issues}
    assert any("No project file found for '2025009'" in message for message in messages)
    assert any("Sample 2 not found in project 2025001" in message for message in messages)
    assert any("sampos 'P9' not found in sample environments" in message for message in messages)
