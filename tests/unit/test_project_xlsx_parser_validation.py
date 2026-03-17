from pathlib import Path

import pandas as pd
import pytest

from mouse_logbook.adapters.project_xlsx import ProjectXlsxParser
from mouse_logbook.exceptions import ProjectSheetFormatError


def test_project_info_missing_required_fields_raises(tmp_path: Path) -> None:
    p = tmp_path / "2025123.xlsx"

    df_proj = pd.DataFrame(
        {
            "k": ["Name", "Organisation", "Email", "Title", "What"],
            "v": ["", "Org", "not-an-email", "Title", ""],
        }
    )
    df_samples = pd.DataFrame(
        columns=["sampleId", "sampleName", "componentId", "composition", "density", "volFrac", "massFrac"]
    )

    with pd.ExcelWriter(p, engine="openpyxl") as w:
        df_proj.to_excel(w, sheet_name="Project_Info", index=False)
        df_samples.to_excel(w, sheet_name="Sample_Info", index=False, startrow=2)

    parser = ProjectXlsxParser(strict=True)
    with pytest.raises(ProjectSheetFormatError):
        parser.parse(p)


def test_project_info_missing_required_fields_are_reported(tmp_path: Path) -> None:
    p = tmp_path / "2025123.xlsx"

    df_proj = pd.DataFrame(
        {
            "k": ["Name", "Organisation", "Email", "Title", "What"],
            "v": ["", "Org", "not-an-email", "Title", ""],
        }
    )
    df_samples = pd.DataFrame(
        columns=["sampleId", "sampleName", "componentId", "composition", "density", "volFrac", "massFrac"]
    )

    with pd.ExcelWriter(p, engine="openpyxl") as w:
        df_proj.to_excel(w, sheet_name="Project_Info", index=False)
        df_samples.to_excel(w, sheet_name="Sample_Info", index=False, startrow=2)

    report = ProjectXlsxParser(strict=False).inspect(p)

    assert report.has_errors
    messages = {str(issue) for issue in report.issues}
    assert "Project_Info: missing Name" in messages
    assert "Project_Info: Invalid email address: 'not-an-email'" in messages
    assert "Project_Info: missing What/Description" in messages
    assert "Sample_Info: no samples found in Sample_Info" in messages
    assert report.value.proposal_id == "2025123"


def test_sample_info_requires_components(tmp_path: Path) -> None:
    p = tmp_path / "2025124.xlsx"

    df_proj = pd.DataFrame({"k": ["Name", "Organisation", "Email", "Title", "What"], "v": ["N", "O", "a@b.de", "T", "D"]})

    # one sample row but no component rows
    df_samples = pd.DataFrame(
        {
            "sampleId": [1.0],
            "sampleName": ["S1"],
            "componentId": [pd.NA],
            "composition": [pd.NA],
            "density": [pd.NA],
            "volFrac": [pd.NA],
            "massFrac": [pd.NA],
        }
    )

    with pd.ExcelWriter(p, engine="openpyxl") as w:
        df_proj.to_excel(w, sheet_name="Project_Info", index=False)
        df_samples.to_excel(w, sheet_name="Sample_Info", index=False, startrow=2)

    parser = ProjectXlsxParser(strict=True)
    with pytest.raises(ProjectSheetFormatError):
        parser.parse(p)
