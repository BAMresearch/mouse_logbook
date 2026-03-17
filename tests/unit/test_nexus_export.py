from pathlib import Path

import h5py
import pandas as pd

from mouse_logbook.nexus_export import NexusMetadataExportService


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


def test_nexus_metadata_export_service_writes_selected_ymd_and_batch_num(tmp_path: Path) -> None:
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
    report = NexusMetadataExportService(logbook_file=logbook_file, project_base_dir=project_base).write_entry(
        output_file=output_file,
        ymd="20260303",
        batch_num=1,
    )

    assert not report.has_errors
    assert report.value is not None
    assert report.value.source_key == "mo_ka"
    with h5py.File(output_file, "r") as handle:
        assert handle["/entry1/sample/name"][()] == b"Water"
        assert handle["/entry1/sample/owner"][()] == b"Owner"
        assert handle["/entry1/sample/overall_mu"].attrs["source_key"] == "mo_ka"
        assert handle["/entry1/processing_required_metadata/background_identifier"][()] == b"20260302_7"


def test_nexus_metadata_export_service_requires_explicit_identifier_when_multiple_entries_exist(tmp_path: Path) -> None:
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

    report = NexusMetadataExportService(logbook_file=logbook_file, project_base_dir=project_base).write_entry(
        output_file=tmp_path / "written.nxs",
    )

    assert report.has_errors
    assert report.value is None
    assert any("Multiple eligible logbook entries found" in str(issue) for issue in report.issues)


def test_nexus_metadata_export_service_supports_custom_energy_override(tmp_path: Path) -> None:
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
        [_valid_logbook_row(sampos="Sync A1")],
        [{"sampos": "Sync A1", "motor_a": 1.0}],
    )

    output_file = tmp_path / "written.nxs"
    report = NexusMetadataExportService(logbook_file=logbook_file, project_base_dir=project_base).write_entry(
        output_file=output_file,
        ymd="20260303",
        batch_num=1,
        energy_kev=12.5,
        source_key="synchrotron_12p5kev",
    )

    assert not report.has_errors
    assert report.value is not None
    assert report.value.source_key == "synchrotron_12p5kev"
    with h5py.File(output_file, "r") as handle:
        assert handle["/entry1/sample/overall_mu"].attrs["source_key"] == "synchrotron_12p5kev"
        assert handle["/entry1/sample/overall_mu"].attrs["energy_kev"] == 12.5


def test_nexus_metadata_export_service_updates_existing_output_file(tmp_path: Path) -> None:
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

    output_file = tmp_path / "written_existing.nxs"
    with h5py.File(output_file, "w") as handle:
        handle.create_group("entry1").create_group("processing_required_metadata").create_dataset(
            "background_file",
            data="already_set_background.nxs",
            dtype=h5py.string_dtype(),
        )

    report = NexusMetadataExportService(logbook_file=logbook_file, project_base_dir=project_base).write_entry(
        output_file=output_file,
        ymd="20260303",
        batch_num=1,
    )

    assert not report.has_errors
    assert report.value is not None
    with h5py.File(output_file, "r") as handle:
        assert handle["/entry1/sample/name"][()] == b"Water"
        assert handle["/entry1/processing_required_metadata/background_file"][()] == b"already_set_background.nxs"
        assert handle["/entry1/processing_required_metadata/background_identifier"][()] == b"20260302_7"


def test_nexus_metadata_export_service_requires_both_ymd_and_batch_num(tmp_path: Path) -> None:
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

    report = NexusMetadataExportService(logbook_file=logbook_file, project_base_dir=project_base).write_entry(
        output_file=tmp_path / "written.nxs",
        ymd="20260303",
    )

    assert report.has_errors
    assert report.value is None
    assert any("Pass both ymd and batch_num together" in str(issue) for issue in report.issues)
