"""ReportRun: turn a finished run into alerts, fill rates and the freshness table."""

from __future__ import annotations

from datetime import date

from fakes.memory import NOW, FixedClock, MemoryCatalog, MemoryEventLog, MemoryHistory, MemoryRepository

from bpk_connector.application.run_report import RunReport
from bpk_connector.application.use_cases.check_targets import CheckSummary
from bpk_connector.application.use_cases.report_run import ReportRun
from bpk_connector.domain.alerts import Severity
from bpk_connector.domain.models import ChangeEvent, Regulation, Relation, Target, TargetOrigin, Tier

P2SK = Regulation(
    "240203", "UU 4/2023", "UU", "4", "2023", status="Berlaku", promulgated_on=date(2023, 1, 12), fields={"Judul": "x"}
)
NEW_PMK = Regulation(
    "400001",
    "PMK 70/2026",
    "PMK",
    "70",
    "2026",
    status="Berlaku",
    promulgated_on=date(2026, 9, 1),
    fields={"Judul": "y"},
)
SEEDS = [Target("240203", Tier.P1, TargetOrigin.SEED), Target("400001", Tier.P2, TargetOrigin.SEED)]


def world():
    repository, events = MemoryRepository(), MemoryEventLog()
    repository.observations.update({"240203": P2SK, "400001": NEW_PMK})
    repository.seen_on.update({"240203": date(2026, 10, 1), "400001": date(2026, 10, 13)})  # first run: 2026-10-01
    use_case = ReportRun(MemoryHistory(repository, events), repository, MemoryCatalog(SEEDS), FixedClock())
    return use_case, repository, events


def test_alerts_come_from_the_run_and_its_events() -> None:
    use_case, _, events = world()
    events.record("run-2", [ChangeEvent("relation_added", "240203", {"record_id": "350166"})], at=NOW)
    report = RunReport("run-2", NOW, status="ok", check=CheckSummary(checked=2, missing=[]))

    use_case.complete(report)

    assert [(a.code, a.severity) for a in report.alerts] == [("target_changed", Severity.INFO)]
    assert report.worst_severity is Severity.INFO and not report.failed_exit


def test_an_error_alert_makes_the_run_fail_loudly() -> None:
    use_case, _, _ = world()
    report = RunReport("run-2", NOW, status="ok", check=CheckSummary(missing=["240203"]))

    use_case.complete(report)

    assert report.worst_severity is Severity.ERROR and report.failed_exit


def test_freshness_measures_lag_only_for_records_first_seen_after_the_first_run() -> None:
    use_case, _, _ = world()
    report = RunReport("run-2", NOW, status="ok")

    use_case.complete(report)

    rows = {row.record_id: row for row in report.freshness}
    assert rows["240203"].baseline and rows["240203"].lag_days is None
    assert rows["400001"].lag_days == 42  # promulgated 2026-09-01, first seen 2026-10-13
    assert report.median_lag_by_form == {"PMK": 42}


def test_fill_rates_are_compared_with_the_previous_run() -> None:
    use_case, repository, _ = world()
    repository.reports.append({"fill_rates": {"Judul": 1.0, "Sumber": 1.0}})
    report = RunReport("run-2", NOW, status="ok")

    use_case.complete(report)

    assert report.fill_rates["Judul"] == 1.0
    assert [a.code for a in report.alerts] == ["parse_fill_drop"]  # "Sumber" vanished from every page


def test_one_sided_links_between_observed_targets_are_reported() -> None:
    use_case, repository, _ = world()
    one_sided = Regulation(
        "240203", "UU 4/2023", "UU", "4", "2023", relations=(Relation("Diubah dengan", "400001", "PMK 70/2026"),)
    )
    repository.observations["240203"] = one_sided
    report = RunReport("run-2", NOW, status="ok")

    use_case.complete(report)

    assert "link_inconsistency" in [a.code for a in report.alerts]
