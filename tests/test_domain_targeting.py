"""The targeting policy: which regulations join the targets, which go to review, which are ignored."""

from __future__ import annotations

from bpk_connector.domain.models import Regulation, Relation, Target, TargetOrigin, Tier
from bpk_connector.domain.targeting import Action, Lineage, WatchRules, lineage_of, triage

RULES = WatchRules(
    forms=frozenset({"UU", "PP", "Permenkum"}),
    title_keywords=("fidusia", "pemilik manfaat"),
    subjects=frozenset({"PERBANKAN, LEMBAGA KEUANGAN"}),
    max_auto_links=3,
)
P2SK = Target("240203", Tier.P1, TargetOrigin.SEED, domain="A")


def regulation(record_id: str, *relations: Relation, form: str = "UU", title: str = "", subjects=()) -> Regulation:
    return Regulation(record_id, title, form, "1", "2026", subjects=tuple(subjects), relations=relations)


def link(kind: str, record_id: str) -> Relation:
    return Relation(kind, record_id, f"citation of {record_id}")


# --- lineage: links on a target's own page -------------------------------------------------


def test_a_newer_amendment_of_a_target_joins_with_the_targets_tier() -> None:
    page = regulation("240203", link("Diubah dengan", "350166"))

    lineage = lineage_of(P2SK, page, RULES)

    assert lineage.targets == [Target("350166", Tier.P1, TargetOrigin.LINEAGE, domain="A", via="240203")]
    assert lineage.for_review == []


def test_an_older_regulation_the_target_amends_or_revokes_joins_as_p3() -> None:
    page = regulation("319773", link("Mencabut", "161835"))

    lineage = lineage_of(Target("319773", Tier.P1, TargetOrigin.SEED), page, RULES)

    assert [(t.record_id, t.tier) for t in lineage.targets] == [("161835", Tier.P3)]


def test_omnibus_links_go_to_review_instead_of_joining() -> None:
    # UU 4/2023 amends ~25 laws (pensions, capital markets …): following them all would undo the targeting.
    page = regulation("240203", *(link("Mengubah", str(n)) for n in range(4)), link("Diubah dengan", "350166"))

    lineage = lineage_of(P2SK, page, RULES)

    assert [t.record_id for t in lineage.targets] == ["350166"]
    assert [r.record_id for r in lineage.for_review] == ["0", "1", "2", "3"]
    assert lineage.for_review[0] == link("Mengubah", "0")  # the link travels with it, for the reviewer


def test_links_that_are_neither_newer_nor_older_versions_are_not_followed() -> None:
    page = regulation("240203", link("Uji Materi", "999"))

    assert lineage_of(P2SK, page, RULES).targets == []


# --- triage: a record BPK just published -------------------------------------------------------


def test_a_new_record_amending_a_target_is_added_automatically() -> None:
    new = regulation("350166", link("Mengubah", "240203"))

    decision = triage(new, {"240203": P2SK}, RULES)

    assert decision.action is Action.AUTO_ADD
    assert decision.target == Target("350166", Tier.P1, TargetOrigin.LINEAGE, domain="A", via="240203")


def test_a_new_central_record_matching_a_keyword_is_a_review_candidate() -> None:
    new = regulation("400001", form="Permenkum", title="Tata Cara Pendaftaran Jaminan Fidusia")

    decision = triage(new, {}, RULES)

    assert decision.action is Action.CANDIDATE
    assert "fidusia" in decision.reason


def test_a_new_central_record_matching_a_subject_is_a_review_candidate() -> None:
    new = regulation("400002", form="PP", subjects=["PERBANKAN, LEMBAGA KEUANGAN"])

    assert triage(new, {}, RULES).action is Action.CANDIDATE


def test_regional_and_unwatched_forms_are_ignored_even_when_the_title_matches() -> None:
    new = regulation("400003", form="Perbup", title="Jaminan Fidusia di Kabupaten")

    assert triage(new, {}, RULES).action is Action.IGNORE


def test_a_new_omnibus_record_touching_a_target_goes_to_review() -> None:
    new = regulation("400004", *(link("Mengubah", str(n)) for n in range(4)), link("Mengubah", "240203"))

    assert triage(new, {"240203": P2SK}, RULES).action is Action.CANDIDATE


def test_lineage_targets_follow_newer_versions_but_not_older_ones() -> None:
    # Keeps the target set current without walking every revocation chain back in time.
    added = Target("350166", Tier.P1, TargetOrigin.LINEAGE, via="240203")
    page = regulation("350166", link("Diubah dengan", "500000"), link("Mencabut", "100000"))

    assert [t.record_id for t in lineage_of(added, page, RULES).targets] == ["500000"]


def test_partial_revocations_go_to_review_because_they_cross_sectors() -> None:
    # Live run 2026-10-13: PP 5/2021 (licensing) is "partly revoked by" PP 11/2023 on fishing quotas.
    page = regulation("161835", link("Dicabut sebagian dengan", "244907"), link("Mencabut sebagian", "1"))

    lineage = lineage_of(Target("161835", Tier.P3, TargetOrigin.SEED), page, RULES)

    assert lineage.targets == [] and [r.record_id for r in lineage.for_review] == ["244907", "1"]


def test_an_older_version_added_as_history_is_not_expanded_further() -> None:
    # Live run 2026-10-13: UU 25/2007 revokes UU 12/1970, which BPK says was amended by the income-tax law.
    history = lineage_of(
        Target("39903", Tier.P1, TargetOrigin.SEED), regulation("39903", link("Mencabut", "47914")), RULES
    )
    old_law = history.targets[0]

    page = regulation("47914", link("Diubah dengan", "46988"))

    assert old_law.historical and lineage_of(old_law, page, RULES) == Lineage()


def test_a_new_record_partly_revoking_a_target_is_a_review_candidate() -> None:
    new = regulation("400005", link("Mencabut sebagian", "240203"), form="Perbup")

    decision = triage(new, {"240203": P2SK}, RULES)

    assert decision.action is Action.CANDIDATE and "240203" in decision.reason
