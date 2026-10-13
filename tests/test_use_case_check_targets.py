"""CheckTargets: re-read every target's detail page, record changes, grow the lineage."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

import pytest
from fakes.memory import FakeGateway, FixedClock, MemoryBlobs, MemoryCatalog, MemoryEventLog, MemoryRepository

from bpk_connector.application.ports import Unavailable
from bpk_connector.application.targets import all_targets
from bpk_connector.application.use_cases.check_targets import CheckTargets
from bpk_connector.domain.models import Regulation, Relation, Target, TargetOrigin, Tier

P2SK = Target("240203", Tier.P1, TargetOrigin.SEED, domain="A")
LEVY_PP_2014 = Target("5448", Tier.P3, TargetOrigin.SEED, domain="A")


def page(record_id: str, *relations: Relation, status: str = "Berlaku") -> Regulation:
    return Regulation(record_id, f"title {record_id}", "UU", "1", "2026", status=status, relations=relations)


def link(kind: str, record_id: str) -> Relation:
    return Relation(kind, record_id, f"citation {record_id}")


class World:
    def __init__(self, pages: dict[str, Regulation], seeds: list[Target]) -> None:
        self.gateway = FakeGateway(pages)
        self.repository = MemoryRepository()
        self.events = MemoryEventLog()
        self.blobs = MemoryBlobs()
        self.use_case = CheckTargets(
            self.gateway, self.repository, self.events, self.blobs, MemoryCatalog(seeds), FixedClock()
        )

    def run(self):
        return self.use_case.run("run-1")


def test_the_first_check_stores_each_target_page_and_reports_it_new() -> None:
    world = World({"240203": page("240203")}, [P2SK])

    summary = world.run()

    assert summary.checked == 1
    assert world.repository.regulation("240203").title == "title 240203"
    assert b"<html>240203</html>" in world.blobs.blobs.values()  # raw bytes kept before parsing
    assert world.events.kinds() == ["new_record"]


def test_an_amendment_link_adds_a_lineage_target_and_checks_it_in_the_same_run() -> None:
    world = World({"240203": page("240203", link("Diubah dengan", "350166")), "350166": page("350166")}, [P2SK])

    summary = world.run()

    assert world.repository.targets()["350166"] == Target("350166", Tier.P1, TargetOrigin.LINEAGE, "A", via="240203")
    assert summary.checked == 2 and summary.added == 1
    assert world.events.kinds().count("target_added") == 1


def test_a_link_to_an_existing_target_neither_duplicates_nor_downgrades_it() -> None:
    # PP 11/2014 (P3) is "revoked by" PP 41/2024, which is itself a P1 seed.
    levy_2024 = Target("304105", Tier.P1, TargetOrigin.SEED)
    world = World(
        {"5448": page("5448", link("Dicabut dengan", "304105")), "304105": page("304105")}, [LEVY_PP_2014, levy_2024]
    )

    summary = world.run()

    assert summary.added == 0 and world.repository.targets() == {}


def test_an_unchanged_second_run_records_nothing() -> None:
    world = World({"240203": page("240203")}, [P2SK])
    world.run()
    world.events.events.clear()

    world.run()

    assert world.events.events == []


def test_a_status_change_on_a_later_run_is_recorded() -> None:
    world = World({"240203": page("240203")}, [P2SK])
    world.run()
    world.gateway.pages["240203"] = page("240203", status="Tidak Berlaku")

    world.run()

    assert world.events.kinds()[-1] == "status_changed"


def test_a_missing_target_is_reported_and_the_run_continues() -> None:
    world = World({"350166": page("350166")}, [P2SK, Target("350166", Tier.P1, TargetOrigin.SEED)])

    summary = world.run()

    assert summary.missing == ["240203"] and summary.checked == 1
    assert world.events.kinds() == ["target_missing", "new_record"]


def test_omnibus_links_become_review_candidates() -> None:
    omnibus = page("240203", *(link("Mengubah", str(n)) for n in range(4)))
    world = World({"240203": omnibus}, [P2SK])

    summary = world.run()

    assert sorted(world.repository.queued) == ["0", "1", "2", "3"]
    assert summary.candidates == 4


def test_an_unavailable_source_stops_the_run() -> None:
    world = World({"240203": page("240203")}, [P2SK])
    world.gateway.failure = Unavailable("HTTP 503")

    with pytest.raises(Unavailable):
        world.run()


def test_seeds_win_over_stored_targets_for_the_same_record() -> None:
    world = World({"240203": page("240203")}, [P2SK])
    world.repository.found_targets["240203"] = replace(P2SK, tier=Tier.P3, origin=TargetOrigin.LINEAGE)

    assert all_targets(world.repository, MemoryCatalog([P2SK]))["240203"] == P2SK


def test_curated_seeds_come_first_then_targets_the_pipeline_found() -> None:
    world = World({}, [P2SK])
    world.repository.found_targets["350166"] = Target("350166", Tier.P1, TargetOrigin.LINEAGE, via="240203")

    assert list(all_targets(world.repository, MemoryCatalog([P2SK]))) == ["240203", "350166"]


def test_an_impossible_date_is_reported_once_when_the_record_is_new_or_changes() -> None:
    future = replace(page("240203"), promulgated_on=date(2026, 12, 6))  # after the run date
    world = World({"240203": future}, [P2SK])

    world.run()
    world.run()  # unchanged: not reported again

    anomalies = [e for e in world.events.events if e.kind == "data_anomaly"]
    assert len(anomalies) == 1 and "2026-12-06" in anomalies[0].detail["problems"][0]


def test_queued_candidates_appear_in_the_event_log() -> None:
    world = World({"240203": page("240203", link("Dicabut sebagian dengan", "244907"))}, [P2SK])

    world.run()

    assert ("candidate_queued", "244907") in [(e.kind, e.record_id) for e in world.events.events]
