# Refactor Plan

## Goal

Improve internal code clarity and maintainability without prematurely splitting the project into multiple Python distributions.

This plan aims to:

- make responsibilities explicit inside the repository
- reduce cross-module sprawl at the package root
- isolate optional scientific and HDF5 concerns behind clear boundaries
- prepare the codebase for a future split into 2 or 3 packages if that becomes useful

## Decision Summary

Do not split `mouse_logbook` into four distributions now.

Instead:

- keep one repository
- keep one installable package for now
- refactor into clearer internal subpackages
- keep dependency direction one-way
- keep `materials` and `hdf5` as optional extras

Why:

- the current shared model and validation contracts are still central enough that a 4-way split would mostly create versioning and release friction
- the stronger maintainability problem today is module clarity, not distribution count
- the scientific and export layers are already optional by dependency, so internal boundaries matter more than packaging boundaries right now

## Current Shape

The current package root still contains nearly all modules directly:

- core ingestion and enrichment
- scientific/material extensions
- export/writer logic
- orchestration workflows
- CLI entrypoints
- legacy compatibility façade

That shape is workable, but it now hides the actual architecture.

Current high-pressure modules by size and mixed concern:

- `src/mouse_logbook/sample_metadata_materials.py`
- `src/mouse_logbook/sample_metadata_xray.py`
- `src/mouse_logbook/nexus_metadata.py`
- `src/mouse_logbook/adapters/project_xlsx.py`
- `src/mouse_logbook/cli.py`

## Shared Parts That Argue Against a Split Today

These pieces are shared across almost all features and should remain the stable center:

- domain identities:
  - `proposal_id`
  - `sample_id`
  - `sampos`
  - `ymd + batchnum`
- core models:
  - `LogbookEntry`
  - `EnrichedLogbookEntry`
- validation contracts:
  - `ValidationIssue`
  - `ValidationReport`
- typed error taxonomy
- MOUSE-specific filesystem and workbook conventions
- enrichment join between logbook, proposal sheet, sample, and sample-environment data

Those shared contracts are the natural foundation for all higher-level features.

## Target Internal Package Boundaries

Target package layout:

```text
src/mouse_logbook/
    __init__.py

    core/
        __init__.py
        exceptions.py
        validation.py
        models.py
        io/
            __init__.py
            logbook_excel.py
            environment_excel.py
        project/
            __init__.py
            project_xlsx.py
            project_repo.py
        enrich/
            __init__.py
            services.py

    materials/
        __init__.py
        models.py
        mapping.py
        chemistry.py
        composition.py
        density.py
        xray.py
        units.py

    export/
        __init__.py
        nexus/
            __init__.py
            writer.py
            layout.py

    workflows/
        __init__.py
        dataset_validation.py
        nexus_export.py

    cli/
        __init__.py
        main.py
        validate_projects.py
        validate_dataset.py
        write_nexus_metadata.py

    compat/
        __init__.py
        legacy.py
```

This is an internal organization target, not a promise that every file above must exist immediately.

## Layer Responsibilities

### `core`

Owns:

- logbook reading/parsing
- project/proposal reading/parsing
- sample-environment reading
- repository lookup/caching
- core models
- validation and exception primitives
- enrichment joins

Must not depend on:

- `periodictable`
- `xraydb`
- `h5py`
- any export format

Why:

- this is the natural candidate for a future `mouse-logbook-core` distribution

### `materials`

Owns:

- mapping core-enriched data into richer sample/material models
- chemistry parsing and validation
- density and composition derivation
- X-ray property derivation
- units used only by scientific/material calculations

Depends on:

- `core`

Must not depend on:

- CLI
- HDF5/NeXus writing

Why:

- this layer is domain-specific and optional by dependency
- it is the cleanest candidate for a future `mouse-logbook-materials` distribution

### `export`

Owns:

- concrete output-format writers
- format-specific path naming
- file update semantics

Depends on:

- `core`
- optionally `materials`, depending on the format needs

Must not own:

- dataset selection logic
- validation orchestration
- project lookup

Why:

- the current NeXus writer is really a format adapter, not an orchestration service

### `workflows`

Owns:

- orchestration that spans multiple layers
- selection logic
- staged validation workflows
- user-facing service objects that compose core + materials + export

Depends on:

- `core`
- `materials`
- `export`

Why:

- this keeps orchestration code out of low-level writer/parser modules

### `cli`

Owns:

- argument parsing
- logging
- command dispatch
- translation between CLI args and workflow services

Must not own:

- business logic
- parsing rules
- derivation logic

Why:

- the current `cli.py` is becoming a command router plus workflow wrapper; splitting commands into modules will keep it readable

### `compat`

Owns:

- legacy surface area only

Why:

- keeps transitional compatibility separate from the clean long-term API

## Dependency Rules

Allowed direction:

```text
core -> nothing internal below it
materials -> core
export -> core, materials
workflows -> core, materials, export
cli -> workflows, core
compat -> core
```

Not allowed:

- `core` importing `materials`
- `core` importing `export`
- `materials` importing `export`
- writer modules doing project lookup or logbook row selection
- CLI modules implementing validation/derivation directly

## Public API Strategy

The top-level package should expose only stable, intentional entrypoints.

Keep at top level:

- stable core exceptions and models
- `Logbook2MouseReader` while compatibility is still needed
- `DatasetValidator`
- `NexusMetadataExportService`
- `NexusMetadataUpserter`

Move users toward namespaced imports for advanced functionality:

- `mouse_logbook.core...`
- `mouse_logbook.materials...`
- `mouse_logbook.workflows...`
- `mouse_logbook.export...`

Why:

- it makes future package extraction easier
- it reduces accidental coupling to internal implementation details

## Immediate Refactor Steps

### Phase 1: Mechanical Moves, No Behavior Changes

- Create the internal subpackages listed above.
- Move modules without changing semantics.
- Leave compatibility re-export shims at the old import paths where useful.
- Keep tests passing after each move.

Primary targets:

- move `exceptions.py`, `validation.py`, `models.py` under `core`
- move `io_excel.py`, `environment_repo.py`, `project_repo.py`, `adapters/project_xlsx.py`, `services.py` under `core`
- move `sample_metadata*.py` and `units.py` under `materials`
- move `nexus_metadata.py` under `export/nexus`
- move `dataset_validation.py` and `nexus_export.py` under `workflows`
- split `cli.py` into command modules under `cli`
- move `legacy.py` under `compat`

### Phase 2: Split Large Modules by Responsibility

#### `sample_metadata_materials.py`

Split into:

- material models
- fraction normalization and provenance helpers
- density derivation
- composition derivation
- formula characterization backend

#### `sample_metadata_xray.py`

Split into:

- X-ray models
- backend interface/backends
- phase calculation
- aggregate sample calculation
- standard-energy precompute logic

#### `nexus_metadata.py`

Split into:

- layout/path constants
- HDF5 primitive write helpers
- sample/proposal/experiment/component writers
- public `NexusMetadataUpserter`

#### `project_xlsx.py`

Split into:

- sheet loading
- schema normalization
- sample-block grouping
- row-to-component parsing
- validation accumulation

#### `cli.py`

Split into:

- `main.py`
- one module per command
- shared logging/report helpers

### Phase 3: Tighten Public Boundaries

- Reduce `src/mouse_logbook/__init__.py` to the stable public API only.
- Stop re-exporting implementation-heavy internals from the package root.
- Add explicit module-level `__all__` where helpful.

### Phase 4: Dependency Cleanup

- Move `pint` out of the base dependency set if it remains materials-only after the refactor.
- Keep `periodictable`, `xraydb`, and `h5py` fully outside the `core` dependency path.
- Ensure `workflows.dataset_validation` can still run at `core` level without scientific extras installed.

### Phase 5: Documentation and Contracts

- Update `docs/DESIGN.md` to describe the new internal layering.
- Update `docs/CONTRACTS.md` with namespaced module locations after the move.
- Keep README focused on user-facing APIs, not internal implementation details.

## Suggested Concrete Module Mapping

Suggested mapping from current modules:

- `io_excel.py` -> `core/io/logbook_excel.py`
- `environment_repo.py` -> `core/io/environment_excel.py`
- `adapters/project_xlsx.py` -> `core/project/project_xlsx.py`
- `project_repo.py` -> `core/project/project_repo.py`
- `services.py` -> `core/enrich/services.py`
- `models.py` -> `core/models.py`
- `exceptions.py` -> `core/exceptions.py`
- `validation.py` -> `core/validation.py`
- `sample_metadata.py` -> `materials/mapping.py`
- `sample_metadata_chemistry.py` -> `materials/chemistry.py`
- `sample_metadata_materials.py` -> `materials/density.py`, `materials/composition.py`, `materials/models.py`
- `sample_metadata_xray.py` -> `materials/xray.py`
- `units.py` -> `materials/units.py`
- `nexus_metadata.py` -> `export/nexus/writer.py`
- `nexus_export.py` -> `workflows/nexus_export.py`
- `dataset_validation.py` -> `workflows/dataset_validation.py`
- `legacy.py` -> `compat/legacy.py`
- `cli.py` -> `cli/main.py` plus command modules

## Future Package Split Paths

### 2-package future

#### `mouse-logbook-core`

Contains:

- `core`
- `compat`
- basic CLI commands that do not require scientific extras

#### `mouse-logbook-materials`

Contains:

- `materials`
- `export`
- `workflows`
- advanced CLI commands that require scientific or HDF5 extras

When this makes sense:

- if core ingestion is stable and widely reusable
- if scientific layers evolve faster than the base reader/parser

### 3-package future

#### `mouse-logbook-core`

- ingestion, validation, enrichment primitives

#### `mouse-logbook-materials`

- chemistry, composition, density, X-ray derivation

#### `mouse-logbook-nexus`

- NeXus/HDF5 writer and export workflows

When this makes sense:

- if multiple export targets appear
- if NeXus compatibility starts moving on a different cadence from materials logic

## Non-Goals

This plan does not aim to:

- change workbook schemas
- replace the current data contracts
- remove the legacy façade immediately
- split the repository now
- redesign the current NeXus output layout

## Acceptance Criteria For The Refactor

The refactor is successful when:

- module names reflect actual architectural layers
- dependency direction is one-way and obvious
- core imports do not drag in scientific or HDF5 dependencies
- CLI modules are thin wrappers around service/workflow objects
- the top-level API is intentionally small
- the codebase is ready for a future 2- or 3-package split without major model churn

## Recommended Next Move

Start with Phase 1 and Phase 2 only.

That gets most of the maintainability benefit without forcing an immediate packaging decision.
