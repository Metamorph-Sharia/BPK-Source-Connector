"""TriageNewRecords: each record BPK just published is auto-added, queued for review, or ignored."""

from __future__ import annotations

import pytest
from fakes.memory import FakeGateway, FixedClock, MemoryCatalog, MemoryEventLog, MemoryRepository

from bpk_connector.application.ports import Unavailable
from bpk_connector.application.use_cases.triage_new_records import TriageNewRecords
from bpk_connector.domain.models import Regulation, Relation, Target, TargetOrigin, Tier
from bpk_connector.domain.targeting import WatchRules

P2SK = Target("240203", Tier.P1, TargetOrigin.SEED, "A")
RULES = WatchRules(forms=frozenset({"UU", "Permenkum"}), title_keywords=("fidusia",))


def world(*pages: Regulation):
    gateway = FakeGateway({p.record_id: p for p in pages})
    repository, events = MemoryRepository(), MemoryEventLog()
    use_case = TriageNewRecords(gateway, repository, events, MemoryCatalog([P2SK], RULES), FixedClock())
    return use_case, repository, events, gateway


def test_an_amendment_of_a_target_joins_the_targets() -> None:
    amendment = Regulation(
        "350166", "UU 4/2026", "UU", "4", "2026", relations=(Relation("Mengubah", "240203", "UU 4/2023"),)
    )
    use_case, repository, events, _ = world(amendment)

    summary = use_case.run("run-1", ["350166"])

    assert summary.added == ["350166"]
    assert repository.targets()["350166"].via == "240203"
    assert events.kinds() == ["new_record_triaged"]
    assert events.events[0].detail["action"] == "auto_add"


def test_a_watch_match_is_queued_with_what_a_reviewer_needs() -> None:
    fiduciary = Regulation("400001", "Peraturan Menteri Hukum tentang Jaminan Fidusia", "Permenkum", "9", "2026")
    use_case, repository, _, _ = world(fiduciary)

    summary = use_case.run("run-1", ["400001"])

    assert summary.candidates == ["400001"]
    assert "Permenkum 9/2026" in repository.queued["400001"] and "fidusia" in repository.queued["400001"]


def test_everything_else_is_ignored_but_the_decision_is_logged() -> None:
    regional = Regulation("400002", "Pedoman Gratifikasi", "Perbup", "1", "2026")
    use_case, repository, events, _ = world(regional)

    summary = use_case.run("run-1", ["400002"])

    assert summary.ignored == 1 and repository.queued == {} and repository.targets() == {}
    assert events.events[0].detail["action"] == "ignore"


def test_a_record_gone_before_we_read_it_is_skipped() -> None:
    use_case, _, _, _ = world()

    assert use_case.run("run-1", ["999"]).gone == ["999"]


def test_an_unavailable_source_stops_triage() -> None:
    use_case, _, _, gateway = world()
    gateway.failure = Unavailable("HTTP 503")

    with pytest.raises(Unavailable):
        use_case.run("run-1", ["1"])
