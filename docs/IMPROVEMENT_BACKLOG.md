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
- Item 4 is implemented in `src/mouse_logbook/project_repo.py` with a dedicated `ProjectFileAmbiguityError`.
- Item 5 is implemented in `src/mouse_logbook/io_excel.py` via explicit row parsing and `inspect_entries()`.
- Item 6 is implemented in `src/mouse_logbook/sample_metadata.py` as the initial sample-metadata extension boundary.
- Item 7 is implemented in `src/mouse_logbook/sample_metadata_chemistry.py` as the chemistry-validation layer on top of sample metadata.
- Item 8 is implemented in `src/mouse_logbook/sample_metadata_materials.py` as the derived-material-properties layer on top of chemistry-validated sample metadata.
- Item 9 is implemented in `src/mouse_logbook/sample_metadata_xray.py` as the X-ray property layer on top of chemistry-validated sample metadata.
- Item 10 is implemented in `src/mouse_logbook/dataset_validation.py` and `src/mouse_logbook/cli.py` as the joined validation workflow and CLI entrypoint.
- Item 11 is implemented in `src/mouse_logbook/nexus_metadata.py` as the compatibility NeXus/HDF5 metadata upsert layer.
- Item 12 is implemented in `src/mouse_logbook/nexus_export.py` and `src/mouse_logbook/cli.py` as the user-facing single-row NeXus export workflow and CLI command.
- The proposal parser now preserves component data when it appears on the same row as `sampleId`.
- Blank Excel cells are now treated as blank consistently instead of leaking through as string values such as `"nan"`.
- The project parser now exposes collected validation issues without depending on `strict` mode to surface them.
- `mouse-logbook validate-projects --lenient` now reports validation problems and can write them to `--report` without returning a failing exit code for schema issues.
- Regression tests were added for both supported sample-block layouts in `tests/unit/test_project_xlsx_parser.py`.
- Validation-report tests were added in `tests/unit/test_project_xlsx_parser_validation.py` and `tests/unit/test_cli_validate_projects.py`.
- Sample-environment tests now cover unnamed leading columns, missing `sampos`, non-numeric motors, and missing sample-position lookups.
- Project-repository tests now cover single-match, no-match, ambiguous-match, caching, and missing-sample behavior.
- Logbook-reader tests now cover structural issues, row-level field validation, optional field validation, filtering, and issue collection.
- Sample-metadata extension tests now cover project/sample mapping, duplicate component IDs, inconsistent enriched entries, and aggregation.
- Chemistry-validation tests now cover valid formulas, invalid formulas, missing descriptions, interpreter failures, and enriched-entry wrapping.
- Materials-derivation tests now cover:
  - formula material characterization
  - apparent-density estimates from volume fractions
  - apparent-density estimates from mass fractions
  - composition derivation when density is unavailable but mass fractions exist
  - unavailable-result warnings when phase fractions are missing
  - enriched-entry wrapping
- Dataset-validation tests now cover:
  - staged core/chemistry/materials/X-ray validation
  - enrichment consistency failures across logbook, project, sample, and sample-environment joins
  - CLI exit codes for core and X-ray validation
  - lenient reporting for extension-layer chemistry failures
- NeXus metadata writer tests now cover:
  - compatibility path creation under `/entry1/...`
  - Cu/Mo source selection from `sampos`
  - explicit nonstandard-energy overrides
  - preservation of externally managed background-file placeholders
  - rejection of mismatched material/X-ray entry pairs
- User-facing NeXus export tests now cover:
  - single-row export by `ymd + batchnum`
  - refusal to guess when multiple eligible logbook rows exist
  - refusal to accept only one half of the selection key
  - custom-energy export through the new CLI/service layer
  - writing into an existing `.nxs` output file
- X-ray extension tests now cover:
  - Cu/Mo precomputation
  - arbitrary-energy calculation
  - overall absorption derived from mass fractions
  - warnings when aggregate absorption cannot be derived
  - missing density / missing parsed formula failures
  - real backend unit conversion against `periodictable` and `xraydb`
- Unit conversions are now centralized in `src/mouse_logbook/units.py` and backed by `pint` instead of inline conversion constants.
- The optional `materials` extra now includes both `periodictable` and `xraydb`.
- The optional `hdf5` extra now includes `h5py`, and `h5py` is also listed in the `dev` extra for test runs.
- Current verification run: `.venv/bin/python -m pytest tests` -> `78 passed`; `.venv/bin/ruff check src tests` -> passed.

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

Status: completed

Implemented in:

- `src/mouse_logbook/project_repo.py`
- `src/mouse_logbook/exceptions.py`
- `tests/unit/test_project_repo.py`

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

Implemented change:

- Added `ProjectFileAmbiguityError` for multi-match proposal lookups.
- Updated `ProjectFileLocator.find_project_file(...)` to:
  - keep `ProjectNotFoundError` for zero matches
  - raise `ProjectFileAmbiguityError` for multiple matches
  - return the file only when the match is unique
- Added repository tests for:
  - unique match
  - missing year directory
  - missing project file
  - multiple matching project files
  - repository caching
  - missing sample lookup

Acceptance criteria:

- Zero matches and multiple matches are both explicit error cases.
- Enrichment never depends on filename sort order.

Verification:

- `tests/unit/test_project_repo.py`
- Full test suite and Ruff pass in the project virtualenv.

### 5. Add row-level validation to the logbook parser

Status: completed

Implemented in:

- `src/mouse_logbook/io_excel.py`
- `tests/unit/test_io_excel.py`

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

Implemented change:

- Added explicit cell parsers for required text, optional text, integers, optional integers, numbers, timestamps, optional timestamps, and `converttoscript`.
- Added `LogbookExcelReader.inspect_entries(...)` to return parsed entries plus structured validation issues.
- Changed `LogbookExcelReader.read_entries(...)` to stay strict while raising `LogbookFormatError` with row-aware messages when any row is invalid.
- Row validation now reports Excel row numbers and field names instead of leaking generic Python conversion exceptions.
- Invalid rows are skipped in `inspect_entries(...)`, while valid rows are still returned so validation can inspect the whole sheet in one pass.

Acceptance criteria:

- Invalid logbook cells produce actionable errors that include row number and field name.
- Logbook validation can be run independently from proposal validation.

Verification:

- `tests/unit/test_io_excel.py`
- Full test suite and Ruff pass in the project virtualenv.

## Sample/Chemistry Extension Roadmap

### 6. Introduce a richer sample domain model

Status: completed

Implemented in:

- `src/mouse_logbook/sample_metadata.py`
- `tests/unit/test_sample_metadata.py`

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

Implemented change:

- Added a dedicated extension module separate from core parsing/enrichment:
  - `SampleMetadataComponent`
  - `SampleMetadataSample`
  - `SampleMetadataProject`
  - `SampleMetadataEnrichedLogbookEntry`
- Added `SampleMetadataBuilder` to map parsed proposal-sheet models into the richer extension types.
- Added `SampleMetadataEnricher` to wrap existing `EnrichedLogbookEntry` values without changing the core pipeline.
- Kept the extension dependency-light and chemistry-free for now, so chemistry and X-ray logic can build on this layer next.
- Added structured validation at the extension boundary for duplicate component IDs while preserving the underlying component list.

Acceptance criteria:

- Core parsing remains dependency-light.
- Sample/material semantics are explicit and testable.

Verification:

- `tests/unit/test_sample_metadata.py`
- Full test suite and Ruff pass in the project virtualenv.

### 7. Add chemistry validation of component descriptions

Status: completed

Implemented in:

- `src/mouse_logbook/sample_metadata_chemistry.py`
- `tests/unit/test_sample_metadata_chemistry.py`

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

Implemented change:

- Added `ParsedChemicalFormula` plus chemistry-validated extension models for components, samples, projects, and enriched entries.
- Added `SampleMetadataChemistryValidator` as a separate layer on top of `sample_metadata`.
- Added an interpreter interface so chemistry parsing is pluggable:
  - tests use fake interpreters
  - real runs can use `PeriodictableChemistryInterpreter`
- Added validation for:
  - missing chemistry descriptions
  - interpreter/backend failures
  - invalid/unparseable formulas
  - non-positive densities at the chemistry-validation layer
- Preserved the original composition string while storing parsed/normalized formula information separately.

Validation checks:

- Formula string is parseable
- Density is positive when required
- At least one of `volFrac` or `massFrac` is available where needed
- Fractions are within range
- Fraction closure rules are explicit rather than silently normalized

Important migration note:

- Do not copy the legacy behavior of silently normalizing fractions (`project_reader.py:103-120`).
- Normalization should only happen when explicitly requested and should always be reported.

Verification:

- `tests/unit/test_sample_metadata_chemistry.py`
- Full test suite and Ruff pass in the project virtualenv.

### 8. Add derived sample composition and density estimates

Status: completed

Implemented in:

- `src/mouse_logbook/sample_metadata_materials.py`
- `tests/unit/test_sample_metadata_materials.py`

Feature goal:

- Derive an overall sample composition from the component list.
- Estimate bulk density when enough information is available.
- Distinguish experimentally determined values from derived values.

Proposed change:

- Compute composition/density from validated components only.
- Record provenance for each result:
  - `experimentally_determined`
  - `estimated_from_volume_fraction`
  - `estimated_from_mass_fraction`
  - `unavailable`
- Track density kind explicitly:
  - `apparent_density`
  - `true_density`
  - `skeletal_density`

Acceptance criteria:

- Missing inputs do not cause silent partial failure.
- Derived values are tagged with provenance and confidence notes.

Implemented change:

- Added explicit materials result models for:
  - formula-level material properties
  - density estimates with provenance and density kind
  - sample-level elemental composition estimates
- Added `SampleMetadataMaterialsCalculator` with component/sample/project/enriched-entry wrappers.
- Component densities supplied by the proposal sheet are now represented as:
  - provenance: `experimentally_determined`
  - density kind: `true_density` by default when the sheet does not say otherwise
- Sample densities derived from phase fractions are represented as:
  - density kind: `apparent_density`
  - provenance: `estimated_from_volume_fraction` or `estimated_from_mass_fraction`
- `skeletal_density` is part of the model surface for future use, but is not inferred from the current proposal-sheet schema.
- Derived sample composition now exposes:
  - overall elemental mass fractions
  - overall elemental atom fractions
  - explicit provenance based on whether the estimate came from mass-fraction or volume-fraction inputs
- When only direct mass fractions are available, the layer can still derive overall composition even if density is missing.
- When the inputs are insufficient, the layer returns structured warnings and explicit `unavailable` provenance instead of silent partial results.

Verification:

- `tests/unit/test_sample_metadata_materials.py`
- Full test suite and Ruff pass in the project virtualenv.

### 9. Add X-ray property calculations with explicit SI units

Status: completed

Implemented in:

- `src/mouse_logbook/sample_metadata_xray.py`
- `tests/unit/test_sample_metadata_xray.py`

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
- Make energy an explicit input to all X-ray calculations rather than a hidden default.

Implemented change:

- Added explicit X-ray result models:
  - `ScatteringLengthDensity`
  - `PhaseXrayProperties`
  - `SampleXrayProperties`
- Added X-ray-enriched extension models for samples, projects, and enriched logbook entries.
- Added `SampleMetadataXrayCalculator` with:
  - `calculate_sample_at_energy(..., energy_kev=...)` for arbitrary energies
  - precomputation of standard lab-source values on samples/projects/enriched entries
- Standard precomputed energies are now:
  - `cu_ka = 8.04 keV`
  - `mo_ka = 17.4 keV`
- Added a real optional backend using:
  - `xraydb.material_mu(...)` for absorption coefficients
  - `periodictable.xsf.xray_sld(...)` for scattering length densities
- The implementation converts library outputs into explicit SI-facing API fields:
  - absorption coefficient in `1/m`
  - real/imaginary SLD in `1/m^2`
- Those conversions now go through a shared `pint`-backed unit layer in `src/mouse_logbook/units.py`.
- Sanity-check tests now use a wider absorption tolerance than SLD tolerance because
  `xraydb` and `periodictable` rely on different underlying tables; SLD reference
  values align more tightly with the current backend than absorption references do.
- Overall sample absorption is computed:
  - directly from `volume_fraction` when complete
  - from volume fractions derived from `mass_fraction` and density when needed
  - otherwise left unavailable with a structured warning rather than a silent partial result
- The `mouse_logbook[materials]` optional dependency set now includes both `periodictable` and `xraydb`.

Design note from current experimental practice:

- Common lab-source energies are:
  - copper source: `8.04 keV`
  - molybdenum source: `17.4 keV`
- Synchrotron measurements may use other energies, so the API must support arbitrary energies cleanly.

Suggested result shapes:

- `AbsorptionCoefficient(value_m_inv: float)`
- `ScatteringLengthDensity(real_m_inv2: float, imag_m_inv2: float | None = None)`
- `PhaseXrayProperties(phase_id, mu, sld)`
- `SampleXrayProperties(overall_mu, per_phase)`

Important migration note:

- Avoid broad `except Exception` recovery like the legacy `Sample.__attrs_post_init__` (`project_reader.py:85-95`).
- Scientific calculations should fail explicitly or emit structured warnings with provenance.

Important implementation note:

- `periodictable` and `xraydb` use different energy conventions:
  - `periodictable.xsf.xray_sld(..., energy=...)` expects `keV`
  - `xraydb.material_mu(..., energy=...)` expects `eV`
- The extension layer hides that mismatch and exposes a consistent `energy_kev` API.
- Cross-library reference comparisons should also expect somewhat larger spread for
  absorption coefficients than for SLDs because the tabulated source data differs.

Verification:

- `tests/unit/test_sample_metadata_xray.py`
- Full test suite and Ruff pass in the project virtualenv.

### 10. Add proposal validation that spans logbook, proposal, and sample semantics

Status: completed

Implemented in:

- `src/mouse_logbook/dataset_validation.py`
- `src/mouse_logbook/cli.py`
- `tests/unit/test_dataset_validation.py`
- `tests/unit/test_cli_validate_dataset.py`

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

Implemented change:

- Added `DatasetValidator` as a staged workflow that runs:
  - logbook inspection
  - referenced-project inspection
  - enrichment consistency checks for samples and sample environments
  - optional chemistry/materials/X-ray validation layers
- Added validation levels:
  - `core`
  - `chemistry`
  - `materials`
  - `xray`
- The validator preserves successfully parsed/enriched entries while still collecting issues across all stages.
- Added a CLI command:
  - `mouse-logbook validate-dataset LOGBOOK PROJECT_BASE_DIR`
- The CLI supports:
  - `--level`
  - `--load-all`
  - `--lenient`
  - `--report`

Verification:

- `tests/unit/test_dataset_validation.py`
- `tests/unit/test_cli_validate_dataset.py`
- Full test suite and Ruff pass in the project virtualenv.

## Suggested Delivery Order

1. Fix parser correctness issues in the current core package.
2. Introduce structured validation results and better CLI reporting.
3. Add independent logbook validation.
4. Create the sample/material extension boundary.
5. Implement chemistry validation with tests.

## Testing Gaps To Add

- CLI or service-level integration tests once the writer is wired into the runtime ingestion workflow.

## Notes From This Review

- The package design is directionally good: the core parsing/enrichment split is much cleaner than the legacy `ProjectReader`.
- The main risk is not missing code volume; it is letting the new chemistry/X-ray work leak back into the core parser layer.
- The next implementation step should be wiring the HDF5 writer/upsert layer into the ingestion runtime once the external file-writing call site is settled.

### 12. Make the NeXus metadata writer user-facing

Status: completed

Implemented in:

- `src/mouse_logbook/nexus_export.py`
- `src/mouse_logbook/cli.py`
- `tests/unit/test_nexus_export.py`
- `tests/unit/test_cli_write_nexus_metadata.py`

Problem:

- The HDF5 writer existed only as a library helper, which left no supported command-line path for operators to create or update a `.nxs` file from the validated logbook/proposal/sample metadata.
- A user-facing export path also needs a stable measurement-selection rule so the tool does not silently write the wrong measurement when one logbook contains multiple rows.

Implemented change:

- Added `NexusMetadataExportService` to orchestrate one selected logbook entry through:
  - selection by `ymd + batchnum`
  - project lookup
  - sample-environment resolution
  - chemistry/material/X-ray derivation
  - final NeXus metadata upsert
- Added CLI command:
  - `mouse-logbook write-nexus-metadata LOGBOOK PROJECT_BASE_DIR OUTPUT_FILE`
- The command supports:
  - `--ymd` plus `--batch-num` to select one measurement series explicitly
  - `--load-all` to include rows with `converttoscript=0`
  - `--source-key` to force a specific precomputed X-ray source label
  - `--energy-kev` to compute a custom-energy export
  - `--report` for issue output
- When multiple eligible rows exist, the command now fails explicitly instead of guessing.
- The command also fails when only one half of the `ymd + batchnum` identifier is provided.

### 11. Add a compatibility NeXus/HDF5 metadata upsert layer

Status: completed

Implemented in:

- `src/mouse_logbook/nexus_metadata.py`
- `tests/unit/test_nexus_metadata.py`

Problem:

- The new package could validate and enrich metadata, but it still had no writer that could push those validated values into the `.nxs` files used by the current downstream processing pipeline.
- The file layout is partially legacy and partially evolved over time, so compatibility depends on matching the current path names rather than inventing a cleaner schema prematurely.

Implemented change:

- Added `NexusMetadataUpserter` to upsert:
  - proposal metadata into `/entry1/proposal`
  - sample metadata into `/entry1/sample`
  - per-phase metadata into `/entry1/sample/components`
  - logbook experiment metadata into `/entry1/experiment`
  - processing identifiers into `/entry1/processing_required_metadata`
- The writer consumes the validated materials/X-ray layers instead of re-deriving chemistry or X-ray properties internally.
- `overall_mu` and per-phase `mu` / `sld_real` / `sld_imag` are written for the selected X-ray energy.
- Standard source selection defaults to `sampos` inference:
  - `Cu ...` -> `cu_ka`
  - `Mo ...` -> `mo_ka`
- Nonstandard energies are supported by passing an explicit `SampleXrayProperties` object.
- Existing `background_file` and `dispersed_background_file` datasets are preserved by default because those file paths are assigned elsewhere.

## Execution Note

The current branch verifies in the project virtualenv with:

- `.venv/bin/python -m pytest tests`
- `.venv/bin/ruff check src tests`
