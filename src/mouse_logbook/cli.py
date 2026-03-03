# src/mouse_logbook/cli.py

from __future__ import annotations

import argparse
import logging
from collections.abc import Iterable
from pathlib import Path

from .adapters.project_xlsx import ProjectXlsxParser
from .exceptions import ProjectSheetFormatError


def _configure_logging(verbosity: int) -> logging.Logger:
    level = logging.WARNING
    if verbosity == 1:
        level = logging.INFO
    elif verbosity >= 2:
        level = logging.DEBUG

    logging.basicConfig(level=level, format="%(levelname)s: %(message)s")
    return logging.getLogger("mouse_logbook")


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

    failures: list[str] = []
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
            proj = parser.parse(f)
            log.info("OK: %s (proposal_id=%s) samples=%d", f.name, proj.proposal_id, len(proj.samples))
        except ProjectSheetFormatError as e:
            failures.append(f"{f}: {e}")
            log.error("FAIL: %s", e)
        except Exception as e:
            failures.append(f"{f}: {e}")
            log.exception("ERROR: unexpected failure while parsing %s", f)

    if failures:
        log.error("Validation failed: %d/%d files invalid.", len(failures), checked)
        if args.report:
            report_path = Path(args.report).expanduser().resolve()
            report_path.write_text("\n".join(failures) + "\n", encoding="utf-8")
            log.error("Wrote report: %s", report_path)
        return 1

    log.info("Validation succeeded: %d files checked.", checked)
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
        help="Do not fail on schema problems (logs problems). Defaults to strict (fails).",
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
