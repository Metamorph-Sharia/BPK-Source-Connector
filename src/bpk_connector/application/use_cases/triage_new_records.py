"""TriageNewRecords: decide what to do with each record BPK published since the last run.

Amendments and revocations of a target join automatically; watch-rule matches go to a person;
the rest are ignored. Every decision is logged, so "why didn't we collect X?" has an answer.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bpk_connector.application.ports import BpkGateway, Clock, EventLog, NotFound, Repository, TargetCatalog
from bpk_connector.application.targets import all_targets
from bpk_connector.domain.models import ChangeEvent, Regulation
from bpk_connector.domain.targeting import Action, Decision, triage


@dataclass
class TriageSummary:
    added: list[str] = field(default_factory=list)
    candidates: list[str] = field(default_factory=list)
    ignored: int = 0
    gone: list[str] = field(default_factory=list)


class TriageNewRecords:
    def __init__(
        self, gateway: BpkGateway, repository: Repository, events: EventLog, catalog: TargetCatalog, clock: Clock
    ) -> None:
        self.gateway = gateway
        self.repository = repository
        self.events = events
        self.catalog = catalog
        self.clock = clock

    def run(self, run_id: str, record_ids: list[str]) -> TriageSummary:
        summary = TriageSummary()
        targets = all_targets(self.repository, self.catalog)
        rules = self.catalog.watch_rules()
        for record_id in record_ids:
            try:
                regulation = self.gateway.detail(record_id).regulation
            except NotFound:
                summary.gone.append(record_id)
                continue
            decision = triage(regulation, targets, rules)
            self._apply(decision, regulation, summary)
            if decision.target:
                targets[decision.target.record_id] = decision.target
            self.events.record(run_id, [_logged(decision, regulation)], at=self.clock.now())
        return summary

    def _apply(self, decision: Decision, regulation: Regulation, summary: TriageSummary) -> None:
        now = self.clock.now()
        if decision.action is Action.AUTO_ADD:
            self.repository.add_target(decision.target, at=now)
            summary.added.append(regulation.record_id)
        elif decision.action is Action.CANDIDATE:
            reason = f"new on BPK: {regulation.citation} — {regulation.title} ({decision.reason})"
            if self.repository.add_candidate(regulation.record_id, reason=reason, at=now):
                summary.candidates.append(regulation.record_id)
        else:
            summary.ignored += 1


def _logged(decision: Decision, regulation: Regulation) -> ChangeEvent:
    detail = {"action": decision.action.value, "reason": decision.reason, "citation": regulation.citation}
    return ChangeEvent("new_record_triaged", regulation.record_id, detail)
