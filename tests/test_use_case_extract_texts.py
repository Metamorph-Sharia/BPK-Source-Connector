"""ExtractTexts: Indonesian text from every stored official file, once per file."""

from __future__ import annotations

from fakes.memory import NOW, FixedClock, MemoryBlobs, MemoryCatalog, MemoryEventLog, MemoryRepository

from bpk_connector.application.dto import ExtractedText, Method, StoredFile, StoredText
from bpk_connector.application.ports import NotExtractable
from bpk_connector.application.use_cases.extract_texts import ExtractTexts
from bpk_connector.domain.models import FileRef, Regulation, Target, TargetOrigin, Tier
from bpk_connector.domain.text_quality import TextQuality

LAW = FileRef("1", "PP.pdf", "/Download/1/PP.pdf")
ANNEX = FileRef("2", "Lampiran.zip", "/Download/2/Lampiran.zip")


class FakeExtractor:
    def __init__(self) -> None:
        self.calls = 0
        self.method = "text_layer"

    def extract(self, data: bytes) -> ExtractedText:
        self.calls += 1
        if data.startswith(b"PK"):
            raise NotExtractable("not a PDF: zip")
        missing = 1 if b"scan" in data and self.method == "text_layer" else 0
        heading = "Pasa1 2" if b"damaged" in data and self.method == "text_layer" else "Pasal 2"
        return ExtractedText(f"<!-- page 1 -->\nPasal 1\n{heading}\nPERATURAN PEMERINTAH", 3, missing, self.method)


def world(*files: tuple[FileRef, bytes]):
    repository, blobs, events = MemoryRepository(), MemoryBlobs(), MemoryEventLog()
    repository.observations["319773"] = Regulation(
        "319773", "PP 28/2025", "PP", "28", "2025", files=tuple(f for f, _ in files)
    )
    for ref, data in files:
        repository.save_file(
            "319773", ref, StoredFile(blobs.put(data), None, len(data), "application/pdf", "u"), at=NOW
        )
    extractor = FakeExtractor()
    seeds = MemoryCatalog([Target("319773", Tier.P1, TargetOrigin.SEED)])
    return ExtractTexts(repository, blobs, extractor, events, seeds, FixedClock()), repository, blobs, events, extractor


def test_each_file_gets_its_text_stored_with_its_coverage() -> None:
    use_case, repository, blobs, events, _ = world((LAW, b"%PDF law"))

    summary = use_case.run("run-1")

    file_sha = repository.file_state("319773", LAW.path).sha256
    text = repository.text_state(file_sha)
    assert blobs.get(text.text_sha256).decode().endswith("PERATURAN PEMERINTAH")
    assert (text.pages, text.coverage, text.method) == (3, 1.0, "text_layer")
    assert summary.extracted == 1 and events.kinds() == ["text_extracted"]


def test_a_file_already_extracted_is_not_extracted_again() -> None:
    use_case, _, _, _, extractor = world((LAW, b"%PDF law"))
    use_case.run("run-1")

    assert use_case.run("run-2").extracted == 0 and extractor.calls == 1


def test_pages_needing_ocr_are_reported() -> None:
    use_case, _, _, events, _ = world((LAW, b"%PDF scan"))

    summary = use_case.run("run-1")

    assert summary.needs_ocr == [LAW.path]
    assert events.kinds() == ["text_needs_ocr"] and events.events[0].detail["pages_without_text"] == 1


def test_a_file_that_is_not_a_document_is_recorded_as_unsupported_once() -> None:
    use_case, repository, _, _, extractor = world((ANNEX, b"PK\x03\x04"))

    summary = use_case.run("run-1")
    use_case.run("run-2")

    assert summary.unsupported == [ANNEX.path] and extractor.calls == 1
    assert repository.text_state(repository.file_state("319773", ANNEX.path).sha256).method == "unsupported"


def test_files_marked_unsupported_can_be_retried_after_an_extractor_fix() -> None:
    use_case, repository, _, _, extractor = world((ANNEX, b"PK\x03\x04"))
    use_case.run("run-1")

    use_case.run("run-2", retry_unsupported=True)

    assert extractor.calls == 2


def test_texts_extracted_before_ocr_was_available_are_upgraded_once() -> None:
    use_case, repository, _, _, extractor = world((LAW, b"%PDF scan"))
    use_case.run("run-1")  # text layer only: one page without text
    extractor.method = "ocr"  # OCR tools installed since

    upgraded = with_ocr(use_case, repository, extractor)
    upgraded.run("run-2")
    upgraded.run("run-3")

    assert extractor.calls == 2  # once without OCR, once with; never again
    assert repository.text_state(repository.file_state("319773", LAW.path).sha256).method == "ocr"


def with_ocr(use_case: ExtractTexts, repository: MemoryRepository, extractor: FakeExtractor) -> ExtractTexts:
    return ExtractTexts(
        repository, use_case.blobs, extractor, MemoryEventLog(), use_case.catalog, FixedClock(), ocr_available=True
    )


def test_each_text_is_stored_with_how_well_its_article_headings_read() -> None:
    use_case, repository, _, _, _ = world((LAW, b"%PDF law"))

    use_case.run("run-1")

    assert repository.text_state(repository.file_state("319773", LAW.path).sha256).quality == TextQuality(2, 0)


def test_a_text_whose_headings_are_still_damaged_is_reported() -> None:
    # e.g. no OCR on this machine, or OCR read the page no better than the publisher's text layer
    use_case, repository, _, events, _ = world((LAW, b"%PDF damaged"))

    summary = use_case.run("run-1")

    assert summary.damaged == [LAW.path]
    assert events.kinds() == ["text_damaged"] and events.events[0].detail["damaged_headings"] == 1


def test_texts_extracted_before_their_quality_was_assessed_are_extracted_again_once_ocr_is_available() -> None:
    use_case, repository, _, _, extractor = world((LAW, b"%PDF damaged"))
    file_sha = repository.file_state("319773", LAW.path).sha256
    repository.save_text(StoredText(file_sha, "old", Method.TEXT_LAYER, pages=3), at=NOW)  # quality unknown
    extractor.method = "ocr"  # the extractor now reads damaged text layers again from the page images

    upgraded = with_ocr(use_case, repository, extractor)
    upgraded.run("run-1")
    upgraded.run("run-2")

    assert extractor.calls == 1
    assert repository.text_state(file_sha).quality == TextQuality(2, 0)


def test_a_text_still_damaged_after_ocr_is_not_extracted_again_every_run() -> None:
    use_case, repository, _, _, extractor = world((LAW, b"%PDF damaged"))
    upgraded = with_ocr(use_case, repository, extractor)

    upgraded.run("run-1")
    upgraded.run("run-2")

    assert extractor.calls == 1
