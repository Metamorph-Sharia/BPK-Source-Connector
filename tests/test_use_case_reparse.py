"""Reparse: re-apply the parser to stored pages, with no network, so parser fixes repair history."""

from __future__ import annotations

from pathlib import Path

from fakes.memory import NOW, FixedClock, MemoryBlobs, MemoryEventLog, MemoryRepository

from bpk_connector.adapters.bpk.detail_parser import parse_detail
from bpk_connector.application.use_cases.reparse import Reparse
from bpk_connector.domain.models import Regulation

PAGE = (Path(__file__).parent / "fixtures/bpk/details/164278.html").read_bytes()


def stored(regulation: Regulation):
    repository, blobs = MemoryRepository(), MemoryBlobs()
    repository.save_observation(regulation, html_sha256=blobs.put(PAGE), fingerprint="old", at=NOW)
    return repository, blobs


def test_a_parser_fix_updates_stored_records_and_reports_what_changed() -> None:
    broken = Regulation("164278", "", "PMK", "130/PMK.010/2012", "2012")  # e.g. an old parser lost the title
    repository, blobs = stored(broken)
    events = MemoryEventLog()

    summary = Reparse(repository, events, blobs, parse_detail, FixedClock()).run("reparse-1")

    assert summary.reparsed == 1 and summary.changed == 1
    assert repository.regulation("164278").title.startswith("Peraturan Menteri Keuangan")
    assert "metadata_changed" in events.kinds()


def test_reparsing_with_the_same_parser_changes_nothing() -> None:
    repository, blobs = stored(parse_detail("164278", PAGE))
    events = MemoryEventLog()

    summary = Reparse(repository, events, blobs, parse_detail, FixedClock()).run("reparse-1")

    assert summary.changed == 0 and events.events == []
