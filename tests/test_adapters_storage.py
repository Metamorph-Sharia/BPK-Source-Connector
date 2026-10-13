"""SQLite repository, event log and file blob store: what we save comes back, and survives a reopen."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from fakes.memory import NOW

from bpk_connector.adapters.bpk.detail_parser import parse_detail
from bpk_connector.adapters.storage.blobs import FileBlobStore
from bpk_connector.adapters.storage.sqlite import SqliteStore
from bpk_connector.application.dto import Candidate, SitemapEntry, SitemapFile, StoredFile, StoredText
from bpk_connector.domain.models import ChangeEvent, FileRef, Target, TargetOrigin, Tier

FIXTURE = Path(__file__).parent / "fixtures" / "bpk" / "details" / "240203.html"


def test_a_parsed_regulation_round_trips_unchanged(tmp_path: Path) -> None:
    regulation = parse_detail("240203", FIXTURE.read_bytes())
    store = SqliteStore(tmp_path / "db.sqlite")

    store.save_observation(regulation, html_sha256="abc", fingerprint="f1", at=NOW)

    assert SqliteStore(tmp_path / "db.sqlite").regulation("240203") == regulation
    assert store.stored_pages() == {"240203": "abc"}
    assert store.regulation("1") is None


def test_targets_and_candidates_persist_and_candidates_are_queued_once(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    lineage = Target("350166", Tier.P1, TargetOrigin.LINEAGE, domain="A", via="240203")
    history = Target("46102", Tier.P3, TargetOrigin.LINEAGE, via="39965", historical=True)

    store.add_target(lineage, at=NOW)
    store.add_target(history, at=NOW)
    assert store.add_candidate("999", reason="omnibus link from 240203", at=NOW) is True
    assert store.add_candidate("999", reason="again", at=NOW) is False

    assert SqliteStore(tmp_path / "db.sqlite").targets() == {"350166": lineage, "46102": history}


def test_file_state_is_kept_per_record_and_path(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    file = FileRef("295189", "UU.pdf", "/Download/295189/UU.pdf")
    stored = StoredFile("sha", '"v1"', 10, "application/pdf", "https://peraturan.bpk.go.id/Download/295189/UU.pdf")

    store.save_file("240203", file, stored, at=NOW)
    store.save_file("240203", file, StoredFile("sha", '"v2"', 10, "application/pdf", stored.url), at=NOW)

    assert store.file_state("240203", file.path).etag == '"v2"'
    assert store.file_state("240203", "/other") is None


def test_events_are_appended_with_their_run(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")

    store.record("run-1", [ChangeEvent("relation_added", "240203", {"record_id": "350166"})], at=NOW)

    assert store.events_since(date(2026, 1, 1)) == [
        {
            "run_id": "run-1",
            "at": NOW.isoformat(),
            "record_id": "240203",
            "kind": "relation_added",
            "detail": {"record_id": "350166"},
        }
    ]


def test_blobs_are_content_addressed_and_written_once(tmp_path: Path) -> None:
    blobs = FileBlobStore(tmp_path / "raw")

    sha = blobs.put(b"%PDF")

    assert blobs.put(b"%PDF") == sha
    assert (tmp_path / "raw" / sha[:2] / sha).read_bytes() == b"%PDF"
    assert blobs.get(sha) == b"%PDF"


def test_a_schema_v1_database_is_migrated_in_place(tmp_path: Path) -> None:
    import sqlite3

    path = tmp_path / "db.sqlite"
    old = sqlite3.connect(path)
    old.executescript(
        "CREATE TABLE files (record_id TEXT, path TEXT, file_id TEXT, name TEXT, category TEXT, sha256 TEXT,"
        " etag TEXT, size INTEGER, media_type TEXT, url TEXT, fetched_at TEXT, PRIMARY KEY (record_id, path));"
        "INSERT INTO files VALUES ('1', '/d', 'f', 'n', 'Peraturan', 'sha', '\"e\"', 1, 'application/pdf', 'u', 'at');"
        "PRAGMA user_version = 1;"
    )
    old.close()

    store = SqliteStore(path)

    assert store.file_state("1", "/d") == StoredFile("sha", '"e"', 1, "application/pdf", "u", None)
    file = FileRef("f2", "n2", "/d2")
    store.save_file(
        "1", file, StoredFile("sha2", None, 2, "application/pdf", "u2", "Mon, 12 Oct 2026 05:54:20 GMT"), at=NOW
    )
    assert store.file_state("1", "/d2").last_modified == "Mon, 12 Oct 2026 05:54:20 GMT"


def test_run_history_for_monitoring(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    store.save_observation(parse_detail("240203", FIXTURE.read_bytes()), html_sha256="a", fingerprint="f", at=NOW)
    store.add_candidate("999", reason="link from 240203", at=NOW)
    store.record("run-1", [ChangeEvent("target_added", "350166", {"via": "240203"})], at=NOW)
    store.save_run(
        "run-1", started_at=NOW.isoformat(), finished_at=None, status="ok", report={"fill_rates": {"Judul": 1.0}}
    )

    assert store.run_events("run-1") == [ChangeEvent("target_added", "350166", {"via": "240203"})]
    assert store.run_events("run-2") == []
    assert store.open_candidates() == {"999": NOW.date()}
    assert store.first_seen() == {"240203": NOW.date()}
    assert store.last_report() == {"fill_rates": {"Judul": 1.0}}


def test_candidates_are_listed_by_state_and_decided_once(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    store.add_candidate("999", reason="link from 240203", at=NOW)
    store.add_candidate("998", reason="new on BPK", at=NOW)

    store.decide_candidate("999", state="rejected", note="other sector", at=NOW)

    assert [c.record_id for c in store.candidates("open")] == ["998"]
    assert store.candidates("rejected") == [Candidate("999", "link from 240203", "rejected", NOW.date())]
    assert store.open_candidates() == {"998": NOW.date()}
    assert store.add_candidate("999", reason="again", at=NOW) is False  # a decision sticks


def test_sitemap_state_round_trips(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    file = SitemapFile("2026", "https://peraturan.bpk.go.id/sitemap-peraturan-2026.xml", date(2026, 10, 13))

    store.save_sitemap(file, [SitemapEntry("1", "a", date(2026, 1, 5)), SitemapEntry("2", "b", None)], at=NOW)
    store.save_sitemap(file, [SitemapEntry("2", "b", None)], at=NOW)  # 1 removed
    store.mark_full_sweep(at=NOW)

    reopened = SqliteStore(tmp_path / "db.sqlite")
    assert reopened.sitemap_lastmods() == {"2026": date(2026, 10, 13)}
    assert reopened.sitemap_ids("2026") == {"2"}
    assert reopened.last_full_sweep() == NOW.date()


def test_the_last_new_record_falls_back_to_the_baseline_sweep(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    assert store.last_new_record_on() is None

    store.mark_full_sweep(at=NOW)
    assert store.last_new_record_on() == NOW.date()

    later = NOW.replace(day=20)
    store.record("run-2", [ChangeEvent("new_record_triaged", "400001", {"action": "ignore"})], at=later)
    assert store.last_new_record_on() == later.date()


def test_texts_are_kept_per_file_hash(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    text = StoredText("pdfsha", "textsha", "text_layer", pages=23, pages_without_text=1, chars=9000)

    store.save_text(text, at=NOW)

    assert SqliteStore(tmp_path / "db.sqlite").text_state("pdfsha") == text
    assert store.text_state("other") is None
