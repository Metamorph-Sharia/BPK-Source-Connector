"""Alert rules: the facts of one run in, alerts with a severity out."""

from __future__ import annotations

from dataclasses import replace
from datetime import date

from bpk_connector.domain.alerts import RunFacts, Severity, evaluate, fill_rates
from bpk_connector.domain.models import ChangeEvent, FileRef, Regulation

TODAY = date(2026, 10, 13)
CLEAN = RunFacts(status="ok", today=TODAY)


def codes(facts: RunFacts) -> list[tuple[str, Severity]]:
    return [(a.code, a.severity) for a in evaluate(facts)]


def test_a_clean_run_raises_nothing() -> None:
    assert evaluate(CLEAN) == []


def test_being_blocked_is_critical_and_an_outage_is_a_warning() -> None:
    assert codes(replace(CLEAN, status="error", error="blocked: HTTP 403")) == [("source_blocked", Severity.CRITICAL)]
    assert codes(replace(CLEAN, status="paused", error="HTTP 503")) == [("source_unavailable", Severity.WARNING)]


def test_missing_targets_and_files_are_errors_and_deferred_files_a_warning() -> None:
    facts = replace(CLEAN, missing_targets=["240203"], failed_files=["/Download/1/a.pdf"], deferred_files=["/x"])

    assert codes(facts) == [
        ("target_missing", Severity.ERROR),
        ("file_missing", Severity.ERROR),
        ("file_deferred", Severity.WARNING),
    ]


def test_amended_or_revoked_targets_and_new_lineage_are_reported_as_info() -> None:
    events = [
        ChangeEvent("relation_added", "240203", {"kind": "Diubah dengan", "record_id": "350166"}),
        ChangeEvent("status_changed", "161835", {"from": "Berlaku", "to": "Tidak Berlaku"}),
        ChangeEvent("target_added", "350166", {"via": "240203"}),
        ChangeEvent("candidate_queued", "244907", {"via": "161835"}),
    ]

    alerts = evaluate(replace(CLEAN, events=events))

    assert [(a.code, a.severity) for a in alerts] == [
        ("target_changed", Severity.INFO),
        ("lineage_added", Severity.INFO),
        ("candidates_queued", Severity.INFO),
    ]
    assert alerts[0].details["record_ids"] == ["240203", "161835"]


def test_texts_with_pages_needing_ocr_are_a_warning() -> None:
    facts = replace(CLEAN, events=[ChangeEvent("text_needs_ocr", "347826", {"pages_without_text": 23})])

    assert codes(facts) == [("text_incomplete", Severity.WARNING)]


def test_data_anomalies_need_a_person_to_look() -> None:
    facts = replace(CLEAN, events=[ChangeEvent("data_anomaly", "352349", {"problems": ["date in the future"]})])

    assert codes(facts) == [("data_anomaly", Severity.WARNING)]


def test_candidates_waiting_too_long_for_review_are_a_warning() -> None:
    facts = replace(CLEAN, open_candidates={"1": date(2026, 9, 1), "2": date(2026, 10, 10)})

    alerts = evaluate(facts)

    assert [(a.code, a.details["record_ids"]) for a in alerts] == [("review_backlog", ["1"])]


def test_a_field_filled_much_less_often_than_last_run_signals_layout_drift() -> None:
    facts = replace(CLEAN, fill_rates={"Judul": 1.0, "Status": 0.5}, previous_fill_rates={"Judul": 1.0, "Status": 1.0})

    alerts = evaluate(facts)

    assert [(a.code, a.severity, a.details["fields"]) for a in alerts] == [
        ("parse_fill_drop", Severity.WARNING, {"Status": [1.0, 0.5]})
    ]


def test_fill_rates_cover_bpk_fields_and_what_we_parse() -> None:
    complete = Regulation(
        "1", "t", "UU", "4", "2023", status="Berlaku", files=(FileRef("1", "a", "/a"),), fields={"Judul": "t"}
    )
    empty = Regulation("2", "", "", "", "", fields={"Judul": ""})

    rates = fill_rates([complete, empty])

    assert rates["Judul"] == 0.5 and rates["status"] == 0.5 and rates["files"] == 0.5 and rates["relations"] == 0.0


def test_one_sided_links_are_reported_for_a_person_to_check_with_bpk() -> None:
    facts = replace(CLEAN, one_sided_links=["306614 Diubah dengan 326338 (PMK 53/2025)"])

    assert codes(facts) == [("link_inconsistency", Severity.INFO)]
    assert evaluate(facts)[0].details == {"links": ["306614 Diubah dengan 326338 (PMK 53/2025)"]}


def test_a_week_without_any_new_bpk_record_means_discovery_is_broken() -> None:
    # BPK adds 40-60 records a day; silence means our sitemap reading or BPK's sitemap broke.
    assert codes(replace(CLEAN, days_since_new_record=8)) == [("no_new_records", Severity.WARNING)]
    assert codes(replace(CLEAN, days_since_new_record=2)) == []
