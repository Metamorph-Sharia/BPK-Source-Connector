"""ExtractTexts: Indonesian text from every stored official file of every target, once per file.

Keyed by the file's sha256, so a rerun extracts nothing new and a replaced file is extracted again.
Each text is stored with how well its article headings read (domain/text_quality.py); one whose
headings are still OCR-damaged is reported, because the structure parser turns each into a cascade.
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
from bpk_connector.domain.file_roles import FileRole, file_roles
from bpk_connector.domain.models import ChangeEvent, FileRef
from bpk_connector.domain.text_quality import assess


@dataclass
class ExtractSummary:
    extracted: int = 0
    pages: int = 0
    needs_ocr: list[str] = field(default_factory=list)
    damaged: list[str] = field(default_factory=list)  # article headings still OCR-damaged
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
        ocr_available: bool = False,
    ) -> None:
        self.repository = repository
        self.blobs = blobs
        self.extractor = extractor
        self.events = events
        self.catalog = catalog
        self.clock = clock
        # When the extractor can OCR, texts it can now do better are extracted again, once: those the text
        # layer alone left incomplete, and those extracted before quality was assessed (their text layer
        # may be the publisher's damaged OCR, which the extractor now reads again).
        self.ocr_available = ocr_available

    def run(self, run_id: str, *, retry_unsupported: bool = False, again: bool = False) -> ExtractSummary:
        """`again`: every stored file, extracted before or not (after a change to how text is read)."""
        summary = ExtractSummary()
        for record_id in all_targets(self.repository, self.catalog):
            regulation = self.repository.regulation(record_id)
            roles = file_roles(regulation.files) if regulation else {}
            for ref in regulation.files if regulation else ():
                stored = self.repository.file_state(record_id, ref.path)
                if stored and (again or self._due(stored.sha256, retry_unsupported)):
                    event = self._extract(record_id, ref, roles[ref.path], stored.sha256, summary)
                    self.events.record(run_id, [event], at=self.clock.now())
        return summary

    def _due(self, file_sha256: str, retry_unsupported: bool) -> bool:
        held = self.repository.text_state(file_sha256)
        if held is None:
            return True
        if held.method == Method.UNSUPPORTED:
            return retry_unsupported
        if not self.ocr_available:
            return False
        return held.quality is None or (held.method == Method.TEXT_LAYER and held.pages_without_text > 0)

    def _extract(
        self, record_id: str, ref: FileRef, role: FileRole, file_sha256: str, summary: ExtractSummary
    ) -> ChangeEvent:
        try:
            extracted = self.extractor.extract(self.blobs.get(file_sha256), role)
        except NotExtractable as e:
            self.repository.save_text(
                StoredText(file_sha256, None, Method.UNSUPPORTED, note=str(e)), at=self.clock.now()
            )
            summary.unsupported.append(ref.path)
            return ChangeEvent("text_unsupported", record_id, {**ref.summary, "reason": str(e)})
        quality = assess(extracted.text)
        text = StoredText(
            file_sha256,
            self.blobs.put(extracted.text.encode("utf-8")),
            extracted.method,
            extracted.pages,
            extracted.pages_without_text,
            len(extracted.text),
            quality=quality,
            extraction=extracted.extraction,
        )
        self.repository.save_text(text, at=self.clock.now())
        summary.extracted += 1
        summary.pages += extracted.pages
        if extracted.needs_ocr:
            summary.needs_ocr.append(ref.path)
        if quality.is_damaged:
            summary.damaged.append(ref.path)
        detail = {**ref.summary, "pages": extracted.pages, "pages_without_text": extracted.pages_without_text}
        detail |= {"coverage": extracted.coverage, "damaged_headings": quality.damaged_headings}
        return ChangeEvent(_event_kind(extracted.needs_ocr, quality.is_damaged), record_id, detail)


def _event_kind(needs_ocr: bool, damaged: bool) -> str:
    if needs_ocr:
        return "text_needs_ocr"
    return "text_damaged" if damaged else "text_extracted"
