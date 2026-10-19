"""ExportCorpus: one self-contained folder per target, readable offline, only exportable content."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from fakes.memory import FixedClock, MemoryCatalog, MemoryRepository

from bpk_connector.adapters.storage.blobs import FileBlobStore
from bpk_connector.adapters.storage.corpus import CorpusWriter
from bpk_connector.application.dto import StoredFile, StoredText
from bpk_connector.application.use_cases.export_corpus import ExportCorpus
from bpk_connector.domain.models import FileRef, Regulation, Relation, Target, TargetOrigin, Tier

LAW = FileRef("295189", "UU Nomor 4 Tahun 2023.pdf", "/Download/295189/UU.pdf")
P2SK = Regulation(
    "240203", "UU 4/2023 tentang P2SK", "UU", "4", "2023", status="Berlaku",
    relations=(Relation("Diubah dengan", "350166", "UU No. 4 Tahun 2026"),), files=(LAW,),
    fields={"Judul": "UU 4/2023 tentang P2SK", "Status": "Berlaku"},
)  # fmt: skip


def export(tmp_path: Path, repository: MemoryRepository, blobs: FileBlobStore, seeds: list[Target]):
    writer = CorpusWriter(tmp_path / "corpus", blobs)
    return ExportCorpus(repository, MemoryCatalog(seeds), writer, FixedClock()).run()


def test_each_target_gets_metadata_and_its_files(tmp_path: Path) -> None:
    repository, blobs = MemoryRepository(), FileBlobStore(tmp_path / "raw")
    repository.observations["240203"] = P2SK
    sha = blobs.put(b"%PDF law")
    repository.stored_files[("240203", LAW.path)] = StoredFile(sha, '"v1"', 8, "application/pdf", "https://bpk/x")

    summary = export(tmp_path, repository, blobs, [Target("240203", Tier.P1, TargetOrigin.SEED, "A", note="omnibus")])

    folder = tmp_path / "corpus" / "documents" / "bpk" / "240203"
    metadata = json.loads((folder / "metadata.json").read_text())
    assert metadata["source"] == {
        "name": "bpk",
        "record_id": "240203",
        "url": "https://peraturan.bpk.go.id/Details/240203",
    }
    assert metadata["fields"] == P2SK.fields  # BPK's own fields, unchanged
    assert metadata["target"] == {"tier": "P1", "domain": "A", "origin": "seed", "via": None, "note": "omnibus"}
    assert metadata["relations"][0]["record_id"] == "350166"
    assert (
        metadata["files"][0] | {"sha256": sha, "path": "files/Peraturan-295189.pdf", "rights": "public"}
        == metadata["files"][0]
    )
    assert (folder / "files" / "Peraturan-295189.pdf").read_bytes() == b"%PDF law"
    assert summary.documents == 1 and summary.files == 1


def test_the_index_has_one_line_per_target(tmp_path: Path) -> None:
    repository = MemoryRepository()
    repository.observations["240203"] = P2SK

    export(tmp_path, repository, FileBlobStore(tmp_path / "raw"), [Target("240203", Tier.P1, TargetOrigin.SEED)])

    lines = (tmp_path / "corpus" / "regulations.jsonl").read_text().splitlines()
    assert [json.loads(line)["citation"] for line in lines] == ["UU 4/2023"]


def test_targets_never_observed_are_listed_as_missing_not_exported(tmp_path: Path) -> None:
    summary = export(
        tmp_path, MemoryRepository(), FileBlobStore(tmp_path / "raw"), [Target("1", Tier.P1, TargetOrigin.SEED)]
    )

    assert summary.documents == 0 and summary.missing == ["1"]


def test_a_file_not_downloaded_yet_is_listed_without_a_local_copy(tmp_path: Path) -> None:
    repository = MemoryRepository()
    repository.observations["240203"] = P2SK

    export(tmp_path, repository, FileBlobStore(tmp_path / "raw"), [Target("240203", Tier.P1, TargetOrigin.SEED)])

    metadata = json.loads((tmp_path / "corpus/documents/bpk/240203/metadata.json").read_text())
    assert metadata["files"][0]["path"] is None and metadata["files"][0]["file_id"] == "295189"


def test_a_file_keeps_its_own_extension_in_the_corpus(tmp_path: Path) -> None:
    # Live: the Perpres 10/2021 annex (the investment list itself) is a .zip, not a PDF.
    annex = FileRef("1", "Perpres Nomor 10 Tahun 2021 - Lampiran.zip", "/Download/1/Lampiran.zip")
    repository, blobs = MemoryRepository(), FileBlobStore(tmp_path / "raw")
    repository.observations["161806"] = Regulation("161806", "Perpres 10/2021", "Perpres", "10", "2021", files=(annex,))
    sha = blobs.put(b"PK\x03\x04")
    repository.stored_files[("161806", annex.path)] = StoredFile(sha, None, 4, "application/octet-stream", "u")

    export(tmp_path, repository, blobs, [Target("161806", Tier.P1, TargetOrigin.SEED)])

    assert (tmp_path / "corpus/documents/bpk/161806/files/Peraturan-1.zip").read_bytes() == b"PK\x03\x04"


def test_extracted_text_is_exported_beside_its_file_and_as_the_documents_main_text(tmp_path: Path) -> None:
    repository, blobs = MemoryRepository(), FileBlobStore(tmp_path / "raw")
    repository.observations["240203"] = P2SK
    sha = blobs.put(b"%PDF law")
    repository.stored_files[("240203", LAW.path)] = StoredFile(sha, '"v1"', 8, "application/pdf", "u")
    text_sha = blobs.put(b"<!-- page 1 -->\nUNDANG-UNDANG NOMOR 4 TAHUN 2023")
    repository.texts[sha] = StoredText(sha, text_sha, "text_layer", pages=1, chars=40)

    export(tmp_path, repository, blobs, [Target("240203", Tier.P1, TargetOrigin.SEED)])

    folder = tmp_path / "corpus/documents/bpk/240203"
    assert (folder / "text.id.md").read_text().endswith("UNDANG-UNDANG NOMOR 4 TAHUN 2023")
    assert (folder / "texts/Peraturan-295189.id.md").exists()
    entry = json.loads((folder / "metadata.json").read_text())["files"][0]["text"]
    assert entry == {"path": "texts/Peraturan-295189.id.md", "method": "text_layer", "pages": 1,
                     "coverage": 1.0, "origin": "self_extracted", "rights": "public", "language": "id"}  # fmt: skip


def test_the_main_text_is_the_regulation_s_even_when_bpk_lists_an_annex_first(tmp_path: Path) -> None:
    annex = FileRef("165983", "Lampiran-Peraturan-PPATK-Nomor-11-Tahun-2020.pdf", "/Download/165983/Lampiran.pdf")
    repository, blobs = MemoryRepository(), FileBlobStore(tmp_path / "raw")
    repository.observations["240203"] = replace(P2SK, files=(annex, LAW))
    for ref, body in ((annex, b"LAMPIRAN I"), (LAW, b"UNDANG-UNDANG NOMOR 4 TAHUN 2023")):
        sha = blobs.put(b"%PDF " + body)
        repository.stored_files[("240203", ref.path)] = StoredFile(sha, None, 8, "application/pdf", "u")
        repository.texts[sha] = StoredText(sha, blobs.put(b"<!-- page 1 -->\n" + body), "text_layer", pages=1)

    export(tmp_path, repository, blobs, [Target("240203", Tier.P1, TargetOrigin.SEED)])

    folder = tmp_path / "corpus/documents/bpk/240203"
    assert (folder / "text.id.md").read_text().endswith("UNDANG-UNDANG NOMOR 4 TAHUN 2023")
    files = json.loads((folder / "metadata.json").read_text())["files"]
    assert [(f["file_id"], f["role"]) for f in files] == [("165983", "annex"), ("295189", "main")]
