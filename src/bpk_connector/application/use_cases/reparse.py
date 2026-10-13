"""Reparse: re-apply the parser to every stored detail page. No network.

Raw pages are kept before parsing (principle 4), so a parser fix, or the cross-agency schema
of a later phase, can be applied to everything already collected.
"""

from __future__ import annotations

from dataclasses import dataclass

from bpk_connector.application.ports import BlobStore, Clock, EventLog, PageParser, Repository
from bpk_connector.domain.changes import diff, fingerprint


@dataclass
class ReparseSummary:
    reparsed: int = 0
    changed: int = 0


class Reparse:
    def __init__(
        self, repository: Repository, events: EventLog, blobs: BlobStore, parse: PageParser, clock: Clock
    ) -> None:
        self.repository = repository
        self.events = events
        self.blobs = blobs
        self.parse = parse
        self.clock = clock

    def run(self, run_id: str) -> ReparseSummary:
        summary = ReparseSummary()
        for record_id, html_sha256 in self.repository.stored_pages().items():
            regulation = self.parse(record_id, self.blobs.get(html_sha256))
            events = diff(self.repository.regulation(record_id), regulation)
            summary.reparsed += 1
            if events:
                summary.changed += 1
                self.repository.save_observation(
                    regulation, html_sha256=html_sha256, fingerprint=fingerprint(regulation), at=self.clock.now()
                )
                self.events.record(run_id, events, at=self.clock.now())
        return summary
