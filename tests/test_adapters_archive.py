"""Text from PDFs inside a .zip annex (live: the Perpres 10/2021 investment list is a zip of 4 PDFs)."""

from __future__ import annotations

import io
import zipfile

import pytest

from bpk_connector.adapters.extraction.archive import ArchiveTextExtractor
from bpk_connector.application.dto import ExtractedText
from bpk_connector.application.ports import NotExtractable


class EchoExtractor:
    """Pretends each PDF is one page holding its own bytes as text."""

    def extract(self, data: bytes, role="main") -> ExtractedText:
        if not data.startswith(b"%PDF"):
            raise NotExtractable("not a PDF")
        return ExtractedText(f"<!-- page 1 -->\n{data.decode()}", 1, 0, "text_layer")


def archive(members: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        for name, data in members.items():
            z.writestr(name, data)
    return buffer.getvalue()


def test_each_pdf_in_the_archive_is_extracted_in_name_order_with_a_file_marker() -> None:
    data = archive({"2. Lampiran I.pdf": b"%PDF annex", "1. Salinan Perpres.pdf": b"%PDF body", "readme.txt": b"x"})

    extracted = ArchiveTextExtractor(EchoExtractor()).extract(data)

    assert extracted.pages == 2 and extracted.method == "text_layer"
    assert extracted.text.index("<!-- file: 1. Salinan Perpres.pdf -->") < extracted.text.index(
        "<!-- file: 2. Lampiran I.pdf -->"
    )
    assert "%PDF annex" in extracted.text and "readme" not in extracted.text


def test_anything_that_is_not_an_archive_goes_straight_to_the_inner_extractor() -> None:
    assert ArchiveTextExtractor(EchoExtractor()).extract(b"%PDF plain").text.endswith("%PDF plain")


def test_an_archive_without_any_pdf_is_not_extractable() -> None:
    with pytest.raises(NotExtractable, match="no PDF"):
        ArchiveTextExtractor(EchoExtractor()).extract(archive({"table.xlsx": b"PK..."}))


def test_an_archive_that_would_unpack_too_large_is_refused() -> None:
    data = archive({"big.pdf": b"%PDF" + b"0" * 5000})

    with pytest.raises(NotExtractable, match="too large"):
        ArchiveTextExtractor(EchoExtractor(), max_unpacked_bytes=1000).extract(data)
