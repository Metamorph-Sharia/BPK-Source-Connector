"""``TextExtractor`` with pymupdf: the PDF's own text layer, page by page.

The rollback engine (``METAMORPH_PDF_ENGINE=pymupdf``): 98% of target pages have a text layer (measured
2026-10-13), and pages without one are counted as needing OCR, which MinerU does (mineru.py).

A page's text is a printed line to a line (``metamorph_contract.printed_text``): pymupdf's own lines split a
justified line set a word at a time, and a list's number from its text. ``printed_lines=False`` keeps pymupdf's
own lines, as before (``METAMORPH_PDF_LINES=extracted``, read in wiring).
"""

from __future__ import annotations

import pymupdf
from metamorph_contract import printed_text

from bpk_connector.application.dto import ExtractedText, Method
from bpk_connector.application.ports import NotExtractable
from bpk_connector.domain.file_roles import FileRole

pymupdf.TOOLS.mupdf_display_errors(False)  # MuPDF prints parser warnings to stdout, corrupting CLI JSON output

MIN_PAGE_CHARS = 50  # fewer: a scanned page, or only a page number or stamp
HEADER_WINDOW = 1024  # "%PDF" may sit anywhere in the first 1024 bytes; BPK serves some after "\r\n"
SIGNATURES = {b"PK\x03\x04": "zip", b"\xd0\xcf\x11\xe0": "old Office document"}


class PdfTextExtractor:
    def __init__(self, printed_lines: bool = True) -> None:
        self.printed_lines = printed_lines

    def extract(self, data: bytes, role: FileRole = FileRole.MAIN) -> ExtractedText:
        return compose(self.page_texts(data), Method.TEXT_LAYER)

    def page_texts(self, data: bytes) -> list[str]:
        """The text layer of each page, in order."""
        if not is_pdf(data):
            kind = next((name for magic, name in SIGNATURES.items() if data.startswith(magic)), "unknown format")
            raise NotExtractable(f"not a PDF: {kind}")
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except (pymupdf.FileDataError, RuntimeError) as e:
            raise NotExtractable(f"unreadable PDF: {e}") from e
        with doc:
            return [self._page_text(page).strip() for page in doc]

    def _page_text(self, page: pymupdf.Page) -> str:
        text = page.get_text()
        if not self.printed_lines:
            return text
        return printed_text(text, page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT))


def is_pdf(data: bytes) -> bool:
    return b"%PDF" in data[:HEADER_WINDOW]


def compose(pages: list[str], method: Method) -> ExtractedText:
    text = "\n\n".join(f"<!-- page {n} -->\n{content}" for n, content in enumerate(pages, start=1))
    return ExtractedText(text, len(pages), sum(not has_text(p) for p in pages), method)


def has_text(page: str) -> bool:
    return len(page) >= MIN_PAGE_CHARS
