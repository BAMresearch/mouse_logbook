## Context summary

### What this repo/package is

We created a new Python package (src-layout) called **`mouse-logbook`** (`mouse_logbook` module) whose job is to **read a MOUSE logbook Excel file and proposal sheets, validate them strictly, and provide iterable logbook entries** that other systems use as the **single source of truth** for measurement execution and metadata ingestion (e.g., OpenBIS, Tiled).

### Core design principles

* **Logbook entries are the single source of truth**: downstream systems should derive measurement intent, provenance, and catalog metadata from the entries.
* **Separation of concerns**:

  * Excel I/O and parsing is separate from project lookup/caching.
  * Enrichment (joining logbook ↔ project ↔ sample ↔ sample-environment) is separate from parsing.
* **Strict schema validation for user-authored project sheets** because it’s the most common source of errors.
* **attrs** is used for models; **ruff** with max line length 120; docs include design/contract markdown.

### Filesystem conventions (kept)

Project/proposal sheets are located using the longstanding convention:

`{project_base_dir}/{year}/{proposal_id}*.xlsx`
where `year` is the first 4 digits of `proposal_id`.

### Key components (modules/classes)

#### Logbook reading (pure I/O)

* `mouse_logbook.io_excel.LogbookExcelReader`

  * Reads an Excel logbook file into immutable `mouse_logbook.models.LogbookEntry` objects.
  * Handles the “additional parameters” key/val columns.
  * Filters by `converttoscript` unless `load_all=True`.

#### Project reading + strict schema validation

* `mouse_logbook.adapters.project_xlsx.ProjectXlsxParser`

  * Parses proposal sheets with two sheets:

    * `Project_Info`: key/value pairs
    * `Sample_Info`: block-structured samples with component rows
  * **Strict validation by default**, raises `ProjectSheetFormatError` with actionable errors.
  * Normalizes Excel numeric proposal IDs (e.g., `2025001.0` → `"2025001"`).

* `mouse_logbook.project_repo.ProjectFileLocator`

  * Finds the correct proposal file under the implicit directory convention.

* `mouse_logbook.project_repo.ProjectRepository`

  * Caches parsed projects and provides `get_sample(proposal_id, sample_id)`.

#### Sample environment / motor positions

* `mouse_logbook.environment_repo.SampleEnvironmentRepository`

  * Reads sheet `"Sample Environments"` from the logbook and returns motor positions per `sampos`.
  * Cached in memory.

#### Enrichment (joining)

* `mouse_logbook.services.LogbookEnricher`

  * Turns `LogbookEntry` into enriched data by joining:

    * project metadata
    * sample definition
    * sample-environment motor positions

### Main user-facing entry point (current)

* `mouse_logbook.legacy.Logbook2MouseReader`

  * Keeps the familiar initialization pattern:

    ```python
    reader = Logbook2MouseReader(logbook_path, project_base_path=project_base_path)
    for entry in reader:
        ...
    ```
  * Iteration yields `Logbook2MouseEntry` (a compatibility adapter with common legacy field names like `proposal`, `sampleid`, `batchnum`, `sampos`, etc.).
  * Internally it uses the clean pipeline (`LogbookExcelReader` + repositories + enricher).
  * Project parsing defaults to `ProjectXlsxParser(strict=True)` but can be overridden via `project_parser=` injection.

### Errors / failure modes

Typed exceptions:

* `LogbookFormatError`: logbook doesn’t match expected column schema
* `ProjectNotFoundError`: proposal sheet can’t be located under conventions
* `ProjectFileAmbiguityError`: more than one proposal sheet matches a proposal ID
* `ProjectSheetFormatError`: proposal sheet content/schema invalid (most common)
* `SampleNotFoundError`: sample referenced by logbook not found in project sheet
* `SampleEnvironmentNotFoundError`: `sampos` missing in Sample Environments

### CLI (for ingestion-time validation)

A CLI entrypoint exists via `pyproject.toml` scripts:

```bash
mouse-logbook validate-projects /path/to/projects
```

* Scans `{base}/{YYYY}/*.xlsx`, parses each file with strict schema validation.
* Exit codes:

  * `0` all ok
  * `1` some invalid
  * `2` base directory missing
* Optional flags: `--files ...`, `--report path`, `--lenient`, `-v/-vv`.

### Tests included

* Unit tests for model behavior, parsing errors, and CLI exit codes.
* Functional test uses anonymized example files under `tests/data/`.

### Known limitation / migration note

There was legacy code (measurement script generator) that relied on deep implicit assumptions (`__repr__`, `type(entry)==...`, mutability). We decided to **stop bending the new system to match all hidden legacy assumptions** and instead build new downstream methods on top of the **new clean contracts** (`LogbookEntry` + explicit enrichment), using the compatibility wrapper only where needed.

---

## Quick “how to use” snippet (for new code)

```python
from pathlib import Path
from mouse_logbook.io_excel import LogbookExcelReader
from mouse_logbook.project_repo import ProjectFileLocator, ProjectRepository
from mouse_logbook.environment_repo import SampleEnvironmentRepository
from mouse_logbook.adapters.project_xlsx import ProjectXlsxParser
from mouse_logbook.services import LogbookEnricher

logbook = Path("Logbook_MOUSE.xlsx")
projects_dir = Path("projects")

entries = LogbookExcelReader(logbook).read_entries(load_all=False)

projects = ProjectRepository(ProjectFileLocator(projects_dir), ProjectXlsxParser(strict=True).parse)
env = SampleEnvironmentRepository(logbook)

enricher = LogbookEnricher(projects=projects, environments=env)
enriched = enricher.enrich_many(entries)
```
