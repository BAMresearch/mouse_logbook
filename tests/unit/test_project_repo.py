from pathlib import Path

import attrs
import pytest

from mouse_logbook.exceptions import ProjectFileAmbiguityError, ProjectNotFoundError, SampleNotFoundError
from mouse_logbook.project_repo import ProjectFileLocator, ProjectRepository


def _touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("placeholder", encoding="utf-8")
    return path


@attrs.frozen(kw_only=True, slots=True)
class DummyProject:
    samples: dict[int, str]


def test_project_file_locator_returns_single_match(tmp_path: Path) -> None:
    expected = _touch(tmp_path / "2025" / "2025001.xlsx")

    locator = ProjectFileLocator(tmp_path)

    assert locator.find_project_file("2025001") == expected


def test_project_file_locator_raises_when_year_directory_is_missing(tmp_path: Path) -> None:
    locator = ProjectFileLocator(tmp_path)

    with pytest.raises(ProjectNotFoundError, match="Project year directory not found"):
        locator.find_project_file("2025001")


def test_project_file_locator_raises_when_no_file_matches(tmp_path: Path) -> None:
    (tmp_path / "2025").mkdir(parents=True)
    locator = ProjectFileLocator(tmp_path)

    with pytest.raises(ProjectNotFoundError, match="No project file found"):
        locator.find_project_file("2025001")


def test_project_file_locator_raises_when_multiple_files_match(tmp_path: Path) -> None:
    _touch(tmp_path / "2025" / "2025001.xlsx")
    _touch(tmp_path / "2025" / "2025001-v2.xlsx")

    locator = ProjectFileLocator(tmp_path)

    with pytest.raises(ProjectFileAmbiguityError, match="Multiple project files found"):
        locator.find_project_file("2025001")


def test_project_repository_caches_parsed_projects(tmp_path: Path) -> None:
    project_file = _touch(tmp_path / "2025" / "2025001.xlsx")
    parse_calls: list[Path] = []

    def parser(path: Path) -> DummyProject:
        parse_calls.append(path)
        return DummyProject(samples={1: "sample-1"})

    repo = ProjectRepository(ProjectFileLocator(tmp_path), parser)

    assert repo.get("2025001").samples[1] == "sample-1"
    assert repo.get("2025001").samples[1] == "sample-1"
    assert parse_calls == [project_file]


def test_project_repository_get_sample_raises_for_missing_sample(tmp_path: Path) -> None:
    _touch(tmp_path / "2025" / "2025001.xlsx")

    repo = ProjectRepository(ProjectFileLocator(tmp_path), lambda _: DummyProject(samples={}))

    with pytest.raises(SampleNotFoundError, match="Sample 2 not found in project 2025001"):
        repo.get_sample("2025001", 2)
