"""SyncSitemaps: find records BPK published since the last run, from its daily-updated sitemaps."""

from __future__ import annotations

from datetime import date

import pytest
from fakes.memory import FakeGateway, FixedClock, MemorySitemapState

from bpk_connector.application.dto import SitemapEntry
from bpk_connector.application.ports import Unavailable
from bpk_connector.application.use_cases.sync_sitemaps import SyncSitemaps


def entries(*ids: str) -> list[SitemapEntry]:
    return [SitemapEntry(i, f"slug-{i}", date(2026, 10, 1)) for i in ids]


def bpk(**years: list[SitemapEntry]) -> FakeGateway:
    gateway = FakeGateway()
    gateway.sitemaps = dict(years)
    gateway.sitemap_lastmods = {year: date(2026, 10, 12) for year in years}
    return gateway


def test_the_first_sync_records_a_baseline_and_reports_nothing_new() -> None:
    state = MemorySitemapState()

    result = SyncSitemaps(bpk(**{"2026": entries("1", "2"), "2025": entries("3")}), state, FixedClock()).run()

    assert result.baseline and result.new_ids == []
    assert state.sitemap_ids("2026") == {"1", "2"}


def test_ids_that_appear_after_the_baseline_are_new() -> None:
    state = MemorySitemapState()
    gateway = bpk(**{"2026": entries("1")})
    SyncSitemaps(gateway, state, FixedClock()).run()
    gateway.sitemaps["2026"] = entries("1", "2")
    gateway.sitemap_lastmods["2026"] = date(2026, 10, 13)

    result = SyncSitemaps(gateway, state, FixedClock()).run()

    assert result.new_ids == ["2"] and not result.baseline


def test_year_files_whose_lastmod_did_not_change_are_not_fetched() -> None:
    state = MemorySitemapState()
    gateway = bpk(**{"2026": entries("1"), "1999": entries("9")})
    SyncSitemaps(gateway, state, FixedClock()).run()
    gateway.calls.clear()
    gateway.sitemap_lastmods["2026"] = date(2026, 10, 13)

    SyncSitemaps(gateway, state, FixedClock()).run()

    assert gateway.calls == ["index", "sitemap 2026"]


def test_a_full_sweep_reads_every_year_and_reports_ids_that_disappeared() -> None:
    state = MemorySitemapState()
    gateway = bpk(**{"2026": entries("1", "2"), "1999": entries("9", "10")})
    SyncSitemaps(gateway, state, FixedClock()).run()
    gateway.sitemaps["1999"] = entries("10")  # unchanged lastmod: only a full sweep would notice

    result = SyncSitemaps(gateway, state, FixedClock()).run(full=True)

    assert result.removed_ids == ["9"] and result.years_read == 2
    assert state.last_full_sweep() is not None


def test_a_new_regulation_year_is_read_even_without_a_full_sweep() -> None:
    state = MemorySitemapState()
    gateway = bpk(**{"2026": entries("1")})
    SyncSitemaps(gateway, state, FixedClock()).run()
    gateway.sitemaps["2027"] = entries("5")
    gateway.sitemap_lastmods["2027"] = date(2027, 1, 2)

    assert SyncSitemaps(gateway, state, FixedClock()).run().new_ids == ["5"]


def test_a_year_that_suddenly_lists_nothing_is_a_source_problem_not_mass_removal() -> None:
    state = MemorySitemapState()
    gateway = bpk(**{"2026": entries("1", "2")})
    SyncSitemaps(gateway, state, FixedClock()).run()
    gateway.sitemaps["2026"] = []
    gateway.sitemap_lastmods["2026"] = date(2026, 10, 13)

    with pytest.raises(Unavailable, match="2026"):
        SyncSitemaps(gateway, state, FixedClock()).run()
    assert state.sitemap_ids("2026") == {"1", "2"}  # nothing saved


def test_a_full_sweep_is_due_once_the_last_is_a_week_old() -> None:
    state = MemorySitemapState()
    gateway = bpk(**{"2026": entries("1"), "1999": entries("9")})
    SyncSitemaps(gateway, state, FixedClock()).run()  # baseline: counts as a full sweep
    gateway.calls.clear()
    SyncSitemaps(gateway, state, FixedClock()).run()
    assert gateway.calls == ["index"]  # nothing changed, swept today

    state.full_sweep = date(2026, 10, 6)
    SyncSitemaps(gateway, state, FixedClock()).run()
    assert gateway.calls.count("sitemap 1999") == 1
