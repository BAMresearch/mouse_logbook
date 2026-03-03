from pathlib import Path

import pandas as pd
import pytest

from mouse_logbook.exceptions import LogbookFormatError
from mouse_logbook.io_excel import LogbookExcelReader, LogbookExcelSpec


def test_missing_required_columns_raises(tmp_path: Path) -> None:
    p = tmp_path / "logbook.xlsx"
    pd.DataFrame({"foo": [1], "bar": [2]}).to_excel(p, index=False)
    reader = LogbookExcelReader(file_path=p, spec=LogbookExcelSpec(header_row=0))
    with pytest.raises(LogbookFormatError):
        reader.read_entries(load_all=True)
