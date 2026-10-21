"""What the use cases need from the outside world. Adapters implement these; use cases import only these.

Each port has a test fake, and the gateway is also where a faster second source would plug in
(roadmap Future F1).
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Protocol

from bpk_connector.application.dto import (
    BundleDocument,
    Candidate,
    CorpusDocument,
    DetailPage,
    Download,
    ExtractedText,
    SitemapEntry,
    SitemapFile,
    StoredFile,
    StoredText,
)
from bpk_connector.domain.file_roles import FileRole
from bpk_connector.domain.models import ChangeEvent, FileRef, Regulation, Target
from bpk_connector.domain.targeting import WatchRules


class GatewayError(Exception):
    """The source failed for this request."""


class Unavailable(GatewayError):
    """The source is down or rate-limiting us. Stop now; a later run retries."""


class Blocked(Unavailable):
    """The source refuses us (403, bot challenge). A person must look; never work around it."""


class NotFound(GatewayError):
    """The record or file is gone. Retrying won't help."""


class FileTooLarge(GatewayError):
    """The file exceeds the configured size cap; it is deferred, not downloaded."""


class BpkGateway(Protocol):
    def sitemap_index(self) -> list[SitemapFile]: ...

    def sitemap(self, file: SitemapFile) -> list[SitemapEntry]: ...

    def detail(self, record_id: str) -> DetailPage: ...

    def download(self, file: FileRef, held: StoredFile | None = None) -> Download:
        """Conditional on what we hold: ``Download.not_modified`` if BPK's copy is unchanged."""
        ...


class Repository(Protocol):
    """What we know about BPK records, our targets and their files."""

    def regulation(self, record_id: str) -> Regulation | None:
        """The last observation of a record, or None if never seen."""
        ...

    def save_observation(self, regulation: Regulation, *, html_sha256: str, fingerprint: str, at: datetime) -> None: ...

    def stored_pages(self) -> dict[str, str]:
        """Record ID → sha256 of the detail page we last stored for it."""
        ...

    def targets(self) -> dict[str, Target]:
        """Targets found by the pipeline (lineage, approved). Seeds come from the catalog."""
        ...

    def add_target(self, target: Target, *, at: datetime) -> None: ...

    def add_candidate(self, record_id: str, *, reason: str, at: datetime) -> bool:
        """Queue for review; False if already queued or decided."""
        ...

    def candidates(self, state: str = "open") -> list[Candidate]: ...

    def decide_candidate(self, record_id: str, *, state: str, note: str, at: datetime) -> None: ...

    def file_state(self, record_id: str, path: str) -> StoredFile | None: ...

    def save_file(self, record_id: str, file: FileRef, stored: StoredFile, *, at: datetime) -> None: ...

    def text_state(self, file_sha256: str) -> StoredText | None: ...

    def save_text(self, text: StoredText, *, at: datetime) -> None: ...


class EventLog(Protocol):
    def record(self, run_id: str, events: list[ChangeEvent], *, at: datetime) -> None: ...


class BlobStore(Protocol):
    """Content-addressed and write-once."""

    def put(self, data: bytes) -> str:
        """Returns the sha256."""
        ...

    def get(self, sha256: str) -> bytes: ...


class TargetCatalog(Protocol):
    """The curated target list and watch rules (config/targets.csv, config/watch.toml)."""

    def seeds(self) -> list[Target]: ...

    def watch_rules(self) -> WatchRules: ...

    def approve(self, target: Target, *, citation: str, rationale: str) -> None:
        """Add a reviewed candidate to the curated list (a row in targets.csv, for a pull request)."""
        ...


class Clock(Protocol):
    def now(self) -> datetime: ...


class CorpusWriter(Protocol):
    """Writes the knowledge-database hand-off (``data/corpus/``), replacing what was there."""

    def write(self, documents: list[CorpusDocument]) -> None: ...


class BundleWriter(Protocol):
    """Writes the platform hand-off: one contract v2 bundle, a full snapshot of what we hold."""

    def write(self, documents: list[BundleDocument]) -> None: ...


class RunHistory(Protocol):
    """What monitoring needs to know about earlier runs and the review queue."""

    def run_events(self, run_id: str) -> list[ChangeEvent]: ...

    def open_candidates(self) -> dict[str, date]:
        """Record ID → the day it was queued."""
        ...

    def first_seen(self) -> dict[str, date]:
        """Record ID → the day we first saw it on BPK."""
        ...

    def last_report(self) -> dict | None:
        """The previous run's report, or None before the first run."""
        ...

    def last_new_record_on(self) -> date | None:
        """When a new BPK record was last triaged; the baseline sync day if none yet; None before that."""
        ...


class PageParser(Protocol):
    """Detail-page bytes → Regulation. The use cases can't import the HTML parser (an adapter)."""

    def __call__(self, record_id: str, html: bytes) -> Regulation: ...


class SitemapState(Protocol):
    """What we last saw in BPK's sitemaps: one row per record ID, and each year file's lastmod."""

    def sitemap_lastmods(self) -> dict[str, date | None]: ...

    def sitemap_ids(self, year: str) -> set[str]: ...

    def save_sitemap(self, file: SitemapFile, entries: list[SitemapEntry], *, at: datetime) -> None: ...

    def last_full_sweep(self) -> date | None: ...

    def mark_full_sweep(self, *, at: datetime) -> None: ...


class NotExtractable(Exception):
    """The file isn't a document we can read text from (e.g. BPK's .zip annexes)."""


class TextExtractor(Protocol):
    def extract(self, data: bytes, role: FileRole = FileRole.MAIN) -> ExtractedText:
        """`role`: the file's to its regulation, which decides how carefully an engine reads it (MinerU reads the
        regulation with its vision model, an annex's tables with its small models)."""
        ...
