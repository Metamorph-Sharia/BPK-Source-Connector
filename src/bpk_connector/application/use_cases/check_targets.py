"""CheckTargets: re-read every target's detail page, record what changed, follow its version links.

Runs every time, because BPK's sitemap doesn't show when a newer regulation amends or revokes a
record. The first run is the backfill. Lineage targets found on the way are checked in the same run.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bpk_connector.application.dto import DetailPage
from bpk_connector.application.ports import BlobStore, BpkGateway, Clock, EventLog, Repository, TargetCatalog
from bpk_connector.application.targets import all_targets
from bpk_connector.application.walk import Visit, walk_targets
from bpk_connector.domain.changes import diff, fingerprint
from bpk_connector.domain.freshness import date_anomalies
from bpk_connector.domain.models import ChangeEvent


@dataclass
class CheckSummary:
    checked: int = 0
    changed: int = 0
    added: int = 0
    candidates: int = 0
    missing: list[str] = field(default_factory=list)


class CheckTargets:
    def __init__(
        self,
        gateway: BpkGateway,
        repository: Repository,
        events: EventLog,
        blobs: BlobStore,
        catalog: TargetCatalog,
        clock: Clock,
    ) -> None:
        self.gateway = gateway
        self.repository = repository
        self.events = events
        self.blobs = blobs
        self.catalog = catalog
        self.clock = clock

    def run(self, run_id: str) -> CheckSummary:
        summary = CheckSummary()
        targets = all_targets(self.repository, self.catalog)
        for visit in walk_targets(self.gateway, targets, self.catalog.watch_rules()):
            events = self._record(visit, summary)
            self.events.record(run_id, events, at=self.clock.now())
        return summary

    def _record(self, visit: Visit, summary: CheckSummary) -> list[ChangeEvent]:
        if visit.page is None:
            summary.missing.append(visit.target.record_id)
            return [ChangeEvent("target_missing", visit.target.record_id)]
        return self._observe(visit.page, summary) + self._follow(visit, summary)

    def _observe(self, page: DetailPage, summary: CheckSummary) -> list[ChangeEvent]:
        regulation = page.regulation
        now = self.clock.now()
        events = diff(self.repository.regulation(regulation.record_id), regulation)
        self.repository.save_observation(
            regulation, html_sha256=self.blobs.put(page.html), fingerprint=fingerprint(regulation), at=now
        )
        summary.checked += 1
        summary.changed += bool(events)
        if events and (problems := date_anomalies(regulation, observed=now.date())):
            events.append(ChangeEvent("data_anomaly", regulation.record_id, {"problems": problems}))
        return events

    def _follow(self, visit: Visit, summary: CheckSummary) -> list[ChangeEvent]:
        via = visit.target.record_id
        events = []
        for found in visit.added:
            self.repository.add_target(found, at=self.clock.now())
            events.append(ChangeEvent("target_added", found.record_id, {"via": via, "tier": found.tier}))
        summary.added += len(visit.added)
        for link in visit.for_review:
            reason = f"{link.kind} link from {via}: {link.citation} — {link.about}".rstrip(" —")
            if self.repository.add_candidate(link.record_id, reason=reason, at=self.clock.now()):
                events.append(ChangeEvent("candidate_queued", link.record_id, {"via": via, "reason": reason}))
                summary.candidates += 1
        return events
