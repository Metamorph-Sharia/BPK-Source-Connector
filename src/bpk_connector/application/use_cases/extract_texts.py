"""ExtractTexts: Indonesian text from every stored official file of every target, once per file.

Keyed by the file's sha256, so a rerun extracts nothing new and a replaced file is extracted again.
Text we extract from an official file is ``self_extracted`` and ``public``.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bpk_connector.application.dto import Method, StoredText
from bpk_connector.application.ports import (
    BlobStore,
    Clock,
    EventLog,
    NotExtractable,
    Repository,
    TargetCatalog,
    TextExtractor,
)
from bpk_connector.application.targets import all_targets
from bpk_connector.domain.models import ChangeEvent, FileRef


@dataclass
class ExtractSummary:
    extracted: int = 0
    pages: int = 0
    needs_ocr: list[str] = field(default_factory=list)
    unsupported: list[str] = field(default_factory=list)


class ExtractTexts:
    def __init__(
        self,
        repository: Repository,
        blobs: BlobStore,
        extractor: TextExtractor,
        events: EventLog,
        catalog: TargetCatalog,
        clock: Clock,
        *,
        upgrade_incomplete: bool = False,
    ) -> None:
        self.repository = repository
        self.blobs = blobs
        self.extractor = extractor
        self.events = events
        self.catalog = catalog
        self.clock = clock
        # When the extractor can OCR: re-extract, once, texts the text layer alone left incomplete.
        self.upgrade_incomplete = upgrade_incomplete

    def run(self, run_id: str, *, retry_unsupported: bool = False) -> ExtractSummary:
        summary = ExtractSummary()
        for record_id in all_targets(self.repository, self.catalog):
            regulation = self.repository.regulation(record_id)
            for ref in regulation.files if regulation else ():
                stored = self.repository.file_state(record_id, ref.path)
                if stored and self._due(stored.sha256, retry_unsupported):
                    event = self._extract(record_id, ref, stored.sha256, summary)
                    self.events.record(run_id, [event], at=self.clock.now())
        return summary

    def _due(self, file_sha256: str, retry_unsupported: bool) -> bool:
        held = self.repository.text_state(file_sha256)
        if held is None:
            return True
        if held.method == Method.UNSUPPORTED:
            return retry_unsupported
        return self.upgrade_incomplete and held.method == Method.TEXT_LAYER and held.pages_without_text > 0

    def _extract(self, record_id: str, ref: FileRef, file_sha256: str, summary: ExtractSummary) -> ChangeEvent:
        try:
            extracted = self.extractor.extract(self.blobs.get(file_sha256))
        except NotExtractable as e:
            self.repository.save_text(
                StoredText(file_sha256, None, Method.UNSUPPORTED, note=str(e)), at=self.clock.now()
            )
            summary.unsupported.append(ref.path)
            return ChangeEvent("text_unsupported", record_id, {**ref.summary, "reason": str(e)})
        text = StoredText(
            file_sha256,
            self.blobs.put(extracted.text.encode("utf-8")),
            extracted.method,
            extracted.pages,
            extracted.pages_without_text,
            len(extracted.text),
        )
        self.repository.save_text(text, at=self.clock.now())
        summary.extracted += 1
        summary.pages += extracted.pages
        if extracted.needs_ocr:
            summary.needs_ocr.append(ref.path)
        detail = {**ref.summary, "pages": extracted.pages, "pages_without_text": extracted.pages_without_text}
        kind = "text_needs_ocr" if extracted.needs_ocr else "text_extracted"
        return ChangeEvent(kind, record_id, detail | {"coverage": extracted.coverage})
