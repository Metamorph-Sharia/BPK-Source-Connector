"""``TextExtractor`` with MinerU (metamorph-pdf-text): the file read by a layout model, its page furniture removed
("SK No 054949 C", the running head, the printed page number), each page checked against the PDF's own text
layer, which a page falls back to when MinerU's reading of it can't be trusted.

It replaces both the text layer and OCR: MinerU OCRs a scanned page, and a publisher's poor OCR layer, itself.
Chosen by METAMORPH_PDF_ENGINE=mineru (wiring.py). A MinerU service out of reach raises
``ExtractionUnavailable``, so the run stops and is run again; nothing falls back to the other engine.
"""

from __future__ import annotations

from dataclasses import replace

from metamorph_pdf_text import ExtractionFailed, ExtractPdf, text_extraction

from bpk_connector.adapters.extraction.pdf import SIGNATURES, compose, is_pdf
from bpk_connector.application.dto import ExtractedText, Extraction, Method
from bpk_connector.application.ports import NotExtractable
from bpk_connector.domain.file_roles import FileRole


class MinerUTextExtractor:
    def __init__(self, extract: ExtractPdf) -> None:
        self.extract_pdf = extract

    def extract(self, data: bytes, role: FileRole = FileRole.MAIN) -> ExtractedText:
        if not is_pdf(data):
            kind = next((name for magic, name in SIGNATURES.items() if data.startswith(magic)), "unknown format")
            raise NotExtractable(f"not a PDF: {kind}")
        try:
            read = self.extract_pdf.run(data, str(role))
        except ExtractionFailed as e:
            raise NotExtractable(f"unreadable PDF: {e}") from e
        extracted = compose(list(read.pages), Method(read.method))
        return replace(extracted, extraction=Extraction(**vars(text_extraction(read))))
