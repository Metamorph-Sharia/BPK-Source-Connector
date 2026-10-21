"""Text-layer extraction with pymupdf, on PDFs made in the test (a text page, a blank 'scanned' page)."""

from __future__ import annotations

import pymupdf
import pytest

from bpk_connector.adapters.extraction.pdf import PdfTextExtractor
from bpk_connector.application.ports import NotExtractable
from bpk_connector.config import Config
from bpk_connector.wiring import build_extractor

BODY = "Dengan Rahmat Tuhan Yang Maha Esa, Presiden Republik Indonesia, menimbang bahwa"


def pdf(*pages: str) -> bytes:
    """Each non-empty page gets its heading plus a realistic line of body text."""
    doc = pymupdf.open()
    for text in pages:
        page = doc.new_page()
        if text:
            page.insert_text((72, 72), text)
            page.insert_text((72, 90), BODY)
    return doc.tobytes()


def set_apart() -> bytes:
    """A justified line set a word at a time, and a list's number set apart from its text, as BI and BPK PDFs do."""
    doc = pymupdf.open()
    page = doc.new_page()
    for n, word in enumerate(["selanjutnya", "disebut", "Pengolahan", "adalah", "kegiatan"]):
        page.insert_text((72 + 80 * n, 100), word)
    page.insert_text((72, 130), "1.")
    page.insert_text((100, 130), "Uang Rupiah adalah alat pembayaran")
    return doc.tobytes()


def test_each_printed_line_is_one_line_of_the_text() -> None:
    assert PdfTextExtractor().page_texts(set_apart()) == [
        "selanjutnya disebut Pengolahan adalah kegiatan\n1. Uang Rupiah adalah alat pembayaran"
    ]


def test_pymupdfs_own_lines_are_kept_when_asked_for() -> None:
    assert PdfTextExtractor(printed_lines=False).page_texts(set_apart()) == [
        "selanjutnya\ndisebut\nPengolahan\nadalah\nkegiatan\n1.\nUang Rupiah adalah alat pembayaran"
    ]


def test_extraction_lines_follow_the_metamorph_pdf_lines_setting(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    config = Config(tmp_path / "pipeline.toml", tmp_path, tmp_path / "t.csv", tmp_path / "w.toml", "test", ocr=False)

    monkeypatch.setenv("METAMORPH_PDF_LINES", "extracted")
    assert build_extractor(config).extract(set_apart()).text.count("\n") > 3
    monkeypatch.delenv("METAMORPH_PDF_LINES")
    assert "selanjutnya disebut" in build_extractor(config).extract(set_apart()).text


def test_text_is_extracted_page_by_page_with_markers() -> None:
    extracted = PdfTextExtractor().extract(pdf("PERATURAN PEMERINTAH NOMOR 28 TAHUN 2025", "Pasal 1 ketentuan umum"))

    assert extracted.pages == 2 and extracted.pages_without_text == 0 and extracted.method == "text_layer"
    assert extracted.text.startswith("<!-- page 1 -->\nPERATURAN PEMERINTAH NOMOR 28 TAHUN 2025")
    assert "<!-- page 2 -->\nPasal 1" in extracted.text
    assert extracted.coverage == 1.0 and not extracted.needs_ocr


def test_pages_without_a_text_layer_are_counted_as_needing_ocr() -> None:
    extracted = PdfTextExtractor().extract(pdf("PERATURAN MENTERI KOORDINATOR", ""))

    assert extracted.pages_without_text == 1 and extracted.needs_ocr and extracted.coverage == 0.5


def test_a_file_that_is_not_a_pdf_is_not_extractable() -> None:
    with pytest.raises(NotExtractable, match="zip"):
        PdfTextExtractor().extract(b"PK\x03\x04 zipped annex")


def test_a_pdf_header_after_a_few_stray_bytes_is_still_a_pdf() -> None:
    # Live: BPK serves Permenko 1/2022 and 1/2023 with two bytes before "%PDF"; the spec allows 1024.
    extracted = PdfTextExtractor().extract(b"\r\n" + pdf("PERATURAN MENTERI KOORDINATOR BIDANG PEREKONOMIAN"))

    assert extracted.pages == 1 and not extracted.needs_ocr
