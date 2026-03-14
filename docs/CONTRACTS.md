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

## SampleMetadataBuilder

- Maps parsed proposal-sheet `ProjectInfo` / `Sample` objects into richer sample-metadata extension models.
- Returns `ValidationReport[...]` so extension-level issues can be collected without changing the core parser contract.

## SampleMetadataChemistryValidator

- Validates chemistry descriptions for sample-metadata extension objects.
- Uses a pluggable interpreter interface so the chemistry backend is optional and replaceable.
- Returns `ValidationReport[...]` and preserves the original component description alongside parsed formula metadata.

## SampleMetadataMaterialsCalculator

- Derives sample-level material properties from chemistry-validated sample metadata.
- Treats component densities supplied by the proposal sheet as `true_density` with `experimentally_determined` provenance unless the schema later becomes more explicit.
- Derives sample density as `apparent_density` from complete phase-fraction inputs plus component densities.
- Can derive overall elemental mass and atom fractions from validated formulas and phase mass fractions.
- Returns `ValidationReport[...]` and leaves unavailable results explicit with structured warnings.

## SampleMetadataXrayCalculator

- Computes X-ray properties from chemistry-validated sample metadata, not from raw proposal parsing.
- `calculate_sample_at_energy(sample, energy_kev=...)` returns per-phase properties plus overall absorption when the required fractions are available.
- `precompute_sample(...)`, `precompute_project(...)`, and `precompute_enriched_entry(...)` attach standard Cu/Mo calculations to extension models.
- Exposes absorption in `1/m` and scattering length densities in `1/m^2`.
- Uses optional `periodictable` + `xraydb` backends behind the `materials` extra.

## DatasetValidator

- Validates the joined dataset rooted at one logbook file and one project base directory.
- Always runs logbook inspection, referenced-project inspection, and enrichment consistency checks.
- Supports staged levels:
  - `core`
  - `chemistry`
  - `materials`
  - `xray`
- Returns `ValidationReport[DatasetValidationResult]` and preserves successfully validated entries at each stage even when some issues are present.

## NexusMetadataUpserter

- Upserts one validated measurement into a `.nxs`/HDF5 file.
- Input:
  - one `MaterialEnrichedLogbookEntry`
  - one matching `XrayEnrichedLogbookEntry`
  - optionally one explicit `SampleXrayProperties` for nonstandard energies
- Raises `NexusMetadataError` if the material/X-ray entries do not describe the same measurement or if the X-ray source cannot be resolved.
- Writes compatibility metadata under:
  - `/entry1/proposal`
  - `/entry1/sample`
  - `/entry1/sample/components`
  - `/entry1/experiment`
  - `/entry1/processing_required_metadata`
- Selects the written X-ray metadata in this order:
  - explicit `sample_xray=...`
  - explicit `source_key=...`
  - inferred from `sampos` (`Cu ...` -> `cu_ka`, `Mo ...` -> `mo_ka`)
- Preserves existing `background_file` and `dispersed_background_file` dataset values by default because those paths are managed elsewhere.

## units

- Provides a shared `pint` registry plus conversion helpers for cross-module unit handling.
- Current helpers cover the X-ray backend library mismatches:
  - `keV -> eV`
  - `1/cm -> 1/m`
  - `1e-6/Å^2 -> 1/m^2`

## Logbook2MouseReader (legacy façade)

- Provides iteration over **enriched entries**
- Keeps the initialization pattern:
  `Logbook2MouseReader(logbook_path, project_base_path=project_base_path)`
