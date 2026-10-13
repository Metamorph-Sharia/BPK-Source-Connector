"""ReviewCandidates: a person decides on what the targeting rules proposed.

Approving adds a row to the curated list (targets.csv) for a pull request; the next run collects it.
"""

from __future__ import annotations

from bpk_connector.application.dto import Candidate
from bpk_connector.application.ports import BpkGateway, Clock, EventLog, Repository, TargetCatalog
from bpk_connector.domain.models import ChangeEvent, Target, TargetOrigin, Tier


class ReviewError(ValueError):
    pass


class ReviewCandidates:
    def __init__(
        self, gateway: BpkGateway, repository: Repository, events: EventLog, catalog: TargetCatalog, clock: Clock
    ) -> None:
        self.gateway = gateway
        self.repository = repository
        self.events = events
        self.catalog = catalog
        self.clock = clock

    def open(self) -> list[Candidate]:
        return self.repository.candidates("open")

    def approve(self, record_id: str, *, tier: Tier, domain: str, note: str) -> None:
        self._require_open(record_id)
        citation = self.gateway.detail(record_id).regulation.citation
        self.catalog.approve(
            Target(record_id, tier, TargetOrigin.SEED, domain, note=note), citation=citation, rationale=note
        )
        self._decide(record_id, "approved", note, {"tier": tier.value, "domain": domain, "note": note})

    def reject(self, record_id: str, *, note: str) -> None:
        self._require_open(record_id)
        self._decide(record_id, "rejected", note, {"note": note})

    def _require_open(self, record_id: str) -> None:
        if record_id not in {c.record_id for c in self.open()}:
            raise ReviewError(f"{record_id} is not an open candidate")

    def _decide(self, record_id: str, state: str, note: str, detail: dict) -> None:
        now = self.clock.now()
        self.repository.decide_candidate(record_id, state=state, note=note, at=now)
        self.events.record("review", [ChangeEvent(f"candidate_{state}", record_id, detail)], at=now)
