# Improvement Backlog

## Scope

Reviewed:

- Current `mouse_logbook` package in this repository
- Legacy reader at `/Users/bpauw/Code/logbook2mouse/logbook2mouse/project_reader.py`

This backlog separates confirmed implementation issues from feature work. The goal is to make the package reliable first, then add chemistry-aware sample validation and derived material/X-ray properties in a clean extension layer.

## Progress Update

Completed on the current branch:

- Item 1 is implemented in `src/mouse_logbook/adapters/project_xlsx.py`.
- Item 2 is implemented via structured validation reports in `src/mouse_logbook/validation.py`, `src/mouse_logbook/adapters/project_xlsx.py`, and `src/mouse_logbook/cli.py`.
- Item 3 is implemented in `src/mouse_logbook/environment_repo.py` with a dedicated `SampleEnvironmentFormatError`.
- The proposal parser now preserves component data when it appears on the same row as `sampleId`.
- Blank Excel cells are now treated as blank consistently instead of leaking through as string values such as `"nan"`.
- The project parser now exposes collected validation issues without depending on `strict` mode to surface them.
- `mouse-logbook validate-projects --lenient` now reports validation problems and can write them to `--report` without returning a failing exit code for schema issues.
- Regression tests were added for both supported sample-block layouts in `tests/unit/test_project_xlsx_parser.py`.
- Validation-report tests were added in `tests/unit/test_project_xlsx_parser_validation.py` and `tests/unit/test_cli_validate_projects.py`.
- Sample-environment tests now cover unnamed leading columns, missing `sampos`, non-numeric motors, and missing sample-position lookups.
- Current verification run: `.venv/bin/python -m pytest tests` -> `17 passed`; `.venv/bin/ruff check src tests` -> passed.

## Recommendation

Do **not** fold chemistry parsing and X-ray calculations directly into the core logbook/parser layer.

Recommended boundary:

- Keep `mouse_logbook` responsible for Excel I/O, sheet/schema validation, project lookup, and enrichment joins.
- Add a separate **sample/material extension layer** on top of it for chemistry validation, density estimation, and X-ray property calculation.

That extension can live:

- In the same repository at first, behind optional dependencies such as `mouse_logbook[materials]`
- Or as a separate distribution later if reuse outside this repo becomes important

Reasoning:

- The current package is intentionally lightweight and dependency-minimal.
- `periodictable` and `xraydb` are domain-specific and should stay optional.
- The legacy reader mixed parsing, normalization, chemistry semantics, and X-ray calculations in one object graph. That coupling is the main thing to avoid when porting the old functionality.

## Highest-Priority Work

### 1. Fix proposal parsing for sample-start rows that also contain the first component

Status: completed

Implemented in:

- `src/mouse_logbook/adapters/project_xlsx.py`
- `tests/unit/test_project_xlsx_parser.py`

Original issue location: `src/mouse_logbook/adapters/project_xlsx.py` sample-block loop

Problem:

- When a row contains `sampleId`, the parser starts a new sample and immediately `continue`s.
- Any component fields on that same row are discarded.
- The legacy reader treated that same row as part of the sample block and therefore kept the first component (`project_reader.py:176-205`).

Why this matters:

- This is a compatibility break with older proposal sheets.
- It can turn valid samples into empty/incomplete samples during migration.

Proposed change:

- Treat a sample-start row as both:
  - the start of a new sample
  - an optional first component row when component data is present
- Add regression tests for both layouts:
  - sample header row with component data
  - sample header row followed by separate component rows

Implemented change:

- Removed the early `continue` on sample-start rows so the same row can also be parsed as a component row.
- Added parser helpers for blank-safe text handling so `pd.NA`/`NaN` values are not converted into fake strings such as `"nan"`.
- Added regression coverage for:
  - sample-start rows that contain the first component
  - equivalent layouts where components begin on continuation rows

Acceptance criteria:

- Both proposal layouts parse to the same component list.
- No component is lost solely because it appears on the first row of a sample block.

Verification:

- `tests/unit/test_project_xlsx_parser.py`
- Full test suite currently passes in the project virtualenv.

### 2. Replace `strict`/`lenient` boolean behavior with structured validation results

Status: completed

Implemented in:

- `src/mouse_logbook/validation.py`
- `src/mouse_logbook/adapters/project_xlsx.py`
- `src/mouse_logbook/cli.py`

Current code:

- `src/mouse_logbook/adapters/project_xlsx.py:233-284`
- `src/mouse_logbook/cli.py:41-42`
- `src/mouse_logbook/cli.py:96-100`

Problem:

- In lenient mode the parser suppresses exceptions, but it also suppresses the actual validation messages.
- The CLI help says lenient mode "logs problems", but the parser currently drops them.

Why this matters:

- Users can get a false sense that a proposal sheet is acceptable.
- This becomes a blocker once chemistry validation is added, because warnings and derived estimates need to be reported, not just pass/fail.

Proposed change:

- Introduce a typed validation result model, for example:
  - `ValidationIssue`
  - `ValidationResult`
  - severities such as `error`, `warning`, `info`
- Let the parser return parsed data plus issues, and let the CLI decide whether issues are fatal.

Implemented change:

- Added reusable `ValidationIssue` and `ValidationReport` types.
- Added `ProjectXlsxParser.inspect(...)` to return parsed project data together with collected issues.
- Kept `ProjectXlsxParser.parse(...)` compatible for existing strict consumers by raising only when `strict=True` and error issues are present.
- Updated the CLI to:
  - log structured issues
  - fail in strict mode on validation errors
  - continue in lenient mode while still reporting the issues
  - write issue lines to `--report`

Acceptance criteria:

- `--lenient` emits warnings without pretending the file is clean.
- `--report` can contain both hard errors and warnings.
- The same validation engine can later host chemistry/sample issues.

Verification:

- `tests/unit/test_project_xlsx_parser_validation.py`
- `tests/unit/test_cli_validate_projects.py`
- Full test suite and Ruff pass in the project virtualenv.

### 3. Harden the sample-environment parser against layout drift

Status: completed

Implemented in:

- `src/mouse_logbook/environment_repo.py`
- `src/mouse_logbook/exceptions.py`
- `tests/unit/test_environment_repo.py`

Current code: `src/mouse_logbook/environment_repo.py:33-49`

Problem:

- The parser unconditionally drops the first column via `df.iloc[:, 1:]`.
- It relies on column position instead of validating the schema.
- If the workbook layout changes, `sampos` can be shifted or silently misread.

Why this matters:

- This is the same class of fragility the project parser is trying to eliminate.
- Wrong motor positions are worse than missing motor positions because they look valid.

Proposed change:

- Stop slicing columns by position.
- Normalize/validate column names explicitly.
- Ignore unnamed columns by name, not by position.
- Raise a typed format error when `sampos` is missing or motor values are non-numeric.

Implemented change:

- Removed the positional `df.iloc[:, 1:]` assumption entirely.
- Added explicit column normalization and ignored unnamed Excel columns by name.
- Added `SampleEnvironmentFormatError` for malformed sample-environment sheets.
- Validated that:
  - `sampos` exists
  - normalized column names are not ambiguous
  - motor values are numeric when present
- Kept lookup errors separate via the existing `SampleEnvironmentNotFoundError`.

Acceptance criteria:

- The parser works with and without a leading unnamed Excel column.
- Misformatted sample-environment sheets fail with actionable messages.

Verification:

- `tests/unit/test_environment_repo.py`
- Full test suite and Ruff pass in the project virtualenv.

### 4. Fail on ambiguous project file matches

Current code: `src/mouse_logbook/project_repo.py:30-35`

Problem:

- `ProjectFileLocator` returns the first match for `{proposal_id}*.xlsx`.
- Multiple matching files are silently resolved to whichever sorts first.

Why this matters:

- A logbook entry can be enriched against the wrong proposal without any explicit failure.
- This is especially risky if old and new proposal forms coexist in the same year directory.

Proposed change:

- Raise an explicit ambiguity error when more than one file matches.
- If needed, add a configurable resolution strategy later.

Acceptance criteria:

- Zero matches and multiple matches are both explicit error cases.
- Enrichment never depends on filename sort order.

### 5. Add row-level validation to the logbook parser

Current code:

- `src/mouse_logbook/io_excel.py:58-84`
- `src/mouse_logbook/models.py:57-88`

Problem:

- The logbook parser validates columns but not row semantics.
- It relies on direct `int(...)`/`float(...)` coercion in places where user-authored Excel values can be blank, strings, or malformed.
- Failure modes are generic Python conversion errors rather than typed domain errors.

Why this matters:

- Proposal validation alone is not enough if the logbook rows themselves are malformed.
- Chemistry/sample enrichment will rely on proposal IDs, sample IDs, dates, and environment references being trustworthy.

Proposed change:

- Add typed row validation for:
  - `converttoscript`
  - `proposal_id`
  - `sample_id`
  - `batch_num`
  - dates
  - numeric fields such as `matrix_fraction` and `sample_thickness`
- Return row-index-aware messages.

Acceptance criteria:

- Invalid logbook cells produce actionable errors that include row number and field name.
- Logbook validation can be run independently from proposal validation.

## Sample/Chemistry Extension Roadmap

### 6. Introduce a richer sample domain model

Current code:

- `src/mouse_logbook/adapters/project_xlsx.py:49-81`

Problem:

- The current `Sample` model is intentionally minimal.
- `composition` is only a display summary string, not a validated material definition.
- That is too weak for chemistry-aware validation and derived-property calculation.

Proposed change:

- Add a richer sample/material model in the extension layer, for example:
  - `MaterialComponent`
  - `MaterialSample`
  - `MaterialPropertyEstimate`
- Keep the core parser responsible for extracting raw proposal content.
- Map raw parsed samples into richer material models only in the extension layer.

Acceptance criteria:

- Core parsing remains dependency-light.
- Sample/material semantics are explicit and testable.

### 7. Add chemistry validation of component descriptions

Legacy reference:

- `project_reader.py:40-66`
- `project_reader.py:96-132`

Feature goal:

- Validate that all chemistry descriptions in the proposal are parseable.
- Reject or flag ambiguous/unsupported formulas.

Proposed change:

- Use `periodictable` in the extension layer to parse component formulas.
- Validate each component independently before computing any aggregate sample properties.
- Preserve the original entered string and the parsed/normalized representation.

Validation checks:

- Formula string is parseable
- Density is positive when required
- At least one of `volFrac` or `massFrac` is available where needed
- Fractions are within range
- Fraction closure rules are explicit rather than silently normalized

Important migration note:

- Do not copy the legacy behavior of silently normalizing fractions (`project_reader.py:103-120`).
- Normalization should only happen when explicitly requested and should always be reported.

### 8. Add derived sample composition and density estimates

Feature goal:

- Derive an overall sample composition from the component list.
- Estimate bulk density when enough information is available.
- Distinguish user-entered values from derived values.

Proposed change:

- Compute composition/density from validated components only.
- Record provenance for each result:
  - `entered`
  - `estimated_from_volume_fraction`
  - `estimated_from_mass_fraction`
  - `unavailable`

Acceptance criteria:

- Missing inputs do not cause silent partial failure.
- Derived values are tagged with provenance and confidence notes.

### 9. Add X-ray property calculations with explicit SI units

Legacy reference:

- `project_reader.py:59-66`
- `project_reader.py:122-132`

Feature goal:

- Compute:
  - overall X-ray absorption coefficient in `1/m`
  - per-phase scattering length densities in `1/m^2`

Proposed change:

- Keep this in the extension layer with optional dependencies.
- Use explicit result types rather than anonymous floats.
- Treat units as part of the API, not a comment.

Suggested result shapes:

- `AbsorptionCoefficient(value_m_inv: float)`
- `ScatteringLengthDensity(real_m_inv2: float, imag_m_inv2: float | None = None)`
- `PhaseXrayProperties(phase_id, mu, sld)`
- `SampleXrayProperties(overall_mu, per_phase)`

Important migration note:

- Avoid broad `except Exception` recovery like the legacy `Sample.__attrs_post_init__` (`project_reader.py:85-95`).
- Scientific calculations should fail explicitly or emit structured warnings with provenance.

### 10. Add proposal validation that spans logbook, proposal, and sample semantics

Feature goal:

- Validate not just individual files, but the joined dataset:
  - logbook references an existing proposal
  - proposal contains referenced samples
  - sample components are chemically valid
  - required derived properties can be computed when requested

Proposed change:

- Add a top-level validation workflow that runs:
  1. logbook schema validation
  2. proposal schema validation
  3. enrichment consistency validation
  4. optional chemistry/X-ray validation

Acceptance criteria:

- Validation can run in stages.
- A user can request core-only validation or full materials validation.

## Suggested Delivery Order

1. Fix parser correctness issues in the current core package.
2. Introduce structured validation results and better CLI reporting.
3. Add independent logbook validation.
4. Create the sample/material extension boundary.
5. Implement chemistry validation with tests.
6. Implement density/composition derivation.
7. Implement X-ray property calculations with explicit units.
8. Add an end-to-end validator that joins logbook, proposal, samples, and optional materials checks.

## Testing Gaps To Add

- Proposal parser handles first-row component data.
- Proposal parser detects ambiguous fractions and reports them cleanly.
- Lenient validation still emits warnings.
- Sample-environment parser handles optional leading unnamed columns.
- Ambiguous proposal file matches fail explicitly.
- Chemistry parser rejects malformed formulas.
- Derived density/composition results are provenance-tagged.
- X-ray outputs are unit-tested and conversion-tested.

## Notes From This Review

- The package design is directionally good: the core parsing/enrichment split is much cleaner than the legacy `ProjectReader`.
- The main risk is not missing code volume; it is letting the new chemistry/X-ray work leak back into the core parser layer.
- The next implementation step should be item 1 or item 2, not the chemistry feature itself.

## Execution Note

I could not run the local test suite in this environment because `pytest` is not installed here (`python3 -m pytest` fails with `No module named pytest`).
