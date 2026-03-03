# Design

## Goal

Parse logbook Excel files into immutable `LogbookEntry` records (single source of truth),
and optionally enrich them with project/sample and sample-environment metadata.

## Architecture

- `io_excel.LogbookExcelReader`: pure Excel -> `LogbookEntry`
- `project_repo.ProjectRepository`: locate + parse + cache project sheets
- `environment_repo.SampleEnvironmentRepository`: read + cache motor positions per `sampos`
- `services.LogbookEnricher`: join entries with project/sample/environment
- `legacy.Logbook2MouseReader`: compatibility façade to keep downstream code stable

## Validation philosophy

Project/proposal sheets are user-authored and are a common source of errors.
The default `ProjectXlsxParser` therefore performs **strict schema validation** by default and raises
`ProjectSheetFormatError` with actionable error messages.

## Contracts

- `LogbookEntry` is immutable and safe to persist / hash / compare.
- Enrichment is deterministic and testable.
- Errors are typed (format vs missing project vs missing sample vs missing sampos).
