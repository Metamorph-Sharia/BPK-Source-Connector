"""MinerU as BPK's text extractor (METAMORPH_PDF_ENGINE=mineru): what it reads, how that is stored and exported."""

from __future__ import annotations

import io
import zipfile
from dataclasses import replace
from pathlib import Path

import pytest
from fakes.memory import NOW
from metamorph_contract import Extraction as ContractExtraction
from metamorph_pdf_text import ExtractedPdf, ExtractionFailed, OcrMode, Tier
from metamorph_pdf_text import Extraction as Read
from test_adapters_v2_bundle import bundle_document, write

from bpk_connector import wiring
from bpk_connector.adapters.extraction.archive import ArchiveTextExtractor
from bpk_connector.adapters.extraction.mineru import MinerUTextExtractor
from bpk_connector.adapters.storage.blobs import FileBlobStore
from bpk_connector.adapters.storage.sqlite import SqliteStore
from bpk_connector.application.dto import Extraction, Method, StoredText
from bpk_connector.application.ports import NotExtractable
from bpk_connector.config import Config
from bpk_connector.domain.file_roles import FileRole

PDF = b"%PDF-1.7 PP 28/2025"
EXTRACTION = Extraction("mineru", "4.0.12+t1", "basic", "ocr", pages_ocrd=2, pages_fallen_back=0)


class FakeMinerU:
    """ExtractPdf as the adapter needs it: what MinerU read, and the role each file was read as."""

    def __init__(self, *pages: str, failing: bool = False) -> None:
        read = Read("mineru", "4.0.12+t1", Tier.BASIC, OcrMode.OCR, pages_ocrd=len(pages), pages_fallen_back=0)
        self.read, self.failing, self.roles = ExtractedPdf(pages, "ocr", read, ()), failing, []

    def run(self, pdf: bytes, role: str) -> ExtractedPdf:
        self.roles.append(role)
        if self.failing:
            raise ExtractionFailed("encrypted")
        return self.read


def test_minerus_pages_are_the_text_read_with_how_they_were_read() -> None:
    mineru = FakeMinerU("Pasal 1\nSetiap Orang wajib.", "Pasal 2\nCukup jelas.")

    extracted = MinerUTextExtractor(mineru).extract(PDF, FileRole.ANNEX)

    assert extracted.text == "<!-- page 1 -->\nPasal 1\nSetiap Orang wajib.\n\n<!-- page 2 -->\nPasal 2\nCukup jelas."
    assert (extracted.pages, extracted.method, extracted.extraction) == (2, Method.OCR, EXTRACTION)
    assert mineru.roles == ["annex"]  # an annex is read with the small models


def test_a_file_that_isnt_a_pdf_or_that_mineru_cant_read_is_not_extractable() -> None:
    with pytest.raises(NotExtractable, match="not a PDF"):
        MinerUTextExtractor(FakeMinerU("x")).extract(b"PK\x03\x04 a zip")
    with pytest.raises(NotExtractable, match="encrypted"):
        MinerUTextExtractor(FakeMinerU("x", failing=True)).extract(PDF)


def test_a_zip_of_pdfs_read_by_mineru_counts_every_pdfs_pages() -> None:
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as zipped:
        zipped.writestr("1.pdf", PDF)
        zipped.writestr("2.pdf", PDF)

    extracted = ArchiveTextExtractor(MinerUTextExtractor(FakeMinerU("Lampiran I"))).extract(archive.getvalue())

    assert extracted.extraction == replace(EXTRACTION, pages_ocrd=2)


def test_how_a_text_was_read_is_stored_with_it(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "bpk.db")
    store.save_text(StoredText("f" * 64, "t" * 64, Method.OCR, 2, extraction=EXTRACTION), at=NOW)

    assert store.text_state("f" * 64).extraction == EXTRACTION


def test_a_text_read_before_mineru_has_no_extraction(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "bpk.db")
    store.save_text(StoredText("f" * 64, "t" * 64, Method.TEXT_LAYER, 2), at=NOW)

    assert store.text_state("f" * 64).extraction is None


def test_the_bundle_records_how_the_text_was_read(tmp_path: Path) -> None:
    blobs = FileBlobStore(tmp_path / "raw")
    document = bundle_document(blobs)
    main = document.files[0]
    read = replace(main, text=replace(main.text, extraction=EXTRACTION))

    bundle = write(tmp_path, blobs, replace(document, files=(read, *document.files[1:])))

    [text] = next(bundle.entries()).document.texts
    assert text.extraction == ContractExtraction("mineru", "4.0.12+t1", "basic", "ocr", 2, 0)


def test_the_engine_setting_chooses_mineru_and_needs_no_tesseract(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("METAMORPH_PDF_ENGINE", "mineru")
    monkeypatch.setenv("METAMORPH_MINERU_URL", "http://mineru.test:8010")
    monkeypatch.setenv("METAMORPH_MINERU_CACHE", str(tmp_path / "cache"))
    config = Config(tmp_path / "pipeline.toml", tmp_path, tmp_path / "t.csv", tmp_path / "w.toml", "test", ocr=True)

    assert isinstance(wiring.build_extractor(config).inner, MinerUTextExtractor)
    assert wiring.environment_problems(config) == []
