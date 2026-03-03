# mouse-logbook

Read and enrich MOUSE logbook entries from Excel while keeping the **logbook entry as the single source of truth**.

## What you get

- `LogbookExcelReader`: pure Excel -> immutable `LogbookEntry`
- `ProjectRepository`: locate + parse + cache project sheets (parser injected)
- `SampleEnvironmentRepository`: read + cache sample-position motor values
- `LogbookEnricher`: join entries with project/sample/environment
- `Logbook2MouseReader`: **legacy-compatible façade** matching downstream usage:

  ```python
  reader = Logbook2MouseReader(logbook_path, project_base_path=project_base_path)
  for enriched in reader:
      ...
  ```

## Install (dev)

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

## Usage

```python
from pathlib import Path
from mouse_logbook import Logbook2MouseReader

reader = Logbook2MouseReader(Path("Logbook_MOUSE.xlsx"), project_base_path=Path("projects"))
for enriched_entry in reader:
    print(enriched_entry.proposal, enriched_entry.sample_position)
```

## Testing

- Unit tests: `pytest tests/unit`
- Functional tests: `pytest tests/functional`

Functional tests are designed to run against files in `tests/data/`. Add a small anonymized example logbook
and project sheet there (or use Git LFS for larger files).

## License

Choose your license for the repo (e.g. BSD-3-Clause) and add it as `LICENSE`.


    ## CLI

    Validate all proposal sheets under the implicit filesystem convention:

    ```bash
    mouse-logbook validate-projects /path/to/projects
    ```

    Validate only specific files:

    ```bash
    mouse-logbook validate-projects /path/to/projects --files /path/to/projects/2025/2025001.xlsx
    ```

    Write a failure report:

    ```bash
    mouse-logbook validate-projects /path/to/projects --report validation_report.txt
    ```
    