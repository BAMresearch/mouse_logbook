import pandas as pd

from mouse_logbook.models import LogbookEntry


def test_logbook_entry_ymd_is_derived() -> None:
    e = LogbookEntry(
        row_index=1,
        convert_to_script=True,
        date=pd.Timestamp("2026-03-03T10:00:00"),
        proposal_id="2026-ABC",
        sample_id=1,
        user="user",
        batch_num=1,
        sample_position_id="P1",
        matrix_fraction=0.5,
        sample_thickness=1.2,
        protocol="prot",
        additional_parameters={},
    )
    assert e.ymd == "20260303"
