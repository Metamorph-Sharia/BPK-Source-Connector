"""``TextExtractor`` for .zip annexes: extracts each PDF inside, in name order.

Live case: the Perpres 10/2021 annex (the positive investment list) is a zip of the regulation and
Annexes I-III. Archives are untrusted data: read in memory only (nothing written to disk) and
refused when they would unpack beyond a size cap.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable
from dataclasses import replace

from bpk_connector.application.dto import ExtractedText, Extraction, Method
from bpk_connector.application.ports import NotExtractable, TextExtractor
from bpk_connector.domain.file_roles import FileRole

ZIP_MAGIC = b"PK\x03\x04"
DEFAULT_MAX_UNPACKED_BYTES = 500 * 1024 * 1024


class ArchiveTextExtractor:
    def __init__(self, inner: TextExtractor, *, max_unpacked_bytes: int = DEFAULT_MAX_UNPACKED_BYTES) -> None:
        self.inner = inner
        self.max_unpacked_bytes = max_unpacked_bytes

    def extract(self, data: bytes, role: FileRole = FileRole.MAIN) -> ExtractedText:
        if not data.startswith(ZIP_MAGIC):
            return self.inner.extract(data, role)
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = sorted(
                (m for m in archive.infolist() if m.filename.lower().endswith(".pdf")), key=lambda m: m.filename
            )
            if not members:
                raise NotExtractable("zip with no PDF inside")
            if sum(m.file_size for m in members) > self.max_unpacked_bytes:
                raise NotExtractable(f"zip too large to unpack (over {self.max_unpacked_bytes} bytes)")
            parts = [(m.filename, self.inner.extract(archive.read(m), role)) for m in members]
        return _combine(parts)


def _combine(parts: list[tuple[str, ExtractedText]]) -> ExtractedText:
    texts = [extracted for _, extracted in parts]
    return ExtractedText(
        "\n\n".join(f"<!-- file: {name} -->\n{extracted.text}" for name, extracted in parts),
        sum(t.pages for t in texts),
        sum(t.pages_without_text for t in texts),
        Method.OCR if any(t.method is Method.OCR for t in texts) else Method.TEXT_LAYER,
        _combined(t.extraction for t in texts),
    )


def _combined(extractions: Iterable[Extraction | None]) -> Extraction | None:
    """How the archive's PDFs were read, as one: the engine's, with every PDF's OCR'd and fallen-back pages."""
    read = [extraction for extraction in extractions if extraction is not None]
    if not read:
        return None
    ocr_mode = "ocr" if any(extraction.ocr_mode == "ocr" for extraction in read) else read[0].ocr_mode
    return replace(
        read[0],
        ocr_mode=ocr_mode,
        pages_ocrd=sum(extraction.pages_ocrd for extraction in read),
        pages_fallen_back=sum(extraction.pages_fallen_back for extraction in read),
    )
