from pathlib import Path

import pandas as pd
import pytest

from mouse_logbook.environment_repo import SampleEnvironmentRepository


def test_environment_repo_missing_file_raises(tmp_path: Path) -> None:
    repo = SampleEnvironmentRepository(tmp_path / "missing.xlsx")
    with pytest.raises(FileNotFoundError):
        repo.load_all()


def test_environment_repo_parses_sheet(tmp_path: Path) -> None:
    # Build a minimal workbook with the expected sheet/columns.
    p = tmp_path / "logbook.xlsx"

    # header_row=2 means header is written at row index 2 -> easiest: write a DF with startrow=2
    df = pd.DataFrame(
        {
            "dropme": [None, None],
            "sampos": ["P1", "P2"],
            "motor_a": [1.0, 2.0],
            "motor_b": [3.0, 4.0],
        }
    )

    with pd.ExcelWriter(p, engine="openpyxl") as w:
        df.to_excel(w, sheet_name="Sample Environments", index=False, startrow=2)

    repo = SampleEnvironmentRepository(p)
    pos = repo.get("P1")
    assert pos["motor_a"] == 1.0
    assert pos["motor_b"] == 3.0
