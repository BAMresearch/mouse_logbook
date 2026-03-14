# src/mouse_logbook/cli.py

from __future__ import annotations

import argparse
import logging
from collections.abc import Iterable
from pathlib import Path

from .adapters.project_xlsx import ProjectXlsxParser
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

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
