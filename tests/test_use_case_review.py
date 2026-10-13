"""ReviewCandidates: a person approves or rejects what the targeting rules proposed."""

from __future__ import annotations

import pytest
from fakes.memory import NOW, FakeGateway, FixedClock, MemoryCatalog, MemoryEventLog, MemoryRepository

from bpk_connector.application.use_cases.review_candidates import ReviewCandidates, ReviewError
from bpk_connector.domain.models import Regulation, Target, TargetOrigin, Tier

FIDUCIARY = Regulation("400001", "Permenkum tentang Jaminan Fidusia", "Permenkum", "9", "2026")


def world():
    repository, events, catalog = MemoryRepository(), MemoryEventLog(), MemoryCatalog([])
    repository.add_candidate("400001", reason="new on BPK: Permenkum 9/2026", at=NOW)
    review = ReviewCandidates(FakeGateway({"400001": FIDUCIARY}), repository, events, catalog, FixedClock())
    return review, repository, events, catalog


def test_open_candidates_are_listed_with_their_reason() -> None:
    review, _, _, _ = world()

    assert [(c.record_id, c.reason) for c in review.open()] == [("400001", "new on BPK: Permenkum 9/2026")]


def test_approving_adds_the_record_to_the_curated_list_and_closes_the_candidate() -> None:
    review, repository, events, catalog = world()

    review.approve("400001", tier=Tier.P1, domain="B", note="fiduciary registration procedure")

    assert catalog.approved == [
        (Target("400001", Tier.P1, TargetOrigin.SEED, "B", note="fiduciary registration procedure"), "Permenkum 9/2026")
    ]
    assert review.open() == [] and repository.candidates("approved")[0].record_id == "400001"
    assert events.kinds() == ["candidate_approved"]


def test_rejecting_closes_the_candidate_and_records_why() -> None:
    review, repository, events, _ = world()

    review.reject("400001", note="regional")

    assert review.open() == [] and events.events[0].detail == {"note": "regional"}


def test_only_open_candidates_can_be_decided() -> None:
    review, _, _, _ = world()
    review.reject("400001", note="x")

    with pytest.raises(ReviewError, match="not an open candidate"):
        review.approve("400001", tier=Tier.P1, domain="B", note="")
