"""FetchFiles: keep every official file of every target, byte-for-byte.

Downloads are conditional on the stored ETag, so a rerun downloads nothing unchanged.
Big files (UU 4/2023 is 82 MB) are budgeted: once a run has spent ``max_bytes``, the rest wait.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bpk_connector.application.dto import StoredFile
from bpk_connector.application.ports import BlobStore, BpkGateway, Clock, EventLog, FileTooLarge, NotFound, Repository
from bpk_connector.domain.models import ChangeEvent, FileRef


@dataclass
class FetchSummary:
    stored: int = 0
    unchanged: int = 0
    bytes: int = 0
    deferred: list[str] = field(default_factory=list)
    failed: list[str] = field(default_factory=list)


class FetchFiles:
    def __init__(
        self, gateway: BpkGateway, repository: Repository, events: EventLog, blobs: BlobStore, clock: Clock
    ) -> None:
        self.gateway = gateway
        self.repository = repository
        self.events = events
        self.blobs = blobs
        self.clock = clock

    def run(self, run_id: str, record_ids: list[str], *, max_bytes: int | None = None) -> FetchSummary:
        summary = FetchSummary()
        for record_id in record_ids:
            regulation = self.repository.regulation(record_id)
            for file in regulation.files if regulation else ():
                if max_bytes is not None and summary.bytes >= max_bytes:
                    summary.deferred.append(file.path)
                    continue
                if event := self._fetch(record_id, file, summary):
                    self.events.record(run_id, [event], at=self.clock.now())
        return summary

    def _fetch(self, record_id: str, file: FileRef, summary: FetchSummary) -> ChangeEvent | None:
        held = self.repository.file_state(record_id, file.path)
        try:
            download = self.gateway.download(file, held)
        except FileTooLarge as e:
            summary.deferred.append(file.path)
            return ChangeEvent("file_deferred", record_id, {**file.summary, "reason": str(e)})
        except NotFound:
            summary.failed.append(file.path)
            return ChangeEvent("file_missing", record_id, file.summary)
        if download.not_modified:
            summary.unchanged += 1
            return None
        stored = StoredFile(
            self.blobs.put(download.content),
            download.etag,
            len(download.content),
            download.media_type,
            download.url,
            download.last_modified,
        )
        self.repository.save_file(record_id, file, stored, at=self.clock.now())  # also refreshes the validators
        if held and held.sha256 == stored.sha256:
            summary.unchanged += 1
            return None
        summary.stored += 1
        summary.bytes += stored.size
        return ChangeEvent(
            "file_changed" if held else "file_stored", record_id, {**file.summary, "sha256": stored.sha256}
        )
