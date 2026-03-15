# mouse-logbook

Read, validate, enrich, and export MOUSE logbook metadata from Excel while keeping the logbook entry as the primary source of truth.

## Scope

This package covers four main jobs:

- read logbook `.xlsx` files into stable Python objects
- locate and validate proposal/project sheets
- enrich logbook rows with sample and sample-environment information
- validate and export chemistry, materials, X-ray, and NeXus/HDF5 metadata

The package keeps the core Excel parsing separate from the optional chemistry/material/X-ray layers.

## Installation

Base package:

```bash
python -m venv .venv
. .venv/bin/activate
pip install -e .
```

Recommended for full validation and NeXus writing:

```bash
pip install -e ".[materials,hdf5]"
```

Recommended for development:

```bash
pip install -e ".[dev,materials,hdf5]"
```

Extras:

- `materials`: installs `periodictable` and `xraydb`
- `hdf5`: installs `h5py`
- `dev`: installs pytest, ruff, mypy, and typing helpers

## CLI

The package installs a `mouse-logbook` command.

### Validate project sheets

Validate all proposal sheets under the filesystem convention `{base}/{year}/{proposal_id}*.xlsx`:

```bash
mouse-logbook validate-projects /path/to/projects
```

Validate specific files only:

```bash
mouse-logbook validate-projects /path/to/projects --files /path/to/projects/2025/2025001.xlsx
```

Write a report:

```bash
mouse-logbook validate-projects /path/to/projects --report validation_report.txt
```

### Validate a joined dataset

Validate a logbook together with its referenced proposal sheets:

```bash
mouse-logbook validate-dataset /path/to/logbook.xlsx /path/to/projects
```

Run deeper optional checks:

```bash
mouse-logbook validate-dataset /path/to/logbook.xlsx /path/to/projects --level xray
```

Available levels:

- `core`
- `chemistry`
- `materials`
- `xray`

Useful flags:

- `--load-all`
- `--lenient`
- `--report PATH`
- `-v` / `-vv`

### Write NeXus/HDF5 metadata

Write one measurement series into a new or existing `.nxs`/`.h5` file:

```bash
mouse-logbook write-nexus-metadata /path/to/logbook.xlsx /path/to/projects /path/to/output.nxs --ymd 20260303 --batch-num 4
```

Write custom-energy X-ray metadata:

```bash
mouse-logbook write-nexus-metadata /path/to/logbook.xlsx /path/to/projects /path/to/output.nxs --ymd 20260303 --batch-num 4 --energy-kev 12.5 --source-key synchrotron_12p5kev
```

Selection rules:

- the export identity is `ymd + batchnum`
- if there is exactly one eligible row, the command can export without explicit selection
- if multiple eligible rows exist, the command fails until you pass `--ymd` and `--batch-num`

Important behavior:

- the target file may be new or already exist
- the writer opens the file in HDF5 append mode and updates the compatibility metadata paths in place
- existing `background_file` and `dispersed_background_file` datasets are preserved by default, because those paths are managed elsewhere

Useful flags:

- `--ymd YYYYMMDD`
- `--batch-num N`
- `--load-all`
- `--source-key KEY`
- `--energy-kev VALUE`
- `--report PATH`
- `-v` / `-vv`

## Python Interfaces

### Core reading and enrichment

Read logbook rows:

```python
from pathlib import Path
from mouse_logbook.io_excel import LogbookExcelReader

entries = LogbookExcelReader(Path("Logbook_MOUSE.xlsx")).read_entries()
```

Use the legacy-compatible façade:

```python
from pathlib import Path
from mouse_logbook import Logbook2MouseReader

reader = Logbook2MouseReader(
    Path("Logbook_MOUSE.xlsx"),
    project_base_path=Path("projects"),
)

for entry in reader:
    print(entry.proposal, entry.sampleid, entry.sampos)
```

Build the clean enrichment pipeline explicitly:

```python
from pathlib import Path

from mouse_logbook.adapters.project_xlsx import ProjectXlsxParser
from mouse_logbook.environment_repo import SampleEnvironmentRepository
from mouse_logbook.io_excel import LogbookExcelReader
from mouse_logbook.project_repo import ProjectFileLocator, ProjectRepository
from mouse_logbook.services import LogbookEnricher

logbook = Path("Logbook_MOUSE.xlsx")
projects_dir = Path("projects")

entries = LogbookExcelReader(logbook).read_entries()
projects = ProjectRepository(ProjectFileLocator(projects_dir), ProjectXlsxParser(strict=True).parse)
environments = SampleEnvironmentRepository(logbook)
enricher = LogbookEnricher(projects=projects, environments=environments)

enriched_entries = enricher.enrich_many(entries)
```

### Validation workflow

Run joined validation from Python:

```python
from pathlib import Path
from mouse_logbook.dataset_validation import DatasetValidator

report = DatasetValidator(
    logbook_file=Path("Logbook_MOUSE.xlsx"),
    project_base_dir=Path("projects"),
).validate(level="xray")

for issue in report.issues:
    print(issue)

print(report.value.entries)
print(report.value.xray_entries)
```

### NeXus export workflow

Use the user-facing export service directly:

```python
from pathlib import Path
from mouse_logbook.nexus_export import NexusMetadataExportService

report = NexusMetadataExportService(
    logbook_file=Path("Logbook_MOUSE.xlsx"),
    project_base_dir=Path("projects"),
).write_entry(
    output_file=Path("output.nxs"),
    ymd="20260303",
    batch_num=4,
)

if report.has_errors:
    for issue in report.issues:
        print(issue)
else:
    print(report.value.output_file)
```

Write custom-energy metadata:

```python
from pathlib import Path
from mouse_logbook.nexus_export import NexusMetadataExportService

report = NexusMetadataExportService(
    logbook_file=Path("Logbook_MOUSE.xlsx"),
    project_base_dir=Path("projects"),
).write_entry(
    output_file=Path("output.nxs"),
    ymd="20260303",
    batch_num=4,
    energy_kev=12.5,
    source_key="synchrotron_12p5kev",
)
```

Low-level upsert API:

```python
from pathlib import Path

from mouse_logbook.nexus_metadata import NexusMetadataUpserter

# material_entry and xray_entry are validated/enriched objects
NexusMetadataUpserter().upsert_entry(
    Path("output.nxs"),
    material_entry=material_entry,
    xray_entry=xray_entry,
)
```

## Main Public Components

Core:

- `LogbookExcelReader`
- `ProjectXlsxParser`
- `ProjectFileLocator`
- `ProjectRepository`
- `SampleEnvironmentRepository`
- `LogbookEnricher`
- `Logbook2MouseReader`

Validation and domain layers:

- `DatasetValidator`
- `SampleMetadataEnricher`
- `SampleMetadataChemistryValidator`
- `SampleMetadataMaterialsCalculator`
- `SampleMetadataXrayCalculator`

NeXus/HDF5 export:

- `NexusMetadataUpserter`
- `NexusMetadataExportService`

## Notes on X-ray Metadata

- Standard precomputed sources are:
  - Cu K-alpha: `8.04 keV`
  - Mo K-alpha: `17.4 keV`
- Arbitrary energies are supported for synchrotron or other sources.
- Absorption coefficients are written in `1/m`.
- Scattering length densities are written in `1/m^2`.

## Testing

Run the full suite:

```bash
.venv/bin/python -m pytest tests
```

Run linting:

```bash
.venv/bin/ruff check src tests
```

## License

Choose your license for the repo and add it as `LICENSE`.
