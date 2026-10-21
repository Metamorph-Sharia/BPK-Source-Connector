"""SQLite: our records, targets, candidates, files and events. Implements ``Repository`` and ``EventLog``.

A regulation is stored as JSON exactly as parsed (BPK's fields unchanged), plus a few columns
for querying. Raw detail pages and files live in the blob store; here we keep their hashes.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path
from typing import Any

from bpk_connector.application.dto import (
    Candidate,
    Extraction,
    Method,
    SitemapEntry,
    SitemapFile,
    StoredFile,
    StoredText,
)
from bpk_connector.domain.models import ChangeEvent, FileRef, Regulation, Relation, Target, TargetOrigin, Tier
from bpk_connector.domain.text_quality import TextQuality

SCHEMA_VERSION = 6  # v2: files.last_modified · v3: candidate decisions, sitemap state · v4: texts · v5: text quality
# · v6: texts.extraction
SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    record_id TEXT PRIMARY KEY,
    citation TEXT NOT NULL,
    status TEXT,
    promulgated_on TEXT,
    regulation_json TEXT NOT NULL,
    html_sha256 TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    first_seen_at TEXT NOT NULL,
    last_checked_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS targets (
    record_id TEXT PRIMARY KEY,
    tier TEXT NOT NULL,
    origin TEXT NOT NULL,
    domain TEXT NOT NULL DEFAULT '',
    via TEXT,
    note TEXT NOT NULL DEFAULT '',
    historical INTEGER NOT NULL DEFAULT 0,
    added_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
    record_id TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open',
    found_at TEXT NOT NULL,
    decided_at TEXT,
    note TEXT
);
CREATE TABLE IF NOT EXISTS texts (
    file_sha256 TEXT PRIMARY KEY,
    text_sha256 TEXT,
    method TEXT NOT NULL,
    pages INTEGER NOT NULL,
    pages_without_text INTEGER NOT NULL,
    chars INTEGER NOT NULL,
    note TEXT NOT NULL,
    extracted_at TEXT NOT NULL,
    clean_headings INTEGER,
    damaged_headings INTEGER,
    extraction TEXT  -- JSON: how an engine read it (contract 2.1 Extraction); NULL: read by the connector
);
CREATE TABLE IF NOT EXISTS sitemap_files (
    year TEXT PRIMARY KEY,
    lastmod TEXT,
    url_count INTEGER NOT NULL,
    fetched_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sitemap_records (
    record_id TEXT PRIMARY KEY,
    year TEXT NOT NULL,
    lastmod TEXT
);
CREATE INDEX IF NOT EXISTS sitemap_records_year ON sitemap_records(year);
CREATE TABLE IF NOT EXISTS sweeps (
    at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS files (
    record_id TEXT NOT NULL,
    path TEXT NOT NULL,
    file_id TEXT NOT NULL,
    name TEXT NOT NULL,
    category TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    etag TEXT,
    size INTEGER NOT NULL,
    media_type TEXT NOT NULL,
    url TEXT NOT NULL,
    last_modified TEXT,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (record_id, path)
);
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    at TEXT NOT NULL,
    record_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    detail_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_at ON events(at);
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    status TEXT,
    report_json TEXT
);
"""


class SqliteStore:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self._migrate()
        self.db.executescript(SCHEMA)
        self.db.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")

    def _migrate(self) -> None:
        """Bring an older database up to date in place, by the columns it actually has."""
        added = (
            ("files", "last_modified", "TEXT"),
            ("candidates", "decided_at", "TEXT"),
            ("candidates", "note", "TEXT"),
            ("texts", "clean_headings", "INTEGER"),
            ("texts", "damaged_headings", "INTEGER"),
            ("texts", "extraction", "TEXT"),
        )
        for table, column, kind in added:
            columns = {r[1] for r in self.db.execute(f"PRAGMA table_info({table})")}
            if columns and column not in columns:
                self.db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")

    # --- Repository -------------------------------------------------------------------------

    def regulation(self, record_id: str) -> Regulation | None:
        row = self.db.execute("SELECT regulation_json FROM records WHERE record_id = ?", (record_id,)).fetchone()
        return _regulation_from_json(row["regulation_json"]) if row else None

    def save_observation(self, regulation: Regulation, *, html_sha256: str, fingerprint: str, at: datetime) -> None:
        with self.db:
            self.db.execute(
                """INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(record_id) DO UPDATE SET citation = excluded.citation, status = excluded.status,
                     promulgated_on = excluded.promulgated_on, regulation_json = excluded.regulation_json,
                     html_sha256 = excluded.html_sha256, fingerprint = excluded.fingerprint,
                     last_checked_at = excluded.last_checked_at""",
                (
                    regulation.record_id, regulation.citation, regulation.status, _iso(regulation.promulgated_on),
                    _regulation_to_json(regulation), html_sha256, fingerprint, at.isoformat(), at.isoformat(),
                ),
            )  # fmt: skip

    def stored_pages(self) -> dict[str, str]:
        return {r["record_id"]: r["html_sha256"] for r in self.db.execute("SELECT record_id, html_sha256 FROM records")}

    def targets(self) -> dict[str, Target]:
        rows = self.db.execute("SELECT * FROM targets ORDER BY added_at, record_id").fetchall()
        return {
            r["record_id"]: Target(
                r["record_id"],
                Tier(r["tier"]),
                TargetOrigin(r["origin"]),
                r["domain"],
                r["via"],
                r["note"],
                bool(r["historical"]),
            )
            for r in rows
        }

    def add_target(self, target: Target, *, at: datetime) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR IGNORE INTO targets VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    target.record_id,
                    target.tier,
                    target.origin,
                    target.domain,
                    target.via,
                    target.note,
                    int(target.historical),
                    at.isoformat(),
                ),
            )

    def add_candidate(self, record_id: str, *, reason: str, at: datetime) -> bool:
        with self.db:
            cursor = self.db.execute(
                "INSERT OR IGNORE INTO candidates (record_id, reason, found_at) VALUES (?, ?, ?)",
                (record_id, reason, at.isoformat()),
            )
        return cursor.rowcount == 1

    def candidates(self, state: str = "open") -> list[Candidate]:
        rows = self.db.execute("SELECT * FROM candidates WHERE state = ? ORDER BY found_at, record_id", (state,))
        return [Candidate(r["record_id"], r["reason"], r["state"], _day(r["found_at"])) for r in rows]

    def decide_candidate(self, record_id: str, *, state: str, note: str, at: datetime) -> None:
        with self.db:
            self.db.execute(
                "UPDATE candidates SET state = ?, note = ?, decided_at = ? WHERE record_id = ?",
                (state, note, at.isoformat(), record_id),
            )

    def text_state(self, file_sha256: str) -> StoredText | None:
        row = self.db.execute("SELECT * FROM texts WHERE file_sha256 = ?", (file_sha256,)).fetchone()
        if row is None:
            return None
        quality = (
            None if row["damaged_headings"] is None else TextQuality(row["clean_headings"], row["damaged_headings"])
        )
        extraction = Extraction(**json.loads(row["extraction"])) if row["extraction"] else None
        return StoredText(
            row["file_sha256"], row["text_sha256"], Method(row["method"]), row["pages"], row["pages_without_text"],
            row["chars"], row["note"], quality, extraction,
        )  # fmt: skip

    def save_text(self, text: StoredText, *, at: datetime) -> None:
        quality = text.quality
        with self.db:
            self.db.execute(
                """INSERT OR REPLACE INTO texts (file_sha256, text_sha256, method, pages, pages_without_text, chars,
                   note, extracted_at, clean_headings, damaged_headings, extraction)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    text.file_sha256, text.text_sha256, text.method, text.pages, text.pages_without_text,
                    text.chars, text.note, at.isoformat(),
                    quality.clean_headings if quality else None, quality.damaged_headings if quality else None,
                    json.dumps(asdict(text.extraction)) if text.extraction else None,
                ),
            )  # fmt: skip

    def file_state(self, record_id: str, path: str) -> StoredFile | None:
        row = self.db.execute("SELECT * FROM files WHERE record_id = ? AND path = ?", (record_id, path)).fetchone()
        if row is None:
            return None
        return StoredFile(
            row["sha256"], row["etag"], row["size"], row["media_type"], row["url"], row["last_modified"],
            fetched_at=_datetime_or_none(row["fetched_at"]),
        )  # fmt: skip

    def save_file(self, record_id: str, file: FileRef, stored: StoredFile, *, at: datetime) -> None:
        with self.db:
            self.db.execute(
                """INSERT OR REPLACE INTO files (record_id, path, file_id, name, category, sha256,
                     etag, size, media_type, url, last_modified, fetched_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",  # named: migrated tables order columns differently
                (
                    record_id, file.path, file.file_id, file.name, file.category, stored.sha256,
                    stored.etag, stored.size, stored.media_type, stored.url, stored.last_modified, at.isoformat(),
                ),
            )  # fmt: skip

    # --- EventLog ----------------------------------------------------------------------------

    def record(self, run_id: str, events: list[ChangeEvent], *, at: datetime) -> None:
        with self.db:
            self.db.executemany(
                "INSERT INTO events (run_id, at, record_id, kind, detail_json) VALUES (?, ?, ?, ?, ?)",
                [
                    (run_id, at.isoformat(), e.record_id, e.kind, json.dumps(dict(e.detail), ensure_ascii=False))
                    for e in events
                ],
            )

    def events_since(self, since: date) -> list[dict[str, Any]]:
        rows = self.db.execute("SELECT * FROM events WHERE at >= ? ORDER BY id", (since.isoformat(),)).fetchall()
        return [
            {
                "run_id": r["run_id"],
                "at": r["at"],
                "record_id": r["record_id"],
                "kind": r["kind"],
                "detail": json.loads(r["detail_json"]),
            }
            for r in rows
        ]

    # --- SitemapState --------------------------------------------------------------------------

    def sitemap_lastmods(self) -> dict[str, date | None]:
        rows = self.db.execute("SELECT year, lastmod FROM sitemap_files")
        return {r["year"]: date.fromisoformat(r["lastmod"]) if r["lastmod"] else None for r in rows}

    def sitemap_ids(self, year: str) -> set[str]:
        return {r[0] for r in self.db.execute("SELECT record_id FROM sitemap_records WHERE year = ?", (year,))}

    def save_sitemap(self, file: SitemapFile, entries: list[SitemapEntry], *, at: datetime) -> None:
        with self.db:
            self.db.execute("DELETE FROM sitemap_records WHERE year = ?", (file.year,))
            self.db.executemany(
                "INSERT OR REPLACE INTO sitemap_records VALUES (?, ?, ?)",
                [(e.record_id, file.year, _iso(e.lastmod)) for e in entries],
            )
            self.db.execute(
                "INSERT OR REPLACE INTO sitemap_files VALUES (?, ?, ?, ?)",
                (file.year, _iso(file.lastmod), len(entries), at.isoformat()),
            )

    def last_full_sweep(self) -> date | None:
        row = self.db.execute("SELECT MAX(at) FROM sweeps").fetchone()
        return _day(row[0]) if row[0] else None

    def mark_full_sweep(self, *, at: datetime) -> None:
        with self.db:
            self.db.execute("INSERT INTO sweeps VALUES (?)", (at.isoformat(),))

    # --- RunHistory ---------------------------------------------------------------------------

    def run_events(self, run_id: str) -> list[ChangeEvent]:
        rows = self.db.execute("SELECT * FROM events WHERE run_id = ? ORDER BY id", (run_id,)).fetchall()
        return [ChangeEvent(r["kind"], r["record_id"], json.loads(r["detail_json"])) for r in rows]

    def open_candidates(self) -> dict[str, date]:
        rows = self.db.execute("SELECT record_id, found_at FROM candidates WHERE state = 'open'").fetchall()
        return {r["record_id"]: _day(r["found_at"]) for r in rows}

    def first_seen(self) -> dict[str, date]:
        rows = self.db.execute("SELECT record_id, first_seen_at FROM records").fetchall()
        return {r["record_id"]: _day(r["first_seen_at"]) for r in rows}

    def last_new_record_on(self) -> date | None:
        row = self.db.execute(
            "SELECT COALESCE((SELECT MAX(at) FROM events WHERE kind = 'new_record_triaged'),"
            " (SELECT MIN(at) FROM sweeps))"
        ).fetchone()
        return _day(row[0]) if row[0] else None

    def last_report(self) -> dict | None:
        row = self.db.execute("SELECT report_json FROM runs ORDER BY started_at DESC LIMIT 1").fetchone()
        return json.loads(row["report_json"]) if row and row["report_json"] else None

    # --- Runs and status (for the CLI and reports) -------------------------------------------

    def last_success(self) -> datetime | None:
        row = self.db.execute(
            "SELECT finished_at FROM runs WHERE status = 'ok' AND finished_at IS NOT NULL"
            " ORDER BY finished_at DESC LIMIT 1"
        ).fetchone()
        return datetime.fromisoformat(row["finished_at"]) if row else None

    def save_run(self, run_id: str, *, started_at: str, finished_at: str | None, status: str, report: dict) -> None:
        with self.db:
            self.db.execute(
                "INSERT OR REPLACE INTO runs VALUES (?, ?, ?, ?, ?)",
                (run_id, started_at, finished_at, status, json.dumps(report, ensure_ascii=False, default=str)),
            )

    def status_counts(self) -> dict[str, Any]:
        def count(sql: str) -> dict[str, int]:
            return {str(k): v for k, v in self.db.execute(sql).fetchall()}

        return {
            "records_observed": self.db.execute("SELECT COUNT(*) FROM records").fetchone()[0],
            "records_by_status": count("SELECT status, COUNT(*) FROM records GROUP BY status"),
            "found_targets_by_origin": count("SELECT origin, COUNT(*) FROM targets GROUP BY origin"),
            "candidates_by_state": count("SELECT state, COUNT(*) FROM candidates GROUP BY state"),
            "files_by_category": count("SELECT category, COUNT(*) FROM files GROUP BY category"),
            "file_bytes": self.db.execute("SELECT COALESCE(SUM(size), 0) FROM files").fetchone()[0],
            "last_run": dict(row)
            if (
                row := self.db.execute(
                    "SELECT run_id, started_at, finished_at, status FROM runs ORDER BY started_at DESC LIMIT 1"
                ).fetchone()
            )
            else None,
        }

    def close(self) -> None:
        self.db.close()


def _day(timestamp: str) -> date:
    return datetime.fromisoformat(timestamp).date()


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _regulation_to_json(regulation: Regulation) -> str:
    data = asdict(regulation)
    for key in ("enacted_on", "promulgated_on", "effective_on"):
        data[key] = _iso(getattr(regulation, key))
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


def _regulation_from_json(text: str) -> Regulation:
    data = json.loads(text)
    for key in ("enacted_on", "promulgated_on", "effective_on"):
        data[key] = date.fromisoformat(data[key]) if data[key] else None
    data["subjects"] = tuple(data["subjects"])
    data["relations"] = tuple(Relation(**r) for r in data["relations"])
    data["files"] = tuple(FileRef(**f) for f in data["files"])
    return Regulation(**data)


def _datetime_or_none(text: str | None) -> datetime | None:
    """Rows written before fetch times were ISO timestamps carry something else; treat it as unknown."""
    try:
        return datetime.fromisoformat(text) if text else None
    except ValueError:
        return None
