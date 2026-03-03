from pathlib import Path

import pandas as pd

from mouse_logbook.cli import main


def test_cli_validate_projects_exit_codes(tmp_path: Path) -> None:
    base = tmp_path / "projects"
    year = base / "2025"
    year.mkdir(parents=True)

    # valid-ish project file
    p_ok = year / "2025001.xlsx"
    df_proj = pd.DataFrame({"k": ["Name", "Organisation", "Email", "Title", "What"], "v": ["N", "O", "a@b.de", "T", "D"]})
    df_samples = pd.DataFrame(
        {
            "sampleId": [1.0, pd.NA],
            "sampleName": ["S1", pd.NA],
            "componentId": [pd.NA, "a"],
            "composition": [pd.NA, "H2O"],
            "density": [pd.NA, 1.0],
            "volFrac": [pd.NA, 1.0],
            "massFrac": [pd.NA, pd.NA],
        }
    )
    with pd.ExcelWriter(p_ok, engine="openpyxl") as w:
        df_proj.to_excel(w, sheet_name="Project_Info", index=False)
        df_samples.to_excel(w, sheet_name="Sample_Info", index=False, startrow=2)

    rc = main(["validate-projects", str(base)])
    assert rc == 0

    # invalid project file
    p_bad = year / "2025002.xlsx"
    df_proj_bad = pd.DataFrame({"k": ["Name", "Organisation", "Email", "Title", "What"], "v": ["", "O", "bad", "T", ""]})
    df_samples_bad = pd.DataFrame(columns=["sampleId", "sampleName", "componentId", "composition", "density", "volFrac", "massFrac"])
    with pd.ExcelWriter(p_bad, engine="openpyxl") as w:
        df_proj_bad.to_excel(w, sheet_name="Project_Info", index=False)
        df_samples_bad.to_excel(w, sheet_name="Sample_Info", index=False, startrow=2)

    rc2 = main(["validate-projects", str(base)])
    assert rc2 == 1
