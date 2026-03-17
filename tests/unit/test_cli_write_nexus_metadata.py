from pathlib import Path

import h5py
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
        "samplethickness": 0.0001,
        "sampos": "Mo B5",
        "protocol": "prot.py",
        "procpipeline": "pipe.nxs",
        "notes": "note",
        "bgdate": "2026-03-02",
        "bgnumber": 7,
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
            "v": [path.stem, "Owner", "Org", "a@b.de", "Title", "Description"],
        }
    )
    df_samples = pd.DataFrame(sample_rows)

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        df_proj.to_excel(writer, sheet_name="Project_Info", index=False)
        df_samples.to_excel(writer, sheet_name="Sample_Info", index=False, startrow=2)


def test_cli_write_nexus_metadata_writes_file_for_selected_identifier(tmp_path: Path) -> None:
    project_base = tmp_path / "projects"
    year_dir = project_base / "2025"
    year_dir.mkdir(parents=True)
    _write_project_file(
        year_dir / "2025001.xlsx",
        [
            {
                "sampleId": 1.0,
                "sampleName": "Water",
                "componentId": "a",
                "componentName": "Water",
                "composition": "H2O",
                "density": 0.998,
                "volFrac": 1.0,
                "massFrac": 1.0,
            }
        ],
    )

    logbook_file = tmp_path / "logbook.xlsx"
    _write_logbook_file(
        logbook_file,
        [_valid_logbook_row()],
        [{"sampos": "Mo B5", "motor_a": 1.0}],
    )

    output_file = tmp_path / "written.nxs"
    rc = main(
        [
            "write-nexus-metadata",
            str(logbook_file),
            str(project_base),
            str(output_file),
            "--ymd",
            "20260303",
            "--batch-num",
            "1",
        ]
    )

    assert rc == 0
    with h5py.File(output_file, "r") as handle:
        assert handle["/entry1/sample/overall_mu"].attrs["source_key"] == "mo_ka"


def test_cli_write_nexus_metadata_fails_for_ambiguous_selection(tmp_path: Path) -> None:
    project_base = tmp_path / "projects"
    year_dir = project_base / "2025"
    year_dir.mkdir(parents=True)
    _write_project_file(
        year_dir / "2025001.xlsx",
        [
            {
                "sampleId": 1.0,
                "sampleName": "Water",
                "componentId": "a",
                "componentName": "Water",
                "composition": "H2O",
                "density": 0.998,
                "volFrac": 1.0,
                "massFrac": 1.0,
            }
        ],
    )

    logbook_file = tmp_path / "logbook.xlsx"
    _write_logbook_file(
        logbook_file,
        [_valid_logbook_row(), _valid_logbook_row(batchnum=2)],
        [{"sampos": "Mo B5", "motor_a": 1.0}],
    )

    rc = main(
        [
            "write-nexus-metadata",
            str(logbook_file),
            str(project_base),
            str(tmp_path / "written.nxs"),
        ]
    )

    assert rc == 1


def test_cli_write_nexus_metadata_requires_both_identifier_parts(tmp_path: Path) -> None:
    project_base = tmp_path / "projects"
    year_dir = project_base / "2025"
    year_dir.mkdir(parents=True)
    _write_project_file(
        year_dir / "2025001.xlsx",
        [
            {
                "sampleId": 1.0,
                "sampleName": "Water",
                "componentId": "a",
                "componentName": "Water",
                "composition": "H2O",
                "density": 0.998,
                "volFrac": 1.0,
                "massFrac": 1.0,
            }
        ],
    )

    logbook_file = tmp_path / "logbook.xlsx"
    _write_logbook_file(
        logbook_file,
        [_valid_logbook_row()],
        [{"sampos": "Mo B5", "motor_a": 1.0}],
    )

    rc = main(
        [
            "write-nexus-metadata",
            str(logbook_file),
            str(project_base),
            str(tmp_path / "written.nxs"),
            "--ymd",
            "20260303",
        ]
    )

    assert rc == 1
