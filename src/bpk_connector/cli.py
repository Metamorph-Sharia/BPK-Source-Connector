"""Command line: ``bpk-connector <command>``. Run ``bpk-connector --help`` for the list."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from collections.abc import Callable, Sequence
from dataclasses import asdict
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from bpk_connector.adapters.catalog.files import CatalogError
from bpk_connector.application.dto import Candidate
from bpk_connector.application.targets import all_targets
from bpk_connector.application.use_cases.review_candidates import ReviewError
from bpk_connector.config import DEFAULT_CONFIG_PATH, MB, ConfigError, load_config
from bpk_connector.domain.alerts import Severity
from bpk_connector.domain.health import check_health
from bpk_connector.domain.models import Tier
from bpk_connector.wiring import App, build, environment_problems

EXIT_OK, EXIT_PROBLEMS, EXIT_USAGE = 0, 2, 64


def _print(value: Any) -> None:
    print(json.dumps(value, indent=2, ensure_ascii=False, default=str))


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="bpk-connector", description="Collect targeted regulations from peraturan.bpk.go.id."
    )
    p.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="pipeline config (default: %(default)s)")
    p.add_argument("-v", "--verbose", action="store_true", help="debug logging")
    sub = p.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="the scheduled job: check targets, fetch files, export the corpus")
    run.add_argument("--max-mb", type=int, help="download budget for this run (default: from config)")
    run.add_argument("--no-export", action="store_true")
    sub.add_parser("check", help="re-read every target's page; record changes; grow the lineage")
    fetch = sub.add_parser("fetch", help="download new or changed files of every target")
    fetch.add_argument("--max-mb", type=int)
    extract = sub.add_parser("extract", help="extract text from stored files not yet extracted (no network)")
    extract.add_argument("--retry-unsupported", action="store_true", help="try again files once found unreadable")
    extract.add_argument(
        "--again", action="store_true", help="every stored file, extracted before or not (METAMORPH_PDF_LINES changed)"
    )
    export = sub.add_parser("export", help="rebuild data/corpus/ from what we hold (no network)")
    export.add_argument(
        "--format", choices=["corpus", "v2"], default="corpus",
        help="corpus: data/corpus/ (default); v2: a contract v2 bundle for the platform loader",
    )  # fmt: skip
    export.add_argument("--out", type=Path, help="v2 only: an empty or new directory for the bundle")
    export.add_argument("--run-id", help="v2 only: identifies this export to the loader (default: UTC timestamp)")
    sub.add_parser("reparse", help="re-apply the parser to every stored page (no network), then export")
    sub.add_parser("status", help="counts: targets, records, files, candidates, last run")
    sub.add_parser("health", help="is ingestion healthy? exit 0 ok / 1 warning / 2 critical")
    review = sub.add_parser("review", help="the review queue: list, approve or reject candidates")
    review_sub = review.add_subparsers(dest="review_command", required=True)
    review_sub.add_parser("list", help="open candidates and why they were proposed")
    approve = review_sub.add_parser("approve", help="add to config/targets.csv (commit it as a pull request)")
    approve.add_argument("record_id")
    approve.add_argument("--tier", required=True, choices=[t.value for t in Tier])
    approve.add_argument("--domain", required=True, help="target-list domain letter, e.g. B")
    approve.add_argument("--note", required=True, help="why it belongs (becomes the rationale)")
    reject = review_sub.add_parser("reject", help="close without collecting it")
    reject.add_argument("record_id")
    reject.add_argument("--note", required=True, help="why not")
    events = sub.add_parser("events", help="what changed, from the event log")
    events.add_argument("--since", type=date.fromisoformat, default=date.today(), help="YYYY-MM-DD (default: today)")
    return p


def _run_id() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")


def _budget(app: App, max_mb: int | None) -> int:
    return max_mb * MB if max_mb is not None else app.config.max_bytes_per_run


def _export(app: App, args: argparse.Namespace) -> int:
    if args.format == "corpus":
        _print(asdict(app.export.run()))
        return EXIT_OK
    if args.out is None:
        print("bpk-connector: export --format v2 needs --out DIR", file=sys.stderr)
        return EXIT_USAGE
    run_id = args.run_id or _run_id()
    _print({"bundle": str(args.out), "run_id": run_id} | asdict(app.export_bundle(args.out, run_id).run()))
    return EXIT_OK


NEEDS_ENVIRONMENT = {"run", "extract"}
RUN_SUMMARY = ("run_id", "status", "error", "worst_severity", "sync", "triage", "check", "fetch", "extract", "export")


def _dispatch(app: App, args: argparse.Namespace) -> int:
    problems = environment_problems(app.config)
    if problems and args.command in NEEDS_ENVIRONMENT:
        print("bpk-connector: this machine can't run the connector: " + "; ".join(problems), file=sys.stderr)
        print("  see README.md, 'System requirements', or set [extraction] ocr = false", file=sys.stderr)
        return EXIT_PROBLEMS
    return COMMANDS[args.command](app, args)


def _run(app: App, args: argparse.Namespace) -> int:
    report = app.pipeline.run(_run_id(), max_bytes=_budget(app, args.max_mb), export=not args.no_export)
    summary = report.as_dict()
    finished = report.finished_at and report.finished_at.isoformat()
    app.store.save_run(
        report.run_id,
        started_at=report.started_at.isoformat(),
        finished_at=finished,
        status=report.status,
        report=summary,
    )
    app.reports.write(report)
    _print({k: summary[k] for k in RUN_SUMMARY})
    _print([f"{a['severity']}: {a['code']}: {a['message']}" for a in summary["alerts"]])
    return EXIT_PROBLEMS if report.failed_exit else EXIT_OK


def _health(app: App, args: argparse.Namespace) -> int:
    last = app.store.last_report() or {}
    worst = Severity[last["worst_severity"].upper()] if last.get("worst_severity") else None
    result = check_health(
        app.store.last_success(),
        worst,
        now=app.clock.now(),
        max_hours=app.config.max_hours_between_runs,
        environment_problems=environment_problems(app.config),
    )
    _print({"health": result.status.name.lower(), "message": result.message})
    return result.status.exit_code


def _printing(produce: Callable[[App, argparse.Namespace], Any]) -> Callable[[App, argparse.Namespace], int]:
    """A command that only prints what it produces."""

    def command(app: App, args: argparse.Namespace) -> int:
        _print(produce(app, args))
        return EXIT_OK

    return command


def _review(app: App, args: argparse.Namespace) -> int:
    try:
        if args.review_command == "list":
            _print([_candidate(c) for c in app.review.open()])
        elif args.review_command == "approve":
            app.review.approve(args.record_id, tier=Tier(args.tier), domain=args.domain, note=args.note)
            print(f"added {args.record_id} to {app.config.targets_csv}; commit it as a pull request")
        else:
            app.review.reject(args.record_id, note=args.note)
            print(f"rejected {args.record_id}")
    except (ReviewError, CatalogError) as e:
        print(f"bpk-connector: {e}", file=sys.stderr)
        return EXIT_USAGE
    return EXIT_OK


def _candidate(candidate: Candidate) -> dict[str, Any]:
    url = f"https://peraturan.bpk.go.id/Details/{candidate.record_id}"
    return {"record_id": candidate.record_id, "queued": candidate.found_on, "reason": candidate.reason, "url": url}


COMMANDS: dict[str, Callable[[App, argparse.Namespace], int]] = {
    "run": _run,
    "health": _health,
    "review": _review,
    "check": _printing(lambda app, args: asdict(app.check.run(_run_id()))),
    "fetch": _printing(
        lambda app, args: asdict(
            app.fetch.run(_run_id(), list(all_targets(app.store, app.catalog)), max_bytes=_budget(app, args.max_mb))
        )
    ),
    "extract": _printing(
        lambda app, args: asdict(
            app.extract.run(f"extract-{_run_id()}", retry_unsupported=args.retry_unsupported, again=args.again)
        )
    ),
    "export": _export,
    "reparse": _printing(
        lambda app, args: asdict(app.reparse.run(f"reparse-{_run_id()}")) | {"export": asdict(app.export.run())}
    ),
    "status": _printing(lambda app, args: {"seeds": len(app.catalog.seeds()), **app.store.status_counts()}),
    "events": _printing(lambda app, args: app.store.events_since(args.since)),
}


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        config = load_config(args.config)
    except ConfigError as e:
        print(f"bpk-connector: {e}", file=sys.stderr)
        return EXIT_USAGE
    app = build(config)
    try:
        return _dispatch(app, args)
    finally:
        app.close()
