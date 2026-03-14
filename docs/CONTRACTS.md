# Contracts

## LogbookExcelReader

- Input: a logbook `.xlsx`
- Output: `list[LogbookEntry]`
- `inspect_entries(load_all=...)` returns parsed entries plus structured validation issues
- No side effects other than reading the Excel file.
- Raises:
  - `FileNotFoundError` if file missing
  - `LogbookFormatError` if required columns are missing or row values are invalid

## ProjectRepository

- Locates a project file under `{base_dir}/{year}/{proposal_id}*.xlsx`
- Raises `ProjectNotFoundError` if no file matches
- Raises `ProjectFileAmbiguityError` if more than one file matches
- Uses an injected parser `(Path) -> ProjectLike`
- Caches parsed projects by `proposal_id`
- `get_sample(proposal_id, sample_id)` expects `project.samples` to be a `dict[int, Any]`

## SampleEnvironmentRepository

- Reads sheet `Sample Environments` with a `sampos` column.
- Returns a mapping of motor name -> float for a given `sampos`.

## Logbook2MouseReader (legacy façade)

- Provides iteration over **enriched entries**
- Keeps the initialization pattern:
  `Logbook2MouseReader(logbook_path, project_base_path=project_base_path)`
