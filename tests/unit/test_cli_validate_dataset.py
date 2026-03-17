from pathlib import Path

import pandas as pd

from mouse_logbook.cli import main


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


def test_cli_validate_dataset_exit_codes_across_levels(tmp_path: Path) -> None:
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

    assert main(["validate-dataset", str(logbook_file), str(project_base)]) == 0
    assert main(["validate-dataset", str(logbook_file), str(project_base), "--level", "xray"]) == 0


def test_cli_validate_dataset_lenient_reports_extension_issues(tmp_path: Path) -> None:
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

    report = tmp_path / "dataset_validation.txt"

    strict_rc = main(["validate-dataset", str(logbook_file), str(project_base), "--level", "chemistry"])
    lenient_rc = main(
        [
            "validate-dataset",
            str(logbook_file),
            str(project_base),
            "--level",
            "chemistry",
            "--lenient",
            "--report",
            str(report),
        ]
    )

    assert strict_rc == 1
    assert lenient_rc == 0
    assert "invalid chemistry description 'NotChem'" in report.read_text(encoding="utf-8")
