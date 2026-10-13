"""``TextExtractor`` with pymupdf: the PDF's own text layer, page by page.

98% of target pages have a text layer (measured 2026-10-13); pages without one are counted so
they can be OCR'd once OCR tools are installed (``ocrmypdf`` + Tesseract ``ind``).
"""

from __future__ import annotations

import pymupdf

from bpk_connector.application.dto import ExtractedText, Method
from bpk_connector.application.ports import NotExtractable

pymupdf.TOOLS.mupdf_display_errors(False)  # MuPDF prints parser warnings to stdout, corrupting CLI JSON output

MIN_PAGE_CHARS = 50  # fewer: a scanned page, or only a page number or stamp
HEADER_WINDOW = 1024  # "%PDF" may sit anywhere in the first 1024 bytes; BPK serves some after "\r\n"
SIGNATURES = {b"PK\x03\x04": "zip", b"\xd0\xcf\x11\xe0": "old Office document"}


class PdfTextExtractor:
    def extract(self, data: bytes) -> ExtractedText:
        return compose(self.page_texts(data), Method.TEXT_LAYER)

    def page_texts(self, data: bytes) -> list[str]:
        """The text layer of each page, in order."""
        if b"%PDF" not in data[:HEADER_WINDOW]:
            kind = next((name for magic, name in SIGNATURES.items() if data.startswith(magic)), "unknown format")
            raise NotExtractable(f"not a PDF: {kind}")
        try:
            doc = pymupdf.open(stream=data, filetype="pdf")
        except (pymupdf.FileDataError, RuntimeError) as e:
            raise NotExtractable(f"unreadable PDF: {e}") from e
        with doc:
            return [page.get_text().strip() for page in doc]


def compose(pages: list[str], method: Method) -> ExtractedText:
    text = "\n\n".join(f"<!-- page {n} -->\n{content}" for n, content in enumerate(pages, start=1))
    return ExtractedText(text, len(pages), sum(not has_text(p) for p in pages), method)


def has_text(page: str) -> bool:
    return len(page) >= MIN_PAGE_CHARS
