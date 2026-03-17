# src/mouse_logbook/cli.py

from __future__ import annotations

import argparse
import logging
from collections.abc import Iterable
from pathlib import Path

from .adapters.project_xlsx import ProjectXlsxParser
from .dataset_validation import DatasetValidator
from .nexus_export import NexusMetadataExportService
from .validation import ValidationIssue


def _configure_logging(verbosity: int) -> logging.Logger:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logging.basicConfig(level=level, format="%(levelname)s: %(message)s", force=True)
    return logging.getLogger("mouse_logbook")


def _log_issue(log: logging.Logger, file_path: Path, issue: ValidationIssue, *, strict: bool) -> str:
    line = f"{file_path}: {issue.severity}: {issue}"
    if issue.severity == "info":
        level = logging.INFO
    elif issue.severity == "warning":
        level = logging.WARNING
    else:
        level = logging.ERROR if strict else logging.WARNING
    log.log(level, "%s", line)
    return line


def _log_dataset_issue(log: logging.Logger, issue: ValidationIssue, *, strict: bool) -> str:
    line = f"{issue.severity}: {issue}"
    if issue.severity == "info":
        level = logging.INFO
    elif issue.severity == "warning":
        level = logging.WARNING
    else:
        level = logging.ERROR if strict else logging.WARNING
    log.log(level, "%s", line)
    return line


def _iter_project_files(project_base_dir: Path) -> Iterable[Path]:
    # Convention: {base}/{year}/{proposal_id}*.xlsx
    for year_dir in sorted(project_base_dir.glob("[0-9][0-9][0-9][0-9]")):
        if not year_dir.is_dir():
            continue
        yield from sorted(year_dir.glob("*.xlsx"))


def cmd_validate_projects(args: argparse.Namespace) -> int:
    log = _configure_logging(args.verbose)

    base_dir = Path(args.project_base_dir).expanduser().resolve()
    if not base_dir.is_dir():
        log.error("Project base directory not found: %s", base_dir)
        return 2

    strict = not args.lenient
    parser = ProjectXlsxParser(strict=strict)

    validation_failures: list[str] = []
    fatal_failures: list[str] = []
    report_lines: list[str] = []
    checked = 0

    files = (
        [Path(f).expanduser().resolve() for f in args.files]
        if args.files
        else list(_iter_project_files(base_dir))
    )

    if not files:
        log.warning("No project files found under %s", base_dir)
        return 0

    for f in files:
        checked += 1
        try:
            report = parser.inspect(f)
            error_issues = report.issues_for("error")
            warning_issues = report.issues_for("warning")

            for issue in report.issues:
                report_lines.append(_log_issue(log, f, issue, strict=strict))

            if error_issues:
                failure = f"{f}: " + "; ".join(str(issue) for issue in error_issues)
                if strict:
                    validation_failures.append(failure)
                    log.error("FAIL: %s", failure)
                else:
                    log.warning("WARN: %s has %d validation error(s) in lenient mode.", f.name, len(error_issues))
            elif warning_issues:
                log.warning("WARN: %s has %d validation warning(s).", f.name, len(warning_issues))
            else:
                proj = report.value
                log.info("OK: %s (proposal_id=%s) samples=%d", f.name, proj.proposal_id, len(proj.samples))
        except Exception as e:
            failure = f"{f}: {e}"
            fatal_failures.append(failure)
            report_lines.append(failure)
            log.exception("ERROR: unexpected failure while parsing %s", f)

    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        text = ""
        if report_lines:
            text = "\n".join(report_lines) + "\n"
        report_path.write_text(text, encoding="utf-8")
        log.info("Wrote report: %s", report_path)

    if strict and (validation_failures or fatal_failures):
        total_failures = len(validation_failures) + len(fatal_failures)
        log.error("Validation failed: %d/%d files invalid.", total_failures, checked)
        return 1

    if fatal_failures:
        log.error("Validation encountered %d unexpected failure(s).", len(fatal_failures))
        return 1

    if strict:
        log.info("Validation succeeded: %d files checked.", checked)
    else:
        issue_count = len(report_lines)
        if issue_count:
            log.warning("Lenient validation completed: %d files checked, %d issue(s) reported.", checked, issue_count)
        else:
            log.info("Lenient validation succeeded: %d files checked.", checked)
    return 0


def cmd_validate_dataset(args: argparse.Namespace) -> int:
    log = _configure_logging(args.verbose)

    logbook_file = Path(args.logbook_file).expanduser().resolve()
    if not logbook_file.is_file():
        log.error("Logbook file not found: %s", logbook_file)
        return 2

    project_base_dir = Path(args.project_base_dir).expanduser().resolve()
    if not project_base_dir.is_dir():
        log.error("Project base directory not found: %s", project_base_dir)
        return 2

    strict = not args.lenient

    try:
        report = DatasetValidator(logbook_file=logbook_file, project_base_dir=project_base_dir).validate(
            level=args.level,
            load_all=args.load_all,
        )
    except Exception:
        log.exception("ERROR: unexpected failure while validating dataset")
        return 1

    report_lines = [_log_dataset_issue(log, issue, strict=strict) for issue in report.issues]

    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        text = ""
        if report_lines:
            text = "\n".join(report_lines) + "\n"
        report_path.write_text(text, encoding="utf-8")
        log.info("Wrote report: %s", report_path)

    if strict and report.has_errors:
        log.error("Dataset validation failed at level=%s.", args.level)
        return 1

    if strict:
        log.info(
            "Dataset validation succeeded at level=%s: entries=%d enriched=%d",
            args.level,
            len(report.value.entries),
            len(report.value.enriched_entries),
        )
    elif report_lines:
        log.warning(
            "Lenient dataset validation completed at level=%s with %d issue(s).",
            args.level,
            len(report_lines),
        )
    else:
        log.info("Lenient dataset validation succeeded at level=%s.", args.level)
    return 0


def cmd_write_nexus_metadata(args: argparse.Namespace) -> int:
    log = _configure_logging(args.verbose)

    logbook_file = Path(args.logbook_file).expanduser().resolve()
    if not logbook_file.is_file():
        log.error("Logbook file not found: %s", logbook_file)
        return 2

    project_base_dir = Path(args.project_base_dir).expanduser().resolve()
    if not project_base_dir.is_dir():
        log.error("Project base directory not found: %s", project_base_dir)
        return 2

    output_file = Path(args.output_file).expanduser().resolve()

    try:
        report = NexusMetadataExportService(
            logbook_file=logbook_file,
            project_base_dir=project_base_dir,
        ).write_entry(
            output_file=output_file,
            ymd=args.ymd,
            batch_num=args.batch_num,
            load_all=args.load_all,
            source_key=args.source_key,
            energy_kev=args.energy_kev,
        )
    except Exception:
        log.exception("ERROR: unexpected failure while writing NeXus metadata")
        return 1

    report_lines = [_log_dataset_issue(log, issue, strict=True) for issue in report.issues]

    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        text = ""
        if report_lines:
            text = "\n".join(report_lines) + "\n"
        report_path.write_text(text, encoding="utf-8")
        log.info("Wrote report: %s", report_path)

    if report.has_errors or report.value is None:
        log.error("NeXus metadata write failed.")
        return 1

    log.info(
        "Wrote NeXus metadata: %s (proposal_id=%s sampleId=%s source=%s energy=%.4g keV)",
        report.value.output_file,
        report.value.entry.proposal_id,
        report.value.entry.sample_id,
        report.value.source_key,
        report.value.energy_kev,
    )
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mouse-logbook", description="Validate and work with MOUSE logbook assets.")
    sub = p.add_subparsers(dest="cmd", required=True)

    v = sub.add_parser(
        "validate-projects",
        help="Validate proposal sheets in the implicit filesystem convention {base}/{year}/{proposal}*.xlsx",
    )
    v.add_argument("project_base_dir", help="Base directory that contains year subdirectories (e.g. .../projects).")
    v.add_argument(
        "--files",
        nargs="*",
        default=None,
        help="Optional explicit list of .xlsx files to validate (skips directory scanning).",
    )
    v.add_argument(
        "--lenient",
        action="store_true",
        help="Report schema problems without failing validation. Defaults to strict (fails on errors).",
    )
    v.add_argument(
        "--report",
        default=None,
        help="Write a newline-separated report of failures to this path.",
    )
    v.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (-v, -vv).")
    v.set_defaults(func=cmd_validate_projects)

    d = sub.add_parser(
        "validate-dataset",
        help="Validate a logbook together with referenced proposal sheets and optional chemistry/material/X-ray layers.",
    )
    d.add_argument("logbook_file", help="Path to the logbook .xlsx file.")
    d.add_argument("project_base_dir", help="Base directory that contains year subdirectories with proposal sheets.")
    d.add_argument(
        "--level",
        choices=("core", "chemistry", "materials", "xray"),
        default="core",
        help="Validation depth. 'core' validates logbook/project/enrichment only; higher levels add optional domain checks.",
    )
    d.add_argument(
        "--load-all",
        action="store_true",
        help="Validate all logbook rows, not only rows with converttoscript=1.",
    )
    d.add_argument(
        "--lenient",
        action="store_true",
        help="Report validation problems without failing the command. Defaults to strict (fails on errors).",
    )
    d.add_argument(
        "--report",
        default=None,
        help="Write a newline-separated report of issues to this path.",
    )
    d.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (-v, -vv).")
    d.set_defaults(func=cmd_validate_dataset)

    w = sub.add_parser(
        "write-nexus-metadata",
        help="Write validated proposal/sample/logbook metadata into a new or existing NeXus/HDF5 file.",
    )
    w.add_argument("logbook_file", help="Path to the logbook .xlsx file.")
    w.add_argument("project_base_dir", help="Base directory that contains year subdirectories with proposal sheets.")
    w.add_argument("output_file", help="Path to the target .nxs/.h5 file to create or update.")
    w.add_argument(
        "--ymd",
        default=None,
        help="Logbook date code in YYYYMMDD form used together with --batch-num to select one measurement series.",
    )
    w.add_argument(
        "--batch-num",
        type=int,
        default=None,
        help="Logbook batch number used together with --ymd to select one measurement series.",
    )
    w.add_argument(
        "--load-all",
        action="store_true",
        help="Allow selecting from all logbook rows, not only rows with converttoscript=1.",
    )
    w.add_argument(
        "--source-key",
        default=None,
        help="Override the X-ray source key to write (for example: cu_ka, mo_ka, or a custom label).",
    )
    w.add_argument(
        "--energy-kev",
        type=float,
        default=None,
        help="Compute and write X-ray metadata for this explicit energy instead of the standard Cu/Mo precompute.",
    )
    w.add_argument(
        "--report",
        default=None,
        help="Write a newline-separated report of export issues to this path.",
    )
    w.add_argument("-v", "--verbose", action="count", default=0, help="Increase verbosity (-v, -vv).")
    w.set_defaults(func=cmd_write_nexus_metadata)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
