"""In-memory implementations of every port, so use cases are tested without network or disk."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

from bpk_connector.application.dto import (
    Candidate,
    DetailPage,
    Download,
    SitemapEntry,
    SitemapFile,
    StoredFile,
    StoredText,
)
from bpk_connector.application.ports import NotFound
from bpk_connector.domain.models import ChangeEvent, FileRef, Regulation, Target
from bpk_connector.domain.targeting import WatchRules

NOW = datetime(2026, 10, 13, 6, 0, tzinfo=UTC)


class FakeGateway:
    """BPK as a dict: record ID → Regulation; file path → bytes. Missing → NotFound."""

    def __init__(self, pages: dict[str, Regulation] | None = None, files: dict[str, bytes] | None = None) -> None:
        self.pages = dict(pages or {})
        self.files = dict(files or {})
        self.sitemaps: dict[str, list[SitemapEntry]] = {}
        self.sitemap_lastmods: dict[str, date] = {}
        self.calls: list[str] = []
        self.failure: Exception | None = None  # raised on every call when set

    def sitemap_index(self) -> list[SitemapFile]:
        self._call("index")
        return [
            SitemapFile(year, f"https://bpk.test/sitemap-peraturan-{year}.xml", self.sitemap_lastmods.get(year))
            for year in self.sitemaps
        ]

    def sitemap(self, file: SitemapFile) -> list[SitemapEntry]:
        self._call(f"sitemap {file.year}")
        return self.sitemaps[file.year]

    def detail(self, record_id: str) -> DetailPage:
        self._call(f"detail {record_id}")
        if record_id not in self.pages:
            raise NotFound(record_id)
        return DetailPage(f"<html>{record_id}</html>".encode(), self.pages[record_id])

    def download(self, file: FileRef, held: StoredFile | None = None) -> Download:
        self._call(f"download {file.path}")
        if file.path not in self.files:
            raise NotFound(file.path)
        content = self.files[file.path]
        current = '"' + hashlib.sha256(content).hexdigest()[:8] + '"'
        if held and held.etag == current:
            return Download(None, held.etag, "", f"https://bpk.test{file.path}")
        return Download(content, current, "application/pdf", f"https://bpk.test{file.path}")

    def _call(self, what: str) -> None:
        self.calls.append(what)
        if self.failure:
            raise self.failure


@dataclass
class MemoryRepository:
    observations: dict[str, Regulation] = field(default_factory=dict)
    found_targets: dict[str, Target] = field(default_factory=dict)
    queued: dict[str, str] = field(default_factory=dict)  # record ID → reason
    stored_files: dict[tuple[str, str], StoredFile] = field(default_factory=dict)
    seen_on: dict[str, date] = field(default_factory=dict)
    queued_on: dict[str, date] = field(default_factory=dict)
    reports: list[dict] = field(default_factory=list)
    pages: dict[str, str] = field(default_factory=dict)
    decisions: dict[str, str] = field(default_factory=dict)
    texts: dict[str, StoredText] = field(default_factory=dict)

    def regulation(self, record_id: str) -> Regulation | None:
        return self.observations.get(record_id)

    def save_observation(self, regulation: Regulation, *, html_sha256: str, fingerprint: str, at: datetime) -> None:
        self.observations[regulation.record_id] = regulation
        self.pages[regulation.record_id] = html_sha256
        self.seen_on.setdefault(regulation.record_id, at.date())

    def stored_pages(self) -> dict[str, str]:
        return dict(self.pages)

    def targets(self) -> dict[str, Target]:
        return dict(self.found_targets)

    def add_target(self, target: Target, *, at: datetime) -> None:
        self.found_targets[target.record_id] = target

    def add_candidate(self, record_id: str, *, reason: str, at: datetime) -> bool:
        if record_id in self.queued:
            return False
        self.queued[record_id] = reason
        self.queued_on[record_id] = at.date()
        return True

    def candidates(self, state: str = "open") -> list[Candidate]:
        decided = self.decisions
        return [
            Candidate(rid, reason, decided.get(rid, "open"), self.queued_on.get(rid, NOW.date()))
            for rid, reason in self.queued.items()
            if decided.get(rid, "open") == state
        ]

    def decide_candidate(self, record_id: str, *, state: str, note: str, at: datetime) -> None:
        self.decisions[record_id] = state

    def text_state(self, file_sha256: str) -> StoredText | None:
        return self.texts.get(file_sha256)

    def save_text(self, text: StoredText, *, at: datetime) -> None:
        self.texts[text.file_sha256] = text

    def file_state(self, record_id: str, path: str) -> StoredFile | None:
        return self.stored_files.get((record_id, path))

    def save_file(self, record_id: str, file: FileRef, stored: StoredFile, *, at: datetime) -> None:
        self.stored_files[(record_id, file.path)] = stored

    # RunHistory (the event log part lives in MemoryEventLog; tests wire them together)
    def open_candidates(self) -> dict[str, date]:
        return dict(self.queued_on)

    def first_seen(self) -> dict[str, date]:
        return dict(self.seen_on)

    def last_report(self) -> dict | None:
        return self.reports[-1] if self.reports else None


@dataclass
class MemoryEventLog:
    events: list[ChangeEvent] = field(default_factory=list)
    by_run: dict[str, list[ChangeEvent]] = field(default_factory=dict)

    def record(self, run_id: str, events: list[ChangeEvent], *, at: datetime) -> None:
        self.events.extend(events)
        self.by_run.setdefault(run_id, []).extend(events)

    def run_events(self, run_id: str) -> list[ChangeEvent]:
        return list(self.by_run.get(run_id, []))

    def kinds(self) -> list[str]:
        return [e.kind for e in self.events]


@dataclass
class MemoryBlobs:
    blobs: dict[str, bytes] = field(default_factory=dict)

    def put(self, data: bytes) -> str:
        sha = hashlib.sha256(data).hexdigest()
        self.blobs[sha] = data
        return sha

    def get(self, sha256: str) -> bytes:
        return self.blobs[sha256]


@dataclass
class MemoryCatalog:
    seed_list: list[Target]
    rules: WatchRules = field(default_factory=lambda: WatchRules(forms=frozenset({"UU", "PP"}), max_auto_links=3))
    approved: list[tuple[Target, str]] = field(default_factory=list)

    def seeds(self) -> list[Target]:
        return list(self.seed_list)

    def watch_rules(self) -> WatchRules:
        return self.rules

    def approve(self, target: Target, *, citation: str, rationale: str) -> None:
        self.approved.append((target, citation))
        self.seed_list.append(target)


class FixedClock:
    def now(self) -> datetime:
        return NOW


class MemoryHistory:
    """RunHistory over the in-memory repository and event log, as SQLite provides it from one store."""

    def __init__(self, repository: MemoryRepository, events: MemoryEventLog) -> None:
        self.repository = repository
        self.events = events

    def run_events(self, run_id: str) -> list[ChangeEvent]:
        return self.events.run_events(run_id)

    def open_candidates(self) -> dict[str, date]:
        return self.repository.open_candidates()

    def first_seen(self) -> dict[str, date]:
        return self.repository.first_seen()

    def last_report(self) -> dict | None:
        return self.repository.last_report()

    def last_new_record_on(self) -> date | None:
        return None


@dataclass
class MemorySitemapState:
    lastmods: dict[str, date | None] = field(default_factory=dict)
    ids: dict[str, set[str]] = field(default_factory=dict)
    full_sweep: date | None = None

    def sitemap_lastmods(self) -> dict[str, date | None]:
        return dict(self.lastmods)

    def sitemap_ids(self, year: str) -> set[str]:
        return set(self.ids.get(year, set()))

    def save_sitemap(self, file: SitemapFile, entries: list[SitemapEntry], *, at: datetime) -> None:
        self.lastmods[file.year] = file.lastmod
        self.ids[file.year] = {e.record_id for e in entries}

    def last_full_sweep(self) -> date | None:
        return self.full_sweep

    def mark_full_sweep(self, *, at: datetime) -> None:
        self.full_sweep = at.date()
