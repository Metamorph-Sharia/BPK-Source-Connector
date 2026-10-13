"""``TextExtractor`` with OCR for pages that have no text layer (ocrmypdf + Tesseract).

Only those pages are OCR'd: they are cut into a small PDF, recognised, and merged back by page
number. Most target PDFs are fully text (UU 4/2023 is 82 MB); OCRing whole files would waste hours.
System requirements: Tesseract with Indonesian data, and Ghostscript (see README).
"""

from __future__ import annotations

import io
import logging
import shutil
import subprocess

import ocrmypdf
import pymupdf

from bpk_connector.adapters.extraction.pdf import PdfTextExtractor, compose, has_text
from bpk_connector.application.dto import ExtractedText, Method

log = logging.getLogger(__name__)
for noisy in ("ocrmypdf", "fontTools"):  # they log every page and font at INFO: floods orchestrator task logs
    logging.getLogger(noisy).setLevel(logging.WARNING)

DEFAULT_LANGUAGES = "ind+eng"  # Indonesian text, with English terms and citations
OCR_DPI = 300  # Tesseract's sweet spot for printed text


class OcrTextExtractor:
    def __init__(self, languages: str = DEFAULT_LANGUAGES, text_layer: PdfTextExtractor | None = None) -> None:
        self.languages = languages
        self.text_layer = text_layer or PdfTextExtractor()

    def extract(self, data: bytes) -> ExtractedText:
        pages = self.text_layer.page_texts(data)
        missing = [n for n, page in enumerate(pages) if not has_text(page)]
        if not missing:
            return compose(pages, Method.TEXT_LAYER)
        try:
            recognised = self._ocr(data, missing)
        except ocrmypdf.exceptions.ExitCodeException as e:
            log.warning("OCR failed (%s); keeping the text layer only", e)
            return compose(pages, Method.TEXT_LAYER)
        for n, text in zip(missing, recognised, strict=True):
            pages[n] = text
        return compose(pages, Method.OCR)

    def _ocr(self, data: bytes, page_numbers: list[int]) -> list[str]:
        output = io.BytesIO()
        ocrmypdf.ocr(
            io.BytesIO(_page_images(data, page_numbers)),
            output,
            language=self.languages.split("+"),
            output_type="pdf",
            optimize=0,
            progress_bar=False,
            use_threads=True,  # no worker processes: safe under the orchestrator and in tests
        )
        return self.text_layer.page_texts(output.getvalue())


def _page_images(data: bytes, page_numbers: list[int]) -> bytes:
    """The given pages as a PDF of plain images: no text, forms or signatures for OCR to trip over.

    The original file is never altered (it is stored byte-for-byte); this copy only feeds the OCR.
    """
    with pymupdf.open(stream=data, filetype="pdf") as source, pymupdf.open() as images:
        for n in page_numbers:
            page = source[n]
            picture = page.get_pixmap(dpi=OCR_DPI)
            images.new_page(width=page.rect.width, height=page.rect.height).insert_image(page.rect, pixmap=picture)
        return images.tobytes()


def ocr_problems(languages: str = DEFAULT_LANGUAGES) -> list[str]:
    """What's missing for OCR on this machine; empty when ready. Checked at startup so a server fails loudly."""
    problems = []
    if not shutil.which("tesseract"):
        return ["Tesseract is not installed"]
    installed = set(subprocess.run(["tesseract", "--list-langs"], capture_output=True, text=True).stdout.split())
    problems += [f"Tesseract has no {lang!r} language data" for lang in languages.split("+") if lang not in installed]
    if not shutil.which("gs"):
        problems.append("Ghostscript (gs) is not installed")
    return problems
