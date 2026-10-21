"""``TextExtractor`` with OCR (ocrmypdf + Tesseract), for pages a text layer can't be trusted on.

Pages without a text layer are OCR'd alone: cut into a small PDF, recognised, and merged back by page
number. Most target PDFs are fully text (UU 4/2023 is 82 MB); OCRing whole files would waste hours.
A text layer can itself be the publisher's OCR, and some of BPK's are bad: their article headings
are damaged (domain/text_quality.py). Then every page is recognised again, and the cleaner reading
is kept. Our own OCR left no damaged heading in any BPK file it read (2026-10-16).
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
from bpk_connector.domain.file_roles import FileRole
from bpk_connector.domain.text_quality import assess

log = logging.getLogger(__name__)
for noisy in ("ocrmypdf", "fontTools"):  # they log every page and font at INFO: floods orchestrator task logs
    logging.getLogger(noisy).setLevel(logging.WARNING)

DEFAULT_LANGUAGES = "ind+eng"  # Indonesian text, with English terms and citations
OCR_DPI = 300  # Tesseract's sweet spot for printed text
# Tesseract's "single column" layout. Its default analysis reads a hanging indent's markers ("(1)") as a
# column of their own, so they land away from their paragraphs and the parser loses ayat.
PAGE_SEGMENTATION = 4
# What OCR recognised is read as pymupdf sets it, not a printed line to a line (pdf.py): OCR finds stray marks
# beside a heading (a ":" or a table's "|"), and joined onto its line they hide it ("Pasal 172 :"). Measured on
# BPK's 40 OCR'd texts (2026-10-20): printed lines gave 3 more structure problems, omnibus laws' nesting changed.
RECOGNISED = PdfTextExtractor(printed_lines=False)


class OcrTextExtractor:
    def __init__(self, languages: str = DEFAULT_LANGUAGES, text_layer: PdfTextExtractor | None = None) -> None:
        self.languages = languages
        self.text_layer = text_layer or PdfTextExtractor()

    def extract(self, data: bytes, role: FileRole = FileRole.MAIN) -> ExtractedText:
        pages = self.text_layer.page_texts(data)
        missing = [n for n, page in enumerate(pages) if not has_text(page)]
        layer = assess(_joined(pages))
        to_read = list(range(len(pages))) if layer.is_damaged else missing
        if not to_read:
            return compose(pages, Method.TEXT_LAYER)
        try:
            recognised = dict(zip(to_read, self._ocr(data, to_read), strict=True))
        except ocrmypdf.exceptions.ExitCodeException as e:
            log.warning("OCR failed (%s); keeping the text layer only", e)
            return compose(pages, Method.TEXT_LAYER)
        read = [recognised.get(n, page) for n, page in enumerate(pages)]
        if layer.is_damaged and not assess(_joined(read)).reads_better_than(layer):
            log.info("OCR read no better than the damaged text layer (%s); keeping the text layer", layer)
            read = [recognised[n] if n in missing else page for n, page in enumerate(pages)]
        return compose(read, Method.OCR if read != pages else Method.TEXT_LAYER)

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
            tesseract_pagesegmode=PAGE_SEGMENTATION,
        )
        return RECOGNISED.page_texts(output.getvalue())


def _joined(pages: list[str]) -> str:
    return "\n".join(pages)


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
