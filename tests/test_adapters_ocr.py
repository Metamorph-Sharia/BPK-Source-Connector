"""OCR of pages without a text layer (ocrmypdf + Tesseract "ind"), on PDFs made in the test."""

from __future__ import annotations

import pymupdf
import pytest

from bpk_connector.adapters.extraction.ocr import OcrTextExtractor, ocr_problems

pytestmark = pytest.mark.skipif(
    bool(ocr_problems("ind")), reason="OCR tools not installed: " + "; ".join(ocr_problems("ind"))
)

HEADING = "PERATURAN MENTERI KOORDINATOR BIDANG PEREKONOMIAN"
BODY = "Pedoman Pelaksanaan Kredit Usaha Rakyat bagi penyalur dan penerima kredit"


def text_page(doc: pymupdf.Document) -> None:
    page = doc.new_page()
    page.insert_text((60, 80), HEADING, fontsize=12)
    page.insert_text((60, 100), BODY, fontsize=12)


def scanned_page(doc: pymupdf.Document) -> None:
    """A page that is only a picture of text, as BPK's scanned regulations are."""
    source = pymupdf.open()
    text_page(source)
    picture = source[0].get_pixmap(dpi=300)
    page = doc.new_page()
    page.insert_image(page.rect, pixmap=picture)


def pdf(*builders) -> bytes:
    doc = pymupdf.open()
    for build in builders:
        build(doc)
    return doc.tobytes()


def test_pages_without_a_text_layer_are_ocrd_and_merged_back_in_page_order() -> None:
    extracted = OcrTextExtractor("ind").extract(pdf(text_page, scanned_page, text_page))

    pages = extracted.text.split("<!-- page ")
    assert extracted.method == "ocr" and extracted.pages == 3 and extracted.pages_without_text == 0
    assert "KREDIT USAHA RAKYAT" in pages[2].upper()  # page 2 came from OCR
    assert pages[1].startswith("1 -->") and pages[3].startswith("3 -->")


def test_a_pdf_with_a_full_text_layer_is_not_ocrd() -> None:
    extracted = OcrTextExtractor("ind").extract(pdf(text_page))

    assert extracted.method == "text_layer"


def test_missing_tools_are_reported_by_name() -> None:
    assert ocr_problems("xx-not-a-language") == ["Tesseract has no 'xx-not-a-language' language data"]


def signed(doc: pymupdf.Document) -> bytes:
    """A document carrying a signature field, as the Constitutional Court's rulings do."""
    widget = pymupdf.Widget()
    widget.field_type = pymupdf.PDF_WIDGET_TYPE_SIGNATURE
    widget.field_name = "Signature1"
    widget.rect = pymupdf.Rect(60, 700, 260, 760)
    doc[0].add_widget(widget)
    return doc.tobytes()


def test_a_digitally_signed_pdf_is_still_ocrd_because_only_page_images_are_recognised() -> None:
    # Live: ocrmypdf refuses signed PDFs ("OCR would alter the document"); we never alter the original.
    doc = pymupdf.open(stream=pdf(scanned_page, text_page), filetype="pdf")

    extracted = OcrTextExtractor("ind").extract(signed(doc))

    assert extracted.method == "ocr" and "KREDIT USAHA RAKYAT" in extracted.text.upper()
