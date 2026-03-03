from pathlib import Path

from mouse_logbook import Logbook2MouseEntry, Logbook2MouseReader


def test_end_to_end_example_files_present() -> None:
    root = Path(__file__).resolve().parents[1]
    logbook = root / "data" / "example_logbook.xlsx"
    projects = root / "data" / "projects"

    assert logbook.is_file(), "Missing tests/data/example_logbook.xlsx"
    assert projects.is_dir(), "Missing tests/data/projects/"

    reader = Logbook2MouseReader(logbook, project_base_path=projects)
    entries = list(reader)

    assert entries, "Expected at least one entry"
    e0 = entries[0]
    assert isinstance(e0, Logbook2MouseEntry)
    assert isinstance(e0.row_index, int)
    assert e0.proposal
    assert e0.project is not None
    assert e0.sample is not None
