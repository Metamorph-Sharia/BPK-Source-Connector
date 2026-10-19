"""Alert rules: the facts of one run in, alerts out. Pure; reports and channels are elsewhere.

A source that breaks must fail loudly, not quietly ingest nothing (definition of done, item 5).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import KW_ONLY, dataclass, field
from datetime import date
from enum import IntEnum
from typing import Any

from bpk_connector.domain.models import ChangeEvent, Regulation

REVIEW_BACKLOG_DAYS = 14
NO_NEW_RECORDS_DAYS = 7  # BPK adds 40-60 records a day: a silent week means discovery is broken
FILL_RATE_DROP = 0.20  # a field filled 20 points less often than last run: the page layout probably changed
TARGET_CHANGES = ("relation_added", "relation_removed", "status_changed", "file_added", "file_removed")


class Severity(IntEnum):
    INFO = 1
    WARNING = 2
    ERROR = 3
    CRITICAL = 4

    def __str__(self) -> str:
        return self.name.lower()


@dataclass(frozen=True)
class Alert:
    code: str
    severity: Severity
    message: str
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RunFacts:
    status: str  # ok | paused | error
    today: date
    error: str | None = None
    missing_targets: list[str] = field(default_factory=list)
    failed_files: list[str] = field(default_factory=list)
    deferred_files: list[str] = field(default_factory=list)
    events: list[ChangeEvent] = field(default_factory=list)  # this run's
    open_candidates: Mapping[str, date] = field(default_factory=dict)  # record ID → queued on
    fill_rates: Mapping[str, float] = field(default_factory=dict)
    previous_fill_rates: Mapping[str, float] = field(default_factory=dict)
    one_sided_links: list[str] = field(default_factory=list)  # "<record> <kind> <record> (<citation>)"
    days_since_new_record: int | None = None  # None before monitoring has a baseline


def evaluate(facts: RunFacts) -> list[Alert]:
    return [alert for rule in RULES if (alert := rule(facts))]


def fill_rates(regulations: Iterable[Regulation]) -> dict[str, float]:
    """How often each BPK field, and each value we parse, is filled across the observed records."""
    regulations = list(regulations)
    if not regulations:
        return {}
    filled: dict[str, int] = {}
    for regulation in regulations:
        values = {**regulation.fields, **_parsed(regulation)}
        for name, value in values.items():
            filled[name] = filled.get(name, 0) + bool(value)
    return {name: round(count / len(regulations), 3) for name, count in sorted(filled.items())}


def _parsed(regulation: Regulation) -> dict[str, Any]:
    return {
        "title": regulation.title,
        "form": regulation.form,
        "number": regulation.number,
        "year": regulation.year,
        "status": regulation.status,
        "promulgated_on": regulation.promulgated_on,
        "relations": regulation.relations,
        "files": regulation.files,
    }


# --- Rules, in report order ----------------------------------------------------------------


def _source(facts: RunFacts) -> Alert | None:
    if facts.status == "error" and facts.error and facts.error.startswith("blocked"):
        return Alert("source_blocked", Severity.CRITICAL, f"BPK refused us; a person must look ({facts.error})")
    if facts.status == "error":
        return Alert("run_failed", Severity.ERROR, facts.error or "the run failed")
    if facts.status == "paused":
        return Alert("source_unavailable", Severity.WARNING, f"BPK unavailable; the next run resumes ({facts.error})")
    return None


@dataclass(frozen=True)
class _CountRule:
    """Alert when a run produced some items: a list on the facts, or events of some kinds."""

    code: str
    severity: Severity
    message: str  # "{n} …"
    _: KW_ONLY  # the rest by name: a positional slip once put a detail key into event_kinds
    fact: str | None = None  # a list attribute of RunFacts
    event_kinds: tuple[str, ...] = ()
    detail: str = "record_ids"

    def __call__(self, facts: RunFacts) -> Alert | None:
        items = getattr(facts, self.fact) if self.fact else _record_ids(facts.events, self.event_kinds)
        return (
            Alert(self.code, self.severity, self.message.format(n=len(items)), {self.detail: items}) if items else None
        )


def _review_backlog(facts: RunFacts) -> Alert | None:
    stale = [rid for rid, queued in facts.open_candidates.items() if (facts.today - queued).days > REVIEW_BACKLOG_DAYS]
    if stale:
        message = f"{len(stale)} candidate(s) waiting more than {REVIEW_BACKLOG_DAYS} days for review"
        return Alert("review_backlog", Severity.WARNING, message, {"record_ids": stale})
    return None


def _no_new_records(facts: RunFacts) -> Alert | None:
    days = facts.days_since_new_record
    if days is not None and days > NO_NEW_RECORDS_DAYS:
        return Alert("no_new_records", Severity.WARNING, f"no new BPK record for {days} days: is discovery broken?")
    return None


def _fill_drop(facts: RunFacts) -> Alert | None:
    dropped = {
        name: [before, facts.fill_rates.get(name, 0.0)]
        for name, before in facts.previous_fill_rates.items()
        if before - facts.fill_rates.get(name, 0.0) >= FILL_RATE_DROP
    }
    if dropped:
        return Alert(
            "parse_fill_drop",
            Severity.WARNING,
            "fields parsed much less often: BPK's layout may have changed",
            {"fields": dropped},
        )
    return None


def _record_ids(events: list[ChangeEvent], kinds: tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(e.record_id for e in events if e.kind in kinds))


RULES = (
    _source,
    _CountRule("target_missing", Severity.ERROR, "{n} target(s) gone from BPK", fact="missing_targets"),
    _CountRule("file_missing", Severity.ERROR, "{n} file(s) gone from BPK", fact="failed_files", detail="paths"),
    _CountRule(
        "file_deferred", Severity.WARNING, "{n} file(s) wait for a later run", fact="deferred_files", detail="paths"
    ),
    _CountRule(
        "target_changed", Severity.INFO, "{n} target(s) amended, revoked or re-filed", event_kinds=TARGET_CHANGES
    ),
    _CountRule("lineage_added", Severity.INFO, "{n} target(s) added by lineage", event_kinds=("target_added",)),
    _CountRule(
        "candidates_queued", Severity.INFO, "{n} record(s) queued for review", event_kinds=("candidate_queued",)
    ),
    _CountRule("data_anomaly", Severity.WARNING, "{n} record(s) with impossible data", event_kinds=("data_anomaly",)),
    _CountRule(
        "text_incomplete", Severity.WARNING, "{n} target(s) with pages needing OCR", event_kinds=("text_needs_ocr",)
    ),
    _CountRule(
        "text_damaged",
        Severity.WARNING,
        "{n} target(s) whose text has OCR-damaged article headings",
        event_kinds=("text_damaged",),
    ),
    _CountRule(
        "link_inconsistency",
        Severity.INFO,
        "{n} link(s) BPK shows on one side only",
        fact="one_sided_links",
        detail="links",
    ),
    _review_backlog,
    _no_new_records,
    _fill_drop,
)
