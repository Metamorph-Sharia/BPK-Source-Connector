"""ReportRun: complete a run's report with alerts, field fill rates and the freshness table."""

from __future__ import annotations

from bpk_connector.application.ports import Clock, Repository, RunHistory, TargetCatalog
from bpk_connector.application.run_report import RunReport
from bpk_connector.application.targets import all_targets
from bpk_connector.domain.alerts import RunFacts, evaluate, fill_rates
from bpk_connector.domain.changes import one_sided_links
from bpk_connector.domain.freshness import freshness_row, median_lag_by_form
from bpk_connector.domain.models import Regulation


class ReportRun:
    def __init__(self, history: RunHistory, repository: Repository, catalog: TargetCatalog, clock: Clock) -> None:
        self.history = history
        self.repository = repository
        self.catalog = catalog
        self.clock = clock

    def complete(self, report: RunReport) -> None:
        regulations = self._observed_targets()
        report.fill_rates = fill_rates(regulations)
        report.freshness = self._freshness(regulations)
        report.median_lag_by_form = median_lag_by_form(report.freshness)
        links = one_sided_links({r.record_id: r for r in regulations})
        report.alerts = evaluate(
            self._facts(report, [f"{rid} {r.kind} {r.record_id} ({r.citation})" for rid, r in links])
        )

    def _observed_targets(self) -> list[Regulation]:
        found = (self.repository.regulation(r) for r in all_targets(self.repository, self.catalog))
        return [r for r in found if r is not None]

    def _freshness(self, regulations: list[Regulation]):
        first_seen = self.history.first_seen()
        if not first_seen:
            return []
        baseline = min(first_seen.values())
        return [
            freshness_row(r, first_seen=first_seen[r.record_id], baseline=baseline)
            for r in regulations
            if r.record_id in first_seen
        ]

    def _facts(self, report: RunReport, one_sided: list[str]) -> RunFacts:
        previous = self.history.last_report() or {}
        return RunFacts(
            status=report.status,
            today=self.clock.now().date(),
            error=report.error,
            missing_targets=report.check.missing if report.check else [],
            failed_files=report.fetch.failed if report.fetch else [],
            deferred_files=report.fetch.deferred if report.fetch else [],
            events=self.history.run_events(report.run_id),
            open_candidates=self.history.open_candidates(),
            fill_rates=report.fill_rates,
            previous_fill_rates=previous.get("fill_rates", {}),
            one_sided_links=one_sided,
            days_since_new_record=self._days_since_new_record(),
        )

    def _days_since_new_record(self) -> int | None:
        last = self.history.last_new_record_on()
        return (self.clock.now().date() - last).days if last else None
