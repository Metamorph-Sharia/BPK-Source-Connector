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


ARTICLES = ["Pasal 1", "Pasal 2", "Pasal 3"]
DAMAGED = ["Pasa1 1", "Pasa1 2", "Pasa1 3"]  # as publisher OCR left them in BPK's text layers


def picture_of(lines: list[str], *, layer: list[str] | None = None):
    """A page that shows ``lines`` as an image, with ``layer`` as its invisible text layer, as a scan
    the publisher OCR'd: the text layer is what their OCR made of the image."""

    def build(doc: pymupdf.Document) -> None:
        source = pymupdf.open()
        drawn = source.new_page()
        for n, line in enumerate(lines):
            drawn.insert_text((250, 80 + 60 * n), line, fontsize=12)
            drawn.insert_text((60, 100 + 60 * n), BODY, fontsize=12)
        page = doc.new_page()
        page.insert_image(page.rect, pixmap=drawn.get_pixmap(dpi=300))
        for n, line in enumerate(layer or []):
            page.insert_text((250, 80 + 60 * n), line, fontsize=12, render_mode=3)  # invisible, as OCR text is
            page.insert_text((60, 100 + 60 * n), BODY, fontsize=12, render_mode=3)

    return build


def test_a_text_layer_with_ocr_damaged_headings_is_read_again_from_the_page_images() -> None:
    extracted = OcrTextExtractor("ind").extract(pdf(picture_of(ARTICLES, layer=DAMAGED)))

    assert extracted.method == "ocr"
    assert [line.strip() for line in extracted.text.splitlines() if line.strip().startswith("Pasa")] == ARTICLES


def test_a_damaged_text_layer_is_kept_when_reading_the_images_does_no_better() -> None:
    blank = picture_of([], layer=DAMAGED)  # nothing to read on the image

    extracted = OcrTextExtractor("ind").extract(pdf(blank))

    assert extracted.method == "text_layer" and "Pasa1 2" in extracted.text


def test_paragraph_markers_in_a_hanging_indent_stay_in_front_of_their_paragraph() -> None:
    # Tesseract's default layout analysis reads the marker column apart from the text: "(1)" is lost
    # and the parser reports ayat (1) missing. Read as one column, each marker stays in place.
    def hanging_indent(doc: pymupdf.Document) -> None:
        source = pymupdf.open()
        drawn, y = source.new_page(), 80
        drawn.insert_text((250, y), "Pasal 3", fontsize=11)
        for marker in ("(1)", "(2)", "(3)"):
            y += 24
            drawn.insert_text((72, y), marker, fontsize=11)
            for line in (BODY, HEADING.title(), "sebagaimana dimaksud dalam ayat ini."):
                drawn.insert_text((110, y), line, fontsize=11)
                y += 15
        page = doc.new_page()
        page.insert_image(page.rect, pixmap=drawn.get_pixmap(dpi=300))

    text = OcrTextExtractor("ind").extract(pdf(hanging_indent)).text

    markers = [line.strip() for line in text.splitlines() if line.strip() in ("(1)", "(2)", "(3)")]
    assert markers == ["(1)", "(2)", "(3)"]
    assert text.index("Pasal 3") < text.index("(1)") < text.index(BODY[:20]) < text.index("(2)")
