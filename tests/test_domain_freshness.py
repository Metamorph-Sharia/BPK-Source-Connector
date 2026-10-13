"""Freshness (BPK's publishing lag, accepted under decision D2) and date sanity checks."""

from __future__ import annotations

from datetime import date

from bpk_connector.domain.freshness import date_anomalies, freshness_row, median_lag_by_form
from bpk_connector.domain.models import Regulation

BASELINE = date(2026, 10, 13)  # the first run: records seen then were already on BPK


def regulation(form="PMK", promulgated=None, enacted=None, effective=None) -> Regulation:
    return Regulation(
        "1", "t", form, "1", "2026", enacted_on=enacted, promulgated_on=promulgated, effective_on=effective
    )


def test_lag_runs_from_promulgation_to_first_seen() -> None:
    row = freshness_row(regulation(promulgated=date(2026, 9, 8)), first_seen=date(2026, 10, 20), baseline=BASELINE)

    assert row.lag_days == 42 and not row.baseline


def test_records_from_the_initial_backfill_have_no_lag_we_could_know() -> None:
    row = freshness_row(regulation(promulgated=date(2023, 1, 12)), first_seen=BASELINE, baseline=BASELINE)

    assert row.baseline and row.lag_days is None


def test_without_a_promulgation_date_lag_runs_from_enactment() -> None:
    row = freshness_row(regulation(enacted=date(2026, 10, 1)), first_seen=date(2026, 10, 15), baseline=BASELINE)

    assert row.lag_days == 14


def test_median_lag_per_form_ignores_baseline_records() -> None:
    rows = [
        freshness_row(regulation("PMK", date(2026, 10, 1)), first_seen=date(2026, 10, 20), baseline=BASELINE),
        freshness_row(regulation("PMK", date(2026, 10, 1)), first_seen=date(2026, 11, 1), baseline=BASELINE),
        freshness_row(regulation("PMK", date(2026, 10, 1)), first_seen=date(2026, 11, 30), baseline=BASELINE),
        freshness_row(regulation("UU", date(2020, 1, 1)), first_seen=BASELINE, baseline=BASELINE),
    ]

    assert median_lag_by_form(rows) == {"PMK": 31}


def test_a_promulgation_date_in_the_future_is_an_anomaly() -> None:
    # Seen live: POJK 8/2026 carries a promulgation date of 2026-12-06.
    anomalies = date_anomalies(regulation(promulgated=date(2026, 12, 6)), observed=BASELINE)

    assert anomalies == ["promulgated_on 2026-12-06 is after the day we saw it (2026-10-13)"]


def test_promulgation_before_enactment_is_an_anomaly() -> None:
    anomalies = date_anomalies(regulation(enacted=date(2026, 5, 2), promulgated=date(2026, 5, 1)), observed=BASELINE)

    assert anomalies == ["promulgated_on 2026-05-01 is before enacted_on 2026-05-02"]


def test_ordinary_dates_have_no_anomalies() -> None:
    dates = {"enacted": date(2026, 1, 5), "promulgated": date(2026, 1, 13), "effective": date(2027, 1, 1)}

    assert date_anomalies(regulation(**dates), observed=BASELINE) == []  # effective dates may be in the future
