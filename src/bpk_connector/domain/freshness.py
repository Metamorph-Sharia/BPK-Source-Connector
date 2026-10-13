"""How late BPK publishes, and dates that can't be right.

BPK's publishing lag is accepted under decision D2 and measured here, so a future decision to add a
faster source rests on data. Lag is only knowable for records first seen after monitoring began:
the initial backfill found records that were already on BPK, so those are ``baseline``.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from statistics import median

from bpk_connector.domain.models import Regulation


@dataclass(frozen=True)
class FreshnessRow:
    record_id: str
    citation: str
    form: str
    promulgated_on: date | None
    first_seen: date
    lag_days: int | None  # None when baseline, or when BPK gives no date
    baseline: bool


def freshness_row(regulation: Regulation, *, first_seen: date, baseline: date) -> FreshnessRow:
    is_baseline = first_seen <= baseline
    published = regulation.promulgated_on or regulation.enacted_on
    lag = None if is_baseline or published is None else (first_seen - published).days
    return FreshnessRow(
        regulation.record_id, regulation.citation, regulation.form, published, first_seen, lag, is_baseline
    )


def median_lag_by_form(rows: list[FreshnessRow]) -> dict[str, float]:
    lags: dict[str, list[int]] = defaultdict(list)
    for row in rows:
        if row.lag_days is not None:
            lags[row.form].append(row.lag_days)
    return {form: median(values) for form, values in sorted(lags.items())}


def date_anomalies(regulation: Regulation, *, observed: date) -> list[str]:
    """Dates BPK shows that can't be right. Effective dates may legitimately lie in the future."""
    found = []
    for name in ("enacted_on", "promulgated_on"):
        value = getattr(regulation, name)
        if value and value > observed:
            found.append(f"{name} {value} is after the day we saw it ({observed})")
    enacted, promulgated = regulation.enacted_on, regulation.promulgated_on
    if enacted and promulgated and promulgated < enacted:
        found.append(f"promulgated_on {promulgated} is before enacted_on {enacted}")
    return found
