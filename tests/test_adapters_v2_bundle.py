"""V2BundleWriter: BundleDocuments → a contract v2 bundle the platform loader accepts."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from metamorph_contract import Bundle, Confidence, FileRole, Kind, Relation, Status, split_pages

from bpk_connector.adapters.storage.blobs import FileBlobStore
from bpk_connector.adapters.storage.v2_bundle import V2BundleWriter
from bpk_connector.application.dto import BundleCitation, BundleDocument, BundleFile, Method, StoredFile, StoredText
from bpk_connector.domain import file_roles
from bpk_connector.domain.models import FileRef, Regulation

FETCHED = datetime(2026, 10, 12, 5, 0, tzinfo=UTC)
P2SK = Regulation(
    "240203", "Undang-undang (UU) Nomor 4 Tahun 2023 tentang Pengembangan dan Penguatan Sektor Keuangan",
    "UU", "4", "2023", status="Berlaku", enacted_on=date(2023, 1, 12), promulgated_on=date(2023, 1, 12),
    fields={"Judul": "UU 4/2023", "Alias": "UU No. 4 Tahun 2023 • UU 4/2023 • UU Nomor 4 Tahun 2023"},
)  # fmt: skip


def bundle_document(blobs: FileBlobStore, **changes) -> BundleDocument:
    law = blobs.put(b"%PDF law")
    annex = blobs.put(b"%PDF annex")
    ruling = blobs.put(b"%PDF ruling")
    text = blobs.put(b"<!-- page 1 -->\nUNDANG-UNDANG\n\n<!-- page 2 -->\nPasal 1")
    values = {
        "regulation": P2SK,
        "canonical_id": "id:uu:2023:4",
        "id_conflict": False,
        "standing": "amended",
        "files": (
            BundleFile(FileRef("1", "UU 4 2023.pdf", "/Download/1/UU.pdf"),
                       StoredFile(law, None, 8, "application/pdf", "https://bpk/1", fetched_at=FETCHED),
                       StoredText(law, text, Method.OCR, pages=2), file_roles.FileRole.MAIN),
            BundleFile(FileRef("3", "UU 4 2023 - Lampiran.pdf", "/Download/3/Lampiran.pdf"),
                       StoredFile(annex, None, 10, "application/pdf", "https://bpk/3", fetched_at=FETCHED), None,
                       file_roles.FileRole.ANNEX),
            BundleFile(FileRef("2", "Putusan MK.pdf", "/Download/2/MK.pdf", category="UjiMateri"),
                       StoredFile(ruling, None, 11, "application/pdf", "https://bpk/2", fetched_at=FETCHED), None,
                       file_roles.FileRole.OTHER),
        ),
        "citations": (BundleCitation("amends", "Mengubah", "UU No. 40 Tahun 2014", "Perasuransian", "id:uu:2014:40"),),
        "fetched_at": FETCHED,
    }  # fmt: skip
    return BundleDocument(**(values | changes))


def write(tmp_path: Path, blobs: FileBlobStore, *documents: BundleDocument) -> Bundle:
    V2BundleWriter(tmp_path / "bundle", blobs, run_id="r1", connector_version="0.1.0").write(list(documents))
    return Bundle(tmp_path / "bundle")


def test_a_regulation_becomes_a_valid_contract_document(tmp_path: Path) -> None:
    blobs = FileBlobStore(tmp_path / "raw")

    bundle = write(tmp_path, blobs, bundle_document(blobs))

    assert (bundle.manifest.connector, bundle.manifest.documents) == ("bpk", 1)
    [entry] = list(bundle.entries())
    assert entry.is_valid, entry.problems
    document = entry.document
    assert document.source.source_id == "bpk:240203"  # the interface connector's key for the same record
    assert document.source.url == "https://peraturan.bpk.go.id/Details/240203"
    assert document.source.fetched_at == FETCHED.isoformat()
    info = document.document
    assert (info.id, info.id_confidence, info.issuer, info.family, info.kind) == (
        "id:uu:2023:4",
        Confidence.HIGH,
        "id",
        "uu",
        Kind.LAW,
    )
    assert info.citation == "UU No. 4 Tahun 2023"
    assert info.title == "Pengembangan dan Penguatan Sektor Keuangan"
    assert info.aliases == (
        "UU No. 4 Tahun 2023", "UU 4/2023", "UU Nomor 4 Tahun 2023", "Undang-undang Nomor 4 Tahun 2023"
    )  # fmt: skip
    assert (info.status.value, info.status.source) == (Status.AMENDED, "bpk")
    assert (info.dates.enacted, info.dates.effective) == ("2023-01-12", None)


def test_files_texts_and_citations_are_carried(tmp_path: Path) -> None:
    blobs = FileBlobStore(tmp_path / "raw")

    bundle = write(tmp_path, blobs, bundle_document(blobs))

    document = next(bundle.entries()).document
    assert [(f.role, f.title) for f in document.files] == [
        (FileRole.MAIN, None), (FileRole.ANNEX, "UU 4 2023 - Lampiran.pdf"), (FileRole.OTHER, "Putusan MK.pdf")
    ]  # fmt: skip
    [text] = document.texts
    assert (text.of_file, text.method, text.paged) == (document.files[0].sha256, "ocr", True)
    assert split_pages(bundle.blob_path(text.sha256).read_text()) == [(1, "UNDANG-UNDANG"), (2, "Pasal 1")]
    [citation] = document.citations
    assert (citation.relation, citation.target_id, citation.target_text) == (
        Relation.AMENDS,
        "id:uu:2014:40",
        "UU No. 40 Tahun 2014",
    )


def test_a_record_without_an_id_or_with_a_conflicting_one_is_unresolved(tmp_path: Path) -> None:
    blobs = FileBlobStore(tmp_path / "raw")
    nameless = bundle_document(blobs, canonical_id=None)
    clash = bundle_document(blobs, regulation=Regulation("999", "UU 4/2023", "UU", "4", "2023"), id_conflict=True)

    entries = list(write(tmp_path, blobs, nameless, clash).entries())

    assert all(entry.is_valid for entry in entries), [entry.problems for entry in entries]
    assert [e.document.document.id_confidence for e in entries] == [Confidence.NONE, Confidence.CONFLICT]
    assert all(e.document.document.id.startswith("unresolved:bpk:") for e in entries)


def test_bpk_s_own_record_travels_as_source_fields(tmp_path: Path) -> None:
    blobs = FileBlobStore(tmp_path / "raw")

    fields = next(write(tmp_path, blobs, bundle_document(blobs)).entries()).document.source_fields

    assert fields["record_id"] == "240203"
    assert fields["fields"] == P2SK.fields
